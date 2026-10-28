"""定价与折扣（规格见 `specs/pricing.md`）。与 Task-001 无关，用于回归范围控制。"""

from __future__ import annotations

MEMBER_DISCOUNT_PERCENT = 10  # SPEC-101
THRESHOLD_CENTS = 10_000  # SPEC-102
THRESHOLD_OFF_CENTS = 1_500  # SPEC-102
COUPON_CENTS = {  # SPEC-103
    "NEW100": 100,
    "SPRING500": 500,
    "VIP1000": 1_000,
}


def apply_discounts(
    subtotal_cents: int,
    member: bool = False,
    coupon: str | None = None,
) -> int:
    """依次应用会员折扣、满减、优惠券抵扣，结果不小于 0。"""

    if subtotal_cents < 0:
        raise ValueError("subtotal_cents 不得为负")

    total = subtotal_cents
    if member:
        total -= total * MEMBER_DISCOUNT_PERCENT // 100
    if total >= THRESHOLD_CENTS:
        total -= THRESHOLD_OFF_CENTS

    if coupon is not None:
        if coupon not in COUPON_CENTS:
            raise ValueError(f"未知券码: {coupon}")
        total -= COUPON_CENTS[coupon]

    return max(total, 0)
