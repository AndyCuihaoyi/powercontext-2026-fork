"""回归测试（SPEC-101 / SPEC-102 / SPEC-103）：与 Task-001 无关，修改前后都必须通过。"""

from __future__ import annotations

import pytest

from app.pricing import apply_discounts


def test_non_member_without_coupon_is_unchanged():
    assert apply_discounts(9999) == 9999


def test_member_discount_is_floor_of_10_percent():
    assert apply_discounts(10000, member=True) == 9000
    assert apply_discounts(1050, member=True) == 945


def test_threshold_discount_applies_once_after_membership():
    assert apply_discounts(12000, member=True) == 9300
    assert apply_discounts(11000, member=False) == 9500


def test_threshold_is_evaluated_after_member_discount():
    # 11000 分打 9 折后是 9900 分，已低于满减门槛，因此只应用会员折扣。
    assert apply_discounts(11000, member=True) == 9900


def test_coupon_is_applied_last():
    assert apply_discounts(5000, coupon="NEW100") == 4900
    assert apply_discounts(15000, member=True, coupon="SPRING500") == 11500


def test_total_never_drops_below_zero():
    assert apply_discounts(50, coupon="VIP1000") == 0


def test_unknown_coupon_raises_value_error():
    with pytest.raises(ValueError):
        apply_discounts(1000, coupon="NOPE")


def test_negative_subtotal_raises_value_error():
    with pytest.raises(ValueError):
        apply_discounts(-1)
