# kw_traceminator

A self-contained modem diagnostic and trace-capture toolchain for a
Raspberry Pi connected to a **Quectel EC25** USB modem and (optionally)
an **Osmocom SIMtrace2** USB device.

The project bundles four small services and a web UI that, together, let
you:

- talk to the modem with raw AT commands,
- run scripted batches of AT/shell commands with retries, regex success
  criteria and `goto`/`sleep` flow control,
- capture **modem-side** packet traces via `qcsuper.py` (GSM/UMTS/LTE/NR
  L2/L3, NAS, reassembled SIBs, IP traffic) into `pcap`,
- capture **SIM-side** APDU traces via `simtrace2-sniff` + `tcpdump`
  (GSMTAP on `udp/4729`) into `pcap`,
- browse and download the resulting trace files from the same web UI.

Everything runs locally on the Pi, behind one orange-themed page at
`http://<pi>:9000`.

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
		- at the moment QCSuper and Simtrase via Sysmocom Simtrace2 supported
		- by clicking Start and Stop button you start or terminate the traces collection
	- **Logs**
	          ![](attachments/Pasted%20image%2020260504100031.png)
		- contains the information about all logging attempts
	- **Log Files**
	          ![](attachments/Pasted%20image%2020260504100107.png)
		- is an interface to download the collected logs and traces locally
- Modem Commands

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
└──────────┬─────────┘            └──────────┬───────────────┘            └──────────────┬────────────┘
           │ pyserial                        │ qcsuper.py                                │ simtrace2-sniff
           ▼                                 ▼                                           │ + tcpdump (udp/4729)
   /dev/serial/by-id/...              /dev/serial/by-id/...                              ▼
   (Quectel EC25 AT port)             (Quectel EC25 Diag port)                  /dev/bus/usb/... (SIMtrace2)
```

The browser only ever talks to `webapp-flask`; CORS and split origins
never come up. The webapp does **not** drive USB / serial / SIMtrace2
hardware directly - it is a UI plus a thin same-origin proxy.

# Components

Each component has its own README with full endpoint reference, smoke
tests, and troubleshooting notes:

| Component             | Port  | Path                              | Role                                                         |
|-----------------------|-------|-----------------------------------|--------------------------------------------------------------|
| `serial-at-api`       | 8666  | [src/code/serial-at-api/](src/code/serial-at-api)              | Detect modem & expose `/modem` + `/at` (raw AT)              |
| `serial-modemtracing` | 8888  | [src/code/serial-modemtracing/](src/code/serial-modemtracing/README.md)  | Wrap `qcsuper.py` for modem `pcap` capture                   |
| `serial-simtracing`   | 8777  | [src/code/serial-simtracing/](src/code/serial-simtracing/README.md)      | Wrap `simtrace2-sniff` + `tcpdump` for SIM `pcap` capture    |
| `webapp-flask`        | 9000  | [src/gui/webapp-flask/](src/gui/webapp-flask/README.md)                  | Single-page UI + same-origin JSON proxy + script runner      |

External binaries pulled in by the installer:

- **QCSuper** - cloned from `https://github.com/P1sec/QCSuper` into `/opt/qcsuper`,
  with its own venv (`pyserial`, `pyusb`, `crcmod`, `pycrate`).
- **simtrace2-utils**, **libosmocore**, **tcpdump** - via the Osmocom
  Debian repo (`https://downloads.osmocom.org/packages/osmocom:/latest/...`).

# Hardware

Tested on a **Raspberry Pi 5 with 8GB or RAM running Debian 13 (Bookworm/Trixie)** with:

- **[Quectel EC25](https://www.quectel.com/product/lte-ec25-mini-pcie-series/)** modem (any `EC25-*` variant). The AT and Diag
  serial nodes are mapped via `udev`-stable paths (see
  `src/code/serial-at-api/modules/data/modem.json` for the interface
  index → role mapping). 
- The modem was connected to RasPi via the **[LTE Hat from Sixfab](https://sixfab.com/product/raspberry-pi-base-hat-3g-4g-lte-minipcie-cards/?srsltid=AfmBOopjMbo1sII3IzJqDuX9xgrr7PmO8YUcu7Z7fgfbVAe8KM7sxNPp)**
- **[Osmocom SIMtrace2](https://osmocom.org/projects/simtrace2/wiki)** USB device for SIM-side capture (optional;
  modem-only setups can ignore the simtracing service).

Other Qualcomm-based USB modems should work for the QCSuper part as long
as they expose a Diag interface; the AT endpoint mapping is currently
EC25-specific.

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

# 2. plug in the EC25 modem (and optionally the SIMtrace2)

# 3. install everything (services, QCSuper, simtrace2-utils, webapp)
sudo ./install.sh -i

# 4. open the UI from any host that can reach the Pi
xdg-open http://localhost:9000        # or http://<pi-ip>:9000
```

The UI surfaces:

1. **Modem Information** - which interfaces were detected (red rows on
   missing interfaces).
2. **Trace and Logs Management** - QCSuper / SIMtracer2 status dots,
   Start/Stop buttons, an event log, and a "Log Files" tab to download
   captured `pcap`s.
3. **Modem Commands** - single AT command sender, a 250-line script
   runner ("Modem Batch Instructions") with live streamed results, and
   the cumulative AT command log (every attempt, AT and `sh` both).

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
`/opt/webapp-flask`, and `/opt/qcsuper`. Captured `pcap`s under
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
  the expected EC25 interfaces. Re-plug the modem; if the kernel labels
  changed, check the mapping in
  `src/code/serial-at-api/modules/data/modem.json`.
- **`/api/batch/run` returns HTTP 409** - another batch is already
  running on the webapp. POST `/api/batch/abort` (the **Abort** button
  does this) and retry.
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

- [serial-at-api](src/code/serial-at-api/)
- [serial-modemtracing](src/code/serial-modemtracing/README.md)
- [serial-simtracing](src/code/serial-simtracing/README.md)
- [webapp-flask](src/gui/webapp-flask/README.md)

# Changelog


| Date       | Version | Author                            | Description     |
| ---------- | ------- | --------------------------------- | --------------- |
| 2026-05-04 | 1.0.0   | Tomislav Miksa <tmiksa@zgmc.info> | Initial Version |


# License

MIT - see [LICENSE](LICENSE).
