# 一页技术说明 · SDD 上下文模块（`sddctx`）

## 一、模块结构

```
              demo_project/{specs,app,tests,tasks}        任务 ID（front matter: title/statement/keywords）
                        │ ingest（符号级切块 + sha 增量）    │
                        ▼                                   ▼
   ┌──────────────────────────── seekdb 1.4（sdd_eco）────────────────────────────┐
   │ sdd_documents  sdd_items(FULLTEXT ik)  sdd_tasks  sdd_query_log              │
   └───────────────┬──────────────────────────────────────────────┬───────────────┘
                   │ retrieve（6 路信号 → RRF → 来源回查）           │ state（PowerContext 内嵌 runtime）
                   ▼                                              ▼
        ContextBundle { applicable_specs, target_code, verification_tests,
                        regression_files, task_state, db }
                   │ render.prompt_text（规格 → 代码 → 测试 → 状态 + 整文件输出协议）
                   ▼
              MiniMax /chat/completions ──► demo_project/app/*.py ──► pytest（目标 + 回归）
                                                          │
                                             evidence/{diffs,test-logs,minimax,context,db,powercontext}
```

| 文件 | 职责 |
|---|---|
| `sddctx/config.py` | 只读环境变量的运行时配置（路径、端口、模型、上限、可写白名单） |
| `sddctx/store.py` | seekdb DDL、增删改查、全文/关键词/结构关联检索、`sdd_query_log` 留痕 |
| `sddctx/ingest.py` | 切块口径：`### SPEC-x` = 一条规格；顶层 `def/class/常量` = 一个符号；`test_*` = 一个测试 |
| `sddctx/retrieve.py` | 上下文选择：6 路信号 + RRF 融合 + 磁盘行区间回读校验（不符即报错，不静默丢弃） |
| `sddctx/state.py` | PowerContext `open_builtin_runtime` + `atomic_memory` 写入/跨进程读回 |
| `sddctx/minimax_client.py` | OpenAI 兼容 `POST /chat/completions`（只用标准库 `urllib`），记录 usage/request_id |
| `sddctx/agent.py` | 上下文 → MiniMax → 解析整文件块 → 白名单落盘 → 跑测试 → 失败回灌重试（≤2 轮）→ 重新导入 |
| `sddctx/render.py` / `cli.py` / `reset.py` | 上下文包渲染（md/json/prompt）、CLI 入口、初始快照与重置 |

## 二、上下文选择方式

给定任务 ID，只从 seekdb 的 `SELECT` 结果里选资料，**不遍历磁盘文件**（磁盘只用于回读校验行区间）：

| 信号 | SQL 形态 | 作用 |
|---|---|---|
| `fulltext` | `MATCH(text) AGAINST(%s)`（`sdd_items` 上 `FULLTEXT INDEX ... WITH PARSER ik`） | 规格/代码/测试的语义召回主路 |
| `keyword` | `name LIKE %t% OR keywords LIKE %t% OR text LIKE %t%` | 中英混排、驼峰符号名、`since=2024-03-01` 这类分词盲区的兜底 |
| `applies` | `qualified_path LIKE %<target>` | 规格 `Applies-to: app/queries.py::list_orders` → 结构性拉取被作用代码，不靠文本相似度 |
| `referencers` | `text LIKE %<symbol>%`（`kind='test'`） | 哪些测试引用了待改符号 → 即「用于验证的测试」 |
| `sibling` | 同一 `doc_id` 的其它条目 | 同规格文件的相邻条款（如 SPEC-205 带上 SPEC-201/202/212） |
| `coverage` | `sdd_documents` 名册 + 每文件至少一条 | 保证回归护栏（每个测试文件）都出现在上下文里 |

六路结果按 RRF 融合：`score = Σ 1/(k_signal + rank)`，各路 `k` 不同（结构信号权重高于文本），
每类截断到 `--limit`（默认 spec/code/test 各 8）。任务状态来自 PowerContext 读回的记录，
按任务关键词逐条 `search()` 后取最大相关度排序，与检索结果并列注入同一个上下文包。

**反硬编码**：上下文的每条来源都是查询返回的 `item_id + 行区间 + 内容 sha`；
改规格 → `ingest`（sha 变化 → 覆盖并清理失效条目）→ 再检索即取到新值，旧值不残留。

## 三、技术分工

| 技术 | 承担的作用（不是「测连接」） | 失败即失分的点 |
|---|---|---|
| **seekdb 1.4** | 存工程资料与全文索引；上下文由真实 SQL 结果构造；每次查询把 SQL/检索词/命中数/耗时写入 `sdd_query_log` | 若上下文改成读磁盘拼装 → A4 不成立 |
| **PowerContext 1.4.1** | `atomic_memory` 落 SQLite，写进程与读进程不同（模块重启语义）；「已完成/待办/验证结果/判定」回读后进上下文 | 若自写 JSON 状态文件 → A5 不成立 |
| **MiniMax** | 收到上下文包后返回 `demo_project/app/` 的**整文件**改写，落盘的就是提交的 diff；失败时把 pytest 输出回灌再试 | 若补丁是手写的 → A2 不成立 |
| 三者衔接 | MiniMax 改写后**立刻重新导入** seekdb 并重跑来源回查，保证索引、上下文、代码三者不脱节 | — |

## 四、关键取舍

- **整文件返回**而不是 unified diff：避免模型行号漂移与 `git apply` 跨环境失败；补丁由 `difflib` 生成，行号必然对得上。
- **写白名单 `demo_project/app/`**：模型无法改测试与规格，A6 的「测试集前后一致」由代码约束 + `reset.check_untouched()` 双重保证。
- **交付改前状态**：评审首跑看到的是「目标测试失败」，自己执行一遍 `run_sample.sh` 即可复现 rc≠0 → rc=0；改后状态在 `evidence/snapshots/after-task-001/` 与 `evidence/diffs/`。
- **内嵌 PowerContext runtime**：无守护进程，pip 即装；HTTP 后端留作备选，不作为验收路径。
- **推理模型预算**：`MiniMax-M3.1-Flash` 的 `reasoning_tokens` 计入 completion，`MINIMAX_MAX_TOKENS` 需 ≥16000，否则正文字段为空。
