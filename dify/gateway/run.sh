#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "missing gateway/.env; copy .env.example to .env and fill in seekdb/PowerContext/model settings" >&2
  exit 1
fi

exec "${PYTHON:-python3}" app.py
