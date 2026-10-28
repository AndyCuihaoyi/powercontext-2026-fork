# 规格：订单查询（Order Queries）

> 本文件是 SDD 规格事实来源之一。每条规格以 `### SPEC-<id>` 开头，条目 ID 全局唯一。
> `Status: Active` 表示当前必须成立；`Status: Draft` 表示尚未生效。
> 上下文库按条目切块导入，条目正文与关键词都会参与检索。

### SPEC-201 · 按状态筛选订单

- Status: Active
- Applies-to: `app/queries.py::list_orders`
- Keywords: status filter, pending, shipped, completed, cancelled, ValueError

规则：

1. `list_orders(orders, status=None, ...)` 传入状态时只返回该状态的订单；`status=None` 表示不按状态过滤。
2. 状态取值集合固定为 `pending`、`shipped`、`completed`、`cancelled`。
3. 传入未知状态时抛出 `ValueError`，且不得返回任何数据（不得静默返回全量）。

### SPEC-202 · 分页语义

- Status: Active
- Applies-to: `app/queries.py::list_orders`
- Keywords: pagination, page, page_size, slice, ValueError

规则：

1. `page` 从 1 开始，`page_size` 是每页条数；返回顺序为「过滤 → 排序 → 分页」。
2. 请求页超出数据范围时返回空列表，不抛异常、不重复返回最后一页。
3. `page < 1` 或 `page_size < 1` 时抛出 `ValueError`。

### SPEC-205 · 按创建时间窗口筛选订单

- Status: Active
- Applies-to: `app/queries.py::list_orders`, `app/reporting.py::summarize`, `app/repository.py::Order`
- Keywords: since, created_at, time window, inclusive boundary, ordering, sort key, stable order

规则：

1. `list_orders(orders, status=None, since=None, page=1, page_size=20)` 的 `since` 接受 `YYYY-MM-DD`
   字符串；给出 `since` 时只返回 `created_at >= since` 的订单，**边界包含当天**（`created_at == since` 必须保留）。
2. `since=None` 时不启用时间过滤，其余行为与 SPEC-201/SPEC-202 完全一致（向后兼容，不得改变既有结果集合）。
3. 排序键固定为 `(created_at 升序, order_id 升序)`；同一 `created_at` 的多条记录按 `order_id` 升序输出，
   不得依赖输入列表的插入顺序。
4. 过滤顺序为：状态过滤 → 时间窗口过滤 → 排序 → 分页。分页必须在过滤与排序之后进行。
5. `reporting.summarize(orders, status=None, since=None)` 必须接受与 `list_orders` 相同的时间窗口参数，
   并且只统计过滤后的集合。
6. `since` 不是合法 `YYYY-MM-DD` 时抛出 `ValueError`，与 SPEC-201 的未知状态处理保持一致的错误语义。
7. 兼容性：本条不改变 SPEC-201 的状态取值、SPEC-202 的分页边界与错误行为。

### SPEC-212 · 分页参数上界

- Status: Active
- Applies-to: `app/queries.py::list_orders`
- Keywords: page_size upper bound, limit, 100, ValueError, bounds

规则：

1. `page_size` 必须满足 `1 <= page_size <= 100`；超过上界时抛出 `ValueError`。
2. 上界为 100。任何调用方需要更大的读取批量时应分页多次请求，而不是放宽本条上界。
