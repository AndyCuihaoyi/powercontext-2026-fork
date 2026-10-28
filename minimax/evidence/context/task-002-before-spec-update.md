# 上下文包 · task-002

> 由 `python -m sddctx context --task task-002` 生成。
> 每条来源都来自 seekdb 查询结果，并逐条回读磁盘行区间核对内容摘要。

## 一、任务（输入只有 front matter）

- 标题：调用方想一次读取更多订单，page_size 上界是多少
- 陈述：调用方希望一次读取更多订单。page_size 的上界是多少？超出上界会怎样？分页参数还有哪些边界约束？
- 关键词：page_size, upper bound, limit, 分页, 上界, 参数校验, ValueError, MAX_PAGE_SIZE
- 来源：`seekdb:sdd_tasks` → `demo_project/tasks/task-002-spec-update.md` · 回查 ✅

## 二、检索信号

- 查询词（13）：page_size, upper, bound, limit, ValueError, MAX_PAGE_SIZE, 调用方想一次读取更多订单, 上界是多少, 调用方希望一次读取更多订单, 的上界是多少, 超出上界会怎样, 分页参数还有哪些边界约束, 参数校验
- 各路信号：{"spec": ["fulltext", "keyword", "sibling"], "code": ["fulltext", "keyword", "applies"], "test": ["fulltext", "keyword", "referencers"]}
- 规格 Applies-to 展开：app/queries.py::list_orders, app/reporting.py::summarize, app/repository.py::Order, app/pricing.py::apply_discounts
- 每类上限：{"spec": 8, "code": 8, "test": 8}

## 三、适用规格（8 条）

### SPEC-202

- 来源：`demo_project/specs/order_queries.md:19-30`
- 索引记录：`spec:SPEC-202` · 内容摘要 `sha256:678b66d6` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03647`
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

### SPEC-212

- 来源：`demo_project/specs/order_queries.md:50-59`
- 索引记录：`spec:SPEC-212` · 内容摘要 `sha256:52ee4568` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03632`
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

### SPEC-205

- 来源：`demo_project/specs/order_queries.md:31-49`
- 索引记录：`spec:SPEC-205` · 内容摘要 `sha256:f9e8630e` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.036`
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

### SPEC-201

- 来源：`demo_project/specs/order_queries.md:7-18`
- 索引记录：`spec:SPEC-201` · 内容摘要 `sha256:f2b72829` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03521`
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

### SPEC-103

- 来源：`demo_project/specs/pricing.md:21-27`
- 索引记录：`spec:SPEC-103` · 内容摘要 `sha256:73b5174d` · 回查 ✅
- 命中信号：fulltext, keyword, sibling · RRF `0.03474`
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
- 命中信号：fulltext, sibling · RRF `0.02382`
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

### SPEC-101

- 来源：`demo_project/specs/pricing.md:5-12`
- 索引记录：`spec:SPEC-101` · 内容摘要 `sha256:a4cf14c4` · 回查 ✅
- 命中信号：fulltext, sibling · RRF `0.02319`
- Applies-to：`app/pricing.py::apply_discounts`
- Status：Active

```text
SPEC-101 会员折扣
### SPEC-101 · 会员折扣

- Status: Active
- Applies-to: `app/pricing.py::apply_discounts`
- Keywords: membership, discount, 10 percent, member

规则：会员订单按小计（`subtotal_cents`）打 9 折，向下取整到分。非会员不打折。
```

### SPEC-301

- 来源：`demo_project/specs/reporting.md:3-12`
- 索引记录：`spec:SPEC-301` · 内容摘要 `sha256:c91f0ffa` · 回查 ✅
- 命中信号：fulltext, sibling · RRF `0.02296`
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

## 四、需要修改的代码（8 处）

### list_orders

- 来源：`demo_project/app/queries.py:21-47`
- 索引记录：`code:queries:list_orders` · 内容摘要 `sha256:b72146d4` · 回查 ❌ 行区间与索引摘要不一致：磁盘 f9575845 ≠ 索引 b72146d4
- 命中信号：fulltext, keyword, applies · RRF `0.05228`

```text
def list_orders(
    orders: Sequence[Order] | None = None,
    status: str | None = None,
    since: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[Order]:
    """按状态与时间窗口分页返回订单。

    已实现：SPEC-201（状态筛选）、SPEC-202（分页语义）、SPEC-212（分页上界）。
    未实现：SPEC-205（`since` 时间窗口过滤与 `(created_at, order_id)` 稳定排序）。
    """

    rows = as_sequence(orders)
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"未知状态: {status}")
        rows = [order for order in rows if order.status == status]

    # TODO(SPEC-205): since 过滤与 created_at 排序尚未落地，当前参数被忽略。
    del since
    rows.sort(key=lambda order: order.order_id)

    _validate_pagination(page, page_size)
    start = (page - 1) * page_size
    return rows[start : start + page_size]
```

### apply_discounts

- 来源：`demo_project/app/pricing.py:15-37`
- 索引记录：`code:pricing:apply_discounts` · 内容摘要 `sha256:5a5d92eb` · 回查 ✅
- 命中信号：keyword, applies · RRF `0.0363`

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

- 来源：`demo_project/app/reporting.py:10-41`
- 索引记录：`code:reporting:summarize` · 内容摘要 `sha256:231b7c80` · 回查 ❌ 行区间与索引摘要不一致：磁盘 e77dc6b1 ≠ 索引 231b7c80
- 命中信号：keyword, applies · RRF `0.03449`

```text
def summarize(
    orders: Sequence[Order] | None = None,
    status: str | None = None,
    since: str | None = None,
) -> dict[str, object]:
    """返回 `count` / `total_cents` / `average_cents` / `by_status`。

    已实现：SPEC-301（汇总字段）、SPEC-302（空集合）、SPEC-201（状态过滤）。
    未实现：SPEC-205 第 5 点——`since` 时间窗口尚未作用于汇总口径。
    """

    rows = as_sequence(orders)
    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"未知状态: {status}")
        rows = [order for order in rows if order.status == status]

    # TODO(SPEC-205): since 应把汇总范围收敛到 created_at >= since 的订单。
    del since

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

### _validate_pagination

- 来源：`demo_project/app/queries.py:12-19`
- 索引记录：`code:queries:_validate_pagination` · 内容摘要 `sha256:c256f78b` · 回查 ❌ 行区间与索引摘要不一致：磁盘 5d259c58 ≠ 索引 c256f78b
- 命中信号：fulltext, keyword · RRF `0.02844`

```text
def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page 必须 >= 1")
    if page_size < 1:
        raise ValueError("page_size 必须 >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 不得超过 {MAX_PAGE_SIZE}")
```

### MAX_PAGE_SIZE

- 来源：`demo_project/app/queries.py:9-10`
- 索引记录：`code:queries:MAX_PAGE_SIZE` · 内容摘要 `sha256:704da090` · 回查 ❌ 行区间与索引摘要不一致：磁盘 1e9ebfde ≠ 索引 704da090
- 命中信号：fulltext, keyword · RRF `0.02807`

```text
MAX_PAGE_SIZE = 100  # SPEC-212
```

### Order

- 来源：`demo_project/app/repository.py:12-35`
- 索引记录：`code:repository:Order` · 内容摘要 `sha256:e20136f2` · 回查 ✅
- 命中信号：applies · RRF `0.02326`

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

### seed_orders

- 来源：`demo_project/app/repository.py:37-41`
- 索引记录：`code:repository:seed_orders` · 内容摘要 `sha256:995a346c` · 回查 ✅
- 命中信号：fulltext · RRF `0.01562`

```text
def seed_orders() -> tuple[Order, ...]:
    """返回固定的 11 条订单样例数据。"""

    return _SEED
```

### __module__

- 来源：`demo_project/app/repository.py:1-1`
- 索引记录：`code:repository:__module__` · 内容摘要 `sha256:060d41ac` · 回查 ✅
- 命中信号：fulltext · RRF `0.01538`

```text
"""订单仓储：验证样例使用固定内存数据，保证任何环境下的结果可复现。"""
```

## 五、验证测试（10 条）

### test_explicit_order_list_is_respected

- 来源：`demo_project/tests/test_regression_queries.py:77-80`
- 索引记录：`test:test_regression_queries:test_explicit_order_list_is_respected` · 内容摘要 `sha256:9b9ad762` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.04095`

```text
def test_explicit_order_list_is_respected():
    rows = [seed_orders()[0], seed_orders()[1]]
    assert _ids(list_orders(rows, page_size=MAX_PAGE_SIZE)) == {rows[0].order_id, rows[1].order_id}
```

### test_page_size_upper_bound_is_enforced

- 来源：`demo_project/tests/test_regression_queries.py:49-53`
- 索引记录：`test:test_regression_queries:test_page_size_upper_bound_is_enforced` · 内容摘要 `sha256:aacca81d` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.04037`

```text
def test_page_size_upper_bound_is_enforced():
    with pytest.raises(ValueError):
        list_orders(page_size=MAX_PAGE_SIZE + 1)
    assert len(list_orders(page_size=MAX_PAGE_SIZE)) == len(ALL_IDS)
```

### test_page_beyond_range_is_empty

- 来源：`demo_project/tests/test_regression_queries.py:69-71`
- 索引记录：`test:test_regression_queries:test_page_beyond_range_is_empty` · 内容摘要 `sha256:d42e4e9b` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.04014`

```text
def test_page_beyond_range_is_empty():
    assert list_orders(page=99, page_size=MAX_PAGE_SIZE) == []
```

### test_negative_subtotal_raises_value_error

- 来源：`demo_project/tests/test_regression_pricing.py:43-46`
- 索引记录：`test:test_regression_pricing:test_negative_subtotal_raises_value_error` · 内容摘要 `sha256:ff3ab869` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.0388`

```text
def test_negative_subtotal_raises_value_error():
    with pytest.raises(ValueError):
        apply_discounts(-1)
```

### test_pagination_arguments_are_validated

- 来源：`demo_project/tests/test_regression_queries.py:43-47`
- 索引记录：`test:test_regression_queries:test_pagination_arguments_are_validated` · 内容摘要 `sha256:1cb67f06` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.03856`

```text
def test_pagination_arguments_are_validated():
    for kwargs in ({"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": -5}):
        with pytest.raises(ValueError):
            list_orders(**kwargs)
```

### test_status_filter_for_each_status

- 来源：`demo_project/tests/test_regression_queries.py:27-36`
- 索引记录：`test:test_regression_queries:test_status_filter_for_each_status` · 内容摘要 `sha256:3112c439` · 回查 ✅
- 命中信号：fulltext, keyword, referencers · RRF `0.03719`

```text
def test_status_filter_for_each_status():
    expected = {
        "pending": {"O-1002", "O-1005", "O-1011"},
        "shipped": {"O-1004", "O-1008"},
        "completed": {"O-1001", "O-1003", "O-1007", "O-1009", "O-1010"},
        "cancelled": {"O-1006"},
    }
    for status, ids in expected.items():
        assert _ids(list_orders(status=status, page_size=MAX_PAGE_SIZE)) == ids
```

### test_without_status_returns_every_order

- 来源：`demo_project/tests/test_regression_queries.py:73-75`
- 索引记录：`test:test_regression_queries:test_without_status_returns_every_order` · 内容摘要 `sha256:314dbbd3` · 回查 ✅
- 命中信号：fulltext, keyword · RRF `0.02655`

```text
def test_without_status_returns_every_order():
    assert _ids(list_orders(page_size=MAX_PAGE_SIZE)) == ALL_IDS
```

### test_all_pages_are_disjoint_and_cover_every_order

- 来源：`demo_project/tests/test_regression_queries.py:55-67`
- 索引记录：`test:test_regression_queries:test_all_pages_are_disjoint_and_cover_every_order` · 内容摘要 `sha256:49fd36f6` · 回查 ✅
- 命中信号：keyword, referencers · RRF `0.02643`

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

### test_summarize_full_data_set

- 来源：`demo_project/tests/test_regression_reporting.py:10-21`
- 索引记录：`test:test_regression_reporting:test_summarize_full_data_set` · 内容摘要 `sha256:e8b168b5` · 回查 ✅
- 命中信号：coverage · RRF `0.00763`

```text
def test_summarize_full_data_set():
    result = summarize()
    assert result["count"] == 11
    assert result["total_cents"] == 12090
    assert result["average_cents"] == 1099
    assert result["by_status"] == {
        "completed": 5,
        "pending": 3,
        "shipped": 2,
        "cancelled": 1,
    }
```

### test_since_filters_out_older_orders

- 来源：`demo_project/tests/test_target_task_001.py:32-39`
- 索引记录：`test:test_target_task_001:test_since_filters_out_older_orders` · 内容摘要 `sha256:9f685fca` · 回查 ✅
- 命中信号：coverage · RRF `0.00763`

```text
def test_since_filters_out_older_orders():
    """SPEC-205 rule 1: keep orders with created_at >= since."""

    rows = list_orders(since="2024-03-01", page_size=100)
    assert len(rows) == len(FILTERED_IDS)
    assert all(order.created_at >= "2024-03-01" for order in rows)
    assert set(_ids(rows)) == set(FILTERED_IDS)
```

## 六、回归护栏名册（seekdb 里的全部测试文件）

| 文件 | 用例数 | 文件摘要 |
| --- | --- | --- |
| `demo_project/tests/test_regression_pricing.py` | 8 | `be5e1901` |
| `demo_project/tests/test_regression_queries.py` | 9 | `ec23f8d5` |
| `demo_project/tests/test_regression_reporting.py` | 5 | `94ef3ffb` |
| `demo_project/tests/test_target_task_001.py` | 7 | `972ee252` |

## 七、任务状态（PowerContext）

_未加 `--with-state`，本次不注入任务状态。_

## 八、数据库参与证据

- 引擎：seekdb `5.7.25-OceanBase seekdb-v1.4.0.0` · 库 `sdd_eco` · 地址 `127.0.0.1:2893`
- 表计数：{"sdd_items": 58, "sdd_documents": 14, "sdd_tasks": 2, "sdd_query_log": 119, "items_code": 18, "items_spec": 9, "items_task": 2, "items_test": 29}

| log_id | 阶段 | 查询词 | 命中 | 耗时(ms) | SQL |
| --- | --- | --- | --- | --- | --- |
| 1000021 | applies:test | `demo_project/tests/test_target_task_001.py::` | 7 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000020 | applies:test | `demo_project/tests/test_regression_reporting.py::` | 5 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000019 | referencers:test | `MAX_PAGE_SIZE Order _validate_pagination apply_discounts lis` | 16 | 4 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000018 | keyword:test | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 16 | 5 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000017 | fulltext:test | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 8 | 4 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000016 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 1000015 | keyword:code | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 5 | 5 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000014 | fulltext:code | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 8 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 1000013 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 4 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 1000012 | keyword:spec | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 5 | 12 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 1000011 | fulltext:spec | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 8 | 154 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 48 | applies:test | `demo_project/tests/test_target_task_001.py::` | 7 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 47 | applies:test | `demo_project/tests/test_regression_reporting.py::` | 5 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 46 | referencers:test | `MAX_PAGE_SIZE Order _validate_pagination apply_discounts lis` | 16 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 45 | keyword:test | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 16 | 4 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 44 | fulltext:test | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 8 | 2 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 43 | applies:code | `app/queries.py::list_orders app/reporting.py::summarize app/` | 4 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256 FROM sdd` |
| 42 | keyword:code | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 5 | 4 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 41 | fulltext:code | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 8 | 1 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |
| 40 | sibling:spec | `spec:3f416aa7d79d47627f735aba:demo_project/specs/order_queri` | 9 | 0 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords, sha256, doc_id ` |
| 39 | keyword:spec | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 5 | 4 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, text, keywords FROM sdd_items W` |
| 38 | fulltext:spec | `page_size upper bound limit ValueError MAX_PAGE_SIZE 调用方想一次读` | 8 | 3 | `SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status, MATCH(text) AGAINST (%s) AS sco` |

## 九、来源回查结论

- 来源 26 条，全部可回查：否
- 异常条目：code:queries:list_orders, code:reporting:summarize, code:queries:_validate_pagination, code:queries:MAX_PAGE_SIZE
