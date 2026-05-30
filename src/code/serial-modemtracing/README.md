# Introduction

This module exposes a small HTTP API around **QCSuper** so that a Qualcomm
modem's diagnostic interface can be queried and captured to a `pcap` file
remotely.

The API wraps one external tool:

- `qcsuper.py` - reads the modem's Qualcomm Diag interface (`/dev/ttyUSB0`
  or whichever port maps to `Diag`) and either prints modem identity
  (`--info`) or writes a Wireshark-readable pcap with reassembled SIBs,
  decrypted NAS, and IP traffic (`--pcap-dump`).

The Diag port mapping is **not** discovered locally - it is fetched from
the `serial-at-api` service on `http://localhost:8666/modem` at startup,
so that service must be reachable before this one starts.

**Modem compatibility:** EC25, EG25G, and BG96 are used routinely for
QCSuper and QLog captures. **RG255C-GL** support is still **under testing**;
5G **RedCap** trace decode and attach behaviour are **under evaluation**
(QCSuper has partial NR support; Quectel QLog is often the practical path on
newer Quectel 5G modules).

Application is running API on `http://localhost:8888`. The idea is not to
expose this to the world, as RasPi should run locally.

The web UI proxies these endpoints as `/api/qcsuper-*` and `/api/qlog-*` on
port 9000.

# Application Setup

## System dependencies

Installed and configured via the `../../../install.sh` script. In short:

- QCSuper is cloned to `/opt/qcsuper/` and its venv contains `pyserial`,
  `pyusb`, `crcmod`, `pycrate`.
- **QLog** binary at `/opt/QLog` (installed from `bin/aarch64/QLog` by
  `install.sh`; see `bin/aarch64/qlog_compile.md` for build notes).
- `serial-at-api` must be installed and running on port `8666`.

## Python environment

- accessing the diag port requires root, so the API service runs as root
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

The API binds `0.0.0.0:8888`. On startup it:

1. runs `qcsuper.py --help` to confirm QCSuper is installed -> exits `1` if not
2. calls `http://localhost:8666/modem` -> exits `1`/`2`/`3` if no modem or
   no Diag port is detected

# API endpoints

All endpoints are `GET` and return JSON.

| Method | Path            | Purpose                                                  |
|--------|-----------------|----------------------------------------------------------|
| GET    | `/`             | API metadata                                             |
| GET    | `/modem-info`   | Output of `qcsuper --info` (manufacturer, model, IMEI)   |
| GET    | `/trace-active` | Is `qcsuper.py` writing a pcap?                          |
| GET    | `/trace-start`  | Start a new `qcsuper` capture                            |
| GET    | `/trace-stop`   | SIGTERM all qcsuper trace processes                      |
| GET    | `/trace-list`   | List files in the trace directory                        |
| GET    | `/qlog-active`  | Is `/opt/QLog` running?                                  |
| GET    | `/qlog-start`   | Start QLog (QXDM) capture into `TRACE_DIR`               |
| GET    | `/qlog-stop`    | SIGTERM all QLog processes                               |

## Trace lifecycle

`qcsuper.py` is invoked with these flags:

```
--reassemble-sibs --decrypt-nas --include-ip-traffic
--pcap-dump <TRACE_DIR>/<TZ>-<YYYYMMDD>-<HHMMSS>-qcsuper.pcap
```

The trace runs in the background as a separate process group; combined
stdout/stderr is appended to `/var/log/qcsuper-api.log`.

## QLog (QXDM) lifecycle

QLog is started as:

```
/opt/QLog -s /opt/serial-modemtracing/traces -p <diag port>
```

`<diag port>` is the same `/dev/ttyUSB*` path QCSuper uses (from
`http://localhost:8666/modem`). QCSuper and QLog share the Diag port; the
API enforces exclusivity automatically: `/trace-start` stops any running
QLog first, and `/qlog-start` stops any running QCSuper first (1 s pause
so the port is released). The JSON response may include `stopped_qlog` or
`stopped_qcsuper` listing what was terminated.

```
# is QLog running?
curl -s http://localhost:8888/qlog-active | jq

# start QLog
curl -s http://localhost:8888/qlog-start | jq

# stop QLog
curl -s http://localhost:8888/qlog-stop | jq
```

Service log: `/var/log/qlog-api.log`.

Captured files land in `/opt/serial-modemtracing/traces/` (QCSuper `*.pcap`,
QLog output, and batch-run `*-atserial.tsv` files written by the webapp).

```
# is a qcsuper trace active?
# -> { "running": true, "pids": [9421],
#      "files": ["/opt/serial-modemtracing/traces/UTC-20260503-123045-qcsuper.pcap"] }
curl -s http://localhost:8888/trace-active | jq

# start a new capture (returns 500 if qcsuper exits within 0.5s)
curl -s http://localhost:8888/trace-start | jq

# stop all qcsuper captures (uses SIGTERM so the pcap closes cleanly)
curl -s http://localhost:8888/trace-stop | jq

# list the pcaps that have been captured
curl -s http://localhost:8888/trace-list | jq
```

# Typical workflow

```
# 1. ensure serial-at-api is up (we depend on it for the Diag port)
curl -sf http://localhost:8666/modem | jq

# 2. start the modemtracing API
sudo python3 main.py

# 3. (optional) dump modem identity
curl -s http://localhost:8888/modem-info | jq

# 4. start a capture
curl -s http://localhost:8888/trace-start | jq

# 5. exercise the modem (place a call, attach, send data, ...)

# 6. stop the capture - SIGTERM, qcsuper flushes the pcap trailer
curl -s http://localhost:8888/trace-stop | jq

# 7. find the resulting pcap
curl -s http://localhost:8888/trace-list | jq
ls -lh /opt/serial-modemtracing/traces/
```

The pcap can be opened directly with Wireshark - GSM/UMTS/LTE/NR layers,
NAS, and reassembled SIBs are decoded out of the box.

# Smoke test

A bash smoke test that exercises every endpoint in order is provided at
`tests/curl-smoke.sh`. Run it from any host that can reach the API:

```
./tests/curl-smoke.sh             # full lifecycle (default)
./tests/curl-smoke.sh discovery   # only / and /modem-info
./tests/curl-smoke.sh trace       # only the QCSuper trace section
./tests/curl-smoke.sh qlog        # only the QLog section
./tests/curl-smoke.sh cleanup     # stop any running trace

# capture for 30s instead of the default 10s
CAPTURE_SECONDS=30 ./tests/curl-smoke.sh

# point the test at a different host
BASE=http://10.0.0.5:8888 ./tests/curl-smoke.sh
```

# Troubleshooting

- **`/trace-start` returns 500 with `qcsuper exited immediately`** - check
  `/var/log/qcsuper-api.log` for the actual stderr. Common causes: a
  previous trace still holding the diag port, missing libusb, bad CLI
  arguments, modem unreachable.
- **`/modem-info` hangs / times out** - usually means a trace is running
  (port is in use). Run `/trace-stop` first.
- **`/trace-list` returns an empty list** - check that the `TRACE_DIR`
  (`/opt/serial-modemtracing/traces`) exists and that qcsuper actually
  produced a pcap. Look in `/var/log/qcsuper-api.log` if it didn't.
- **API exits with code `1` on startup** - either QCSuper is not installed
  at `/opt/qcsuper/` or `serial-at-api` isn't reachable on `:8666`.
- **`/qlog-start` fails or QLog exits immediately** - check
  `/var/log/qlog-api.log`. Ensure `/opt/QLog` exists (aarch64 binary from
  `install.sh`). A running QCSuper trace holds the Diag port — run
  `/trace-stop` first (the API also stops QCSuper automatically when starting
  QLog).
