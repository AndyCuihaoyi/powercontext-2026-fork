#!/usr/bin/env bash
# A1 主命令：一条命令跑完「导入 → 上下文 → 改前测试 → 状态 → MiniMax 改写 → 改后测试 → 验收 → 回到改前」。
#
# 用法：bash scripts/run_sample.sh [任务ID]
# 说明：没有 MINIMAX_API_KEY 时第 5 步自动退化为 --replay（复现已记录的模型输出），
#       并在结束时明确告诉你哪些验收项因此没被真实验证。
set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

TASK="${1:-${SDDCTX_TASK:-task-001}}"
BACKEND="replay"
if [[ -n "${MINIMAX_API_KEY:-}" ]]; then
  BACKEND="minimax"
fi

echo "########## 0. 环境"
bash "$MINIMAX_DIR/scripts/start_seekdb.sh"
echo "  seekdb ${SEEKDB_PORT} · MiniMax 后端：$BACKEND · 模型：${MINIMAX_MODEL:-未设置}"

echo "########## 1. 回到样例初始状态（实现=改前，规格/测试=初始快照）"
"$PY" -m sddctx reset --task "$TASK"

echo "########## 2. 导入工程资料 → seekdb（全文索引）"
"$PY" -m sddctx ingest

echo "########## 3. 生成任务上下文（只由 seekdb 查询结果构造）"
"$PY" -m sddctx context --task "$TASK" --format both

echo "########## 4. 改前测试：目标测试必须失败、回归必须通过"
set +e
"$PY" -m sddctx test --task "$TASK" --label before
BEFORE_RC=$?
set -e
echo "  改前退出码 $BEFORE_RC（预期非 0：目标测试断言失败，属设计如此）"
if [[ $BEFORE_RC -eq 0 ]]; then
  echo "  异常：改前就全绿，说明样例状态或测试集被动过" >&2
  exit 1
fi

echo "########## 5. MiniMax 依上下文改写实现代码"
if [[ "$BACKEND" == "minimax" ]]; then
  "$PY" -m sddctx agent --task "$TASK" --keep-changes
else
  echo "  未设置 MINIMAX_API_KEY → 用 --replay 复现 evidence/minimax/$TASK.jsonl 中记录的模型输出"
  "$PY" -m sddctx agent --task "$TASK" --replay --keep-changes
fi

echo "########## 6. 改后测试：目标 + 回归全绿"
"$PY" -m sddctx test --task "$TASK" --label after

echo "########## 7. 状态复用：写入 PowerContext → 新进程读回 → 注入上下文"
"$PY" -m sddctx state save --task "$TASK" --auto \
  --record "note=run_sample.sh 第 7 步写入的演示记录，用于验证跨进程复用"
"$PY" -m sddctx state show --task "$TASK"
"$PY" -m sddctx context --task "$TASK" --format md --with-state \
  --out "evidence/context/${TASK}-with-state.md"

echo "########## 8. 六项验收自检"
set +e
"$PY" scripts/verify_acceptance.py all --task "$TASK"
VERIFY_RC=$?
set -e

echo "########## 9. 回到改前状态（交付的仓库即验证样例初始态）"
"$PY" -m sddctx reset --task "$TASK"

if [[ $VERIFY_RC -ne 0 ]]; then
  echo "run_sample 完成，但有验收项未通过，见上方输出" >&2
  exit $VERIFY_RC
fi
echo "run_sample 完成：A1–A6 全部通过（后端 $BACKEND）。证据在 evidence/ 下。"
