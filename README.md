# kw_traceminator

A self-contained modem diagnostic and trace-capture toolchain for a
Raspberry Pi connected to a Quectel modem, for example:

- **Quectel EC25** (LTE)
- **Quectel EG25G** (LTE)
- **Quectel BG96** (Cat-M1 / NB-IoT)
- **Quectel RG255C-GL** (5G RedCap — still under testing; see [Hardware](#hardware))

and (optionally) an **Osmocom SIMtrace2** USB device.

The measurement system finally looks like
![](attachments/Pasted%20image%2020260506102538.png)

The project bundles four small services and a web UI that, together, let
you:

- talk to the modem with raw AT commands,
- run scripted batches of AT/shell commands with retries, regex success
  criteria and `goto`/`sleep` flow control,
- capture **modem-side** packet traces via `qcsuper.py` (GSM/UMTS/LTE/NR
  L2/L3, NAS, reassembled SIBs, IP traffic) into `pcap`,
- capture **modem-side** diagnostic logs via **QLog** (Quectel QXDM-style
  capture on the Diag port) into `/opt/serial-modemtracing/traces`,
- capture **SIM-side** APDU traces via `simtrace2-sniff` + `tcpdump`
  (GSMTAP on `udp/4729`) into `pcap`,
- browse, download, and delete trace files from the same web UI,
- restart backend services from the UI when serial interfaces get out of sync.

Everything runs locally on the Pi, behind one orange-themed page titled
**TRACEMINATOR** at `http://<pi>:9000`.

As all the tools and publically available under the Opensource license, this product just assembles them and provides and User Interface for easier management and log collection. It is licensed under MIT license, therefore feel free to use it as you wish. 

# Walkthrough

After the successful installation, connect to a WebApp on any of the RasPi IP-s. It runs on the port 9000.

After logged in, the WebApp shall present a simple WebGUI with:
- **Modem Information**
          ![](attachments/Pasted%20image%2020260504095702.png)
	- modem information must load, else all is in vain and application itself makes no sense 
	- modem and modem interfaces shall be automatically detected
- **Trace and Logs Management**
	- **Control**
	          ![](attachments/Pasted%20image%2020260504100007.png)
		- is an interface to control the Tracing and Log collection tools
		- **QCSuper**, **QLog**, and **SIMtrace2** (via Osmocom Simtrace2) are supported
		- QCSuper and QLog share the modem Diag port — only one can run at a time
		- by clicking Start and Stop you start or terminate trace collection
	- **Logs**
	          ![](attachments/Pasted%20image%2020260504100031.png)
		- contains the information about all logging attempts
	- **Log Files**
	          ![](attachments/Pasted%20image%2020260504100107.png)
		- lists files under `/opt/serial-modemtracing/traces` and
		  `/opt/serial-simtracing/traces` (`pcap`, batch-result `*.tsv`, QLog output, …)
		- download or delete individual files from the browser
- **Modem Commands**
	- the GUI interface for executing interactions with the modem via serial AT
	- **Single AT**
	          ![](attachments/Pasted%20image%2020260504100416.png)
		- interface to run a single AT command on the modem
	- **Modem Batch Instructions**
	          ![](attachments/Pasted%20image%2020260504101139.png)
		- interface to run a script — a combination of AT commands (on the modem)
		  and shell commands (on the RasPi)
		- read the separate section about the implemented syntax
		- useful for running measurements over long periods; supports looping,
		  retries, regex matching, and conditional `goto` / `sleep` flow control
		- live results stream into the page; each run also writes a TSV log file
		  (`<TZ>-<YYYYMMDD>-<HHMMSS>-atserial.tsv`) alongside modem traces

## Modem Batch Syntax

| Field            | Mandatory | Description                                                                            |
| ---------------- | --------- | -------------------------------------------------------------------------------------- |
| `index`          | yes       | int. Like BASIC line numbers (`10`, `20`, ...). Used as `goto` target. Must be unique. |
| `type`           | yes       | `at` (modem command via `/api/at`) or `sh` (shell command via `subprocess.run`).       |
| `cmd`            | yes       | The command itself.                                                                    |
| `expected_regex` | no        | If set, success = `re.search(regex, output)`. If empty, success = HTTP 200 / exit 0.   |
| `reattempts`     | no        | Extra retries on failure (default 0). Total tries = `1 + reattempts`.                  |
| `if_success`     | no        | Flow action on success. `""`/`next` (default), `goto N`, `sleep N`, `stop`.            |
| `if_failed`      | no        | Same vocabulary as `if_success`; runs when all retries are exhausted without matching. |

Each batch run streams live NDJSON to the browser and writes a TSV log to
`/opt/serial-modemtracing/traces/<TZ>-<YYYYMMDD>-<HHMMSS>-atserial.tsv`
(columns: Step, Line, Timestamp, Type, Command, Attempt, Result, Action, ms,
Output). Use **Abort** or `POST /api/batch/abort` to stop a long-running script.

### Example 1: SIM available?

- the script below shall
	- reboot the modem
	- sleep 60 seconds until the modem boot is over
	- verify if AT interface is responsive
	- 3 times try to get answer for the AT+CPIN? to make shore the SIM is inserted and ready; if failes 4 consecutive times, we shall reboot the modem again

```
1:at:AT+CFUN=1,1:OK::
2:sh:sleep 60:::
10:sh:date:::
20:at:AT:OK:5::
30:at:AT+CPIN?:READY:3::goto 1
```

- with expected output as
![](attachments/Pasted%20image%2020260506094209.png)

### Example 2: Attach?

- the script below shall
	- list the ICCID and IMSI of the SIM card
	- verify the 

```
40:at:AT+QCCID:::
50:at:AT+CIMI:::
60:at:AT+COPS?:OK::
70:at:AT+QENG="servingcell":::
80:at:AT+CGDCONT?:::
90:at:AT+CREG?:0,(1|5):20::goto 40
```

- with the expected output as
![](attachments/Pasted%20image%2020260506094316.png)
# Architecture

```
                                  ┌─────────────────────────┐
                                  │        Browser          │
                                  │   http://<pi>:9000      │
                                  └──────────┬──────────────┘
                                             │ same-origin
                                             ▼
                              ┌────────────────────────────────┐
                              │  webapp-flask  (port 9000)     │
                              │  • serves index.html            │
                              │  • /api/...  -> proxy + UI bits │
                              │  • batch script runner (NDJSON) │
                              └──┬─────────────┬────────────┬──┘
                                 │             │            │
        ┌────────────────────────┘             │            └───────────────────────────┐
        ▼                                      ▼                                        ▼
┌────────────────────┐            ┌──────────────────────────┐            ┌───────────────────────────┐
│ serial-at-api 8666 │            │ serial-modemtracing 8888 │            │ serial-simtracing  8777   │
│ /modem  /at        │            │ /modem-info /trace-*     │            │ /list /sniff-* /trace-*   │
└──────────┬─────────┘            │ /qlog-*                  │            └──────────────┬────────────┘
           │ pyserial              └──────────┬───────────────┘                       │ simtrace2-sniff
           ▼                                 ▼ qcsuper.py + QLog                      │ + tcpdump (udp/4729)
   /dev/serial/by-id/...              /dev/serial/by-id/...                              ▼
   (Quectel AT port)                   (Quectel Diag port)                       /dev/bus/usb/... (SIMtrace2)
```

The browser only ever talks to `webapp-flask`; CORS and split origins
never come up. The webapp does **not** drive USB / serial / SIMtrace2
hardware directly - it is a UI plus a thin same-origin proxy.

# Components

Each component has its own README with full endpoint reference, smoke
tests, and troubleshooting notes:

| Component             | Port  | Path                              | Role                                                         |
|-----------------------|-------|-----------------------------------|--------------------------------------------------------------|
| `serial-at-api`       | 8666  | [src/code/serial-at-api/](src/code/serial-at-api/README.md)              | Detect modem & expose `/modem` + `/at` (raw AT)              |
| `serial-modemtracing` | 8888  | [src/code/serial-modemtracing/](src/code/serial-modemtracing/README.md)  | Wrap `qcsuper.py` + QLog for modem capture                  |
| `serial-simtracing`   | 8777  | [src/code/serial-simtracing/](src/code/serial-simtracing/README.md)      | Wrap `simtrace2-sniff` + `tcpdump` for SIM `pcap` capture    |
| `webapp-flask`        | 9000  | [src/gui/webapp-flask/](src/gui/webapp-flask/README.md)                  | Single-page UI + same-origin JSON proxy + script runner      |

External binaries pulled in by the installer:

- **QCSuper** - cloned from `https://github.com/P1sec/QCSuper` into `/opt/qcsuper`,
  with its own venv (`pyserial`, `pyusb`, `crcmod`, `pycrate`).
- **QLog** - pre-built binary copied to `/opt/QLog` (aarch64; see
  `bin/aarch64/qlog_compile.md` for build notes). Used for Quectel QXDM-style
  Diag capture when QCSuper is not the right tool.
- **simtrace2-utils**, **libosmocore**, **tcpdump** - via the Osmocom
  Debian repo (`https://downloads.osmocom.org/packages/osmocom:/latest/...`).

# Hardware

Tested on a **Raspberry Pi 5 with 8GB or RAM running Debian 13 (Bookworm/Trixie)** with:

| Modem | Status | Notes |
|-------|--------|-------|
| [Quectel EC25](https://www.quectel.com/product/lte-ec25-mini-pcie-series/) | Supported | LTE; full interface map including NDIS |
| [Quectel EG25G](https://www.quectel.com/product/lte-eg25-g/) | Supported | LTE; same USB interface layout as EC25 (detected via `EG25` profile in `modem.json`) |
| [Quectel BG96](https://www.quectel.com/product/lte-bg96/) | Supported | Cat-M1 / NB-IoT |
| [Quectel RG255C-GL](https://www.quectel.com/product/5g-rg255c-series/) | **Under testing** | 5G module (Qualcomm SDX35). AT/Diag mapping is in `modem.json`, but end-to-end validation is ongoing. **5G RedCap** attach and trace behaviour (QCSuper, QLog) is **under evaluation** — expect gaps compared with mature LTE modules. |

The AT and Diag serial nodes are mapped via `udev`-stable paths (see
`src/code/serial-at-api/modules/data/modem.json` for the interface
index → role mapping per model).

- The modem was connected to RasPi via the **[LTE Hat from Sixfab](https://sixfab.com/product/raspberry-pi-base-hat-3g-4g-lte-minipcie-cards/?srsltid=AfmBOopjMbo1sII3IzJqDuX9xgrr7PmO8YUcu7Z7fgfbVAe8KM7sxNPp)**
- **[Osmocom SIMtrace2](https://osmocom.org/projects/simtrace2/wiki)** USB device for SIM-side capture (optional;
  modem-only setups can ignore the simtracing service).

Other Qualcomm-based USB modems may work for QCSuper/QLog as long as they
expose a Diag interface, but only the models listed above have explicit
`modem.json` mappings for automatic port detection.

# Repository layout

```
kw_traceminator/
├── install.sh                       # one-shot installer / uninstaller
├── testApis.sh                      # runs every API smoke test in order
├── LICENSE                          # MIT
├── README.md                        # (this file)
└── src/
    ├── code/
    │   ├── serial-at-api/           # port 8666: modem detection + AT
    │   ├── serial-modemtracing/     # port 8888: qcsuper trace
    │   └── serial-simtracing/       # port 8777: simtrace2 + tcpdump
    └── gui/
        └── webapp-flask/            # port 9000: single-page UI
```

Each service directory contains a `main.py`, `requirements.txt`, a
`service/<name>.service` systemd unit, and a `tests/curl-smoke.sh`
smoke test. The installer copies the directory into `/opt/<name>/`,
creates a venv, installs the unit file, and starts the service.

# Quickstart

```bash
# 1. clone the repo
git clone <this-repo>.git kw_traceminator
cd kw_traceminator

# 2. plug in the modem (and optionally the SIMtrace2)

# 3. install everything (services, QCSuper, simtrace2-utils, webapp)
sudo ./install.sh -i

# 4. open the UI from any host that can reach the Pi
xdg-open http://localhost:9000        # or http://<pi-ip>:9000

# 5. RasPi OS should automatically detect and map the modem and SIMtrace V2 in RasPi
miksato@raspi-03:~/kw_traceminator $ lsusb
...
Bus 003 Device 006: ID 1d50:60e3 OpenMoko, Inc. Osmocom SIMtrace 2
Bus 003 Device 014: ID 2c7c:0296 Quectel Wireless Solutions Co., Ltd. BG96 CAT-M1/NB-IoT modem
```

The UI surfaces:

1. **Modem Information** - which interfaces were detected (red rows on
   missing interfaces). Banner buttons restart individual backend services
   when serial ports get out of sync after a modem reboot.
2. **Trace and Logs Management** - QCSuper / QLog / SIMtracer2 status dots,
   Start/Stop buttons, an event log, and a **Log Files** tab to download or
   delete captured files (`pcap`, batch TSV, QLog output, …).
3. **Modem Commands** - single AT command sender and a 250-line script
   runner (**Modem Batch Instructions**) with live streamed results and
   per-run TSV export.

# Managing the services

After `install.sh -i`, four systemd units are enabled and running:

| Unit                          | Component             |
|-------------------------------|-----------------------|
| `serialmodeminterface`        | `serial-at-api`       |
| `serialmodemtrace`            | `serial-modemtracing` |
| `serialsimtrace`              | `serial-simtracing`   |
| `webinterface`                | `webapp-flask`        |

```bash
# status / logs
sudo systemctl status serialmodeminterface serialmodemtrace serialsimtrace webinterface
sudo journalctl -u webinterface -f

# restart one
sudo systemctl restart serialmodeminterface

# restart all
sudo systemctl restart serialmodeminterface serialmodemtrace serialsimtrace webinterface
```

Each unit runs as `root` (USB / serial access), uses its own venv at
`/opt/<name>/.venv/`, and has `Restart=on-failure` so a crash auto-recovers.

# Smoke testing

Per-service smoke tests live under
`src/code/<name>/tests/curl-smoke.sh` - each runs the full lifecycle
(discovery → start → capture → stop → list) against `localhost:<port>`.

To run them in dependency order with a confirmation prompt between APIs:

```bash
./testApis.sh                          # full sweep, pause between each
./testApis.sh --no-pause               # full sweep, no prompts
./testApis.sh --only serial-at-api     # one API only
./testApis.sh --section trace          # forward "trace" arg to every smoke script

# longer SIM capture window than the default 5 s
CAPTURE_SECONDS=15 ./testApis.sh --only serial-simtracing
```

Per-API output is also `tee`'d to `/tmp/testApis-<name>.log`. Exit code
is `0` if every API passed, otherwise the count of failed APIs.

The webapp-flask service does not have a smoke test; exercise it via the
browser at `http://localhost:9000`.

# Uninstall

```bash
sudo ./install.sh -d
```

This stops + disables the four units, removes their `.service` files
from `/etc/systemd/system/`, and deletes `/opt/serial-at-api`,
`/opt/serial-modemtracing`, `/opt/serial-simtracing`,
`/opt/webapp-flask`, `/opt/qcsuper`, and `/opt/QLog`. Captured files under
`/opt/serial-*/traces/` are removed with their parent directories - back
them up first if you need them.

System packages installed via `apt` (`tcpdump`, `libosmocore22`,
`libosmocore-utils`, `simtrace2-utils`) and the Osmocom apt source are
left in place; remove them manually if no longer needed.

# Troubleshooting

- **All UI status dots stay gray** - one or more backend services aren't
  running. `systemctl status serialmodeminterface serialmodemtrace
  serialsimtrace webinterface`.
- **Modem Information shows red rows** - `serial-at-api` could not detect
  the expected interfaces for your modem model. Re-plug the modem; if the
  kernel labels changed, check the mapping in
  `src/code/serial-at-api/modules/data/modem.json`.
- **`/api/batch/run` returns HTTP 409** - another batch is already
  running on the webapp. POST `/api/batch/abort` (the **Abort** button
  does this) and retry.
- **QCSuper and QLog both show green** - they share the Diag port; the API
  stops one before starting the other. If a dot stays gray, check
  `journalctl -u serialmodemtrace -f` and `/var/log/qlog-api.log`.
- **Live batch updates show all-at-once instead of streaming** - some
  reverse proxy is buffering. The endpoint sets `X-Accel-Buffering: no`;
  if you've put nginx in front, also set `proxy_buffering off`.
- **`install.sh -i` says "Link already exists"** - one of `/opt/<name>/`
  is already populated. Run `sudo ./install.sh -d` first to wipe and
  reinstall.
- **`pcap`s won't open in Wireshark** - ensure capture stopped via
  `/trace-stop` (SIGTERM, so the pcap trailer is flushed). Pulling the
  USB cable mid-capture can leave a truncated file.

For component-specific failures, see each component's own README:

- [serial-at-api](src/code/serial-at-api/README.md)
- [serial-modemtracing](src/code/serial-modemtracing/README.md)
- [serial-simtracing](src/code/serial-simtracing/README.md)
- [webapp-flask](src/gui/webapp-flask/README.md)

# Changelog


| Date       | Version | Author                            | Description                                                                 |
| ---------- | ------- | --------------------------------- | --------------------------------------------------------------------------- |
| 2026-05-30 | 1.1.0   | Tomislav Miksa <tmiksa@zgmc.info> | QLog, batch TSV, trace delete, service restart; EG25G + RG255C-GL modem profiles |
| 2026-05-04 | 1.0.0   | Tomislav Miksa <tmiksa@zgmc.info> | Initial Version                                                             |


# License

MIT - see [LICENSE](LICENSE).
