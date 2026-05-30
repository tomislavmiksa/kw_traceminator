import re
import requests
import time
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify

# absolute path to the trace directory (shared by QCSuper pcaps and QLog dumps)
QCSUPER_LOG = "/var/log/qcsuper-api.log"
QLOG_LOG    = "/var/log/qlog-api.log"
QLOG_BIN    = "/opt/QLog"
TRACE_DIR   = Path("/opt/serial-modemtracing/traces")
TRACE_DIR.mkdir(parents=True, exist_ok=True)

# helper function to generate a unique filename for the trace
def make_pcap_filename(suffix: str = "qcsuper", ext: str = "pcap") -> str:
    return str(TRACE_DIR / f"{time.strftime('%Z-%Y%m%d-%H%M%S')}-{suffix}.{ext}")

# DEPENDENCIES VERIFICATION
# - at least one of qcsuper (/opt/qcsuper) or QLog (/opt/QLog) must be present
_qcsuper_ok = subprocess.run(
   ["/opt/qcsuper/qcsuper.py", "--help"],
   capture_output=True, text=True,
).returncode == 0
_qlog_ok = subprocess.run(
   [QLOG_BIN, "--help"],
   capture_output=True, text=True,
).returncode == 0
if not _qcsuper_ok and not _qlog_ok:
   print("ERROR: neither qcsuper nor QLog is installed/configured")
   exit(1)

# get the diag port of the modem connected
# - if the modem is not connected, exit the program as running it makes no sense
# - we do not have then anything to trace
r = requests.get("http://localhost:8666/modem")
if r.status_code != 200:
   print("ERROR: no modem detected")
   exit(1)
else:
   data = r.json()
   if data is None:
      print("ERROR: no modem detected")
      exit(1)
   elif 'Diag' not in data.keys():
      print("ERROR: no diag port detected")
      exit(2)
   elif data["Diag"] is None:
      print("ERROR: no diag port detected")
      exit(3)
   else:
      port = data["Diag"]
   print(port)

app = Flask(__name__)

# the entry point to return the basic information about the API
# call: curl http://localhost:8888/
@app.route("/")
def root():
   return { "Version" : "1.0.0" , "Description": "API to get the modem trace, QCSuper or QXDM" }

@app.route("/modem-info", methods=['GET'])
def modemInfo():
   result = subprocess.run(
      ["/opt/qcsuper/qcsuper.py", "--usb-modem", port, "--info"],
      cwd="/opt/qcsuper",
      capture_output=True,
      text=True,
      timeout=30,
   )
   if result.returncode != 0:
      return {
         "Diag": port,
         "error": "qcsuper --info failed",
         "rc": result.returncode,
         "stderr": result.stderr.strip(),
      }, 500
   return { "Diag": port, "info": result.stdout.strip() }

# find PIDs of qcsuper.py processes writing a pcap (--pcap-dump)
def findQcsuperTraces():
   result = subprocess.run(
      ["pgrep", "-af", r"qcsuper\.py.*--pcap-dump"],
      capture_output=True, text=True,
   )
   matches: list[tuple[int, str]] = []
   for line in result.stdout.splitlines():
      pid_str, _, cmdline = line.partition(" ")
      if pid_str.isdigit():
         matches.append((int(pid_str), cmdline))
   return matches

# extract the file path passed via "--pcap-dump <file>" from a qcsuper command line
def extractPcapFile(cmdline: str) -> str | None:
   tokens = cmdline.split()
   try:
      return tokens[tokens.index("--pcap-dump") + 1]
   except (ValueError, IndexError):
      return None

# verify if there is an active qcsuper trace writing a pcap
@app.route("/trace-active", methods=['GET'])
def getTrace():
   matches = findQcsuperTraces()
   pids  = [pid for pid, _ in matches]
   files = [f for _, cmd in matches if (f := extractPcapFile(cmd))]
   return { "running": bool(matches), "pids": pids, "files": files }

# QCSuper and QLog both use the modem Diag port -- only one may run at a time.
# Starting either tool SIGTERMs the other first and waits briefly for the port
# to be released.

def _sigterm_processes(matches: list[tuple[int, str]]) -> list[dict]:
   if not matches:
      return []
   pids = [str(pid) for pid, _ in matches]
   subprocess.run(["kill", "-TERM", *pids], capture_output=True, text=True)
   return [{"pid": pid, "cmd": cmd} for pid, cmd in matches]


def stopQcsuperProcesses() -> list[dict]:
   return _sigterm_processes(findQcsuperTraces())


def stopQlogProcesses() -> list[dict]:
   return _sigterm_processes(findQlogProcesses())


def _wait_for_port_release(seconds: float = 1.0) -> None:
   time.sleep(seconds)


# stop all qcsuper trace processes
@app.route("/trace-stop", methods=['GET'])
def stopTrace():
   killed = stopQcsuperProcesses()
   if not killed:
      return { "info" : "no matching qcsuper process", "killed" : [] }
   return { "info" : f"stopped {len(killed)} qcsuper process(es)", "killed" : killed }

# start the trace capture process
@app.route("/trace-start", methods=['GET'])
def startTrace():
   stopped_qlog = stopQlogProcesses()
   if stopped_qlog:
      _wait_for_port_release()
   filename = make_pcap_filename()
   cmd = [
      "/opt/qcsuper/qcsuper.py",
      "--usb-modem", port,
      "--reassemble-sibs",
      "--decrypt-nas",
      "--include-ip-traffic",
      "--pcap-dump", filename,
   ]
   log_fh = open(QCSUPER_LOG, "ab", buffering=0)
   proc = subprocess.Popen(
      cmd,
      cwd="/opt/qcsuper",
      stdin=subprocess.DEVNULL,
      stdout=log_fh,
      stderr=subprocess.STDOUT,
      start_new_session=True,
      close_fds=True,
   )
   time.sleep(0.5)
   rc = proc.poll()
   if rc is not None:
      print(f"ERROR: qcsuper exited immediately with code {rc}")
      return {
         "error": "qcsuper exited immediately",
         "rc": rc,
         "log": QCSUPER_LOG
      }, 500
   out = {
      "info": "trace started",
      "pid": proc.pid,
      "file": filename,
      "log": QCSUPER_LOG,
      "diag": port,
   }
   if stopped_qlog:
      out["stopped_qlog"] = stopped_qlog
   return out

# list pcaps in the trace directory
@app.route("/trace-list", methods=['GET'])
def listTraces():
   files = sorted(p.name for p in TRACE_DIR.iterdir() if p.is_file())
   return {"info": "list of traces", "dir": str(TRACE_DIR), "traces": files}


# ---------- QLog (QXDM) trace control ----------
# Started as: /opt/QLog -s <TRACE_DIR> -p <diag port>
# Uses the same Diag serial port as QCSuper (from serial-at-api /modem).

def findQlogProcesses():
   result = subprocess.run(
      ["pgrep", "-af", r"QLog -s"],
      capture_output=True, text=True,
   )
   matches: list[tuple[int, str]] = []
   for line in result.stdout.splitlines():
      pid_str, _, cmdline = line.partition(" ")
      if pid_str.isdigit():
         matches.append((int(pid_str), cmdline))
   return matches


def extractQlogStorage(cmdline: str) -> str | None:
   tokens = cmdline.split()
   try:
      return tokens[tokens.index("-s") + 1]
   except (ValueError, IndexError):
      return None


@app.route("/qlog-active", methods=["GET"])
def qlogActive():
   matches = findQlogProcesses()
   pids  = [pid for pid, _ in matches]
   dirs  = [d for _, cmd in matches if (d := extractQlogStorage(cmd))]
   return {"running": bool(matches), "pids": pids, "storage": dirs, "port": port}


@app.route("/qlog-stop", methods=["GET"])
def qlogStop():
   killed = stopQlogProcesses()
   if not killed:
      return {"info": "no matching QLog process", "killed": []}
   return {"info": f"stopped {len(killed)} QLog process(es)", "killed": killed}


@app.route("/qlog-start", methods=["GET"])
def qlogStart():
   if not Path(QLOG_BIN).is_file():
      return {"error": f"{QLOG_BIN} not found"}, 500
   if findQlogProcesses():
      return {"error": "QLog already running", "running": True}, 409
   stopped_qcsuper = stopQcsuperProcesses()
   if stopped_qcsuper:
      _wait_for_port_release()
   cmd = [QLOG_BIN, "-s", str(TRACE_DIR), "-p", port]
   log_fh = open(QLOG_LOG, "ab", buffering=0)
   proc = subprocess.Popen(
      cmd,
      stdin=subprocess.DEVNULL,
      stdout=log_fh,
      stderr=subprocess.STDOUT,
      start_new_session=True,
      close_fds=True,
   )
   time.sleep(0.5)
   rc = proc.poll()
   if rc is not None:
      return {
         "error": "QLog exited immediately",
         "rc": rc,
         "log": QLOG_LOG,
         "cmd": cmd,
      }, 500
   out = {
      "info": "QLog started",
      "pid": proc.pid,
      "storage": str(TRACE_DIR),
      "port": port,
      "log": QLOG_LOG,
      "cmd": cmd,
   }
   if stopped_qcsuper:
      out["stopped_qcsuper"] = stopped_qcsuper
   return out


if __name__ == "__main__":
   app.run(host="127.0.0.1", port=8888, debug=True)