"""订单仓储：验证样例使用固定内存数据，保证任何环境下的结果可复现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

VALID_STATUSES = ("pending", "shipped", "completed", "cancelled")


@dataclass(frozen=True)
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


def seed_orders() -> tuple[Order, ...]:
    """返回固定的 11 条订单样例数据。"""

    return _SEED


def as_sequence(orders: Sequence[Order] | None) -> list[Order]:
    return list(_SEED if orders is None else orders)
