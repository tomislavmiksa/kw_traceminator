import re
import requests
import time
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify

# absolute path to the trace directory, next to this main.py
TRACE_DIR = Path("/opt/serial-simtracing/traces")
TRACE_DIR.mkdir(parents=True, exist_ok=True)

# helper function to generate a unique filename for the trace
def make_pcap_filename(suffix: str = "simtrace", ext: str = "pcap") -> str:
    return str(TRACE_DIR / f"{time.strftime('%Z-%Y%m%d-%H%M%S')}-{suffix}.{ext}")

# INITIALIZE THE SIMTRACE2 PORT
# - makes no sense to proceed if the simtrace2 is not detected
# - if no simtrace2 is detected, exit the program
# - if simtrace2 is detected, map the simtrace2 command to the corresponding port
validate = subprocess.run("simtrace2-list", shell=True, capture_output=True, text=True)
print(validate.stdout)
if validate.returncode != 0:
   print("ERROR: no valid simtrace2 detected")
   exit(1)
simtrace2 = validate.stdout.strip()

app = Flask(__name__)

# the entry point to return the basic information about the API
# call: curl http://localhost:8666/
@app.route("/")
def root():
   return { "Version" : "1.0.0" , "Description": "API to manage the SIMTRACE2 Interface" }

# list the USB interfaces occupied by the SIMTRACE2
@app.route("/list", methods=['GET'])
def list():
   return { "Information" : validate.stdout }

# simtrace2-sniff is the process name for the SIMTRACE2 sniffing process
# - it runs in background and collects the traffic from the SIMTRACE2 interface
# - is starts the UDP datagram in the udp port

# verify if the SIMTRACE2 sniffing process is active
@app.route("/sniff-active", methods=['GET'])
def getSniff():
   name = "simtrace2-sniff"
   result = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
   pids = [int(p) for p in result.stdout.split()]
   return { "running": bool(pids), "pids": pids }

# start the SIMTRACE2 sniffing process
@app.route("/sniff-start", methods=['GET'])
def startSniff() -> bool:
   precondition = False
   LOG = "/var/log/simtrace2-sniff.log"
   name = "simtrace2-sniff"
   log_fh = open(LOG, "ab", buffering=0)
   while not precondition:
      r = requests.get("http://localhost:8777/sniff-active")
      if r.status_code != 200:
          precondition = False
          proc = subprocess.Popen(
              [name],
              stdin=subprocess.DEVNULL,
              stdout=log_fh,
              stderr=subprocess.STDOUT,
              start_new_session=True,   # detach: new session, immune to terminal hangup
              close_fds=True,
          )
          time.sleep(3)
      else:
          data = r.json()
          if data["running"]:
              precondition = True
          else:
              precondition = False
              proc = subprocess.Popen(
                  [name],
                  stdin=subprocess.DEVNULL,
                  stdout=log_fh,
                  stderr=subprocess.STDOUT,
                  start_new_session=True,   # detach: new session, immune to terminal hangup
                  close_fds=True,
              )
              time.sleep(3)
   return { "info" : "running", "pid" : proc.pid, "log" : LOG }

# kill the SIMTRACE2 sniffing process
@app.route("/sniff-stop", methods=['GET'])
def killSniff():
   name = "simtrace2-sniff"
   result = subprocess.run(["pkill", "-x", name], capture_output=True, text=True)
   return { "info" : "process killed" }

# find PIDs of tcpdump processes capturing to a *simtrace* pcap file
def findSimtraceTcpdumps():
   result = subprocess.run(
      ["pgrep", "-af", r"tcpdump.*simtrace"],
      capture_output=True, text=True,
   )
   matches: list[tuple[int, str]] = []
   for line in result.stdout.splitlines():
      pid_str, _, cmdline = line.partition(" ")
      if pid_str.isdigit():
         matches.append((int(pid_str), cmdline))
   return matches

# extract the file path passed via "-w <file>" from a tcpdump command line
def extractTcpdumpFile(cmdline: str) -> str | None:
   tokens = cmdline.split()
   try:
      return tokens[tokens.index("-w") + 1]
   except (ValueError, IndexError):
      return None

# verify if there is an active tcpdump trace writing a *simtrace* pcap
@app.route("/trace-active", methods=['GET'])
def getTrace():
   matches = findSimtraceTcpdumps()
   pids  = [pid for pid, _ in matches]
   files = [f for _, cmd in matches if (f := extractTcpdumpFile(cmd))]
   return { "running": bool(matches), "pids": pids, "files": files }

# stop all tcpdump processes whose command line contains "simtrace"
@app.route("/trace-stop", methods=['GET'])
def stopTrace():
   matches = findSimtraceTcpdumps()
   if not matches:
      return { "info" : "no matching tcpdump process", "killed" : [] }
   pids = [str(pid) for pid, _ in matches]
   subprocess.run(["kill", "-TERM", *pids], capture_output=True, text=True)
   killed = [{"pid": pid, "cmd": cmd} for pid, cmd in matches]
   return { "info" : f"stopped {len(killed)} tcpdump process(es)", "killed" : killed }

# start the trace capture process
@app.route("/trace-start", methods=['GET'])
def startTrace():
    filename = make_pcap_filename()
    precondition = False
    while not precondition:
        r = requests.get("http://localhost:8777/sniff-active")
        if r.status_code != 200:
            while r.status_code != 200:
                r = requests.get("http://localhost:8777/sniff-start")
                time.sleep(3)
        else:
            data = r.json()
            if data["running"]:
                precondition = True
            else:
                while r.status_code != 200:
                    r = requests.get("http://localhost:8777/sniff-start")
                    time.sleep(3)
    proc = subprocess.Popen(
        ["tcpdump", "-i", "lo", "-U", "-w", filename, "udp", "port", "4729"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return { "info" : "trace started", "pid" : proc.pid, "file" : filename }

# start the trace capture process
@app.route("/trace-list", methods=['GET'])
def listTraces():
   files = sorted(p.name for p in TRACE_DIR.glob("*.pcap"))
   return {"info": "list of traces", "dir": str(TRACE_DIR), "traces": files}

if __name__ == "__main__":
   app.run(host="0.0.0.0", port=8777, debug=False)