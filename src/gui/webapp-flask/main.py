import json
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import requests
from flask import Flask, render_template, jsonify, request, send_from_directory, abort, Response, stream_with_context

# upstream serial-at-api - changeable via env if needed
AT_API_BASE         = "http://localhost:8666"
MODEMTRACE_API_BASE = "http://localhost:8888"   # qcsuper trace API
SIMTRACER_API_BASE  = "http://localhost:8777"   # simtrace2 trace API

# Services exposed by the "Restart Service" buttons in the page banner.
# Each entry is { systemd unit -> TCP port we expect to be listening once
# the unit is back up }. The endpoint runs `systemctl restart <unit>` then
# polls 127.0.0.1:<port> until it accepts a connection (or we time out).
# Keys here are the values the frontend POSTs; ports must match the upstream
# bases above so the restart actually validates the same service the rest of
# the UI talks to.
RESTART_SERVICES = {
    "serialmodem": {"unit": "serialmodeminterface", "port": 8666, "label": "Serial Modem"},
    "qcsuper":     {"unit": "serialmodemtrace",     "port": 8888, "label": "QCSuper Service"},
    "simtracer":   {"unit": "serialsimtrace",       "port": 8777, "label": "Simtracer Service"},
}

# How long to wait, total, for the TCP port to come back after the
# `systemctl restart` returns. Restart itself is bounded separately by
# RESTART_SYSTEMCTL_TIMEOUT below. Tuned generously: serial services can
# take a few seconds to re-open their listening socket.
PORT_WAIT_SECONDS        = 15
PORT_POLL_INTERVAL       = 0.3
RESTART_SYSTEMCTL_TIMEOUT = 30

# trace files written by the two background services. Keys appear in the URL
# (/api/trace-files/<source>/<filename>) and as the "Source" column in the UI.
TRACE_DIRS = {
    "simtracer":   Path("/opt/serial-simtracing/traces"),
    "modemtracer": Path("/opt/serial-modemtracing/traces"),
}

app = Flask(__name__)
# pick up template edits without restarting the server
app.config["TEMPLATES_AUTO_RELOAD"] = True

# serve the single page
@app.route("/")
def index():
    return render_template("index.html")

# server-side proxy to the AT API so the browser stays same-origin (no CORS)
@app.route("/api/modem", methods=["GET"])
def modem():
    try:
        r = requests.get(f"{AT_API_BASE}/modem", timeout=5)
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {AT_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy a single AT command -> upstream POST /at
@app.route("/api/at", methods=["POST"])
def at_command():
    payload = request.get_json(silent=True) or {}
    print(payload)
    try:
        r = requests.post(f"{AT_API_BASE}/at", json=payload, timeout=15)
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {AT_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy qcsuper trace status (used by the status indicator)
@app.route("/api/qcsuper-active", methods=["GET"])
def qcsuper_active():
    try:
        r = requests.get(f"{MODEMTRACE_API_BASE}/trace-active")
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {MODEMTRACE_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy qcsuper trace start
@app.route("/api/qcsuper-start", methods=["POST", "GET"])
def qcsuper_start():
    try:
        r = requests.get(f"{MODEMTRACE_API_BASE}/trace-start")
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {MODEMTRACE_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy qcsuper trace stop
@app.route("/api/qcsuper-stop", methods=["POST", "GET"])
def qcsuper_stop():
    try:
        r = requests.get(f"{MODEMTRACE_API_BASE}/trace-stop")
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {MODEMTRACE_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy simtracer trace status (used by the status indicator)
@app.route("/api/simtracer-active", methods=["GET"])
def simtracer_active():
    try:
        r = requests.get(f"{SIMTRACER_API_BASE}/trace-active")
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {SIMTRACER_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy simtracer trace start
@app.route("/api/simtracer-start", methods=["POST", "GET"])
def simtracer_start():
    try:
        r = requests.get(f"{SIMTRACER_API_BASE}/trace-start")
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {SIMTRACER_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})

# proxy simtracer trace stop
@app.route("/api/simtracer-stop", methods=["POST", "GET"])
def simtracer_stop():
    try:
        r = requests.get(f"{SIMTRACER_API_BASE}/trace-stop")
    except requests.RequestException as e:
        return jsonify(error=f"could not reach {SIMTRACER_API_BASE}: {e}"), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})


def _wait_for_port(host, port, deadline):
    """Poll a TCP port until it accepts a connection or `deadline` passes.
    Returns (listening: bool, last_error: str|None). Short per-attempt
    timeouts so we react quickly to the service coming up; the outer
    deadline bounds total wall time."""
    last_err = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True, None
        except OSError as e:
            last_err = str(e)
            # Sleep, but never past the deadline (avoids a final useless wait).
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(PORT_POLL_INTERVAL, remaining))
    return False, last_err


# Restart a systemd unit (serialmodeminterface / serialmodemtrace /
# serialsimtrace) and verify its TCP port is listening afterwards. Wired
# to the three buttons in the page banner. Note: the Flask process must
# have permission to run `systemctl restart <unit>` non-interactively
# (typically via a polkit rule or running as root); a sudo-less failure
# surfaces as restart_ok=false with the systemctl stderr in
# restart_output, so the UI can show the operator why it failed.
@app.route("/api/restart-service", methods=["POST"])
def restart_service():
    payload = request.get_json(silent=True) or {}
    name = payload.get("service")
    cfg = RESTART_SERVICES.get(name)
    if cfg is None:
        return jsonify(error=f"unknown service: {name!r}",
                       known=sorted(RESTART_SERVICES.keys())), 400

    cmd = ["systemctl", "restart", cfg["unit"]]
    started_at = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=RESTART_SYSTEMCTL_TIMEOUT)
        restart_ok      = r.returncode == 0
        restart_output  = ((r.stdout or "") + (r.stderr or "")).strip()
        restart_rc      = r.returncode
    except subprocess.TimeoutExpired:
        restart_ok      = False
        restart_output  = f"systemctl restart {cfg['unit']} timed out after {RESTART_SYSTEMCTL_TIMEOUT}s"
        restart_rc      = None
    except FileNotFoundError as e:
        # systemctl missing entirely (e.g. running on a non-systemd dev box)
        return jsonify(ok=False, error=f"systemctl not available: {e}"), 500

    # Even if `systemctl restart` reported failure, still poll the port
    # briefly: the unit may already have been up, or the restart may have
    # succeeded despite a non-zero rc (rare but observed with units that
    # exit cleanly during their stop phase). We just narrow the window.
    deadline = time.monotonic() + (PORT_WAIT_SECONDS if restart_ok else 3)
    port_listening, port_error = _wait_for_port("127.0.0.1", cfg["port"], deadline)

    overall_ok = restart_ok and port_listening
    body = {
        "ok":              overall_ok,
        "service":         name,
        "label":           cfg["label"],
        "unit":            cfg["unit"],
        "port":            cfg["port"],
        "restart_ok":      restart_ok,
        "restart_rc":      restart_rc,
        "restart_output":  restart_output,
        "port_listening":  port_listening,
        "port_error":      None if port_listening else port_error,
        "elapsed_s":       round(time.time() - started_at, 2),
    }
    return jsonify(body), (200 if overall_ok else 500)

# list every regular file in either trace directory.
# returns [{source, name, size, mtime, url}, ...] sorted by source then name.
@app.route("/api/trace-files", methods=["GET"])
def list_trace_files():
    out = []
    for source, base in TRACE_DIRS.items():
        if not base.exists():
            continue
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name)
        except PermissionError as e:
            return jsonify(error=f"cannot read {base}: {e}"), 500
        for f in entries:
            if not f.is_file():
                continue
            stat = f.stat()
            out.append({
                "source": source,
                "name":   f.name,
                "size":   stat.st_size,
                "mtime":  int(stat.st_mtime),
                "url":    f"/api/trace-files/{source}/{f.name}",
            })
    return jsonify(out)

# stream a single file as a download. send_from_directory does its own
# safety check - it normalises and rejects any path that escapes `base`,
# so user-supplied `filename` cannot reach files outside TRACE_DIRS.
@app.route("/api/trace-files/<source>/<path:filename>", methods=["GET"])
def get_trace_file(source, filename):
    base = TRACE_DIRS.get(source)
    if base is None:
        abort(404)
    return send_from_directory(str(base), filename, as_attachment=True)

# ============================================================
# Script runner ("Modem Batch Instructions" tab)
#
# Script syntax (one statement per line; blank lines and lines starting with
# "#" are ignored):
#
#     <index>:<type>:<cmd>:<expected_regex>:<reattempts>:<if_success>:<if_failed>
#
# Fields, in order:
#   index           int, mandatory. Like BASIC line numbers (10, 20, ...).
#                   Used as goto target. Duplicates are rejected.
#   type            "at" | "sh" (mandatory).
#                       at = AT command via the upstream serial-at-api proxy.
#                       sh = shell command via subprocess (DANGER: arbitrary
#                            shell exec; this UI is intended for localhost
#                            diagnostic use only).
#   cmd             the command itself (mandatory).
#   expected_regex  if non-empty, the line is "successful" iff this regex
#                   matches the command output (Python re.search).
#                   if empty, success is decided by exec status:
#                       at -> HTTP 200 from /at
#                       sh -> exit code 0
#   reattempts      additional attempts on failure (default 0). Total tries
#                   = 1 + reattempts.
#   if_success      flow action when the line ultimately succeeds. One of:
#                       ""           -> next (default)
#                       "next"
#                       "goto <N>"   -> jump to index N
#                       "sleep <N>"  -> sleep N seconds, then next
#                       "stop"       -> end the script
#   if_failed       same vocabulary as if_success.
#
# Literal ":" inside cmd or regex must be escaped as "\:".
# ============================================================

# Caps to keep a runaway script from hanging Flask indefinitely. Tuned for
# diagnostic use on a single-board computer; raise if real scripts need more.
MAX_AT_TIMEOUT       = 30      # one HTTP call to /at
MAX_SH_TIMEOUT       = 60      # one shell command
MAX_SCRIPT_STEPS     = 500     # total executed steps (defends against goto loops)
INTER_ATTEMPT_DELAY  = 0.2     # seconds between retries on the same line

# Sentinel used to escape literal ":" inside fields (\: in source). We turn
# every \: into this sentinel before splitting on ":", then turn each piece
# back. Picked a NUL-padded run so it cannot collide with anything user-typed.
_COLON_SENTINEL = "\x00COL\x00"

# ------------------------------------------------------------
# Batch-run lifecycle state
# ------------------------------------------------------------
# Singleton: only one batch script runs at a time on this Flask. The lock
# guards the dict; callers always go through the helpers below so the rules
# stay tidy. `running` is set when a batch starts and cleared when it
# finishes (success, abort, exception); `stop` is set by /api/batch/abort
# and polled by run_script() to bail out promptly.
_batch_lock  = threading.Lock()
_batch_state = {"running": False, "stop": False}


def _begin_batch():
    """Try to claim the batch slot. Returns True iff this caller is now the
    sole active batch run. Returns False if another batch is already running
    -- the caller should respond with HTTP 409 in that case."""
    with _batch_lock:
        if _batch_state["running"]:
            return False
        _batch_state["running"] = True
        _batch_state["stop"]    = False
        return True


def _end_batch():
    """Always pair with a successful _begin_batch(); safe to call twice
    (idempotent). Run from the stream() generator's `finally` so it fires
    on success, on abort, AND on client disconnect."""
    with _batch_lock:
        _batch_state["running"] = False
        _batch_state["stop"]    = False


def _request_stop():
    """Mark the active batch for abort. Returns True iff there was a run to
    stop (so the endpoint can report idempotently)."""
    with _batch_lock:
        if not _batch_state["running"]:
            return False
        _batch_state["stop"] = True
        return True


def _should_stop():
    # Read without the lock: a torn read is fine here -- worst case we
    # do one extra step before noticing the flag.
    return _batch_state["stop"]


def _interruptible_sleep(seconds):
    """Sleep that polls the abort flag every 100 ms. Long inter-attempt or
    post-step sleeps still abort within ~100 ms instead of holding up the
    whole script. ``seconds <= 0`` is a no-op."""
    if seconds <= 0:
        return
    end = time.monotonic() + seconds
    while True:
        if _should_stop():
            return
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


class ScriptParseError(Exception):
    """Raised by parse_script / parse_action on bad syntax."""


def parse_action(text):
    """Translate one if_success/if_failed cell into a (verb, [arg]) tuple.

    Returns one of:
        ("next",)
        ("stop",)
        ("goto",  N)
        ("sleep", N)
    """
    t = (text or "").strip().lower()
    if t in ("", "next"):
        return ("next",)
    if t in ("stop", "end", "halt"):
        return ("stop",)
    parts = t.split(maxsplit=1)
    if len(parts) == 2 and parts[0] in ("goto", "sleep"):
        try:
            n = int(parts[1])
        except ValueError:
            raise ScriptParseError(f"action {text!r}: arg must be integer")
        if parts[0] == "sleep" and n < 0:
            raise ScriptParseError(f"sleep cannot be negative: {text!r}")
        return (parts[0], n)
    raise ScriptParseError(f"unknown action: {text!r}")


def parse_script(text):
    """Parse a multi-line script into a list of dicts (one per executable line).

    Each returned dict has:
        index, type, cmd, regex (or None), reattempts, if_success, if_failed
    Raises ScriptParseError on bad syntax or duplicate indices.
    """
    out = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        # Escape "\:" so a literal colon in cmd/regex doesn't split as a field.
        escaped = s.replace(r"\:", _COLON_SENTINEL)
        parts = escaped.split(":", 6)            # max 7 parts
        # Restore escaped colons in every part.
        parts = [p.replace(_COLON_SENTINEL, ":") for p in parts]
        if len(parts) < 3:
            raise ScriptParseError(
                f"line {lineno}: need at least index:type:cmd, got {raw!r}"
            )
        # pad to 7 fields so we can unpack uniformly
        while len(parts) < 7:
            parts.append("")
        idx_s, ctype, cmd, regex, retries_s, on_succ, on_fail = parts

        try:
            idx = int(idx_s.strip())
            #print(idx)
        except ValueError:
            raise ScriptParseError(
                f"line {lineno}: index must be integer, got {idx_s!r}"
            )

        ctype = ctype.strip().lower()
        #print(ctype)
        if ctype not in ("at", "sh"):
            raise ScriptParseError(
                f"line {lineno}: type must be 'at' or 'sh', got {ctype!r}"
            )

        retries = 0
        if retries_s.strip():
            try:
                retries = int(retries_s.strip())
            except ValueError:
                raise ScriptParseError(
                    f"line {lineno}: reattempts must be integer, got {retries_s!r}"
                )
        #print(retries)

        # Validate regex eagerly so errors surface during parse, not run.
        regex_clean = regex.strip() or None
        if regex_clean is not None:
            try:
                re.compile(regex_clean)
            except re.error as e:
                raise ScriptParseError(
                    f"line {lineno}: bad regex {regex_clean!r}: {e}"
                )
        #print(regex_clean)

        # Validate actions eagerly too.
        for fname, val in (("if_success", on_succ), ("if_failed", on_fail)):
            try:
                parse_action(val)
            except ScriptParseError as e:
                raise ScriptParseError(f"line {lineno}: {fname}: {e}")
        #print(on_succ)
        #print(on_fail)

        out.append({
            "index":      idx,
            "type":       ctype,
            "cmd":        cmd,
            "regex":      regex_clean,
            "reattempts": max(0, retries),
            "if_success": on_succ.strip() or "next",
            "if_failed":  on_fail.strip() or "next",
        })
    #print(out)
    seen = set()
    for ln in out:
        if ln["index"] in seen:
            raise ScriptParseError(f"duplicate index {ln['index']}")
        seen.add(ln["index"])
    return out


def execute_at(cmd):
    """Run one AT command via the upstream proxy. Returns (output, exec_ok, http).
    exec_ok=True iff the upstream returned HTTP 200; http is the HTTP status
    code (int) when one was received, or None on network error."""
    try:
        r = requests.post(f"{AT_API_BASE}/at",
                          json={"cmd": cmd}, timeout=MAX_AT_TIMEOUT)
        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                return (r.text, True, r.status_code)
            return (data.get("response", json.dumps(data)), True, r.status_code)
        return (f"HTTP {r.status_code}: {r.text}", False, r.status_code)
    except requests.RequestException as e:
        return (f"network error: {e}", False, None)


def execute_sh(cmd):
    """Run a shell command. Returns (combined_output, exec_ok, http).
    exec_ok=True iff exit code is 0. stdout+stderr are concatenated so a
    regex can match against either stream uniformly. http is always None
    (kept in the tuple for signature parity with execute_at)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=MAX_SH_TIMEOUT)
        out = (r.stdout or "") + (r.stderr or "")
        return (out, r.returncode == 0, None)
    except subprocess.TimeoutExpired:
        return (f"timeout after {MAX_SH_TIMEOUT}s", False, None)
    except Exception as e:
        return (f"shell error: {e}", False, None)


def run_script(lines):
    """Execute a parsed script as a GENERATOR. Yields one event per command
    *attempt* (so retries are visible) plus synthetic ``error`` events.

    Event shapes (NDJSON over the wire):
      - ``{"kind": "attempt", ...}`` -- emitted after every command execution,
        i.e. once per try. Carries this attempt's output / matched flag /
        timings. The *final* attempt of a step (success, or last retry) also
        carries the step-level fields ``success``, ``action``,
        ``sleep_seconds`` and ``next_index`` so the UI can render the action
        column on that row.
      - ``{"kind": "error", ...}`` -- runaway / bad goto, terminates the run.

    Same line index can appear multiple times across the stream if the flow
    loops via goto. ``list(run_script(lines))`` still works for callers that
    want the synchronous full-list flavour."""
    if not lines:
        return
    line_map = {ln["index"]: ln for ln in lines}
    sorted_indices = sorted(line_map.keys())

    def next_after(idx):
        # next sorted index strictly greater than idx, or None at the end.
        for i in sorted_indices:
            if i > idx:
                return i
        return None

    pc = sorted_indices[0]
    step_no = 0

    while pc is not None:
        # Honour an abort requested before this step starts.
        if _should_stop():
            yield {"kind": "aborted", "step": step_no,
                   "error": "aborted by user"}
            return
        step_no += 1
        if step_no > MAX_SCRIPT_STEPS:
            yield {"kind": "error", "step": step_no,
                   "error": f"max steps ({MAX_SCRIPT_STEPS}) exceeded"}
            return
        if pc not in line_map:
            yield {"kind": "error", "step": step_no,
                   "error": f"goto target {pc} not found"}
            return

        line = line_map[pc]
        max_attempts = 1 + line["reattempts"]
        # Defaults so the post-loop ``pc = next_idx`` is always defined,
        # even if max_attempts somehow ends up at 0 (it shouldn't: parser
        # guarantees reattempts >= 0, hence max_attempts >= 1).
        next_idx = next_after(pc)
        sleep_seconds = 0

        for attempt in range(1, max_attempts + 1):
            attempt_started_at = int(time.time() * 1000)
            if line["type"] == "at":
                output, exec_ok, http = execute_at(line["cmd"])
            else:
                output, exec_ok, http = execute_sh(line["cmd"])
            attempt_ended_at = int(time.time() * 1000)

            if line["regex"]:
                matched = bool(re.search(line["regex"], output))
            else:
                matched = exec_ok

            # An attempt is "final" for its step when it matches, or when
            # we've exhausted the retry budget. Only final attempts carry
            # the step-level action/next_index fields.
            is_final = matched or attempt == max_attempts

            event = {
                "kind":         "attempt",
                "step":         step_no,
                "attempt":      attempt,
                "max_attempts": max_attempts,
                "index":        line["index"],
                "type":         line["type"],
                "cmd":          line["cmd"],
                "regex":        line["regex"],
                "output":       output,
                "matched":      matched,
                "http_status":  http,           # int for at, None for sh
                "started_at":   attempt_started_at,  # epoch ms (server clock)
                "ended_at":     attempt_ended_at,    # epoch ms (server clock)
                "duration_ms":  attempt_ended_at - attempt_started_at,
            }

            if is_final:
                success = matched
                action_text = line["if_success"] if success else line["if_failed"]
                action = parse_action(action_text)  # validated at parse-time
                sleep_seconds = 0
                if action[0] == "next":
                    next_idx = next_after(pc)
                elif action[0] == "stop":
                    next_idx = None
                elif action[0] == "goto":
                    next_idx = action[1]
                elif action[0] == "sleep":
                    sleep_seconds = action[1]
                    next_idx = next_after(pc)
                else:
                    next_idx = None
                event.update({
                    "success":       success,
                    "action":        action_text or "next",
                    "sleep_seconds": sleep_seconds,
                    "next_index":    next_idx,
                })

            yield event

            if matched:
                break
            # Honour abort between retries (after this attempt's event was
            # streamed) so the user sees the failed attempt and the abort
            # marker right after.
            if _should_stop():
                yield {"kind": "aborted", "step": step_no,
                       "error": "aborted by user"}
                return
            # Don't sleep after the final attempt.
            if attempt < max_attempts:
                _interruptible_sleep(INTER_ATTEMPT_DELAY)

        # Post-step sleep is interruptible too -- otherwise a `sleep 30`
        # action would freeze abort for up to 30 seconds.
        if sleep_seconds > 0:
            _interruptible_sleep(sleep_seconds)

        pc = next_idx


@app.route("/api/batch/run", methods=["POST"])
def batch_run():
    """Stream batch-script execution as NDJSON: one JSON object per line,
    flushed as each step completes. The browser uses fetch + ReadableStream
    to render rows live (see runBatch in templates/index.html).

    Errors that happen *before* the first step is run (parse failure, empty
    script, another batch already running) come back as a regular JSON
    response with the appropriate HTTP status -- not as part of the stream
    -- so the frontend's `r.ok` check catches them cleanly without having
    to peek at the body."""
    payload = request.get_json(silent=True) or {}
    text = payload.get("script", "")
    try:
        lines = parse_script(text)
    except ScriptParseError as e:
        return jsonify(error=str(e)), 400
    if not lines:
        return jsonify(error="empty script (only blanks/comments)"), 400

    # Singleton: refuse a second concurrent run instead of racing two
    # generators against each other on the same modem.
    if not _begin_batch():
        return jsonify(error="another batch is already running"), 409

    def stream():
        # stream_with_context preserves Flask's request context across the
        # generator, so anything inside (logging, etc.) sees `request` etc.
        # The try/finally guarantees we release the singleton on success,
        # on user-requested abort, AND on client disconnect (Werkzeug
        # closes the generator -> GeneratorExit -> finally fires).
        try:
            for step in run_script(lines):
                # Trailing newline turns this into NDJSON: each line is
                # one complete JSON document, newline-delimited.
                yield json.dumps(step) + "\n"
        finally:
            _end_batch()

    headers = {
        # Disable proxy/browser buffering so chunks reach the client as
        # soon as they're flushed by Werkzeug. X-Accel-Buffering is the
        # nginx-specific opt-out; browsers ignore it but it's free
        # insurance for anyone deploying behind nginx later.
        "Cache-Control":     "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(stream()),
                    mimetype="application/x-ndjson",
                    headers=headers)


@app.route("/api/batch/abort", methods=["POST"])
def batch_abort():
    """Mark the running batch for abort. Idempotent -- always 200, with a
    flag indicating whether a run was actually live to interrupt. The
    executor polls the flag between attempts and inside its sleeps, so
    abort takes effect within ~100 ms of this call (longer only if a single
    AT/sh command is mid-execution; we let it finish and bail right after
    its event is yielded)."""
    return jsonify(requested=_request_stop()), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, debug=False)
