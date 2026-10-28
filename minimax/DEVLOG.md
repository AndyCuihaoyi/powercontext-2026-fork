# 技术使用记录（DEVLOG）· MiniMax × seekdb × PowerContext

> 本题要求的三类记录都在这个文件里给出口径与索引，原始数据在 `evidence/` 下，可自行复核。
> 记录全部来自真实执行；没有「手写补丁冒充模型输出」，也没有「只测连接就算参与」。

## 0. 一次性复现

```bash
bash scripts/setup.sh && bash scripts/run_sample.sh   # 含真实 MiniMax 调用（需 .env 里的 MINIMAX_API_KEY）
./.venv/bin/python scripts/verify_acceptance.py all   # A1/A2/A3/A3b/A4/A5/A6 逐项 PASS/FAIL
```

## 1. MiniMax 开发记录（A2）

| 项 | 值 | 出处 |
|---|---|---|
| 端点 | `POST https://api.minimaxi.com/v1/chat/completions`（OpenAI 兼容，Bearer 鉴权） | `evidence/minimax/task-001.jsonl` 第 1 轮 `endpoint` |
| 模型 | `MiniMax-M3.1-Flash`（推理模型） | 同上 `model` |
| 请求 | system 205 字符（SDD 规则 + 整文件输出协议）+ user 10561 字符（上下文包渲染） | `messages`、`evidence/context/task-001-prompt.txt`（逐字节相同） |
| 响应 | 2838 字符，2 个 `<<<FILE …>>>` 块 | `response.content`、`evidence/minimax/task-001-round-1.md` |
| 用量 | `total 10054 / prompt 3822 / completion 6232`（其中 `reasoning_tokens 5454`，`cached_tokens 186`） | `usage` |
| 耗时 / 请求号 | 60953 ms · `0730ea2b56058ad7425a2903cfa7272b` | `elapsed_ms` / `request_id` |
| 落地文件 | `demo_project/app/queries.py`、`demo_project/app/reporting.py`（仅此两个） | 写文件白名单 `config.WRITABLE_PREFIXES` |
| 与 diff 的对应 | 模型返回的文件集合 == `evidence/diffs/task-001.patch` 的 `+++ b/` 文件集合（4 个 hunk，155 行） | `verify_acceptance.py A2` |
| 重试 | 第 1 轮即通过（rc=0），未触发失败回灌；策略上限 2 轮 | `agent.run(rounds=2)` |

**上下文即输入**：发给模型的 user 消息就是 `context` 命令渲染出的上下文包（规格 → 待改代码 → 验证测试 → 任务状态），
不含任务描述里的「预期实现方式」，也不含测试文件里的期望值。

## 2. seekdb 数据库记录（A4）

| 项 | 值 |
|---|---|
| 实例 | 本样例专用 `127.0.0.1:2893`，独立 `--base-dir runtime/seekdb`（与同机 2881/2885/2886/2887/2891 等实例互不影响） |
| 版本 | `5.7.25-OceanBase seekdb-v1.4.0.0` · 库 `sdd_eco` |
| 表 | `sdd_documents`(14) / `sdd_items`(58 改前、61 改后) / `sdd_tasks`(2) / `sdd_query_log`(110) |
| 索引 | `sdd_items` 上 `FULLTEXT INDEX sdd_item_ft (text) WITH PARSER ik`；`SHOW CREATE TABLE` 导出在 `evidence/db/schema.md` |
| 切块 | 规格 9 条（`### SPEC-x` 一条一块）、代码 18 条（顶层符号 + 模块 docstring）、测试 29 条（`test_*` 一个一块）、任务 2 条 |
| 留痕 | `evidence/db/queries.md`（由 `sdd_query_log` 导出：SQL、检索词、命中数、耗时） |

真实查询样本（`task-001`，同一次 `context` 调用）：

| stage | 命中 | 耗时 | SQL 形态 |
|---|---|---|---|
| `fulltext:spec` | 8 | 37 ms | `… MATCH(text) AGAINST(%s) AS score … WHERE kind=%s AND MATCH(text) AGAINST(%s) ORDER BY score DESC LIMIT %s` |
| `keyword:spec` | 9 | 22 ms | `… name LIKE %s OR keywords LIKE %s OR text LIKE %s` |
| `sibling:spec` | 9 | 2 ms | 按 `doc_id` 取同文件相邻条款 |
| `applies:code` | 4 | 4 ms | `qualified_path LIKE %s`（规格 `Applies-to` → 代码符号） |
| `fulltext:code` / `keyword:code` | 8 / 9 | 31 / 11 ms | 同上两式，`kind='code'` |
| `referencers:test` | 16 | 5 ms | `text LIKE %<符号>%`（哪些测试引用待改符号） |
| `applies:test` | 8 | 2 ms | 回归护栏名册按 `qualified_path` 前缀补齐 |

上下文里每条来源都带 `path + 行区间 + item_id + sha8`，`retrieve.check_bundle()` 会**逐条回读磁盘**核对行区间内容
与索引里的 sha 是否一致；改前 25/25 通过，改写代码后不重新导入就会出现回查失败——所以 `agent` 在落盘后强制 re-ingest。

## 3. PowerContext 状态记录（A5）

| 项 | 值 |
|---|---|
| 形态 | pip 包 `powercontext[builtin]==1.4.1` 的**内嵌 runtime**（`open_builtin_runtime`），落盘 SQLite `runtime/powercontext/state.db` |
| 作用域 | `scp_3ed3kbsjbb237ts0vw5dvwathm`（idempotency key `sddctx-task-001`；同 key 重复 `scopes.create()` 返回同一 scope） |
| 写入 | `atomic_memory.for_scope().create()`：`done`（导入计数）/ `decision`（适用规格与待改符号）/ `todo`（待办 + 回归约束）/ `verified`（改前 7 failed、改后 29 passed）/ `note`（脚本演示记录） |
| 复用 | 写入进程退出后，`python -m sddctx state show --task task-001` 在**新进程**读回 14 条记录；`context --with-state` 把它们注入上下文第七节 |
| 证据 | `evidence/powercontext/state-write.md`（写入内容与 artifact id）、`state-restart-read-task-001.md`（新进程读回，含逐条命中与相关度） |
| 空状态起步 | `python -m sddctx reset --task task-001 --state` 把 runtime 文件改名归档并清空 seekdb 记录，再从空状态写入（A5 的「从空状态保存」） |

## 4. 开发时间线

| 时间 | 动作 | 产出 |
|---|---|---|
| 10-27 | Stage 1–2：读题面、反推六项必做项验收口径、定 A1–A6 落点 | `topics/eco-04-minimax-sdd/00-brief.md`、`01-mapping.md` |
| 10-27 | Stage 3：CLI 形态 + 验证样例设计（Task-001 用 `SPEC-205` 时间窗口，SPEC-212 作规格更新样例） | `02-plan.md`、`demo_project/` |
| 10-27 | Stage 4：seekdb 专用实例（2893）、符号级切块、6 路信号 RRF 检索、来源回查、PowerContext 内嵌状态 | `store/ingest/retrieve/state/render/cli` |
| 10-28 | 拿到 MiniMax Key，安全落地（`.secrets/` → gitignored `.env`，只在终端打印长度与 sha256 前 12 位）；连通性探针发现 Key 属于国内站点 | `.env.example`、README §3 |
| 10-28 | 第一次真实改写（`MiniMax-M3.1-Flash`，1 轮通过，rc=0）；发现「改后不重新导入 → 来源回查失败」并修复 | `agent.py` 强制 re-ingest |
| 10-28 | 发现并修复索引一致性缺陷：文件 sha 变化后 `doc_id` 改变，旧版本条目成为孤儿行残留 → `upsert_document` 按 `path` 先删旧 doc 的条目，`prune` 增加孤儿清理 | `store.py` |
| 10-28 | 清空状态与索引，跑**完整闭环**重出证据（含 `evidence/context/task-001-prompt.txt`，使「实际发送的提示」与开发记录逐字节一致） | `evidence/`、`run_sample.sh` |
| 10-28 | 六项自检脚本 `verify_acceptance.py`（A1/A2/A3/A3b/A4/A5/A6）全 PASS；文档 README / TECH_NOTES / DEVLOG / docs/acceptance.md | Stage 5 完成 |

## 5. 踩到的坑与修法（全部已验证）

1. **裸 `powercontext` 装不上运行依赖**（`httpx`/`yaml`/`sqlalchemy` 缺失）→ 必须 `powercontext[builtin]==1.4.1`。
2. **Key 站点错**：`api.minimax.io` 返回 401 `invalid api key (2049)`；国内 Key 用 `api.minimaxi.com/v1`。写进 `.env.example` 注释。
3. **推理模型正文为空**：`max_tokens` 太小时 `finish_reason=length` 且 `content=""`（`reasoning_tokens` 吃满预算）→ 明确报错文案 + `MINIMAX_MAX_TOKENS=16000`。
4. **PowerContext `search()` 多词查询按 AND 处理**，长查询串命中 0 → 改成**逐关键词** `search()` 取最大相关度合并（探针：`q='seekdb'` 命中 1，`q='since'` 命中 0）。
5. `open_builtin_runtime` 默认把 `powercontext.scheduler.db` 写进当前工作目录 → 显式 `scheduler_path` 指到 `runtime/powercontext/`。
6. **测试套件名对不上**：`--task task-001` ≠ 文件 `test_target_task_001.py`，早期把 29 条当「回归」跑，掩盖了目标测试失败 → `re.sub(r"[^0-9A-Za-z_]", "_", task_id)` 生成文件名，日志按 target/regression/full 三段各记退出码。
7. **改代码后不重新导入** → 上下文回查出现 4 条 `verified=False`（行区间与索引 sha 不一致）→ `agent.run` 落盘后立即 re-ingest。
8. **孤儿条目**：文件内容变化使 `doc_id = kind:sha:path` 改变，旧版本独有符号（`_filter_orders`）留在 `sdd_items` 里被检索到 → `upsert_document` 先按 `path` 查出旧 `doc_id` 删其条目，`prune()` 再兜底删除「没有父文档的条目」。
9. **`.env.example` 的空占位值**把路径变量解析成 `Path('.')` → 配置改为 `_path()`：空字符串等同未设置。
10. **改前失败必须功能性**：`classify_pytest_failure()` 区分 `AssertionError`（有效失败）与 `ModuleNotFoundError` / `error during collection` / `internal error`（环境错误），后者出现即判 A6 不过。
11. 上游 `jieba` 在 `import powercontext` 时打印 `SyntaxWarning: invalid escape sequence`，无害，README 已注明。

## 6. 未做的事（明确交代）

- 没做 HTTP/MCP 入口：题面允许 CLI，且 CLI 对「干净环境复现」最省事。
- 没实现 seekdb 向量检索/`pylibseekdb` 内嵌后端：FULLTEXT + 关键词 + 结构关联已满足 A3/A4，向量留作扩展点。
- 没做第二个任务的真实改写：`task-002`（规格更新样例）用于演示「改规格 → 重新导入 → 上下文取新值」，不产生代码改动。
- 密钥只在本机 `.env`（600 权限、被 `.gitignore` 排除）与 `/home/cuihaoyi/OceanBase/.secrets/minimax.env`，仓库只出现占位值。
