# 规格：定价与折扣（Pricing）

> 与订单查询无关，用于演示回归测试的范围控制：Task-001 不得改变本文件约束的行为。

### SPEC-101 · 会员折扣

- Status: Active
- Applies-to: `app/pricing.py::apply_discounts`
- Keywords: membership, discount, 10 percent, member

规则：会员订单按小计（`subtotal_cents`）打 9 折，向下取整到分。非会员不打折。

### SPEC-102 · 满减

- Status: Active
- Applies-to: `app/pricing.py::apply_discounts`
- Keywords: threshold discount, 10000, 1500, amount off

规则：会员折扣之后的小计 `>= 10000` 分（即 100 元）时再减 `1500` 分；不足门槛不减。满减只应用一次。

### SPEC-103 · 优惠券与下限

- Status: Active
- Applies-to: `app/pricing.py::apply_discounts`
- Keywords: coupon, floor, non-negative, total

规则：优惠券面额在最后抵扣；抵扣后总额不得小于 0 分（低于 0 时取 0）。未知券码抛出 `ValueError`。
