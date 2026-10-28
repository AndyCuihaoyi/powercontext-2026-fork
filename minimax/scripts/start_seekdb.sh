#!/usr/bin/env bash
# 启动本样例专用的 seekdb 实例（默认 127.0.0.1:2893，独立数据目录，不影响其它端口上的实例）。
#
# 用法：  bash scripts/start_seekdb.sh [check]
# 依赖：  seekdb 1.4（deb 安装后二进制在 /usr/bin/seekdb），或提前设置 SEEKDB_BIN
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${SDDCTX_PYTHON:-$HERE/.venv/bin/python}"
PORT="${SDDCTX_SEEKDB_PORT:-2893}"
BASE="${SDDCTX_SEEKDB_BASE:-$HERE/runtime/seekdb}"
LOG="$BASE/seekdb.log"
PIDFILE="$BASE/seekdb.pid"

find_binary() {
  if [[ -n "${SEEKDB_BIN:-}" && -x "${SEEKDB_BIN}" ]]; then echo "${SEEKDB_BIN}"; return; fi
  for candidate in /usr/bin/seekdb /usr/local/bin/seekdb \
      "$HOME/OceanBase/work/seekdb-install/root/usr/bin/seekdb"; do
    [[ -x "$candidate" ]] && { echo "$candidate"; return; }
  done
  echo ""
}

already_up() {
  "$PY" - "$PORT" <<'PYEOF' >/dev/null 2>&1
import os, sys
import pymysql
port = int(sys.argv[1])
conn = pymysql.connect(host="127.0.0.1", port=port, user=os.environ.get("SDDCTX_SEEKDB_USER", "root"),
                       password=os.environ.get("SDDCTX_SEEKDB_PASSWORD", ""), connect_timeout=3)
cur = conn.cursor()
cur.execute("SELECT VERSION()")
cur.fetchone()
conn.close()
PYEOF
}

BIN="$(find_binary)"
if [[ -z "$BIN" ]]; then
  cat >&2 <<'MSG'
未找到 seekdb 二进制。请先安装 OceanBase seekdb 1.4（MySQL 协议兼容版）：
  # 例：从 https://github.com/oceanbase/seekdb/releases 下载对应系统的 deb/rpm 后安装
  sudo dpkg -i seekdb_1.4.0_*_amd64.deb     # 二进制落在 /usr/bin/seekdb
或已有安装时直接指定：export SEEKDB_BIN=/path/to/seekdb
MSG
  exit 1
fi

if already_up; then
  echo "seekdb 已就绪：127.0.0.1:${PORT}（无需重复启动）"
  exit 0
fi

mkdir -p "$BASE/store"
echo "启动 seekdb：$BIN --port=${PORT} --base-dir=$BASE"
nohup "$BIN" --nodaemon \
  --base-dir="$BASE" \
  --port="$PORT" \
  --data-dir="$BASE/store" \
  --redo-dir="$BASE/store/redo" \
  --parameter memory_limit=4G \
  --parameter datafile_size=2G \
  --parameter log_disk_size=2G \
  >"$LOG" 2>&1 &
echo $! >"$PIDFILE"

for attempt in $(seq 1 90); do
  if already_up; then
    echo "seekdb 就绪（等待 ${attempt}s）：127.0.0.1:${PORT} · pid $(cat "$PIDFILE") · 日志 $LOG"
    exit 0
  fi
  sleep 1
done

echo "seekdb 在 90s 内未就绪，请看日志：$LOG" >&2
tail -n 30 "$LOG" >&2 || true
exit 1
