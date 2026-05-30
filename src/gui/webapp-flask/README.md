# Introduction

This module is the **TRACEMINATOR** single-page web frontend for the modem
diagnostic toolchain. It serves a static HTML/JS UI and a thin same-origin JSON
proxy in front of the three backend APIs that do the real work:

- `serial-at-api`        on `http://localhost:8666` - modem info + AT commands
- `serial-modemtracing`  on `http://localhost:8888` - QCSuper modem trace
- `serial-simtracing`    on `http://localhost:8777` - SIMtrace2 SIM trace

The browser only ever talks to this Flask (`/api/...`), so CORS and split
origins never come up. The webapp does **not** drive USB, serial or SIMtrace2
hardware directly - it is a UI/orchestrator only.

Application is running on `http://localhost:9000`. The idea is not to expose
this to the world, as the RasPi should run locally; binding is on `0.0.0.0`
only so the page can be opened from another machine on the same LAN.

# Application Setup

## System dependencies

Installed and configured via the `../../../install.sh` script. In short:

- The three backend APIs (`serial-at-api`, `serial-modemtracing`,
  `serial-simtracing`) must be installed and running. The webapp degrades
  gracefully (gray status dots, "could not reach ..." JSON errors) when
  they are not, but most features are dependent on them.
- Trace files are read from `/opt/serial-simtracing/traces` and
  `/opt/serial-modemtracing/traces`; these directories are created by the
  respective backend services.

## Python environment

- the webapp itself does not need root, but is installed as root so
  systemd can manage it alongside the backend services
- all commands below should be executed as root

```
python3 -m venv .venv
source .venv/bin/activate

pip3 install -r ./requirements.txt
```

`requirements.txt` is intentionally tiny:

- `Flask`     - HTTP server + Jinja2 templating
- `requests`  - server-side proxy to the backend APIs

## Run

```
python3 main.py
```

The app binds `0.0.0.0:9000`. Templates are auto-reloaded
(`TEMPLATES_AUTO_RELOAD = True`), so editing `templates/index.html` does
not require a restart - just refresh the browser.

## Run as a systemd service

`service/webinterface.service` is the unit file installed by `install.sh`
to `/etc/systemd/system/webinterface.service`. It runs `main.py` from
`/opt/webapp-flask/` under the venv's `python3` and restarts on failure:

```
sudo systemctl enable --now webinterface
sudo systemctl status webinterface
sudo journalctl -u webinterface -f
```

# UI tour

The page title is **TRACEMINATOR**. Orange styling (`#c2410c`) is used for
section headings, buttons, the top header, and the footer. The header shows
the Pi hostname and CPU architecture on the left and a "Powered by" link on
the right. The footer lists contact details (address aligned right) with an
orange delimiter line above it.

The page is divided into four `<h1>` sections:

| Section                       | What it does                                                                                |
|-------------------------------|---------------------------------------------------------------------------------------------|
| **Modem Information**         | Table of detected modem interfaces (red row when not detected). |
| **Trace and Logs Management** | QCSuper, QLog, and SIMtracer2 status dots, Start/Stop buttons, **Restart Service** buttons, Log Files browser (download + delete). |
| **Modem Commands**            | Single AT command sender and **Modem Batch Instructions** script runner with live streamed results. |

The status dots poll the corresponding `*-active` endpoint every 5s and turn
red/green/gray. Per-service status lines under the Control panel show the
latest Start/Stop request and HTTP response.

# API endpoints (server side)

All paths below are mounted on `:9000`. Endpoints under `/api/` either
proxy a backend API or implement webapp-local features (file listing,
batch runner). All return JSON unless noted otherwise.

## UI

| Method | Path | Purpose                              |
|--------|------|--------------------------------------|
| GET    | `/`  | Serve `templates/index.html` (HTML). |

## Backend API proxies

These exist purely so the browser stays same-origin. They forward the
request body / status / payload verbatim, with a 502 wrapper if the
upstream is unreachable.

| Method      | Path                     | Upstream call                                |
|-------------|--------------------------|----------------------------------------------|
| GET         | `/api/modem`             | `GET  http://localhost:8666/modem`           |
| POST        | `/api/at`                | `POST http://localhost:8666/at`              |
| GET         | `/api/qcsuper-active`    | `GET  http://localhost:8888/trace-active`    |
| GET / POST  | `/api/qcsuper-start`     | `GET  http://localhost:8888/trace-start`     |
| GET / POST  | `/api/qcsuper-stop`      | `GET  http://localhost:8888/trace-stop`      |
| GET         | `/api/qlog-active`       | `GET  http://localhost:8888/qlog-active`       |
| GET / POST  | `/api/qlog-start`        | `GET  http://localhost:8888/qlog-start`        |
| GET / POST  | `/api/qlog-stop`         | `GET  http://localhost:8888/qlog-stop`         |
| GET         | `/api/simtracer-active`  | `GET  http://localhost:8777/trace-active`    |
| GET / POST  | `/api/simtracer-start`   | `GET  http://localhost:8777/trace-start`     |
| GET / POST  | `/api/simtracer-stop`    | `GET  http://localhost:8777/trace-stop`      |

## Service restart

| Method | Path                   | Purpose                                                                 |
|--------|------------------------|-------------------------------------------------------------------------|
| POST   | `/api/restart-service` | Restart a backend systemd unit and poll until its TCP port is listening |

Request body: `{"service": "<key>"}` where `<key>` is one of:

| Key           | systemd unit           | Port |
|---------------|------------------------|------|
| `serialmodem` | `serialmodeminterface` | 8666 |
| `qcsuper`     | `serialmodemtrace`     | 8888 |
| `simtracer`   | `serialsimtrace`       | 8777 |

Response includes `ok`, `restart_ok`, `restart_output`, `port_listening`, and
`elapsed_s`. The webapp must be able to run `systemctl restart` (installed
as root under systemd).

## Trace files

| Method | Path                                          | Purpose                                                        |
|--------|-----------------------------------------------|----------------------------------------------------------------|
| GET    | `/api/trace-files`                            | List regular files under `TRACE_DIRS`.                         |
| GET    | `/api/trace-files/<source>/<filename>`        | Download one file. `source` is `simtracer` or `modemtracer`.   |
| DELETE | `/api/trace-files/<source>/<filename>`        | Delete one file from disk (path validated like GET).           |

`TRACE_DIRS` is hard-coded in `main.py`:

```
TRACE_DIRS = {
    "simtracer":   Path("/opt/serial-simtracing/traces"),
    "modemtracer": Path("/opt/serial-modemtracing/traces"),
}
```

`send_from_directory` is used for download, so user-supplied filenames
cannot escape these directories.

## Batch script runner

| Method | Path                | Purpose                                                                                  |
|--------|---------------------|------------------------------------------------------------------------------------------|
| POST   | `/api/batch/run`    | Stream batch-script execution as NDJSON (one event per command attempt + step summary).  |
| POST   | `/api/batch/abort`  | Mark the running batch for abort. Idempotent.                                            |

Only one batch runs at a time; a second concurrent `/api/batch/run`
returns HTTP 409.

### Script syntax

One statement per line. Blank lines and lines starting with `#` are
ignored. Literal `:` inside `cmd` or `regex` is escaped as `\:`.

```
<index>:<type>:<cmd>:<expected_regex>:<reattempts>:<if_success>:<if_failed>
```

| Field            | Mandatory | Description                                                                              |
|------------------|-----------|------------------------------------------------------------------------------------------|
| `index`          | yes       | int. Like BASIC line numbers (`10`, `20`, ...). Used as `goto` target. Must be unique.   |
| `type`           | yes       | `at` (modem command via `/api/at`) or `sh` (shell command via `subprocess.run`).         |
| `cmd`            | yes       | The command itself.                                                                      |
| `expected_regex` | no        | If set, success = `re.search(regex, output)`. If empty, success = HTTP 200 / exit 0.     |
| `reattempts`     | no        | Extra retries on failure (default 0). Total tries = `1 + reattempts`.                    |
| `if_success`     | no        | Flow action on success. `""`/`next` (default), `goto N`, `sleep N`, `stop`.              |
| `if_failed`      | no        | Same vocabulary as `if_success`; runs when all retries are exhausted without matching.   |

### Streamed event protocol (NDJSON)

Each line of the response body is one JSON document:

| `kind`      | When                                                                                  |
|-------------|---------------------------------------------------------------------------------------|
| `attempt`   | After every command execution (so retries each get an event).                         |
| `error`     | Executor bailed out (`max steps` exceeded, `goto` target missing).                    |
| `aborted`   | The user POSTed `/api/batch/abort` and the executor honoured it.                      |
| `meta`      | Final line after all steps; includes `tsv_file` and `tsv_name` for the run log.       |

Final attempts of a step (success, or last retry) additionally carry
`success`, `action`, `sleep_seconds`, `next_index`. The frontend uses the
presence of `action` to mark the step's last row.

### Batch TSV log

Every `/api/batch/run` writes a UTF-8 TSV alongside modem trace files:

```
/opt/serial-modemtracing/traces/<TZ>-<YYYYMMDD>-<HHMMSS>-atserial.tsv
```

Columns: `Step`, `Line`, `Timestamp`, `Type`, `Command`, `Attempt`, `Result`,
`Action`, `ms`, `Output`. The file appears in the **Log Files** tab under
source `modemtracer` and can be downloaded or deleted like any other trace file.

### Examples

```
# run a script that does a quick modem health check
read -r -d '' SCRIPT <<'EOF'
10:at:ATI:OK:2::
20:at:AT+CSQ:OK::sleep 1:
30:sh:date::::
40:at:AT+COPS?:,"[^"]+":3:goto 50:goto 30
50:at:AT&F::::stop
EOF

curl -N -s -X POST http://localhost:9000/api/batch/run \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg s "$SCRIPT" '{script:$s}')"

# from another shell, stop a running batch
curl -s -X POST http://localhost:9000/api/batch/abort | jq

# restart a backend service from the banner buttons
curl -s -X POST http://localhost:9000/api/restart-service \
  -H 'Content-Type: application/json' \
  -d '{"service":"serialmodem"}' | jq

# QLog (proxied to serial-modemtracing)
curl -s http://localhost:9000/api/qlog-active | jq
curl -s -X POST http://localhost:9000/api/qlog-start | jq

# list / delete trace files
curl -s http://localhost:9000/api/trace-files | jq
curl -s -X DELETE http://localhost:9000/api/trace-files/modemtracer/old.pcap | jq
```

`-N` (`--no-buffer`) is important - without it `curl` will buffer the
NDJSON stream and you won't see live progress.

# Typical workflow

```
# 1. ensure all three backend APIs are up
sudo systemctl status serialmodeminterface
sudo systemctl status serialmodemtrace
sudo systemctl status serialsimtrace

# 2. start (or restart) the webapp
sudo systemctl restart webinterface

# 3. open the UI
xdg-open http://localhost:9000     # or: http://<rpi>:9000 from your laptop

# 4. drive the modem from the page:
#    - read modem info; use Restart Service if interfaces go stale
#    - send AT commands one by one, or paste a script and click Run
#    - start QCSuper / QLog / SIMtracer2 traces, exercise, stop
#    - download or delete files from the "Log Files" tab
```

# Troubleshooting

- **All status dots stay gray** - one or more backend APIs are not running.
  Check `systemctl status serialmodeminterface serialmodemtrace
  serialsimtrace webinterface` and `journalctl -u <service> -f`.
- **Restart Service fails** - the webapp could not run `systemctl restart`
  or the port did not come back within ~15s. Read `#restart-status` in the UI
  or inspect the JSON from `/api/restart-service`.
- **Modem Info shows red rows** - `serial-at-api` could not detect the
  expected interfaces (modem unplugged, missing `modem.json` mapping, or
  `udev` rule not yet applied).
- **`/api/batch/run` returns 409** - another batch is already running.
  POST `/api/batch/abort` first, or wait for it to finish.
- **Live batch updates don't stream, table fills only at the end** - some
  reverse proxy is buffering. The endpoint already sets
  `X-Accel-Buffering: no`; if you've put nginx in front, also set
  `proxy_buffering off`.
- **"Log Files" tab is empty** - `/opt/serial-simtracing/traces` and
  `/opt/serial-modemtracing/traces` don't exist yet (no captures have run)
  or the webapp doesn't have read permission. The webapp runs as root
  under systemd, so permissions usually aren't the problem.
- **Template changes don't show up** - hard-refresh the browser
  (`Ctrl+Shift+R`). Flask reloads templates on disk automatically, but the
  open tab keeps the JS it loaded originally.
