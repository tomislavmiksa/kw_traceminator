#!/usr/bin/env bash
# Smoke test for the serial-simtracing API on localhost:8777.
# Exercises every endpoint in a logical order; safe to re-run.
#
# Usage:
#   ./tests/curl-smoke.sh              # full smoke test
#   ./tests/curl-smoke.sh discovery    # only run the discovery section
#
# Sections: discovery, sniffer, trace, full (default)

set -uo pipefail

BASE="${BASE:-http://localhost:8777}"
CAPTURE_SECONDS="${CAPTURE_SECONDS:-5}"

# pretty-print JSON if jq is available, otherwise raw
fmt() { command -v jq >/dev/null && jq || cat; }

call() {
   local method=$1 path=$2
   echo "----- ${method} ${path} -----"
   curl -sS --max-time 30 -X "$method" "${BASE}${path}" | fmt
   echo
}

discovery() {
   call GET /
   call GET /list
}

sniffer() {
   call GET /sniff-stop
   call GET /sniff-active
   call GET /sniff-start
   call GET /sniff-active
   # leave the sniffer running for the trace section
}

trace() {
   call GET /trace-active
   call GET /trace-start
   echo "=== capturing for ${CAPTURE_SECONDS}s ==="
   sleep "$CAPTURE_SECONDS"
   call GET /trace-active
   call GET /trace-stop
   call GET /trace-list
}

cleanup() {
   call GET /trace-stop    # idempotent
   call GET /sniff-stop
}

case "${1:-full}" in
   discovery) discovery ;;
   sniffer)   sniffer ;;
   trace)     trace ;;
   cleanup)   cleanup ;;
   full)
      discovery
      sniffer
      trace
      cleanup
      ;;
   *) echo "unknown section: $1 (use: discovery|sniffer|trace|cleanup|full)" >&2; exit 2 ;;
esac
