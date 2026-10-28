# Task-002 必要来源清单（评审核对用，模块不读取本文件）

> 核对 `python -m sddctx context --task task-002` 的输出；自动核对见 `scripts/verify_acceptance.py A3b`。

## 一、规格条目

| 规格 ID | 必须包含的原因 |
|---|---|
| `SPEC-212` | 直接回答 `page_size` 上界取值与越界行为 |
| `SPEC-202` | 分页语义（页码起点、越界页返回空） |

## 二、代码位置

| 符号 | 文件 |
|---|---|
| `MAX_PAGE_SIZE` | `demo_project/app/queries.py` |
| `_validate_pagination` | `demo_project/app/queries.py` |

## 三、测试

| 测试 | 文件 |
|---|---|
| `test_page_size_upper_bound_is_enforced` | `demo_project/tests/test_regression_queries.py` |

## 四、变更前后差异（A3 后半句）

- 变更前后，第一、二、三节的来源集合应保持一致（同一任务、同一工程）。
- **唯一必须变化的是 `SPEC-212` 条目正文中的上界数值**：`100` → `200`，
  且模块必须输出变化后的正文。输出仍带 `100` 即判 A3 不通过。
