# Introduction

This module communicates with the modem over its AT serial interface. It
detects Quectel modems by USB ID and maps kernel interface indices (`if00`,
`if01`, …) to logical roles (`AT`, `Diag`, `NMEA`, …) using
`modules/data/modem.json`.

Supported modem profiles today:

| Model       | `modem.json` key | Notes |
|-------------|------------------|-------|
| EC25        | `EC25`           | Full interface map including NDIS |
| EG25G       | `EG25`           | Same USB interface layout as EC25; detected when `lsusb` product string contains `EG25` |
| BG96        | `BG96`           | AT, Diag, NMEA, Modem (no NDIS in mapping) |
| RG255C-GL   | `RG255C-GL`      | **Under testing.** 5G RedCap (SDX35). Mapping is present; **RedCap functionality is under evaluation** — report issues if attach or tracing behaves unexpectedly. |

Detection walks `modem.json` in order and picks the first entry whose key
matches a substring in `lsusb` output.

Other modules depend on this service — especially `serial-modemtracing`, which
reads the Diag port from `GET /modem` at startup.

Application runs on `http://localhost:8666`. Bind is loopback-only (`127.0.0.1`);
the web UI reaches it via the `webapp-flask` proxy at `/api/modem` and
`/api/at`.

# Application Setup

## System dependencies

Installed and configured via the `../../../install.sh` script. The process
exits on startup if no modem with a valid `AT` port is detected.

## Python environment

- serial port access requires root, so the API service runs as root
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

The API binds `127.0.0.1:8666`.

## Run as a systemd service

`service/serialmodeminterface.service` is installed by `install.sh` to
`/etc/systemd/system/serialmodeminterface.service`:

```
sudo systemctl enable --now serialmodeminterface
sudo systemctl status serialmodeminterface
sudo journalctl -u serialmodeminterface -f
```

# API endpoints

| Method | Path    | Purpose                                                       |
|--------|---------|---------------------------------------------------------------|
| GET    | `/`     | API metadata (`Version`, detected `Modem` port map)           |
| GET    | `/modem`| JSON map of logical roles → `/dev/serial/by-id/...` paths     |
| POST   | `/at`   | Send one AT command; returns normalized single-line response  |

## Discovery

```
curl -s http://localhost:8666/ | jq
curl -s http://localhost:8666/modem | jq
```

## Send AT command

Request body: `{"cmd": "ATI"}` (must match `^[aA][tT].*`).

Optional: `"timeout": <seconds>` (default `2`) — sleep before reading the
serial buffer.

```
curl -s -X POST http://localhost:8666/at \
  -H 'Content-Type: application/json' \
  -d '{"cmd": "ATI"}' | jq
```

Response shape:

```json
{ "Response": "200", "cmd": "ATI", "response": "Quectel;EC25;..." }
```

Newlines in the modem reply are collapsed to `;` for easier JSON handling.

# Typical workflow

```
# 1. confirm the modem is mapped
curl -sf http://localhost:8666/modem | jq

# 2. sanity-check AT
curl -s -X POST http://localhost:8666/at \
  -H 'Content-Type: application/json' \
  -d '{"cmd": "AT"}' | jq

# 3. other services (modemtracing, webapp) consume /modem automatically
```

# Smoke test

```
./tests/curl-smoke.sh
BASE=http://127.0.0.1:8666 ./tests/curl-smoke.sh
```

# Troubleshooting

- **Process exits immediately with "no valid modem detected"** — modem
  unplugged, wrong USB IDs, or interface indices changed. Re-plug and check
  `modules/data/modem.json`.
- **`/at` returns 400** — body missing, or `cmd` does not start with `AT`.
- **Empty `/at` response** — increase `"timeout"` in the JSON body; the modem
  may still be booting after `AT+CFUN=1,1`.
- **Red rows in the TRACEMINATOR UI** — one or more expected interfaces from
  `modem.json` were not found under `/dev/serial/by-id/`. Use the **Restart
  Serial Modem** button or `systemctl restart serialmodeminterface` after a
  modem reset.
