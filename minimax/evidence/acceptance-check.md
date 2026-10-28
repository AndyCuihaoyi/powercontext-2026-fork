# 验收自检 · task-001

生成时间：2026-10-28T08:59:52Z

## A1 能够运行 → PASS
  ok  交付文件存在：requirements.txt
  ok  交付文件存在：.env.example
  ok  交付文件存在：README.md
  ok  交付文件存在：scripts/setup.sh
  ok  交付文件存在：scripts/start_seekdb.sh
  ok  交付文件存在：scripts/init_data.sh
  ok  交付文件存在：scripts/run_sample.sh
  ok  交付文件存在：scripts/verify_acceptance.py
  ok  交付文件存在：sddctx/cli.py
  ok  交付文件存在：sddctx/store.py
  ok  交付文件存在：sddctx/retrieve.py
  ok  交付文件存在：sddctx/state.py
  ok  交付文件存在：sddctx/agent.py
  ok  交付文件存在：demo_project/tasks/task-001.md
  ok  交付文件存在：demo_project/specs/order_queries.md
  ok  交付文件存在：demo_project/app/queries.py
  ok  交付文件存在：demo_project/tests/test_target_task_001.py
  ok  交付文件存在：evidence/snapshots/initial/app/queries.py
  ok  `python -m sddctx --help` 退出码 0
  ok  CLI 子命令齐备：ingest, context, state, agent, test, reset
  ok  seekdb 可连接：5.7.25-OceanBase seekdb-v1.4.0.0 · 库 sdd_eco
  ok  测试目录与初始快照一致

## A2 MiniMax 实际参与 → PASS
  ok  开发记录存在：evidence/minimax/task-001.jsonl（1 轮）
  ok  记录里有真实 API 调用（含 endpoint / request_id / usage，不是纯 replay）
  ok  记录含发送的完整消息（system 规则 + user 上下文包）
  ok  实际发送的提示已留档：evidence/context/<task>-prompt.txt
  ok  留档提示与记录一致（10561 字符）
  ok  usage 记录 total_tokens
  ok  usage 记录 prompt_tokens
  ok  usage 记录 completion_tokens
  --   模型 MiniMax-M3.1-Flash · request_id 0730ea2b56058ad7425a2903cfa7272b · 耗时 60953 ms
  ok  补丁存在：evidence/diffs/task-001.patch
  ok  模型返回的文件与补丁改动的文件一一对应：['demo_project/app/queries.py', 'demo_project/app/reporting.py'] == ['demo_project/app/queries.py', 'demo_project/app/reporting.py']
  ok  补丁只触碰 demo_project/app/

## A3 上下文正确（必要来源齐备 + 来源可回查） → PASS
  ok  必要规格出现在上下文：SPEC-205
  ok  必要规格出现在上下文：SPEC-201
  ok  必要规格出现在上下文：SPEC-202
  ok  必要规格出现在上下文：SPEC-212
  ok  必要规格出现在上下文：SPEC-301
  ok  必要代码符号出现在上下文：list_orders
  ok  必要代码符号出现在上下文：summarize
  ok  必要代码符号出现在上下文：Order
  ok  必要测试文件出现在上下文：demo_project/tests/test_target_task_001.py
  ok  必要测试文件出现在上下文：demo_project/tests/test_regression_queries.py
  ok  必要测试文件出现在上下文：demo_project/tests/test_regression_reporting.py
  ok  必要测试文件出现在上下文：demo_project/tests/test_regression_pricing.py
  ok  上下文包含任务状态字段（无记录时为 null，而不是伪造）
  ok  每条来源带 path/line_range/item_id/sha8：25 条
  ok  逐条回读磁盘行区间，内容与索引一致

## A3b 规格更新后重新导入要用新内容（非硬编码） → PASS
  ok  改前上下文含 SPEC-212
  ok  改前 SPEC-212 正文用上界 100
  ok  改写 SPEC-212 上界为 200：重新导入 seekdb：文档 14（新增 1 / 未变 13）· 清理失效 0
  ok  更新后上下文仍含 SPEC-212（说明取的是同一条规格，不是凭空生成）
  ok  更新后正文用新上界 200
  ok  旧上界 100 已从上下文消失（旧内容不残留）
  ok  上下文行区间与磁盘更新后的文件一致
  ok  已还原初始规格文本并重新导入

## A4 数据库实际参与（seekdb 存储 + 检索 + 留痕） → PASS
  ok  sdd_documents 有真实行数：14
  ok  sdd_items 有真实行数：58
  ok  sdd_tasks 有真实行数：2
  ok  sdd_query_log 有真实行数：190
  ok  sdd_items 建有 FULLTEXT 索引
  ok  本次任务有 190 条 seekdb 查询留痕（SQL/参数/命中数/耗时）
  ok  包含全文检索阶段：['applies:code', 'applies:test', 'fulltext:code', 'fulltext:spec', 'fulltext:test', 'keyword:code', 'keyword:spec', 'keyword:test', 'referencers:test', 'sibling:spec']
  ok  上下文里的数据库信息指向 seekdb：5.7.25-OceanBase seekdb-v1.4.0.0
  ok  上下文包内置本次查询明细（可核对不是磁盘遍历）
  ok  applicable_specs 每条都来自索引记录 ID
  ok  target_code 每条都来自索引记录 ID
  ok  verification_tests 每条都来自索引记录 ID
  --   导出 /home/cuihaoyi/OceanBase/work/powercontext-ecosystem/minimax/evidence/db/queries.md

## A5 状态能够复用（PowerContext 写入 → 新进程读回 → 注入上下文） → PASS
  ok  PowerContext 写入 1 条（scope scp_3ed3kbsjbb237ts0vw5dvwathm）
  ok  落盘文件：/home/cuihaoyi/OceanBase/work/powercontext-ecosystem/minimax/runtime/powercontext/state.db
  ok  新进程 `state show` 退出码 0
  ok  新进程读回到刚才写入的探针记录（跨进程复用）
  ok  读回 16 条记录 · 后端 powercontext-embedded-sqlite
  ok  记录来源是 powercontext.atomic_memory，不是自写 JSON
  ok  上下文注入任务状态 16 条
  ok  状态含 kind：['decision', 'done', 'note', 'todo', 'verified']
  ok  渲染后的上下文 markdown 里能看到该状态

## A6 代码修改有效（改前断言失败 → 改后全绿 · 测试集不变） → PASS
  ok  改前/改后测试日志都在 evidence/test-logs/
  ok  改前日志无环境/导入/收集错误（检出 0）
  ok  改前有 12 处断言失败（功能性失败，不是跑不起来）
  ok  改前退出码非 0：[1, 0, 1]
  ok  改后各套件退出码全为 0：[0, 0, 0]
  ok  改后日志无 failed 用例
  ok  改后通过用例数：29（目标 + 回归全量）
  ok  测试与规格目录与初始快照逐字节一致（差异 {'tests': [], 'specs': []}）
  ok  补丁文件存在：evidence/diffs/task-001.patch
  ok  补丁不含测试文件
  ok  改后代码快照存在：evidence/snapshots/after-task-001/

