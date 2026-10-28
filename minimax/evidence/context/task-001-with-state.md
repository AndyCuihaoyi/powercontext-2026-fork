# 上下文包 · task-001

> 由 `python -m sddctx context --task task-001` 生成。
> 每条来源都来自 seekdb 查询结果，并逐条回读磁盘行区间核对内容摘要。

## 一、任务（输入只有 front matter）

- 标题：让 since 时间窗口真正作用于订单查询与汇总
- 陈述：订单查询与汇总需要按创建时间窗口 since 过滤（边界包含当天），过滤后再排序与分页，排序键为 created_at 升序、order_id 升序；summarize 只统计过滤后的集合；非法 since 抛 ValueError。状态筛选与分页的既有行为必须保持不变。
- 关键词：since, created_at, time window, inclusive boundary, ordering, sort key, stable order, pagination, summarize, 时间窗口, 排序, 分页, 汇总
- 来源：`seekdb:sdd_tasks` → `demo_project/tasks/task-001.md` · 回查 ✅

## 二、检索信号

- 查询词（23）：since, created_at, order_id, summarize, ValueError, time, window, inclusive, boundary, ordering, sort, key, stable, order, pagination, 时间窗口真正作用于订单查询与汇总, 订单查询与汇总需要按创建时间窗口, 边界包含当天, 过滤后再排序与分页, 排序键为, 只统计过滤后的集合, 状态筛选与分页的既有行为必须保持不变, 时间窗口
- 各路信号：{"spec": ["fulltext", "keyword", "sibling"], "code": ["fulltext", "keyword", "applies"], "test": ["fulltext", "keyword", "referencers"]}
- 规格 Applies-to 展开：app/queries.py::list_orders, app/reporting.py::summarize, app/repository.py::Order, app/pricing.py::apply_discounts
- 每类上限：{"spec": 8, "code": 8, "test": 8}

## 三、适用规格（8 条）

### SPEC-205

- 来源：`demo_project/specs/order_queries.md:31-49`
- 索引记录：`spec:SPEC-205` · 内容摘要 `sha256:f9e8630e` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03687`
- Applies-to：`app/queries.py::list_orders, app/reporting.py::summarize, app/repository.py::Order`
- Status：Active

```text
SPEC-205 按创建时间窗口筛选订单
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
```

### SPEC-301

- 来源：`demo_project/specs/reporting.md:3-12`
- 索引记录：`spec:SPEC-301` · 内容摘要 `sha256:c91f0ffa` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03614`
- Applies-to：`app/reporting.py::summarize`
- Status：Active

```text
SPEC-301 汇总口径
### SPEC-301 · 汇总口径

- Status: Active
- Applies-to: `app/reporting.py::summarize`
- Keywords: summary, count, total_cents, average_cents, by_status

规则：`summarize` 返回字典，至少包含 `count`（订单数）、`total_cents`（金额合计）、
`average_cents`（`total_cents // count`，`count == 0` 时为 0）、`by_status`（按状态分组计数，
只包含出现过的状态）。汇总对象必须是经过同一套过滤条件筛出的集合，不得混入被过滤掉的订单。
```

### SPEC-201

- 来源：`demo_project/specs/order_queries.md:7-18`
- 索引记录：`spec:SPEC-201` · 内容摘要 `sha256:f2b72829` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.0359`
- Applies-to：`app/queries.py::list_orders`
- Status：Active

```text
SPEC-201 按状态筛选订单
### SPEC-201 · 按状态筛选订单

- Status: Active
- Applies-to: `app/queries.py::list_orders`
- Keywords: status filter, pending, shipped, completed, cancelled, ValueError

规则：

1. `list_orders(orders, status=None, ...)` 传入状态时只返回该状态的订单；`status=None` 表示不按状态过滤。
2. 状态取值集合固定为 `pending`、`shipped`、`completed`、`cancelled`。
3. 传入未知状态时抛出 `ValueError`，且不得返回任何数据（不得静默返回全量）。
```

### SPEC-202

- 来源：`demo_project/specs/order_queries.md:19-30`
- 索引记录：`spec:SPEC-202` · 内容摘要 `sha256:678b66d6` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03545`
- Applies-to：`app/queries.py::list_orders`
- Status：Active

```text
SPEC-202 分页语义
### SPEC-202 · 分页语义

- Status: Active
- Applies-to: `app/queries.py::list_orders`
- Keywords: pagination, page, page_size, slice, ValueError

规则：

1. `page` 从 1 开始，`page_size` 是每页条数；返回顺序为「过滤 → 排序 → 分页」。
2. 请求页超出数据范围时返回空列表，不抛异常、不重复返回最后一页。
3. `page < 1` 或 `page_size < 1` 时抛出 `ValueError`。
```

### SPEC-302

- 来源：`demo_project/specs/reporting.md:13-20`
- 索引记录：`spec:SPEC-302` · 内容摘要 `sha256:08f74706` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03495`
- Applies-to：`app/reporting.py::summarize`
- Status：Active

```text
SPEC-302 空集合汇总
### SPEC-302 · 空集合汇总

- Status: Active
- Applies-to: `app/reporting.py::summarize`
- Keywords: empty result, zero count, no division

规则：过滤后为空时返回 `count == 0`、`total_cents == 0`、`average_cents == 0`、`by_status == {}`，
不得抛除零异常。
```

### SPEC-212

- 来源：`demo_project/specs/order_queries.md:50-59`
- 索引记录：`spec:SPEC-212` · 内容摘要 `sha256:52ee4568` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03494`
- Applies-to：`app/queries.py::list_orders`
- Status：Active

```text
SPEC-212 分页参数上界
### SPEC-212 · 分页参数上界

- Status: Active
- Applies-to: `app/queries.py::list_orders`
- Keywords: page_size upper bound, limit, 100, ValueError, bounds

规则：

1. `page_size` 必须满足 `1 <= page_size <= 100`；超过上界时抛出 `ValueError`。
2. 上界为 100。任何调用方需要更大的读取批量时应分页多次请求，而不是放宽本条上界。
```

### SPEC-103

- 来源：`demo_project/specs/pricing.md:21-27`
- 索引记录：`spec:SPEC-103` · 内容摘要 `sha256:73b5174d` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03448`
- Applies-to：`app/pricing.py::apply_discounts`
- Status：Active

```text
SPEC-103 优惠券与下限
### SPEC-103 · 优惠券与下限

- Status: Active
- Applies-to: `app/pricing.py::apply_discounts`
- Keywords: coupon, floor, non-negative, total

规则：优惠券面额在最后抵扣；抵扣后总额不得小于 0 分（低于 0 时取 0）。未知券码抛出 `ValueError`。
```

### SPEC-102

- 来源：`demo_project/specs/pricing.md:13-20`
- 索引记录：`spec:SPEC-102` · 内容摘要 `sha256:bc377fdf` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.0341`
- Applies-to：`app/pricing.py::apply_discounts`
- Status：Active

```text
SPEC-102 满减
### SPEC-102 · 满减

- Status: Active
- Applies-to: `app/pricing.py::apply_discounts`
- Keywords: threshold discount, 10000, 1500, amount off

规则：会员折扣之后的小计 `>= 10000` 分（即 100 元）时再减 `1500` 分；不足门槛不减。满减只应用一次。
```

## 四、需要修改的代码（8 处）

### list_orders

- 来源：`demo_project/app/queries.py:13-28`
- 索引记录：`code:queries:list_orders` · 内容摘要 `sha256:6afb3802` · 回查 ✅
- 命中信号：fulltext, keyword, applies · RRF `0.05255`

```text
def list_orders(
    orders: Sequence[Order] | None = None,
    status: str | None = None,
    since: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[Order]:
    """按状态与时间窗口筛选、排序并分页返回订单。"""

    rows = _filter_orders(orders, status=status, since=since)
    rows.sort(key=lambda order: (order.created_at, order.order_id))

    _validate_pagination(page, page_size)
    start = (page - 1) * page_size
    return rows[start : start + page_size]
```

### Order

- 来源：`demo_project/app/repository.py:12-35`
- 索引记录：`code:repository:Order` · 内容摘要 `sha256:e20136f2` · 回查 ✅
- 命中信号：fulltext, keyword, applies · RRF `0.05065`

```text
class Order:
    order_id: str
    customer_id: str
    status: str
    created_at: str  # YYYY-MM-DD
    total_cents: int


# 刻意不按 created_at 或 order_id 排序：SPEC-205 要求输出顺序稳定，
# 与输入列表的插入顺序无关。
_SEED = (
    Order("O-1007", "C-11", "completed", "2024-04-05", 2100),
    Order("O-1001", "C-02", "completed", "2024-01-15", 1200),
    Order("O-1011", "C-07", "pending", "2024-03-01", 640),
    Order("O-1004", "C-03", "shipped", "2024-03-01", 1750),
    Order("O-1002", "C-05", "pending", "2024-02-03", 800),
    Order("O-1005", "C-07", "pending", "2024-03-01", 300),
    Order("O-1009", "C-09", "completed", "2024-05-11", 60),
    Order("O-1003", "C-02", "completed", "2024-02-03", 500),
    Order("O-1006", "C-04", "cancelled", "2024-03-20", 990),
    Order("O-1010", "C-01", "completed", "2024-06-01", 3300),
    Order("O-1008", "C-12", "shipped", "2024-04-05", 450),
)
```

### apply_discounts

- 来源：`demo_project/app/pricing.py:15-37`
- 索引记录：`code:pricing:apply_discounts` · 内容摘要 `sha256:5a5d92eb` · 回查 ✅
- 命中信号：keyword, applies · RRF `0.03602`

```text
def apply_discounts(
    subtotal_cents: int,
    member: bool = False,
    coupon: str | None = None,
) -> int:
    """依次应用会员折扣、满减、优惠券抵扣，结果不小于 0。"""

    if subtotal_cents < 0:
        raise ValueError("subtotal_cents 不得为负")

    total = subtotal_cents
    if member:
        total -= total * MEMBER_DISCOUNT_PERCENT // 100
    if total >= THRESHOLD_CENTS:
        total -= THRESHOLD_OFF_CENTS

    if coupon is not None:
        if coupon not in COUPON_CENTS:
            raise ValueError(f"未知券码: {coupon}")
        total -= COUPON_CENTS[coupon]

    return max(total, 0)
```

### summarize

- 来源：`demo_project/app/reporting.py:9-30`
- 索引记录：`code:reporting:summarize` · 内容摘要 `sha256:63dc6148` · 回查 ✅
- 命中信号：keyword, applies · RRF `0.03492`

```text
def summarize(
    orders: Sequence[Order] | None = None,
    status: str | None = None,
    since: str | None = None,
) -> dict[str, object]:
    """返回 `count` / `total_cents` / `average_cents` / `by_status`。"""

    rows = _filter_orders(orders, status=status, since=since)

    count = len(rows)
    total = sum(order.total_cents for order in rows)
    by_status: dict[str, int] = {}
    for order in rows:
        by_status[order.status] = by_status.get(order.status, 0) + 1

    return {
        "count": count,
        "total_cents": total,
        "average_cents": total // count if count else 0,
        "by_status": by_status,
    }
```

### _filter_orders

- 来源：`demo_project/app/queries.py:30-49`
- 索引记录：`code:queries:_filter_orders` · 内容摘要 `sha256:c6cca3c0` · 回查 ✅
- 命中信号：fulltext, keyword · RRF `0.02818`

```text
def _filter_orders(
    orders: Sequence[Order] | None,
    status: str | None,
    since: str | None,
) -> list[Order]:
    """按状态与创建时间窗口过滤订单。"""

    rows = list(as_sequence(orders))

    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"未知状态: {status}")
        rows = [order for order in rows if order.status == status]

    if since is not None:
        cutoff = _parse_since(since)
        rows = [order for order in rows if order.created_at >= cutoff]

    return rows
```

### _parse_since

- 来源：`demo_project/app/queries.py:51-66`
- 索引记录：`code:queries:_parse_since` · 内容摘要 `sha256:177215c0` · 回查 ✅
- 命中信号：fulltext, keyword · RRF `0.02729`

```text
def _parse_since(since: str) -> str:
    """验证并返回规范化的 ``YYYY-MM-DD`` 时间窗口起点。"""

    if not isinstance(since, str):
        raise ValueError(f"非法 since: {since}")

    try:
        parsed = date.fromisoformat(since)
    except ValueError:
        raise ValueError(f"非法 since: {since}") from None

    if parsed.isoformat() != since:
        raise ValueError(f"非法 since: {since}")

    return parsed.isoformat()
```

### __module__

- 来源：`demo_project/app/queries.py:1-1`
- 索引记录：`code:queries:__module__` · 内容摘要 `sha256:466b2eea` · 回查 ✅
- 命中信号：fulltext, keyword · RRF `0.02614`

```text
"""订单查询接口（规格见 `specs/order_queries.md`）。"""
```

### seed_orders

- 来源：`demo_project/app/repository.py:37-41`
- 索引记录：`code:repository:seed_orders` · 内容摘要 `sha256:995a346c` · 回查 ✅
- 命中信号：fulltext, keyword · RRF `0.02594`

```text
def seed_orders() -> tuple[Order, ...]:
    """返回固定的 11 条订单样例数据。"""

    return _SEED
```

## 五、验证测试（9 条）

### test_boundary_date_is_inclusive

- 来源：`demo_project/tests/test_target_task_001.py:41-49`
- 索引记录：`test:test_target_task_001:test_boundary_date_is_inclusive` · 内容摘要 `sha256:802447a7` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.04116`

```text
def test_boundary_date_is_inclusive():
    """SPEC-205 rule 1: the boundary day itself is included."""

    included = set(_ids(list_orders(since="2024-03-01", page_size=100)))
    assert {"O-1004", "O-1005", "O-1011"} <= included

    excluded = set(_ids(list_orders(since="2024-03-02", page_size=100)))
    assert {"O-1004", "O-1005", "O-1011"}.isdisjoint(excluded)
```

### test_ordering_is_created_at_then_order_id

- 来源：`demo_project/tests/test_target_task_001.py:51-55`
- 索引记录：`test:test_target_task_001:test_ordering_is_created_at_then_order_id` · 内容摘要 `sha256:23df1688` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.0411`

```text
def test_ordering_is_created_at_then_order_id():
    """SPEC-205 rule 3: sort by (created_at, order_id), independent of input order."""

    assert _ids(list_orders(since="2024-03-01", page_size=100)) == FILTERED_IDS
```

### test_explicit_order_list_is_respected

- 来源：`demo_project/tests/test_regression_queries.py:77-80`
- 索引记录：`test:test_regression_queries:test_explicit_order_list_is_respected` · 内容摘要 `sha256:9b9ad762` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.0405`

```text
def test_explicit_order_list_is_respected():
    rows = [seed_orders()[0], seed_orders()[1]]
    assert _ids(list_orders(rows, page_size=MAX_PAGE_SIZE)) == {rows[0].order_id, rows[1].order_id}
```

### test_invalid_since_raises_value_error

- 来源：`demo_project/tests/test_target_task_001.py:88-96`
- 索引记录：`test:test_target_task_001:test_invalid_since_raises_value_error` · 内容摘要 `sha256:0c9ee005` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.04023`

```text
def test_invalid_since_raises_value_error():
    """SPEC-205 rule 6: an unusable since value raises ValueError."""

    with pytest.raises(ValueError):
        list_orders(since="2024-03-32")

    with pytest.raises(ValueError):
        list_orders(since="not-a-date")
```

### test_since_filters_out_older_orders

- 来源：`demo_project/tests/test_target_task_001.py:32-39`
- 索引记录：`test:test_target_task_001:test_since_filters_out_older_orders` · 内容摘要 `sha256:9f685fca` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.03954`

```text
def test_since_filters_out_older_orders():
    """SPEC-205 rule 1: keep orders with created_at >= since."""

    rows = list_orders(since="2024-03-01", page_size=100)
    assert len(rows) == len(FILTERED_IDS)
    assert all(order.created_at >= "2024-03-01" for order in rows)
    assert set(_ids(rows)) == set(FILTERED_IDS)
```

### test_pagination_applies_after_filtering

- 来源：`demo_project/tests/test_target_task_001.py:57-62`
- 索引记录：`test:test_target_task_001:test_pagination_applies_after_filtering` · 内容摘要 `sha256:fc7c15c7` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.03925`

```text
def test_pagination_applies_after_filtering():
    """SPEC-205 rule 4: filter and sort first, paginate last."""

    page_2 = list_orders(since="2024-03-01", page=2, page_size=3)
    assert _ids(page_2) == ["O-1006", "O-1007", "O-1008"]
```

### test_summarize_rejects_unknown_status

- 来源：`demo_project/tests/test_regression_reporting.py:43-46`
- 索引记录：`test:test_regression_reporting:test_summarize_rejects_unknown_status` · 内容摘要 `sha256:01fb82a5` · 回查 ✅
- 命中信号：fulltext, keyword · RRF `0.02625`

```text
def test_summarize_rejects_unknown_status():
    with pytest.raises(ValueError):
        summarize(status="refunded")
```

### test_all_pages_are_disjoint_and_cover_every_order

- 来源：`demo_project/tests/test_regression_queries.py:55-67`
- 索引记录：`test:test_regression_queries:test_all_pages_are_disjoint_and_cover_every_order` · 内容摘要 `sha256:49fd36f6` · 回查 ✅
- 命中信号：keyword, referencers · RRF `0.02419`

```text
def test_all_pages_are_disjoint_and_cover_every_order():
    pages = [
        list_orders(page=page, page_size=5)
        for page in range(1, (len(ALL_IDS) // 5) + 2)
    ]
    assert all(len(page) <= 5 for page in pages)
    collected = [_ids(page) for page in pages]
    union = set().union(*collected)
    assert union == ALL_IDS
    for i in range(len(collected)):
        for j in range(i + 1, len(collected)):
            assert collected[i].isdisjoint(collected[j])
```

### test_non_member_without_coupon_is_unchanged

- 来源：`demo_project/tests/test_regression_pricing.py:10-12`
- 索引记录：`test:test_regression_pricing:test_non_member_without_coupon_is_unchanged` · 内容摘要 `sha256:c189a40d` · 回查 ✅
- 命中信号：coverage · RRF `0.00763`

```text
def test_non_member_without_coupon_is_unchanged():
    assert apply_discounts(9999) == 9999
```

## 六、回归护栏名册（seekdb 里的全部测试文件）

| 文件 | 用例数 | 文件摘要 |
| --- | --- | --- |
| `demo_project/tests/test_regression_pricing.py` | 8 | `be5e1901` |
| `demo_project/tests/test_regression_queries.py` | 9 | `ec23f8d5` |
| `demo_project/tests/test_regression_reporting.py` | 5 | `94ef3ffb` |
| `demo_project/tests/test_target_task_001.py` | 7 | `972ee252` |

## 七、任务状态（PowerContext）

- 后端：powercontext-embedded-sqlite v1.4.1 · 库 `/home/cuihaoyi/OceanBase/work/powercontext-ecosystem/minimax/runtime/powercontext/state.db`
- 作用域：`scp_3ed3kbsjbb237ts0vw5dvwathm`（idempotency key `sddctx-task-001`）
- 读回记录：13 条，其中按查询排序命中 4 条

- 命中 `todo`（powercontext 相关度 0.016393，命中词：summarize）：[task-001] 待办：按上述规格修改 list_orders, Order, summarize, apply_discounts 等 8 项，并保持回归测试全绿
- 命中 `todo`（powercontext 相关度 0.016129，命中词：summarize）：[task-001] 待办：按上述规格修改 list_orders, Order, apply_discounts, summarize 等 8 项，并保持回归测试全绿
- 命中 `decision`（powercontext 相关度 0.015873，命中词：summarize）：[task-001] 上下文判定：适用规格 SPEC-205, SPEC-301, SPEC-201, SPEC-202 等 8 项；需改代码 list_orders, Order, summarize, apply_discounts 等 8 项
- 命中 `decision`（powercontext 相关度 0.015625，命中词：summarize）：[task-001] 上下文判定：适用规格 SPEC-205, SPEC-301, SPEC-201, SPEC-202 等 8 项；需改代码 list_orders, Order, apply_discounts, summarize 等 8 项
- `done` · artifact `art_08926b5b08124e3faeee4438440a268f` r1：[task-001] 已导入 seekdb：文档 14 个 / 索引条目 61 条（规格 9、代码 21、测试 29）
- `decision` · artifact `art_12e468258fea4493a84912db6719c665` r1：[task-001] 上下文判定：适用规格 SPEC-205, SPEC-301, SPEC-201, SPEC-202 等 8 项；需改代码 list_orders, Order, summarize, apply_discounts 等 8 项
- `todo` · artifact `art_25aa3bb3a8c84b46b51855049246fd7e` r1：[task-001] 待办：按上述规格修改 list_orders, Order, summarize, apply_discounts 等 8 项，并保持回归测试全绿
- `decision` · artifact `art_64c42315b4a24d678b791cbd49c2df1e` r1：[task-001] 上下文判定：适用规格 SPEC-205, SPEC-301, SPEC-201, SPEC-202 等 8 项；需改代码 list_orders, Order, apply_discounts, summarize 等 8 项
- `verified` · artifact `art_672b15b35cf44ee0ae9fb9508e40fa31` r1：[task-001] 改前测试：7 failed, 22 passed in 0.05s
- `todo` · artifact `art_8380aad570a94a0b86aaa91a719bb2c0` r1：[task-001] 待办：按上述规格修改 list_orders, Order, apply_discounts, summarize 等 8 项，并保持回归测试全绿
- `done` · artifact `art_86d46f4be49843ca9f2516af18e71029` r1：[task-001] 已导入 seekdb：文档 14 个 / 索引条目 61 条（规格 9、代码 21、测试 29）
- `verified` · artifact `art_89a29108f0f14f7c951034a86b259b62` r1：[task-001] 改后测试：29 passed in 0.03s
- `note` · artifact `art_961435ca6645416899f531ecac46e842` r1：run_sample.sh 第 7 步写入的演示记录，用于验证跨进程复用
- `verified` · artifact `art_a8b7ea0dfa0141839338fb50500aaf94` r1：[task-001] 改后测试：29 passed in 0.03s
- `verified` · artifact `art_df04999dac254f1289595af362fa04c7` r1：[task-001] MiniMax 改写 2 个实现文件后 pytest rc=0
- `verified` · artifact `art_eaef9ed7f2424cb29fc48cba61d186e7` r1：[task-001] 改前测试：7 failed, 22 passed in 0.05s
- `done` · artifact `art_f46ce0771d384bc5bee995b1abb9a0bd` r1：[task-001] 后端 minimax；补丁 evidence/diffs/task-001.patch

## 八、数据库参与证据

- 引擎：seekdb `5.7.25-OceanBase seekdb-v1.4.0.0` · 库 `sdd_eco` · 地址 `127.0.0.1:2893`
- 表计数：{"sdd_items": 61, "sdd_documents": 14, "sdd_tasks": 2, "sdd_query_log": 70, "items_code": 21, "items_spec": 9, "items_task": 2, "items_test": 29}

| log_id | 阶段 | 查询词 | 命中 | 耗时(ms) | SQL |
| --- | --- | --- | --- | --- | --- |
| 1000212 | applies:test | `demo_project/tests/test_regression_pricing.py::` | 8 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000211 | referencers:test | `Order VALID_STATUSES _filter_orders _parse_since _validate_p` | 16 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000210 | keyword:test | `since created_at order_id summarize ValueError time window i` | 20 | 23 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000209 | fulltext:test | `since created_at order_id summarize ValueError time window i` | 8 | 40 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000208 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000207 | keyword:code | `since created_at order_id summarize ValueError time window i` | 11 | 11 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000206 | fulltext:code | `since created_at order_id summarize ValueError time window i` | 8 | 23 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000205 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000204 | keyword:spec | `since created_at order_id summarize ValueError time window i` | 9 | 15 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000203 | fulltext:spec | `since created_at order_id summarize ValueError time window i` | 8 | 10 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000202 | applies:test | `demo_project/tests/test_regression_pricing.py::` | 8 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000201 | referencers:test | `Order VALID_STATUSES _filter_orders _parse_since _validate_p` | 16 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000200 | keyword:test | `since created_at order_id summarize ValueError time window i` | 20 | 23 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000199 | fulltext:test | `since created_at order_id summarize ValueError time window i` | 8 | 13 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000198 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000197 | keyword:code | `since created_at order_id summarize ValueError time window i` | 11 | 13 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000196 | fulltext:code | `since created_at order_id summarize ValueError time window i` | 8 | 12 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000195 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000194 | keyword:spec | `since created_at order_id summarize ValueError time window i` | 9 | 15 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000193 | fulltext:spec | `since created_at order_id summarize ValueError time window i` | 8 | 30 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000192 | applies:test | `demo_project/tests/test_regression_pricing.py::` | 8 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000191 | referencers:test | `Order VALID_STATUSES _validate_pagination apply_discounts as` | 16 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000190 | keyword:test | `since created_at order_id summarize ValueError time window i` | 20 | 24 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000189 | fulltext:test | `since created_at order_id summarize ValueError time window i` | 8 | 40 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000188 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000187 | keyword:code | `since created_at order_id summarize ValueError time window i` | 9 | 18 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000186 | fulltext:code | `since created_at order_id summarize ValueError time window i` | 8 | 10 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000185 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000184 | keyword:spec | `since created_at order_id summarize ValueError time window i` | 9 | 16 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000183 | fulltext:spec | `since created_at order_id summarize ValueError time window i` | 8 | 27 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000182 | applies:test | `demo_project/tests/test_regression_pricing.py::` | 8 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000181 | referencers:test | `Order VALID_STATUSES _validate_pagination apply_discounts as` | 16 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000180 | keyword:test | `since created_at order_id summarize ValueError time window i` | 20 | 21 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000179 | fulltext:test | `since created_at order_id summarize ValueError time window i` | 8 | 36 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000178 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000177 | keyword:code | `since created_at order_id summarize ValueError time window i` | 9 | 20 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000176 | fulltext:code | `since created_at order_id summarize ValueError time window i` | 8 | 24 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000175 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000174 | keyword:spec | `since created_at order_id summarize ValueError time window i` | 9 | 11 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000173 | fulltext:spec | `since created_at order_id summarize ValueError time window i` | 8 | 25 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000172 | applies:test | `demo_project/tests/test_regression_pricing.py::` | 8 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000171 | referencers:test | `Order VALID_STATUSES _validate_pagination apply_discounts as` | 16 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000170 | keyword:test | `since created_at order_id summarize ValueError time window i` | 20 | 12 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000169 | fulltext:test | `since created_at order_id summarize ValueError time window i` | 8 | 13 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000168 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000167 | keyword:code | `since created_at order_id summarize ValueError time window i` | 9 | 12 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000166 | fulltext:code | `since created_at order_id summarize ValueError time window i` | 8 | 11 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000165 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000164 | keyword:spec | `since created_at order_id summarize ValueError time window i` | 9 | 12 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000163 | fulltext:spec | `since created_at order_id summarize ValueError time window i` | 8 | 159 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000162 | applies:test | `demo_project/tests/test_regression_pricing.py::` | 8 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000161 | referencers:test | `Order VALID_STATUSES _validate_pagination apply_discounts as` | 16 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000160 | keyword:test | `since created_at order_id summarize ValueError time window i` | 20 | 24 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000159 | fulltext:test | `since created_at order_id summarize ValueError time window i` | 8 | 13 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000158 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000157 | keyword:code | `since created_at order_id summarize ValueError time window i` | 9 | 11 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000156 | fulltext:code | `since created_at order_id summarize ValueError time window i` | 8 | 30 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000155 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000154 | keyword:spec | `since created_at order_id summarize ValueError time window i` | 9 | 9 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000153 | fulltext:spec | `since created_at order_id summarize ValueError time window i` | 8 | 25 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |

## 九、来源回查结论

- 来源 25 条，全部可回查：是
- 异常条目：无
