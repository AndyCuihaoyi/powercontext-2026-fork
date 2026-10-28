"""订单汇总（规格见 `specs/reporting.md`）。"""

from __future__ import annotations

from typing import Sequence

from .repository import VALID_STATUSES, Order, as_sequence


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
