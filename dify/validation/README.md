# 验证样例 · 记忆当铺

`run_e2e.py` 通过 **Dify Service API**（不是直接调网关）跑完整玩家流程，用来证明
「Dify 编排 + seekdb 账本 + PowerContext 长期记忆」是一条真实链路。

## 前置

1. 按 `../deploy/source-deploy.md` 起好 seekdb、Dify、PowerContext、网关。
2. 用 `../scripts/publish_app.py` 导入并发布 DSL，拿到 Service API Key。
3. 网关 `.env` 已填同一个 `DIFY_API_KEY`，且 `/api/health` 的 `dify_proxy` 为 `true`。

```bash
cd dify
export DIFY_API_KEY=app-xxxx        # 不要把真实 Key 写进仓库
python3 validation/run_e2e.py --cleanup
```

## 场景与预期

每次运行会新建玩家（默认 `验证员HHMMSS`），避免历史数据影响；`--cleanup` 结束时清空该玩家的当票并轮换记忆作用域。

| # | 步骤 | 输入 | 预期不变量 |
|---|---|---|---|
| 1 | 网关健康 | — | `seekdb=ok`、`powercontext=ok`、`fulltext` 为 true（IK 可用时） |
| 2 | 典当 | `action=典当`，一段含「漫画/数学」的记忆 | 返回 `当票编号 Pxxx-yyy` 与 `估价 NNN 回忆币` |
| 3 | 长期记忆召回 | `POST /api/recall` 同玩家、关键词「漫画」 | 账本命中该票号，且 `【长期记忆】` 段非空、无「写入失败」 |
| 4 | 赎回检索 | `action=赎回`，内容「漫画」 | 回答中出现步骤 2 的票号 |
| 5 | 确认赎回 | `action=确认赎回`，内容为票号 | 返回「赎回回执」，账本状态改为 `redeemed` |
| 6 | 重复确认 | 同票号再确认一次 | 返回「已经赎回」，不重复写账 |
| 7 | 查账 | `action=查账` | 账本列出该票号 |

**通过标准**：8 个步骤全部 `PASS`（含 cleanup，若启用），脚本退出码 0。
每次运行把完整回答写入 `evidence/e2e-<时间>.json` 和同名 `.md`。

## 模型模式

- `LLM_MODE=mock`：网关用确定性规则生成当票文案，离线可复跑，步骤 2 的票号/估价由真实账本逻辑产生。
- `LLM_MODE=openai`：网关转发到任意 OpenAI 兼容模型，用来验证真实创作质量；不变量不变，
  但「老板批注」的措辞会变化，因此断言只检查结构字段，不比对整段文本。

## 补充证据

```bash
python3 scripts/verify_powercontext.py        # scope / remember / 中文检索
python3 scripts/verify_seekdb.py              # Dify 172 表 + 当铺表 + IK 索引 + MATCH 探测
```

体验页由网关 `/` 提供；`evidence/ui/01-empty.jpg` … `04-ledger.jpg` 是 Chromium
无头模式跑通「典当 → 拿票去赎回 → 确认赎回 → 查账」后的截图。
