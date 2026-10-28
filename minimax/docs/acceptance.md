# 验收对照 · 题面 §4.1 六项必做项

> 一条命令自测：`./.venv/bin/python scripts/verify_acceptance.py all`（逐项打印 ok/FAIL，明细写 `evidence/acceptance-check.md`）。
> 下表「实测」列取自 2026-10-28 的完整闭环运行（`bash scripts/run_sample.sh`，MiniMax 后端真实调用）。

| # | 验收项 | 判据（题面原文要点） | 复核命令 | 证据文件 | 实测 |
|---|---|---|---|---|---|
| A1 | 能够运行 | 按运行说明可初始化数据、启动模块、执行验证样例；不依赖未交付的本地文件或状态 | `bash scripts/setup.sh && bash scripts/run_sample.sh` | `evidence/acceptance-check.md`、`scripts/{setup,start_seekdb,init_data,run_sample}` | PASS：交付文件齐备、`python -m sddctx --help` rc=0、seekdb 14 文档/58 条目可读、测试目录与初始快照一致 |
| A2 | MiniMax 实际参与 | 开发记录含本次任务、上下文、代码修改过程，且与提交的代码差异对应 | `python -m sddctx agent --task task-001` | `evidence/minimax/task-001.jsonl`、`task-001-round-1.md`、`evidence/context/task-001-prompt.txt`、`evidence/diffs/task-001.patch`、`DEVLOG.md §1` | PASS：`MiniMax-M3.1-Flash` 1 轮，prompt 3822 / completion 6232（reasoning 5454）token，`request_id 0730ea2b…`；返回文件集合 == patch 的 `+++ b/` 文件集合；留档提示与记录逐字节一致 |
| A3 | 上下文正确 | 输出含样例规定的必要规格/代码/测试来源 | `python -m sddctx context --task task-001 --format both` + `verify_acceptance.py A3` | `evidence/context/task-001.md`/`.json`、必要来源清单 `demo_project/tasks/task-001-checklist.md` | PASS：SPEC-205/201/202/212/301(+103/102/302)、`list_orders`/`summarize`/`Order`(+5 项)、4 个测试文件全部命中；25/25 来源回读磁盘行区间一致 |
| A3b | 上下文正确（后半句） | 规格更新并重新导入后，输出使用更新内容（不是固定答案） | `python scripts/spec_update_demo.py --bound 200` → `context` → `--restore` | `evidence/context/task-002-{before,after}-spec-update.md` | PASS：SPEC-212 由 `<= 100 / 上界为 100` 变为 `<= 200 / 上界为 200`，旧上界不再出现，且行区间与磁盘更新后的文件一致；还原后重新导入 |
| A4 | 数据库实际参与 | seekdb 保存工程资料或索引，实际查询结果用于任务上下文 | `python -m sddctx ingest` → `verify_acceptance.py A4` | `evidence/db/schema.md`、`counts.md`、`queries.md` | PASS：4 张表有真实行数（14/58/2/110）；`FULLTEXT INDEX … WITH PARSER ik`；上下文每条来源带索引 `item_id`；10 个检索阶段全部留痕 SQL/检索词/命中数/耗时 |
| A5 | 状态能够复用 | 从空状态保存任务记录，重启模块后能读取并用于后续上下文 | `reset --state`（空状态）→ `state save --auto` → 新进程 `state show` → `context --with-state` | `evidence/powercontext/state-write.md`、`state-restart-read-task-001.md`、`evidence/context/task-001-with-state.md` | PASS：写入 `done/decision/todo/verified/note` 到内嵌 SQLite；**新进程**读回 14 条（含验收探针）并渲染进上下文第七节；来源标记 `powercontext.atomic_memory` |
| A6 | 代码修改有效 | 同一组目标测试改前失败（非环境错误）、改后通过；相关回归也全通过；测试集不变 | `verify_acceptance.py A6`（日志由 `test --label before/after` 产生） | `evidence/test-logs/before-task-001.log`、`after-task-001.log`、`evidence/snapshots/{initial,after-task-001}/`、`evidence/diffs/task-001.patch` | PASS：改前 target rc=1（7 failed / 22 passed，12 处 `AssertionError`，环境错误检出 0）；改后三段 rc=0（29 passed）；`tests/` 与 `specs/` 与初始快照逐字节一致；补丁不含测试文件 |

## 红线的机器核对方式

| 红线 | 代码/脚本层面的保证 |
|---|---|
| 上下文不得硬编码 | `retrieve.py` 只接受 seekdb 返回行；A3b 用「改规格 → 重新导入 → 输出取新值、旧值消失」直接证伪固定答案 |
| 不得改测试通过 | `config.WRITABLE_PREFIXES = ("demo_project/app/",)`，`agent.validate_path` 拒绝其它路径；`reset.check_untouched(("specs","tests"))` 逐字节比对初始快照；A6 断言补丁不含 `demo_project/tests/` |
| 改前失败不能是环境错误 | `verify_acceptance.py::classify_pytest_failure` 把 `ModuleNotFoundError` / `ImportError` / `error during collection` / `internal error` / `command not found` 单独计数，非 0 即 FAIL |
| 三种技术必须真实参与 | A2 要求记录里有 `endpoint/request_id/usage`（纯 replay 不过）；A4 要求 `sdd_query_log` 有全文检索阶段；A5 要求探针记录被**另一个进程**读回 |
| 不提交真实凭据 | 仓库只有 `.env.example` 占位值；`.env`、`runtime/`、`.venv/` 均被 `.gitignore` 排除；开发记录 jsonl 不保存 Authorization 头 |
| 不影响其它作品 | 独立 seekdb 端口 2893 + 独立库 `sdd_eco` + 独立 `runtime/`；资产只在 `minimax/` 目录内 |

## 评审核对「MiniMax 与 diff 对应」的最短路径

```bash
# 1. 模型返回了哪些文件
./.venv/bin/python - <<'PY'
import json,re
row=[json.loads(l) for l in open("evidence/minimax/task-001.jsonl")][-1]
print(sorted(set(re.findall(r"<<<FILE\s+([^\n>]+)", row["response"]["content"]))))
print(row["usage"], row["request_id"])
PY
# 2. 提交的 diff 改了哪些文件
grep '^+++ b/' evidence/diffs/task-001.patch
```

两边的文件集合相同，且 `evidence/context/task-001-prompt.txt` 与 `task-001.jsonl` 里 `messages` 的 user 内容逐字节一致——
即「发给模型的上下文」和「模型改出来的代码」是同一次调用的两端。
