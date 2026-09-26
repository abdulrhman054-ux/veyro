#!/usr/bin/env bash
# Browser end-to-end suites against a test server (fake model, stubbed market data, fake live feed).
# Usage: tools/e2e/run_all.sh    (set CHROMIUM=/path/to/chrome if Playwright's own browser isn't installed)
# Exits non-zero if any check fails or a suite crashes, so CI can gate on it.
set -u
cd "$(dirname "$0")/../.."
mkdir -p verification/e2e
PY=.venv/bin/python; [ -x "$PY" ] || PY=".venv/Scripts/python.exe"
failed=""
for t in ${SUITES:-ui_test new_feats round3 review_fixes round4 persist stop fun round5 screen}; do
  R=Buy; [ "$t" = fun ] && R=Sell   # the easter-egg suite needs a sell call
  pkill -f "[u]i_serve[r]\.py" 2>/dev/null; sleep 1
  (cd backend && FAKE_RATING=$R FAKE_DELAY=0.1 nohup "../$PY" ../tools/e2e/ui_server.py > ../verification/e2e/server_$t.log 2>&1 &)
  for i in $(seq 1 60); do curl -s localhost:8766/api/health >/dev/null && break; sleep 1; done
  echo "== $t"
  out=$(timeout 900 "$PY" tools/e2e/$t.py 2>&1); code=$?
  echo "$out" | grep -E "PASS|FAIL|ALL|SOME|Error"
  if [ $code -ne 0 ] || echo "$out" | grep -qE "^FAIL|SOME FAILED|Traceback" || ! echo "$out" | grep -q "^PASS"; then
    failed="$failed $t"
    echo "$out" | tail -25
  fi
done
pkill -f "[u]i_serve[r]\.py" 2>/dev/null
if [ -n "$failed" ]; then echo "FAILED SUITES:$failed"; exit 1; fi
echo "ALL SUITES PASSED"
