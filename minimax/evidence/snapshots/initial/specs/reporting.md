# 规格：汇总报表（Reporting）

### SPEC-301 · 汇总口径

- Status: Active
- Applies-to: `app/reporting.py::summarize`
- Keywords: summary, count, total_cents, average_cents, by_status

规则：`summarize` 返回字典，至少包含 `count`（订单数）、`total_cents`（金额合计）、
`average_cents`（`total_cents // count`，`count == 0` 时为 0）、`by_status`（按状态分组计数，
只包含出现过的状态）。汇总对象必须是经过同一套过滤条件筛出的集合，不得混入被过滤掉的订单。

### SPEC-302 · 空集合汇总

- Status: Active
- Applies-to: `app/reporting.py::summarize`
- Keywords: empty result, zero count, no division

规则：过滤后为空时返回 `count == 0`、`total_cents == 0`、`average_cents == 0`、`by_status == {}`，
不得抛除零异常。
