"""回归测试（SPEC-301 / SPEC-302 / SPEC-201）：修改前后都必须通过。"""

from __future__ import annotations

import pytest

from app.reporting import summarize


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


def test_summarize_with_status_filter():
    result = summarize(status="pending")
    assert result["count"] == 3
    assert result["total_cents"] == 1740
    assert result["average_cents"] == 580
    assert result["by_status"] == {"pending": 3}


def test_summarize_completed_only():
    result = summarize(status="completed")
    assert result["count"] == 5
    assert result["total_cents"] == 7160
    assert result["by_status"] == {"completed": 5}


def test_summarize_empty_selection_is_not_an_error():
    result = summarize(orders=[])
    assert result == {"count": 0, "total_cents": 0, "average_cents": 0, "by_status": {}}


def test_summarize_rejects_unknown_status():
    with pytest.raises(ValueError):
        summarize(status="refunded")
