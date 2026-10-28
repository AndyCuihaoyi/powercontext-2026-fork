<<<FILE demo_project/app/queries.py>>>
"""订单查询接口（规格见 `specs/order_queries.md`）。"""

from collections.abc import Sequence
from datetime import date

from .repository import Order, as_sequence


MAX_PAGE_SIZE = 100
VALID_STATUSES = frozenset({"pending", "shipped", "completed", "cancelled"})


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


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page 必须 >= 1")
    if page_size < 1:
        raise ValueError("page_size 必须 >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 不得超过 {MAX_PAGE_SIZE}")
<<<END FILE>>>

<<<FILE demo_project/app/reporting.py>>>
"""订单汇总接口（规格见 `specs/reporting.md`）。"""

from collections.abc import Sequence

from .queries import _filter_orders
from .repository import Order


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
<<<END FILE>>>