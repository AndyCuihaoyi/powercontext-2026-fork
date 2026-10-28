"""订单查询接口（规格见 `specs/order_queries.md`）。"""

from __future__ import annotations

from typing import Sequence

from .repository import VALID_STATUSES, Order, as_sequence

MAX_PAGE_SIZE = 100  # SPEC-212


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page 必须 >= 1")
    if page_size < 1:
        raise ValueError("page_size 必须 >= 1")
    if page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 不得超过 {MAX_PAGE_SIZE}")


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
