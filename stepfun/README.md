# StepFun Mini KB · 浏览器端向量化 + seekdb 混合检索

2026 OceanBase 数据库大赛 · AI 生态赛 · 阶跃星辰赛题。

文档与查询的 embedding **全部在浏览器本地计算**（Transformers.js + ONNX Runtime Web），向量、原文和元数据写入 **seekdb**，全文 + 向量混合检索由 seekdb 的 `DBMS_HYBRID_SEARCH` 在库内完成 RRF 融合。默认优先 WebGPU + FP16，设备不支持时自动回退 WebGPU INT8 / WASM INT8，并在界面标注实际后端。

## 快速开始

### 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Linux / macOS（本项目在 Ubuntu + Chromium 140 实测） |
| Node.js | ≥ 20（实测 22.20.0） |
| 浏览器 | Chrome / Edge 最新版；WebGPU 可选，缺失时自动使用 WASM |
| seekdb | 1.4.0 可执行文件（从大赛提供的 seekdb 发行包解压即可）；未在标准路径时用 `SEEKDB_BIN=/path/to/seekdb` 指定 |
| 磁盘 | 模型约 167 MB（FP32+FP16+INT8 合计），另需 node_modules |

### 启动（单链复现）

```bash
cd stepfun
npm install                 # 使用 npmmirror；.npmrc 已关闭 onnxruntime-node 生命周期脚本
npm run db:start            # 启动本地 seekdb，127.0.0.1:2887，数据在 .seekdb/
npm run models:fetch        # 按 models.lock.json 的固定 revision + SHA-256 下载模型
npm run build               # 构建前端并把 ORT WASM 复制到 public/ort
npm start                   # http://127.0.0.1:8797
```

开发模式（Vite HMR + API 双进程）：

```bash
npm run dev                 # 前端 http://127.0.0.1:5173，API http://127.0.0.1:8797
```

`npm run db:stop` / `npm run db:status` 管理本地实例。

### 端口与环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` / `HOST` | `8797` / `127.0.0.1` | 应用 HTTP 端口与监听地址 |
| `SEEKDB_HOST` / `SEEKDB_PORT` | `127.0.0.1` / `2887` | seekdb 连接 |
| `SEEKDB_USER` / `SEEKDB_PASSWORD` / `SEEKDB_DATABASE` | `root` / 空 / `stepfun_kb` | 数据库账号与库名 |
| `SEEKDB_BIN` | 自动探测 | seekdb 可执行文件路径 |
| `STEPFUN_DATA` | `stepfun/.seekdb` | 本地实例数据目录 |
| `HF_ENDPOINT` | 未设置 → hf-mirror → huggingface | 模型下载镜像 |
| `STEPFUN_URL` / `CHROME_PATH` | 本地 8797 / 自动探测 | E2E 与基准的可选覆盖 |
| `BENCH_VARIANTS` | 四个变体 | 逗号分隔，如 `wasm-fp32,wasm-q8` |

### 使用

1. 首次打开会自动创建「我的知识库」集合，也可在左侧新建。
2. 粘贴文本或选择 `.txt` / `.md` 文件，点击「向量化并写入 seekdb」；切块、推理进度实时显示，导入完成后自动刷新索引并做可检索性探测。
3. 输入查询，查看排序结果、原文、分块编号与距离；右上角徽标显示实际后端与精度。
4. 「量化基准」页运行 4 个变体（WASM FP32/INT8、WebGPU FP16/INT8），生成体积、质量与分阶段延迟对比，可下载 JSON。
5. 刷新页面会从会话恢复集合、后端与最近查询；`?backend=wasm` 可强制 WASM。

## 验收项对照

| 题面验收项 | 实现 | 证据 |
|---|---|---|
| 完整流程 | 导入 → 浏览器切块/推理 → seekdb 写入 → 混合检索 → 原文展示 | `evidence/e2e-report.json`、`e2e-02-search.png` |
| 本地推理 | `env.allowRemoteModels=false`，模型/ORT 全部同源静态文件；E2E 记录全部网络请求 | E2E「运行期无外部网络请求」检查（0 个外部请求） |
| 模型量化 | bge-small-zh-v1.5 的 FP32/FP16/INT8 文件，同口径体积与压缩比 + 同一评测集质量 | `evidence/benchmark.json`、本文「模型与量化」 |
| 后端与降级 | WebGPU FP16 → WebGPU INT8 → WASM INT8；UI 徽标 + 降级原因；强制 WASM 可复现 | E2E 实测 WebGPU FP16 被 SwiftShader 拒绝后自动切到 WebGPU INT8；`?backend=wasm` 通过 |
| seekdb 数据层 | 每个集合一张 `c$v2$*` 物理表：`FULLTEXT ... WITH PARSER ik` + `VECTOR KEY ... HNSW`；检索走 `hybridSearch` | E2E 直接查询 `sdk_collections`、`SHOW CREATE TABLE` 与行数 |
| 状态与刷新 | 增量导入、批量 `refresh_index()`、全文/向量双探测、集合/会话持久化、刷新页面恢复 | E2E「增量导入」「会话恢复」检查 |
| 可复现性 | 本文单链命令 + 固定模型 revision/SHA-256 + 本地 seekdb 脚本 | `models.lock.json`、`scripts/*` |

## 架构

```text
┌──────────────────────────── 浏览器 ────────────────────────────┐
│ 文档导入                                                     │
│  文本 ── normalize ── 300 字切块/60 重叠 ── batch=8 ──┐      │
│                                                      ▼      │
│   Transformers.js (bge-small-zh-v1.5 ONNX)                   │
│   WebGPU FP16 → WebGPU INT8 → WASM INT8（自动降级）          │
│                    │ 512 维 CLS + L2 normalize              │
│                    ▼                                         │
│   POST /api/collections/:id/import {chunks, vectors}         │
│   POST /api/collections/:id/search {query, queryVector}      │
│   查询文本 ── 本地向量化 ────────────────────────────────────┘
└──────────────────────────────┬─────────────────────────────────┘
                               ▼
┌──────────────────────── 本地 Node/Express ─────────────────────┐
│ 校验（正文哈希、分块子串、512 维、L2 范数）                     │
│ seekdb-js add / delete / refresh_index / hybridSearch          │
└──────────────────────────────┬─────────────────────────────────┘
                               ▼
┌──────────────────────────── seekdb 1.4.0 ──────────────────────┐
│ sdk_collections + c$v2$<id>（document / embedding / metadata） │
│ FULLTEXT(document) WITH PARSER ik  +  VECTOR KEY HNSW(512)     │
│ DBMS_HYBRID_SEARCH.GET_SQL(...) → 库内 RRF 融合                │
└────────────────────────────────────────────────────────────────┘
```

- 应用层不接收两路候选：`collection.hybridSearch` 由 seekdb-js 生成一条混合检索 SQL，RRF 在数据库内计算。
- 查询清洗只保留 Unicode 字母、数字与空格，候选池 `min(100, max(20, topK×4))`，RRF `rankConstant=60`。

## 模型与量化

| 项 | 值 |
|---|---|
| 模型 | `BAAI/bge-small-zh-v1.5`（中文/英文，512 维） |
| ONNX 转换 | `Xenova/bge-small-zh-v1.5` @ `75c43b069aac4d136ba6bc1122f995fedcfd2781` |
| 池化 | CLS + L2 normalize |
| 完整性 | `models.lock.json` 固定 9 个文件的字节数与 SHA-256 |

| 精度 | 文件 | 体积 | 相对 FP32 压缩比 | 处理方式 |
|---|---|---:|---:|---|
| FP32 | `onnx/model.onnx` | 94,851,877 B（90.5 MiB） | 1.00× | 基线 |
| FP16 | `onnx/model_fp16.onnx` | 47,497,427 B（45.3 MiB） | 2.00× | 仓库提供的 float16 权重，WebGPU 以 FP16 推理 |
| INT8 | `onnx/model_quantized.onnx` | 24,010,842 B（22.9 MiB） | 3.95× | 仓库内 `quantize_config.json` 的动态量化权重，WASM/WebGPU 直接加载 |

量化质量对比使用同一份 24 篇中文语料、22 条标注查询、同一 WASM 后端、同一 seekdb 集合配置，每篇按 300 字/60 重叠切块（25 个分块），文档级指标按标题去重取前 10：

| 变体 | Recall@5 | Recall@10 | nDCG@10 | MRR | 变化 |
|---|---:|---:|---:|---:|---|
| WASM · FP32（基线） | 0.909 | 0.955 | 0.874 | 0.909 | — |
| WASM · INT8 | 0.909 | 0.977 | 0.886 | 0.909 | R@10 +0.022，nDCG +0.012 |
| WebGPU · INT8* | 0.758 | 0.955 | 0.708 | 0.698 | 软件适配器上的补充数据 |
| WebGPU · FP16* | — | — | — | — | SwiftShader 不支持 fp16，未能执行 |

\* 测试机只有 SwiftShader 软件 WebGPU 适配器，不代表真实 GPU 表现；FP16 变体在加载阶段被设备拒绝，正好验证了自动降级路径。

## 性能实测

测试条件：Linux x86_64、HeadlessChrome 140（`--enable-unsafe-webgpu` + SwiftShader）、Node 22.20.0、seekdb 1.4.0、24 篇/25 块、22 条查询、batch=8、topK=10、RRF k=60。延迟为 22 次查询的中位数（P95 见括号），查询前已用 2 条查询预热。

| 变体 | 模型加载 | 预热 | 文档向量化 | 查询向量化 P50/P95 | seekdb 检索 P50/P95 | 端到端 P50/P95 | 首次查询 |
|---|---:|---:|---:|---:|---:|---:|---:|
| WASM · FP32 | 819 ms | 44 ms | 4.73 s（189 ms/块） | 14.4 / 26.3 ms | 7.1 / 9.0 ms | 31.3 / 49.1 ms | 43.1 ms |
| WASM · INT8 | 341 ms | 28 ms | 11.03 s（441 ms/块） | 12.3 / 21.2 ms | 7.9 / 14.9 ms | 31.3 / 38.8 ms | 36.5 ms |
| WebGPU · INT8 | 408 ms | 367 ms | 64.58 s（2583 ms/块） | 594.0 / 670.5 ms | 12.2 / 19.2 ms | 621.2 / 693.8 ms | 651.3 ms |
| WebGPU · FP16 | — | — | — | — | — | — | 设备不支持 fp16 |

补充数据：批量导入 24 篇后只刷新一次索引，WASM 变体刷新 502 ms、WebGPU INT8 刷新 618 ms，刷新后均通过「新文档全文片段 + 向量近邻」双探测；服务端分块写入校验耗时 0.49–7.3 s（与浏览器推理并发时的 CPU 竞争有关）。

**结论与取舍**：

- INT8 把模型从 90.5 MiB 压到 22.9 MiB（3.95×），检索质量不降反升（R@10 0.955 → 0.977）；查询向量化与端到端延迟与 FP32 基本持平，是弱设备/无 GPU 环境的默认选择。
- 本机 SwiftShader 上 WebGPU 的算子由 CPU 软件模拟，推理明显慢于 WASM；应用仍按题面要求优先探测 WebGPU，但保留 `?backend=wasm` 供软件适配器环境强制降级。真实 GPU 上的 FP16/WebGPU 数据需在目标设备复测。
- 优化手段：浏览器内 batch=8 推理、导入阶段 `deferRefresh` 合并为一次 `refresh_index()`、本地模型/ORT 静态资源 + ONNX 长缓存、查询侧仅做一次 embedding 并复用向量。

## seekdb 数据层

每个知识库集合对应一个 seekdb collection，schema 为：

```text
FULLTEXT INDEX (document) WITH PARSER ik, ik_mode="smart"
VECTOR INDEX (embedding) HNSW, dimension=512, distance=cosine
```

物理表由 seekdb-js 管理（`sdk_collections` 记录 `collection_name → collection_id`，数据表为 `c$v2$<collection_id>`），E2E 实际读到的建表语句包含：

```sql
FULLTEXT KEY `idx_fts` (`document`) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart")
VECTOR KEY `idx_vec` (`embedding`) WITH (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG, ...)
```

应用元数据同样存放在 `stepfun_kb` 库：

| 表 | 用途 |
|---|---|
| `stepfun_collections` | 集合名称、seekdb collection 名、模型、维度 |
| `stepfun_documents` | 文档 ID、标题、正文哈希、字数/块数、导入时间、分块前缀 |
| `stepfun_index_state` | 文档/分块数、最近导入/刷新、刷新耗时、验证标记 |
| `stepfun_sessions` | 会话 → 当前集合、后端、精度、最近查询 |

写入与刷新：

1. 以标题归一化哈希生成稳定 `docId`，同标题重复导入时替换旧文档。
2. 每次导入生成随机分块前缀，先批量 `add` 新块，再按 `doc_id` 删除旧块，避免同标题更新后出现旧内容。
3. 默认单文档导入后立即 `refresh_index()`；批量导入使用 `deferRefresh`，全部写完后刷新一次。
4. 刷新后从最新文档抽取独特片段做 `MATCH ... AGAINST` 全文探测，并用其向量做近邻探测，两项都命中才标记 `verified`；同时核对物理行数与元数据块数。
5. 删除文档/集合会清理分块、元数据并刷新索引。

混合检索调用（服务端）：

```js
const result = await collection.hybridSearch({
  query: { whereDocument: { $contains: sanitizedQuery } },
  knn: { queryEmbeddings: [embedding], nResults: candidateK },
  rank: { rrf: { rankWindowSize: candidateK, rankConstant: 60 } },
  nResults: topK,
  include: ['documents', 'metadatas', 'distances'],
});
```

seekdb-js 内部通过 `SET @search_parm` + `DBMS_HYBRID_SEARCH.GET_SQL(...)` 生成并执行融合 SQL，客户端只拿到融合后的结果。

## HTTP API

| 方法/路径 | 说明 |
|---|---|
| `GET /api/health` | seekdb 版本、库、元数据表数量、模型信息 |
| `GET /api/model/status` | 本地模型文件与体积 |
| `GET /api/collections` | 集合列表（含文档/块数、刷新状态） |
| `POST /api/collections` | 创建集合并创建 seekdb collection |
| `GET /api/collections/:id` | 集合详情：文档、索引状态 |
| `DELETE /api/collections/:id` | 删除集合、物理表与元数据 |
| `POST /api/collections/:id/import` | 提交分块 + 向量（可选 `deferRefresh`） |
| `POST /api/collections/:id/refresh` | 刷新索引并验证 |
| `DELETE /api/collections/:id/documents/:docId` | 删除文档并刷新 |
| `POST /api/collections/:id/search` | 查询文本 + 查询向量 → seekdb RRF |
| `GET/PATCH /api/sessions/:id` | 会话读取 / 集合、后端、最近查询更新 |

## 测试与证据

```bash
npm run test:e2e    # Playwright：导入/检索/DB 索引/增量刷新/会话/强制 WASM/外部请求
npm run benchmark   # 四个变体的体积、质量、分阶段延迟（约 2 分钟）
```

相关文件：

| 文件 | 内容 |
|---|---|
| `evidence/e2e-report.json` | 逐步检查、后端状态、DB 证据、外部请求、清理结果 |
| `evidence/benchmark.json` | 浏览器实际运行产生的原始基准数据 |
| `evidence/benchmark-report.json` | 基准检查与失败原因 |
| `evidence/e2e-01-ready.png` … `e2e-04-forced-wasm.png` | UI 截图 |
| `evidence/bench-01-panel.png` / `bench-02-results.png` | 基准页截图 |

复现注意：

- Playwright 会优先自动探测 Playwright 缓存中的完整版 Chromium（headless shell 没有 WebGPU），找不到时退回 Playwright 默认浏览器；可用 `CHROME_PATH` 显式指定。首次跑测试前如缺浏览器，执行 `npx playwright install chromium`。
- `npm install` 通过 `.npmrc` 设置 `ignore-scripts=true`（跳过 `onnxruntime-node` 原生二进制安装，浏览器推理不需要）；E2E/基准的数据库校验使用 `SEEKDB_HOST/PORT/USER/PASSWORD/DATABASE`，默认与本应用一致。
- 模型下载（`npm run models:fetch`）是一次性准备步骤，不计入运行时；基准中的“加载”指浏览器从同源静态文件加载模型的时间。
- 本机 SwiftShader 不支持 FP16，因此基准中 FP16 变体以失败记录呈现；这不影响 WASM / WebGPU INT8 的对比。请在具备真实 GPU 的机器补测 FP16 数据。
- 基准临时集合命名为 `基准-*`，结束后自动删除；E2E 只删除自己创建的 `端到端验收-*` 集合。

## 目录

```text
stepfun/
├── index.html                  # 单页 UI（知识库 / 量化基准 / 技术说明）
├── src/
│   ├── main.ts                 # UI 交互、导入、检索、会话、基准驱动
│   ├── chunker.ts              # 归一化、句段切块、embedding 输入
│   ├── api.ts                  # 类型化 HTTP 客户端
│   ├── embedding/backend.ts    # WebGPU 探测、降级链、状态
│   ├── embedding/embedder.ts   # Transformers.js pipeline、batch、warmup
│   ├── bench/run.ts            # 基准流程与质量指标
│   └── types.ts
├── server/
│   ├── index.mjs               # Express 路由、静态托管、COOP/COEP
│   ├── db.mjs                  # seekdb 客户端、元数据表、schema
│   ├── import.mjs              # 校验、写入、刷新、双探测
│   ├── search.mjs              # 清洗、hybridSearch、RRF
│   ├── text.mjs                # 查询清洗与片段探测
│   └── config.mjs
├── scripts/                    # db / dev / fetch-models / prepare-assets
├── tests/                      # e2e.mjs、benchmark.mjs、lib/common.mjs
├── public/sample-corpus/       # 24 篇文档 + 22 条标注查询
├── models.lock.json            # 模型文件字节数 + SHA-256
└── README.md / TECH_NOTES.md
```

## 红线自查

- 无云端推理：模型、tokenizer、ORT WASM 均为同源静态文件，`allowRemoteModels=false`；E2E 断言运行期 0 个外部 HTTP 请求。
- 无服务端预计算/回放：服务端只做向量校验、持久化与检索，不生成向量，也没有预置答案。
- 存储与检索均使用 seekdb：向量、原文、元数据都在 seekdb collection；应用元数据表也建在同一 seekdb 库。
- 混合检索在库内完成：客户端只提交查询文本 + 查询向量，不接收/拼接两路候选。
- 不伪造数据：性能与质量数字来自 `npm run benchmark` 的实际运行 JSON；模型权重不入库，按固定 revision + SHA-256 下载。

## 已知限制

- 本机只有 SwiftShader 软件 WebGPU，FP16 无法执行，WebGPU 延迟不代表真实 GPU；真实设备数据待补测。
- 应用面向单用户本地知识库，未实现鉴权、多租户与并发写入冲突控制。
- 查询清洗会过滤标点与非字母数字字符；对符号密集型查询的召回有限。
- 模型下载依赖 HF 镜像可达性；离线部署可将 `public/models` 与 `public/ort` 一并打包。

模型、Transformers.js、seekdb 分别遵循其上游许可；示例语料为本项目自建，仅用于演示与评测。
