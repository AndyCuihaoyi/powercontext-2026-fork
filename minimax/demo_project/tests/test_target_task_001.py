"""Task-001 目标功能测试（SPEC-205）。

这些测试在修改前必须失败，且失败原因是「目标行为未实现」（断言/未抛错），
不是缺少依赖或无法导入。修改后全部通过。
测试集在修改前后保持完全一致：不得删断言、不得加 `skip`、不得改预期值。
"""

from __future__ import annotations

import pytest

from app.queries import list_orders
from app.reporting import summarize

# SPEC-205 规则 1/3/4：since=2024-03-01 的期望结果（含边界、稳定排序）。
FILTERED_IDS = [
    "O-1004",
    "O-1005",
    "O-1011",
    "O-1006",
    "O-1007",
    "O-1008",
    "O-1009",
    "O-1010",
]


def _ids(orders):
    return [order.order_id for order in orders]


def test_since_filters_out_older_orders():
    """SPEC-205 rule 1: keep orders with created_at >= since."""

    rows = list_orders(since="2024-03-01", page_size=100)
    assert len(rows) == len(FILTERED_IDS)
    assert all(order.created_at >= "2024-03-01" for order in rows)
    assert set(_ids(rows)) == set(FILTERED_IDS)


def test_boundary_date_is_inclusive():
    """SPEC-205 rule 1: the boundary day itself is included."""

    included = set(_ids(list_orders(since="2024-03-01", page_size=100)))
    assert {"O-1004", "O-1005", "O-1011"} <= included

    excluded = set(_ids(list_orders(since="2024-03-02", page_size=100)))
    assert {"O-1004", "O-1005", "O-1011"}.isdisjoint(excluded)


def test_ordering_is_created_at_then_order_id():
    """SPEC-205 rule 3: sort by (created_at, order_id), independent of input order."""

    assert _ids(list_orders(since="2024-03-01", page_size=100)) == FILTERED_IDS


def test_pagination_applies_after_filtering():
    """SPEC-205 rule 4: filter and sort first, paginate last."""

    page_2 = list_orders(since="2024-03-01", page=2, page_size=3)
    assert _ids(page_2) == ["O-1006", "O-1007", "O-1008"]


def test_status_and_since_combine():
    """SPEC-205 rule 4 + SPEC-201: both filters apply together."""

    assert _ids(list_orders(status="pending", since="2024-03-01", page_size=100)) == [
        "O-1005",
        "O-1011",
    ]


def test_summarize_uses_filtered_set():
    """SPEC-205 rule 5 + SPEC-301: summarize counts only the filtered set."""

    result = summarize(since="2024-03-01")
    assert result["count"] == 8
    assert result["total_cents"] == 9590
    assert result["average_cents"] == 1198
    assert result["by_status"] == {
        "shipped": 2,
        "pending": 2,
        "completed": 3,
        "cancelled": 1,
    }


def test_invalid_since_raises_value_error():
    """SPEC-205 rule 6: an unusable since value raises ValueError."""

    with pytest.raises(ValueError):
        list_orders(since="2024-03-32")

    with pytest.raises(ValueError):
        list_orders(since="not-a-date")
