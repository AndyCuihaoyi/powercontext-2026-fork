# StepFun Mini KB · 一页技术说明

浏览器端 embedding + seekdb 库内混合检索的迷你知识库。所有推理在本机浏览器完成，向量、原文、元数据只写入 seekdb。

## 1. 模型与量化

- **模型**：`BAAI/bge-small-zh-v1.5`（512 维，CLS + L2 normalize），ONNX 转换版 `Xenova/bge-small-zh-v1.5`，固定 revision `75c43b06…`；9 个文件的字节数与 SHA-256 见 `models.lock.json`。
- **INT8**：使用上游模型仓库的 `onnx/model_quantized.onnx`（`quantize_config.json` 动态量化），WASM/WebGPU 直接加载。
- **FP16**：使用上游模型仓库的 `onnx/model_fp16.onnx`（float16 权重），WebGPU 推理；设备不支持时自动回退 INT8。

| 精度 | 文件体积 | 压缩比 |
|---|---:|---:|
| FP32 | 90.5 MiB | 1.00× |
| FP16 | 45.3 MiB | 2.00× |
| INT8 | 22.9 MiB | 3.95× |

**质量（相同 24 篇语料、25 块、22 条标注查询、相同 WASM 后端与 seekdb 配置，文档级按标题去重前 10）**

| 变体 | Recall@5 | Recall@10 | nDCG@10 | MRR |
|---|---:|---:|---:|---:|
| WASM FP32 | 0.909 | 0.955 | 0.874 | 0.909 |
| WASM INT8 | 0.909 | 0.977 | 0.886 | 0.909 |

INT8 压缩 3.95×，R@10 +0.022、nDCG@10 +0.012；FP16 因本机 SwiftShader 不支持 fp16 未能执行，只报告体积与压缩比，真实 GPU 需补测。原始数据：`evidence/benchmark.json`。

## 2. 端侧运行与后端选择

- 运行时：`@huggingface/transformers@3.7.2` + ONNX Runtime Web；模型、tokenizer、ORT WASM 均为同源静态资源，`allowRemoteModels=false`，运行期不访问云端推理服务。
- 选择链：`WebGPU FP16 → WebGPU INT8 → WASM INT8`；`?backend=wasm` 强制 WASM。右上角徽标显示实际后端/精度，降级原因写入徽标 title 与提示条。
- 实测（HeadlessChrome 140 + SwiftShader）：WebGPU FP16 加载被拒（`does not support fp16`）后自动切到 WebGPU INT8；强制 WASM 后核心检索正常。E2E 断言 UI 标注、实际后端与 0 个外部请求。
- 软件适配器上 WebGPU 算子由 CPU 模拟，推理慢于 WASM（见第 4 节）；真实 GPU 上默认仍优先 WebGPU。

## 3. seekdb 使用

- 连接：seekdb 1.4.0 本地 server（`127.0.0.1:2887`，库 `stepfun_kb`），Node 侧通过 `seekdb@1.4.0` 接入；`scripts/db.mjs` 一键启停。
- 每个集合一张 seekdb collection：`FULLTEXT(document) WITH PARSER ik`（smart）+ `VECTOR KEY(embedding) HNSW, 512 维, cosine`；向量、原文、元数据（doc_id、标题、块号等）同表存储。
- 混合检索：服务端只提交清洗后的查询文本与浏览器生成的查询向量，调用 `collection.hybridSearch`；seekdb-js 生成 `DBMS_HYBRID_SEARCH.GET_SQL(...)` 并在库内完成 RRF（k=60，候选 `min(100,max(20,topK×4))`）。客户端不取两路候选、不做融合。
- 增量与刷新：标题哈希生成稳定 docId；写入使用随机分块前缀后清理旧块；批量导入 `deferRefresh`，结束后一次 `refresh_index()`；刷新后用新文档独特片段做全文 `MATCH` + 向量近邻双探测，核对物理表行数与元数据块数后才标记 verified。E2E 直接读取 `sdk_collections` 映射、`SHOW CREATE TABLE` 与行数验证。
- 状态：`stepfun_collections / documents / index_state / sessions` 四张元数据表；集合切换、后端与最近查询写入会话，页面刷新后恢复。

## 4. 状态管理与性能

- 导入：浏览器切块（300 字/60 重叠）→ batch=8 推理 → 服务端校验（正文哈希、分块子串、512 维、L2 范数）→ 批量写入。
- 优化：批量 refresh 代替逐篇刷新；本地模型与 ORT 长缓存；查询只做一次 embedding；会话复用集合与后端状态。
- 测试条件：24 篇/25 块、22 条查询、topK=10、RRF k=60、batch=8；查询前 2 条预热，报告 22 次的中位数/P95。设备为 Linux x86_64、HeadlessChrome 140、SwiftShader、seekdb 1.4.0。
- 模型下载由 `npm run models:fetch` 按固定 revision + SHA-256 一次性完成（全部精度约 167 MB），属于准备步骤；下表的“加载”是浏览器从同源静态文件加载所选精度模型的时间。

| 变体 | 加载 | 文档向量化 | 查询向量化 P50/P95 | seekdb P50/P95 | 端到端 P50/P95 | 首次查询 |
|---|---:|---:|---:|---:|---:|---:|
| WASM FP32 | 819 ms | 4.73 s | 14.4 / 26.3 ms | 7.1 / 9.0 ms | 31.3 / 49.1 ms | 43.1 ms |
| WASM INT8 | 341 ms | 11.03 s | 12.3 / 21.2 ms | 7.9 / 14.9 ms | 31.3 / 38.8 ms | 36.5 ms |
| WebGPU INT8 | 408 ms | 64.58 s | 594 / 671 ms | 12.2 / 19.2 ms | 621 / 694 ms | 651 ms |

批量导入 24 篇后单次刷新 502 ms（WASM）/ 618 ms（WebGPU INT8），均通过双探测。INT8 与 FP32 端到端持平且质量更高；SwiftShader 上的 WebGPU 数据仅用于验证降级链，不代表真实 GPU。原始数据与复现命令见 `evidence/benchmark.json`、`README.md`。
