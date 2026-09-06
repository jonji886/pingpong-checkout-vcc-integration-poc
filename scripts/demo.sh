#!/usr/bin/env bash
set -euo pipefail
base="${BASE_URL:-http://127.0.0.1:8000}"
key="demo-$(date +%s)"
curl -sS -X POST "$base/api/topups" -H 'Authorization: Bearer dev-token' -H "Idempotency-Key: $key" -H 'Content-Type: application/json' -d '{"amount":"100.00","currency":"USD"}'
echo

