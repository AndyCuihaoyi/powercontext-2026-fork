"""回归测试：Task-001 修改前后都必须全部通过。

覆盖 SPEC-201（状态筛选）、SPEC-202（分页语义）、SPEC-212（分页上界）的既有行为。
断言刻意与输出顺序无关（用集合/数量），因为 SPEC-205 才定义排序键；
修改前按 order_id 排序、修改后按 (created_at, order_id) 排序，两种实现都应通过本文件。
"""

from __future__ import annotations

import pytest

from app.queries import MAX_PAGE_SIZE, list_orders
from app.repository import seed_orders

ALL_IDS = {order.order_id for order in seed_orders()}


def _ids(rows):
    return {order.order_id for order in rows}


def test_status_filter_returns_only_matching_orders():
    rows = list_orders(status="pending", page_size=MAX_PAGE_SIZE)
    assert _ids(rows) == {"O-1002", "O-1005", "O-1011"}


def test_status_filter_for_each_status():
    expected = {
        "pending": {"O-1002", "O-1005", "O-1011"},
        "shipped": {"O-1004", "O-1008"},
        "completed": {"O-1001", "O-1003", "O-1007", "O-1009", "O-1010"},
        "cancelled": {"O-1006"},
    }
    for status, ids in expected.items():
        assert _ids(list_orders(status=status, page_size=MAX_PAGE_SIZE)) == ids


def test_unknown_status_raises_value_error():
    with pytest.raises(ValueError):
        list_orders(status="refunded")


def test_pagination_arguments_are_validated():
    for kwargs in ({"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": -5}):
        with pytest.raises(ValueError):
            list_orders(**kwargs)


def test_page_size_upper_bound_is_enforced():
    with pytest.raises(ValueError):
        list_orders(page_size=MAX_PAGE_SIZE + 1)
    assert len(list_orders(page_size=MAX_PAGE_SIZE)) == len(ALL_IDS)


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


def test_page_beyond_range_is_empty():
    assert list_orders(page=99, page_size=MAX_PAGE_SIZE) == []


def test_without_status_returns_every_order():
    assert _ids(list_orders(page_size=MAX_PAGE_SIZE)) == ALL_IDS


def test_explicit_order_list_is_respected():
    rows = [seed_orders()[0], seed_orders()[1]]
    assert _ids(list_orders(rows, page_size=MAX_PAGE_SIZE)) == {rows[0].order_id, rows[1].order_id}
