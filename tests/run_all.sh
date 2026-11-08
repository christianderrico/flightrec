#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
bash -n ../hooks/record.sh
python3 test_transcript.py
python3 scenario.py > /tmp/flightrec-scenario.log 2>&1 || { cat /tmp/flightrec-scenario.log; exit 1; }
grep -E "^(PASS|FAIL)" /tmp/flightrec-scenario.log
echo "all tests passed"
