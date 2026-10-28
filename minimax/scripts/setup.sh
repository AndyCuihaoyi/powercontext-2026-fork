#!/usr/bin/env bash
# A1 第一步：准备运行环境（Python 虚拟环境 + 依赖 + seekdb 实例 + 建库建表）。
#
# 用法：bash scripts/setup.sh
# 可重复执行（幂等）。依赖安装失败会直接退出，不会留下「半装好」的状态。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "== 1/4 检查 Python（需要 3.11+）"
BASE_PY="${SDDCTX_BASE_PYTHON:-}"
if [[ -z "$BASE_PY" ]]; then
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      BASE_PY="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$BASE_PY" ]]; then
  echo "未找到 3.11+ 的 Python解释器" >&2
  exit 1
fi
echo "  使用 $BASE_PY（$("$BASE_PY" -V)）"

echo "== 2/4 创建虚拟环境并安装依赖"
if [[ ! -x "$HERE/.venv/bin/python" ]]; then
  "$BASE_PY" -m venv "$HERE/.venv"
fi
# 用 uv 建的 venv 默认不带 pip：缺 pip 时先 ensurepip，再退回 uv pip。
if ! "$HERE/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
  "$HERE/.venv/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
fi
if "$HERE/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
  "$HERE/.venv/bin/python" -m pip install --quiet --upgrade pip
  "$HERE/.venv/bin/python" -m pip install --quiet -r "$HERE/requirements.txt"
elif command -v uv >/dev/null 2>&1; then
  echo "  该 venv 无 pip，改用 uv pip 安装"
  uv pip install --quiet --python "$HERE/.venv/bin/python" -r "$HERE/requirements.txt"
else
  echo "既没有 pip 也没有 uv，无法装依赖" >&2
  exit 1
fi
"$HERE/.venv/bin/python" - <<'PYEOF'
import importlib.metadata as m
for name in ("powercontext", "pymysql", "pytest"):
    print(f"  {name}=={m.version(name)}")
PYEOF

echo "== 3/4 启动本样例专用 seekdb 实例"
SDDCTX_PYTHON="$HERE/.venv/bin/python" bash "$HERE/scripts/start_seekdb.sh"

echo "== 4/4 建库建表 + 首次导入"
if [[ ! -f "$HERE/.env" && -f "$HERE/.env.example" ]]; then
  echo "  提示：需要真实调用 MiniMax 时执行 cp .env.example .env 后填入 MINIMAX_API_KEY（.env 已被 .gitignore 排除）"
fi
"$HERE/.venv/bin/python" -m sddctx ingest

echo "setup 完成。下一步：bash scripts/run_sample.sh"
