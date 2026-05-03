#!/usr/bin/env bash
# Smoke test for the serial-at-api on localhost:8666.
# Exercises every endpoint and a small battery of common AT commands.
# Safe to re-run; read-only against the modem.
#
# Usage:
#   ./tests/curl-smoke.sh                # full smoke test
#   ./tests/curl-smoke.sh discovery      # only the GET endpoints
#   ./tests/curl-smoke.sh at-basic       # only ATI
#   ./tests/curl-smoke.sh at-info        # device identity (manufacturer, model, IMEI)
#   ./tests/curl-smoke.sh at-network     # signal quality, registration, operator
#   ./tests/curl-smoke.sh at-sim         # SIM state (CPIN, IMSI, ICCID)
#   ./tests/curl-smoke.sh at-error       # exercises the 400 / bad-request path
#
# Override the host or per-command timeout via env vars:
#   BASE=http://10.0.0.5:8666 AT_TIMEOUT=5 ./tests/curl-smoke.sh

set -uo pipefail

BASE="${BASE:-http://localhost:8666}"
AT_TIMEOUT="${AT_TIMEOUT:-2}"

# pretty-print JSON if jq is available, otherwise raw
fmt() { command -v jq >/dev/null && jq || cat; }

# GET helper
get() {
   local path=$1
   echo "----- GET ${path} -----"
   curl -sS --max-time 30 "${BASE}${path}" | fmt
   echo
}

# AT command helper -> POST /at with JSON body
at() {
   local cmd=$1
   local timeout="${2:-$AT_TIMEOUT}"
   echo "----- AT  ${cmd}"
   curl -sS --max-time $((timeout + 10)) \
      --request POST \
      --header "Content-Type: application/json" \
      --data "{\"cmd\": \"${cmd}\"}" \
      "${BASE}/at" | fmt
   echo
}

# Raw POST helper for the error-path tests (lets us send malformed bodies)
post_raw() {
   local body=$1
   echo "----- POST /at  body=${body} -----"
   curl -sS --max-time 10 \
      --request POST \
      --header "Content-Type: application/json" \
      --data "${body}" \
      "${BASE}/at" | fmt
   echo
}

discovery() {
   get /
   get /modem
}

at_basic() {
   at "ATI"           # product identification (manufacturer, model, FW)
   at "AT"            # nop, expects "OK"
}

at_info() {
   at "AT+CGMI"       # manufacturer
   at "AT+CGMM"       # model
   at "AT+CGMR"       # firmware revision
   at "AT+CGSN"       # IMEI
}

at_network() {
   at "AT+CSQ"        # signal quality (RSSI, BER)
   at "AT+CREG?"      # circuit-switched network registration
   at "AT+CGREG?"     # GPRS registration
   at "AT+CEREG?"     # LTE registration
   at "AT+COPS?" 5    # operator selection (slow; allow more time)
}

at_sim() {
   at "AT+CPIN?"      # SIM PIN status
   at "AT+CIMI"       # IMSI
   at "AT+QCCID"      # ICCID (Quectel-specific)
}

at_error() {
   post_raw '{"cmd": "ls /"}'         # not an AT command -> 400
   post_raw '{"cmd": null}'           # null cmd          -> 400 (or KeyError)
   post_raw '{}'                      # missing key       -> 400 (or KeyError)
   post_raw 'not json at all'         # invalid JSON      -> 400 (or KeyError)
}

case "${1:-full}" in
   discovery)  discovery ;;
   at-basic)   at_basic ;;
   at-info)    at_info ;;
   at-network) at_network ;;
   at-sim)     at_sim ;;
   at-error)   at_error ;;
   full)
      discovery
      at_basic
      at_info
      at_network
      at_sim
      at_error
      ;;
   *) echo "unknown section: $1" >&2
      echo "usage: $0 [discovery|at-basic|at-info|at-network|at-sim|at-error|full]" >&2
      exit 2
      ;;
esac
