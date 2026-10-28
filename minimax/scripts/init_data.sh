#!/usr/bin/env bash
# A1 第二步：只准备数据（建库建表 + 导入 + 生成上下文包），不访问外网。
#
# 用法：bash scripts/init_data.sh [任务ID]
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

TASK="${1:-task-001}"

echo "== 1/3 启动 seekdb（已在跑则直接复用）"
bash "$MINIMAX_DIR/scripts/start_seekdb.sh"

echo "== 2/3 导入工程资料（按 sha 增量 + 清理失效条目）"
"$PY" -m sddctx ingest

echo "== 3/3 生成上下文包（seekdb 查询结果 → 上下文）"
"$PY" -m sddctx context --task "$TASK" --format both

echo "数据就绪：库 $("$PY" -c 'from sddctx import config;print(config.SEEKDB_DATABASE)')"
