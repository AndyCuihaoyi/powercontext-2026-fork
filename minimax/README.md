# 规有所依 · SDD 上下文管理系统（MiniMax × seekdb × PowerContext）

给 AI 开发助手用的上下文模块：把业务工程的**规格 / 代码 / 测试**导入 seekdb 建全文索引，
按开发任务检索出「适用规格 + 待改代码 + 验证测试 + 任务状态」的上下文包，
交给 **MiniMax** 完成一次真实代码修改，并用 **PowerContext** 保存、跨进程复用任务状态。

- 调用入口：CLI（`python -m sddctx …`），不需要守护进程或额外端口（seekdb 除外）。
- 验证样例：`demo_project/`（纯标准库 Python + pytest），任务 `task-001`。
- 六项必做项的自动自检：`python scripts/verify_acceptance.py all`（口径见 `docs/acceptance.md`）。

## 1. 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.11+ | 模块与样例只用标准库 + 下列三个包 |
| seekdb | 1.4.0 | MySQL 协议兼容；`scripts/start_seekdb.sh` 自动找二进制 |
| powercontext | 1.4.1 `[builtin]` | 内嵌 runtime + SQLite 持久化，无需起服务 |
| pymysql / pytest | 见 `requirements.txt` | 连接 seekdb / 跑样例测试 |
| MiniMax | OpenAI 兼容 `/chat/completions` | 只有「真实改代码」这一步需要 API Key |

## 2. 快速开始（三步）

```bash
bash scripts/setup.sh          # ① 建虚拟环境装依赖 + 起 seekdb（本样例专用 127.0.0.1:2893）+ 建库建表
bash scripts/init_data.sh      # ② 导入工程资料 + 生成上下文包（离线，可反复执行）
bash scripts/run_sample.sh     # ③ 跑完整闭环：改前失败 → MiniMax 改写 → 改后全绿 → 六项自检 → 回到改前
```

`run_sample.sh` 结束时仓库回到**改前状态**（这是验证样例的设计：评审能自己复现「改前失败 → 改后通过」）。
所有中间结果落在 `evidence/`。

## 3. 配置

全部走环境变量（`cp .env.example .env` 后填写；`.env` 已被 `.gitignore` 排除，**不要提交密钥**）。

| 变量 | 默认值 | 用途 |
|---|---|---|
| `MINIMAX_API_KEY` | 空 | 必填才能真实调用；空则 `agent` 拒绝发请求 |
| `MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | 国内 Key 用 `https://api.minimaxi.com/v1`；**用错站点会返回 401 `invalid api key (2049)`** |
| `MINIMAX_MODEL` | `MiniMax-M2` | 本项目验证用的是 `MiniMax-M3.1-Flash`（推理模型，需把 `MINIMAX_MAX_TOKENS` 调大，如 16000） |
| `SDDCTX_SEEKDB_PORT` | `2893` | 本样例专用实例端口，避开 2881/2885 等已在用的端口 |
| `SDDCTX_SEEKDB_DATABASE` | `sdd_eco` | 独立库名，不动其它作品的数据 |
| `SDDCTX_FTS_PARSER` | `ik` | 中文全文解析器；不可用时自动回退默认解析器 |
| `SDDCTX_ROOT` / `SDDCTX_DEMO_ROOT` / `SDDCTX_RUNTIME_DIR` / `SDDCTX_EVIDENCE_DIR` | 项目内路径 | 换机器/换目录时用 |

## 4. 命令一览（输入 → 输出）

| 命令 | 输入 | 输出 |
|---|---|---|
| `python -m sddctx ingest [--root demo_project]` | `demo_project/{specs,app,tests,tasks}` | seekdb `sdd_documents` / `sdd_items` / `sdd_tasks` 行数；`evidence/db/{schema,counts}.md` |
| `python -m sddctx context --task task-001 [--format md\|json\|both] [--with-state] [--limit spec=8]` | 任务 ID（读 `sdd_tasks`） | 上下文包 `evidence/context/task-001.{md,json}`：适用规格 / 待改代码 / 验证测试 / 任务状态，每条带 `path + 行区间 + item_id + sha8` |
| `python -m sddctx state save --task task-001 [--auto] [--record kind=文本]` | 上下文包 + seekdb 计数 + 测试日志 | PowerContext `atomic_memory` 记录（`runtime/powercontext/state.db`）、`evidence/powercontext/state-write.md` |
| `python -m sddctx state show --task task-001` | 任务关键词 | **新进程**读回的记录列表 + 按关键词排序命中，写 `evidence/powercontext/state-restart-read-task-001.md` |
| `python -m sddctx agent --task task-001 [--rounds 2] [--replay] [--dry-run] [--keep-changes]` | 上下文包（+ 上一轮失败输出） | MiniMax 请求/响应与用量记录 `evidence/minimax/task-001.jsonl`；实际写文件；`evidence/diffs/task-001.patch`；`evidence/test-logs/after-*.log` |
| `python -m sddctx test --task task-001 [--label before\|after]` | `demo_project/tests/` | 目标 + 回归 + 全量三段 pytest 日志与退出码 |
| `python -m sddctx reset --task task-001 [--state] [--capture-initial]` | 初始快照 | 实现/规格/测试回到改前；`--state` 额外清空 PowerContext 与 seekdb 记录 |
| `python -m sddctx verify [A1 A2 A3 A3b A4 A5 A6\|all]` | `evidence/` + seekdb + PowerContext | 逐项 PASS/FAIL 与 `evidence/acceptance-check.md` |
| `python scripts/spec_update_demo.py --bound 200` / `--restore` | `SPEC-212` 上界 | 改规格 → 重新导入（演示「规格更新后上下文用新内容」） |

## 5. 三套技术各自干了什么

| 技术 | 承担的作用 | 代码位置 | 怎么核对 |
|---|---|---|---|
| seekdb 1.4 | 存工程资料 + `FULLTEXT` 索引；上下文**只由 SQL 查询结果构造**；每次查询写 `sdd_query_log` | `sddctx/store.py`、`sddctx/ingest.py`、`sddctx/retrieve.py` | `verify_acceptance.py A4`、`evidence/db/queries.md` |
| PowerContext 1.4.1 | `atomic_memory` 保存「已完成 / 待办 / 验证结果 / 判定」到新进程可读回的 SQLite | `sddctx/state.py` | `verify_acceptance.py A5`、`evidence/powercontext/` |
| MiniMax | 收到上下文包 → 返回 `demo_project/app/` 的整文件改写 → 落盘 → 跑测试；失败时带 pytest 输出重试（≤2 轮） | `sddctx/minimax_client.py`、`sddctx/agent.py` | `verify_acceptance.py A2`、`evidence/minimax/task-001.jsonl` |

检索用 6 路信号做 RRF 融合：`fulltext`（`MATCH…AGAINST`）、`keyword`（LIKE 兜底中英混排）、
`applies`（规格 `Applies-to` ↔ 代码符号的结构关联）、`referencers`（测试引用了哪些符号）、
`sibling`（同一规格文件的其它条款）、`coverage`（保证每个测试文件至少一条）。

## 6. 目录

```
minimax/
├── README.md          # 运行说明（依赖版本、配置、数据初始化、调用入口、测试命令、已知限制）
├── TECH_NOTES.md      # 一页技术说明：模块结构、上下文选择方式、技术分工
├── DEVLOG.md          # 技术使用记录：MiniMax 调用、seekdb 查询留痕、PowerContext 状态复用
├── docs/acceptance.md # 六项必做项逐条对照（判据 / 复核命令 / 证据文件 / 实测）
├── sddctx/                              # 模块源码（CLI 入口 ingest/context/state/agent/test/reset/verify）
├── demo_project/                        # 验证样例业务工程（交付时处于「改前」状态）
│   ├── specs/  app/  tests/  tasks/     # 规格 / 实现 / 测试 / 任务陈述（*-checklist.md 只给评审核对，不入索引）
├── scripts/                             # setup / start_seekdb / init_data / run_sample / verify_acceptance / spec_update_demo
├── evidence/                            # 上下文包、开发记录、diff、测试日志、快照、状态与 SQL 证据
├── requirements.txt  .env.example  .gitignore
└── runtime/                             # seekdb 数据目录 + PowerContext SQLite（不入库）
```

对应题面「提交材料」：完整源码 `sddctx/` + `demo_project/` + `scripts/`；运行说明本文；验证样例 `demo_project/`
（任务描述、有效规格、初始数据、操作步骤、预期结果、重置方法齐备）；代码与测试 `evidence/{diffs,snapshots,test-logs}`；
技术使用记录 `DEVLOG.md` + `evidence/{minimax,db,powercontext}`；一页技术说明 `TECH_NOTES.md`。

## 7. 已知限制

- `agent` 真实调用需要 `MINIMAX_API_KEY`；无 Key 时 `--replay` 只能**复现**已记录的模型输出，不能替代真实参与（README 与 `docs/acceptance.md` 都明确标注）。
- seekdb FULLTEXT 对纯中文规格依赖 `ik` 解析器；不可用时回退默认解析器，并用英文 ID + `Keywords` 字段兜底召回。
- PowerContext 走 pip 的 `powercontext[builtin]` 内嵌 runtime（SQLite）；HTTP 后端不是本题的必需路径。
- 样例业务工程刻意最小化（纯标准库、无网络、无框架），保证任意 Python 3.11+ 环境能复现。
- `import powercontext` 时上游 jieba 会打印一条 `SyntaxWarning: invalid escape sequence`，与本模块无关，不影响功能。
