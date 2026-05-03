#!/usr/bin/env bash
# Smoke test for the serial-modemtracing API on localhost:8888.
# Exercises every endpoint in a sane order; safe to re-run.
#
# Usage:
#   ./tests/curl-smoke.sh                # full smoke test
#   ./tests/curl-smoke.sh discovery      # /, /modem-info
#   ./tests/curl-smoke.sh trace          # full trace lifecycle
#   ./tests/curl-smoke.sh cleanup        # stop any running trace
#
# Override defaults via env vars:
#   BASE=http://10.0.0.5:8888 CAPTURE_SECONDS=30 ./tests/curl-smoke.sh

set -uo pipefail

BASE="${BASE:-http://localhost:8888}"
CAPTURE_SECONDS="${CAPTURE_SECONDS:-10}"

# pretty-print JSON if jq is available, otherwise raw
fmt() { command -v jq >/dev/null && jq || cat; }

call() {
   local method=$1 path=$2
   echo "----- ${method} ${path} -----"
   curl -sS --max-time 60 -X "$method" "${BASE}${path}" | fmt
   echo
}

discovery() {
   call GET /
   # /modem-info needs exclusive diag port -> ensure no trace is running first
   call GET /trace-stop >/dev/null
   call GET /modem-info
}

trace() {
   call GET /trace-active
   call GET /trace-start
   echo "=== capturing for ${CAPTURE_SECONDS}s ==="
   sleep "$CAPTURE_SECONDS"
   call GET /trace-active
   call GET /trace-stop
   # qcsuper needs a moment to flush the pcap on SIGTERM
   sleep 1
   call GET /trace-list
}

cleanup() {
   call GET /trace-stop
}

case "${1:-full}" in
   discovery) discovery ;;
   trace)     trace ;;
   cleanup)   cleanup ;;
   full)
      discovery
      trace
      cleanup
      ;;
   *) echo "unknown section: $1" >&2
      echo "usage: $0 [discovery|trace|cleanup|full]" >&2
      exit 2
      ;;
esac
