# demo_project · 验证样例业务工程

一个刻意最小化的订单查询与汇总服务：纯标准库 Python + pytest，任何 Python 3.11+ 环境都能跑，
不依赖网络、不依赖数据库、不依赖 Web 框架。它是**上下文模块的输入**，也是**代码修改的被作用对象**。

```text
demo_project/
├── specs/          规格事实来源（SDD 的 spec），每条以 `### SPEC-<id>` 开头
│   ├── order_queries.md   SPEC-201 / 202 / 205 / 212
│   ├── reporting.md       SPEC-301 / 302
│   └── pricing.md         SPEC-101 / 102 / 103
├── app/            实现
│   ├── repository.py      Order 与固定样例数据
│   ├── queries.py         list_orders（状态过滤、分页、时间窗口）
│   ├── reporting.py       summarize（汇总口径）
│   └── pricing.py         apply_discounts（与本次任务无关，用于回归范围控制）
├── tests/
│   ├── test_target_task_001.py        目标功能测试（SPEC-205）
│   ├── test_regression_queries.py     回归：SPEC-201 / 202 / 212
│   ├── test_regression_reporting.py   回归：SPEC-301 / 302
│   └── test_regression_pricing.py     回归：SPEC-101 / 102 / 103
└── tasks/          任务定义与评审核对清单
    ├── task-001.md / task-001-checklist.md
    └── task-002-spec-update.md / task-002-checklist.md
```

## 规格文件的机器可读约定

`specs/*.md` 中每条规格写成：

```markdown
### SPEC-205 · 标题

- Status: Active | Draft | Deprecated
- Applies-to: `app/queries.py::list_orders`, ...
- Keywords: 逗号分隔的检索关键词

规则：条目正文……
```

`sddctx/ingest.py` 按 `### SPEC-` 切块，一条规格 = 一条索引记录（保留原始行区间，便于回查）。

## 当前状态（重要）

`app/queries.py` 与 `app/reporting.py` 处于 **SPEC-205 未实现** 的状态：

```bash
python -m pytest demo_project/tests            # 7 failed（目标测试）, 22 passed（回归）
python -m pytest demo_project/tests -k regression   # 22 passed
```

这是刻意设计的：验证样例必须从「目标行为尚未实现」的初始状态开始，
才能证明「同一组目标功能测试修改前失败、修改后通过」（赛题 §4.1 第 6 项）。
`python -m sddctx reset --task task-001` 可随时回到该状态。
