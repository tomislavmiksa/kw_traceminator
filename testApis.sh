#!/usr/bin/env bash
# Run the smoke test for every API under src/code/<name>/tests/curl-smoke.sh.
# After each API the result is summarised and the user must confirm before
# the next one starts.
#
# Usage:
#   ./testApis.sh                    # run all, pause between each
#   ./testApis.sh --no-pause         # run all, no prompt between APIs
#   ./testApis.sh --only serial-at-api  # run a single API
#   ./testApis.sh --section trace    # forward "trace" arg to every smoke script
#
# Per-API output is also tee'd to /tmp/testApis-<name>.log
#
# Exit code: 0 if every API passed, otherwise the count of failed APIs.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CODE_DIR="${ROOT}/src/code"

PAUSE=1
SECTION=""        # empty -> let each smoke script use its default
ONLY=""

while [[ $# -gt 0 ]]; do
   case "$1" in
      --no-pause) PAUSE=0; shift ;;
      --only)     ONLY="$2"; shift 2 ;;
      --section)  SECTION="$2"; shift 2 ;;
      -h|--help)
         sed -n '2,12p' "$0"
         exit 0
         ;;
      *) echo "unknown arg: $1" >&2; exit 2 ;;
   esac
done

# discover all smoke test scripts; preserve dependency order:
#   serial-at-api must come first (others discover the modem via :8666/modem)
discover_apis() {
   local first=""
   if [[ -f "${CODE_DIR}/serial-at-api/tests/curl-smoke.sh" ]]; then
      first="serial-at-api"
      echo "$first"
   fi
   for d in "${CODE_DIR}"/*/tests/curl-smoke.sh; do
      [[ -f $d ]] || continue
      local name
      name="$(basename "$(dirname "$(dirname "$d")")")"
      [[ "$name" == "$first" ]] && continue
      echo "$name"
   done
}

mapfile -t APIS < <(discover_apis)

if [[ -n "$ONLY" ]]; then
   APIS=( "$ONLY" )
fi

# results: parallel arrays of name/rc/seconds
RESULT_NAMES=()
RESULT_RCS=()
RESULT_SECS=()

c_red()    { printf '\033[31m%s\033[0m' "$*"; }
c_green()  { printf '\033[32m%s\033[0m' "$*"; }
c_yellow() { printf '\033[33m%s\033[0m' "$*"; }
c_bold()   { printf '\033[1m%s\033[0m'  "$*"; }

print_intermediate() {
   local i name rc secs status
   echo
   c_bold "===== results so far =====" ; echo
   for i in "${!RESULT_NAMES[@]}"; do
      name="${RESULT_NAMES[$i]}"
      rc="${RESULT_RCS[$i]}"
      secs="${RESULT_SECS[$i]}"
      if [[ "$rc" -eq 0 ]]; then status="$(c_green PASS)"; else status="$(c_red "FAIL ($rc)")"; fi
      printf "  %-30s %s  %5ss\n" "$name" "$status" "$secs"
   done
   echo
}

prompt_continue() {
   local next="$1"
   echo
   printf "Press %s to run %s, %s to skip remaining, %s to quit: " \
      "$(c_bold ENTER)" "$(c_bold "$next")" "$(c_bold s)" "$(c_bold q)"
   local ans
   read -r ans
   case "${ans,,}" in
      q*) echo "aborted by user"; return 2 ;;
      s*) echo "skipping remaining"; return 1 ;;
      *)  return 0 ;;
   esac
}

run_one() {
   local name="$1"
   local script="${CODE_DIR}/${name}/tests/curl-smoke.sh"
   local logfile="/tmp/testApis-${name}.log"

   if [[ ! -x "$script" && ! -f "$script" ]]; then
      echo "SKIP $name -- no script at $script" >&2
      RESULT_NAMES+=("$name")
      RESULT_RCS+=(127)
      RESULT_SECS+=("0")
      return
   fi

   echo
   c_bold "===== ${name} ====="; echo
   echo "running: bash $script ${SECTION}"
   echo "log:     $logfile"
   echo

   local start end secs rc
   start=$(date +%s)
   set +e
   bash "$script" ${SECTION:+"$SECTION"} 2>&1 | tee "$logfile"
   rc=${PIPESTATUS[0]}
   set -e
   end=$(date +%s)
   secs=$((end - start))

   RESULT_NAMES+=("$name")
   RESULT_RCS+=("$rc")
   RESULT_SECS+=("$secs")

   echo
   if [[ "$rc" -eq 0 ]]; then
      printf "%s -> %s in %ss\n" "$name" "$(c_green PASS)" "$secs"
   else
      printf "%s -> %s in %ss (see %s)\n" "$name" "$(c_red "FAIL (rc=$rc)")" "$secs" "$logfile"
   fi
}

# main loop
total=${#APIS[@]}
for idx in "${!APIS[@]}"; do
   api="${APIS[$idx]}"
   run_one "$api"

   # show running tally
   print_intermediate

   # prompt before the next one (skip prompt for the last)
   if [[ "$PAUSE" -eq 1 && $((idx + 1)) -lt "$total" ]]; then
      next="${APIS[$((idx + 1))]}"
      if ! prompt_continue "$next"; then
         break
      fi
   fi
done

# final summary
echo
c_bold "===== final summary ====="; echo
fail=0
for i in "${!RESULT_NAMES[@]}"; do
   name="${RESULT_NAMES[$i]}"
   rc="${RESULT_RCS[$i]}"
   secs="${RESULT_SECS[$i]}"
   if [[ "$rc" -eq 0 ]]; then
      printf "  %-30s %s  %5ss\n" "$name" "$(c_green PASS)" "$secs"
   else
      printf "  %-30s %s  %5ss\n" "$name" "$(c_red "FAIL ($rc)")" "$secs"
      fail=$((fail + 1))
   fi
done

echo
if [[ "$fail" -eq 0 ]]; then
   c_green "all APIs passed"; echo
else
   c_red "${fail} of ${#RESULT_NAMES[@]} APIs failed"; echo
fi

exit "$fail"
