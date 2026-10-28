#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "missing gateway/.env; copy .env.example to .env and fill in seekdb/PowerContext/model settings" >&2
  exit 1
fi

if [ -z "${PYTHON:-}" ]; then
  if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
  else
    PYTHON=python3
  fi
fi

exec "$PYTHON" app.py
