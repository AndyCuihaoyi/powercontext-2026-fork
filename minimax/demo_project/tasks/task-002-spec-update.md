---
id: task-002
title: 调用方想一次读取更多订单，page_size 上界是多少
statement: 调用方希望一次读取更多订单。page_size 的上界是多少？超出上界会怎样？分页参数还有哪些边界约束？
keywords: page_size, upper bound, limit, 分页, 上界, 参数校验, ValueError, MAX_PAGE_SIZE
---

# Task-002 · 规格变更样例（证明上下文不是硬编码）

> 本任务**不要求改代码**，只验证赛题 §4.1「上下文正确」的后半句：
> 「更新样例中的规格并重新导入后，模块应使用更新后的内容，不能始终返回固定答案。」
> 本任务的必要来源清单见 `task-002-checklist.md`。

## 一、规格变更

`specs/order_queries.md` 的 `SPEC-212 · 分页参数上界` 当前写的是：

```text
1. `page_size` 必须满足 `1 <= page_size <= 100`；超过上界时抛出 `ValueError`。
2. 上界为 100。
```

把它改成上界 **200**（一行文本替换，见下方命令），然后重新导入。

## 二、操作步骤

```bash
# 1. 记录变更前的上下文输出
python -m sddctx context --task task-002 --format md --out /tmp/task-002-before.md

# 2. 修改规格（示例：100 → 200）
python scripts/spec_update_demo.py --bound 200

# 3. 重新导入 + 重新生成上下文
python -m sddctx ingest --root demo_project
python -m sddctx context --task task-002 --format md --out /tmp/task-002-after.md

# 4. 还原规格（验证样例必须能回到初始状态）
python scripts/spec_update_demo.py --restore
python -m sddctx ingest --root demo_project
```

## 三、预期结果

| 输出 | `task-002-before.md` | `task-002-after.md` |
|---|---|---|
| 适用规格条目 | `SPEC-212`（正文含 `<= 100`、`上界为 100`） | `SPEC-212`（正文含 `<= 200`、`上界为 200`） |
| 关联代码 | `app/queries.py::MAX_PAGE_SIZE`、`_validate_pagination` | 同上 |
| 关联测试 | `tests/test_regression_queries.py::test_page_size_upper_bound_is_enforced` | 同上 |

判定由 `python scripts/verify_acceptance.py A3b` 自动执行：
after 输出必须包含 `200` 且不再包含 SPEC-212 中被替换的 `<= 100`；before 输出必须包含 `100`。

## 四、注意

- 本样例只改规格文档，不改实现与测试：改后 `MAX_PAGE_SIZE` 仍是 100，这正是「规格与实现出现偏差」的场景，
  模块的职责是把**最新规格**呈现给开发助手，而不是替实现打掩护。
- 重置：`python -m sddctx reset --task task-002`（还原 `specs/` 并重建索引）。
