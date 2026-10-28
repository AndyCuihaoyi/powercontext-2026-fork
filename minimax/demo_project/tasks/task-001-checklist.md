# Task-001 必要来源清单（评审核对用，模块不读取本文件）

> 用途：核对 `python -m sddctx context --task task-001` 的输出是否齐备（赛题 §4.1「上下文正确」）。
> 自动核对命令：`python scripts/verify_acceptance.py A3a`（本文件只被校验脚本读取）。

## 一、规格条目（必须全部出现在「适用规格」中）

| 规格 ID | 标题 | 为什么必须 |
|---|---|---|
| `SPEC-205` | 按创建时间窗口筛选订单 | 本任务的目标行为（主规格） |
| `SPEC-201` | 按状态筛选订单 | 规则 7 要求状态过滤行为不变 |
| `SPEC-202` | 分页语义 | 决定「过滤 → 排序 → 分页」的顺序与越界页行为 |
| `SPEC-212` | 分页参数上界 | 决定合法 `page_size` 范围 |
| `SPEC-301` | 汇总口径 | `summarize` 的统计范围与字段 |

## 二、代码位置（必须全部出现在「需要修改的代码」中）

| 符号 | 文件 |
|---|---|
| `list_orders` | `demo_project/app/queries.py` |
| `summarize` | `demo_project/app/reporting.py` |
| `Order` | `demo_project/app/repository.py` |

## 三、测试（必须全部出现在「验证测试」中）

| 类别 | 测试文件 |
|---|---|
| 目标功能测试 | `demo_project/tests/test_target_task_001.py` |
| 回归测试 | `demo_project/tests/test_regression_queries.py` |
| 回归测试 | `demo_project/tests/test_regression_reporting.py` |
| 回归测试 | `demo_project/tests/test_regression_pricing.py` |

## 四、任务状态

「已完成事项 / 待办事项 / 已有验证结果」必须来自 PowerContext 中该任务作用域的真实记录
（`python -m sddctx state show --task task-001` 与 `evidence/powercontext/`）。

## 五、来源真实性

上述每条来源都必须带可回查字段：文件路径、行区间、索引记录 ID、内容摘要。
校验脚本会逐条回读磁盘文件对应行区间，内容不符即判 A3 不通过。
