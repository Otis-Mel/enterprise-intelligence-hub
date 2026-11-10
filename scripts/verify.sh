#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

fail=0

tracked_secret_files=$(git ls-files | grep -E '(^|/)\.env$|\.db$' || true)
if [ -n "$tracked_secret_files" ]; then
  echo "FAIL: file bí mật hoặc cơ sở dữ liệu đang được git theo dõi:"
  echo "$tracked_secret_files"
  fail=1
fi

key_files=$(git grep -lE 'AIza[0-9A-Za-z_-]{30,}' || true)
if [ -n "$key_files" ]; then
  echo "FAIL: có chuỗi giống khóa Gemini trong:"
  echo "$key_files"
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi

(cd backend && pytest -q)
echo "verify: đạt"
