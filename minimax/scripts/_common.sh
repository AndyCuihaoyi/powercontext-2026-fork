#!/usr/bin/env bash
# 其余脚本的公共前置：定位目录、加载 .env（密钥只在本机）、确认虚拟环境可用。
set -euo pipefail

MINIMAX_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$MINIMAX_DIR"

if [[ -f "$MINIMAX_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$MINIMAX_DIR/.env"
  set +a
fi

PY="${SDDCTX_PYTHON:-$MINIMAX_DIR/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "找不到虚拟环境解释器 $PY —— 先执行 bash scripts/setup.sh" >&2
  exit 1
fi

SEEKDB_PORT="${SDDCTX_SEEKDB_PORT:-2893}"

