"""订单汇总接口（规格见 `specs/reporting.md`）。"""

from collections.abc import Sequence

from .queries import VALID_STATUSES, _filter_orders, as_sequence
from .repository import Order


__all__ = ["summarize"]


def summarize(
    orders: Sequence[Order] | None = None,
    status: str | None = None,
    since: str | None = None,
) -> dict[str, object]:
    """返回 `count` / `total_cents` / `average_cents` / `by_status`。

    已实现：SPEC-301（汇总字段）、SPEC-302（空集合）、
    SPEC-201（状态过滤）、SPEC-205（时间窗口过滤）。
    """

    rows = _filter_orders(orders, status, since)

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
