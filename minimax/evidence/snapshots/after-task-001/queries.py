"""订单查询接口（规格见 `specs/order_queries.md`）。"""

from collections.abc import Sequence
from datetime import date
import re

from .repository import Order, seed_orders


VALID_STATUSES = frozenset({"pending", "shipped", "completed", "cancelled"})
MAX_PAGE_SIZE = 100

_SINCE_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def as_sequence(orders: Sequence[Order] | None = None) -> list[Order]:
    """返回订单列表；未指定时使用固定的样例订单。"""

    if orders is None:
        return list(seed_orders())
    return list(orders)


def _validate_since(since: str | None) -> str | None:
    """校验 ``since`` 并返回规范化的日期字符串。"""

    if since is None:
        return None

    if (
        not isinstance(since, str)
        or _SINCE_DATE_PATTERN.fullmatch(since) is None
    ):
        raise ValueError(f"非法 since 日期: {since}")

    try:
        date.fromisoformat(since)
    except ValueError as exc:
        raise ValueError(f"非法 since 日期: {since}") from exc

    return since


def _filter_orders(
    orders: Sequence[Order] | None,
    status: str | None,
    since: str | None,
) -> list[Order]:
    """依次应用状态过滤和时间窗口过滤。"""

    rows = as_sequence(orders)

    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"未知状态: {status}")
        rows = [order for order in rows if order.status == status]

    boundary = _validate_since(since)
    if boundary is not None:
        rows = [order for order in rows if order.created_at >= boundary]

    return rows


def list_orders(
    orders: Sequence[Order] | None = None,
    status: str | None = None,
    since: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[Order]:
    """按状态与时间窗口分页返回订单。

    已实现：SPEC-201（状态筛选）、SPEC-202（分页语义）、
    SPEC-205（时间窗口过滤与稳定排序）、SPEC-212（分页上界）。
    """

    rows = _filter_orders(orders, status, since)
    rows.sort(key=lambda order: (order.created_at, order.order_id))

    _validate_pagination(page, page_size)
    start = (page - 1) * page_size
    return rows[start : start + page_size]


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page 必须 >= 1")
    if page_size < 1:
        raise ValueError("page_size 必须 >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 不得超过 {MAX_PAGE_SIZE}")
