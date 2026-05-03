# Introduction

This module exposes a small HTTP API around **simtrace2** and **tcpdump** so
that SIM card communication can be captured and saved as `pcap` files
remotely.

The API wraps three external tools:

- `simtrace2-list`  - enumerate the SIMtrace2 USB interfaces present on the host.
- `simtrace2-sniff` - long-running daemon that forwards SIM APDUs as GSMTAP datagrams over UDP/4729 on `lo`.
- `tcpdump`         - listens on `lo`, filters `udp port 4729`, and writes a `pcap` to `./traces/`.

Application is running API on `http://localhost:8777`. The idea is not to expose this to the world, as RasPi shopuld run locally.

# Application Setup

## System dependencies

Installed and configured via the `../../../install.sh` script.

## Python environment

- accessing USB and writing to `/var/log/` requires root, so the API service runs as root
- all commands below should be executed as root

```
python3 -m venv .venv
source .venv/bin/activate

pip3 install -r ./requirements.txt
```

## Run

```
python3 main.py
```

The API binds `0.0.0.0:8777`. On startup it runs `simtrace2-list`; if no
SIMtrace2 device is detected, the process exits with code `1`.

# API endpoints

All endpoints are `GET` and return JSON.

| Method | Path            | Purpose                                              |
|--------|-----------------|------------------------------------------------------|
| GET    | `/`             | API metadata                                         |
| GET    | `/list`         | Output of `simtrace2-list` (USB interfaces)          |
| GET    | `/sniff-active` | Is `simtrace2-sniff` running?                        |
| GET    | `/sniff-start`  | Start `simtrace2-sniff` (idempotent)                 |
| GET    | `/sniff-stop`   | Kill `simtrace2-sniff`                               |
| GET    | `/trace-active` | Is `tcpdump` writing a `*simtrace*` pcap?            |
| GET    | `/trace-start`  | Start a new `tcpdump` capture (also ensures sniffer) |
| GET    | `/trace-stop`   | SIGTERM all simtrace `tcpdump` processes             |
| GET    | `/trace-list`   | List the `pcap` files in `./traces/`                 |

## Discovery

```
# basic application information
curl -s http://localhost:8777/ | jq

# enumerate connected SIMtrace2 USB interfaces
curl -s http://localhost:8777/list | jq
```

## Sniffer lifecycle

`simtrace2-sniff` is the daemon that captures APDUs from the SIMtrace2 USB
device and forwards them as GSMTAP datagrams to `udp/4729` on `lo`. Trace
capture only works while it is running.

```
# is the sniffer running?
# -> { "running": true, "pids": [4271] }
curl -s http://localhost:8777/sniff-active | jq

# ensure the sniffer is up (idempotent; will start it if not running)
curl -s http://localhost:8777/sniff-start | jq

# stop the sniffer
curl -s http://localhost:8777/sniff-stop | jq
```

## Trace lifecycle

`tcpdump` listens on `lo`, filters `udp port 4729`, and writes a pcap into
`./traces/<TZ>-<YYYYMMDD>-<HHMMSS>-simtrace.pcap`.

```
# is a simtrace tcpdump active?
# -> { "running": true, "pids": [9421],
#      "files": ["./traces/UTC-20260503-123045-simtrace.pcap"] }
curl -s http://localhost:8777/trace-active | jq

# start a new capture; will also ensure the sniffer is running first
curl -s http://localhost:8777/trace-start | jq

# stop all simtrace captures (uses SIGTERM so the pcap closes cleanly)
curl -s http://localhost:8777/trace-stop | jq

# list the pcaps that have been captured
curl -s http://localhost:8777/trace-list | jq
```

# Typical workflow

```
# 1. plug in the SIMtrace2 device, then start the API
sudo python3 main.py

# 2. start a capture (sniffer is auto-started)
curl -s http://localhost:8777/trace-start | jq

# 3. exercise the SIM (place a call, send an SMS, attach to network, ...)

# 4. stop the capture
curl -s http://localhost:8777/trace-stop | jq

# 5. find the resulting pcap
curl -s http://localhost:8777/trace-list | jq
ls -lh ./traces/
```

The pcap can be opened directly with Wireshark - GSMTAP packets are decoded
out of the box.

# Smoke test

A bash smoke test that exercises every endpoint in order is provided at
`tests/curl-smoke.sh`. Run it from any host that can reach the API:

```
./tests/curl-smoke.sh             # full lifecycle (default)
./tests/curl-smoke.sh discovery   # only the read-only endpoints
./tests/curl-smoke.sh trace       # only the trace section

# capture for 15s instead of the default 5s
CAPTURE_SECONDS=15 ./tests/curl-smoke.sh
```