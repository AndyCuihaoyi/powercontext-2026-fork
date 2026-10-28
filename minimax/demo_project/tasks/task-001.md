---
id: task-001
title: 让 since 时间窗口真正作用于订单查询与汇总
statement: 订单查询与汇总需要按创建时间窗口 since 过滤（边界包含当天），过滤后再排序与分页，排序键为 created_at 升序、order_id 升序；summarize 只统计过滤后的集合；非法 since 抛 ValueError。状态筛选与分页的既有行为必须保持不变。
keywords: since, created_at, time window, inclusive boundary, ordering, sort key, stable order, pagination, summarize, 时间窗口, 排序, 分页, 汇总
---

# Task-001 · 让 `since` 时间窗口真正作用于订单查询与汇总

> 上方 front matter 是**模块的唯一任务输入**（`statement` + `keywords`）。
> 「上下文必须包含哪些来源」写在 `task-001-checklist.md` 里，只给评审核对用；
> 索引与检索代码路径禁止读取 `*-checklist.md`（`sddctx/ingest.py` 的采集白名单已排除该文件）。

## 一、任务描述（要改什么）

`specs/order_queries.md` 中的 **SPEC-205** 已是 `Status: Active`，但实现落后于规格：
`app/queries.py::list_orders` 与 `app/reporting.py::summarize` 目前**忽略 `since` 参数**，
排序键仍是 `order_id`。需要按 SPEC-205 落地：

1. `since`（`YYYY-MM-DD`）只保留 `created_at >= since` 的订单，边界当天包含在内。
2. 过滤顺序：状态过滤 → 时间窗口过滤 → 排序 → 分页。
3. 排序键固定为 `(created_at 升序, order_id 升序)`，不得依赖输入列表顺序。
4. `summarize(...)` 接受同样的 `since`，且只统计过滤后的集合。
5. 非法 `since`（格式错误或不存在日期）抛 `ValueError`。

只允许修改 `demo_project/app/` 下的实现文件。**不得修改 `demo_project/tests/` 与 `demo_project/specs/`**
（测试集在修改前后必须完全一致，这是赛题红线）。

## 二、必须保持的原有行为（回归范围）

| 来源 | 必须保持的行为 |
|---|---|
| SPEC-201 | 状态取值集合、未知状态抛 `ValueError`、`status=None` 不过滤 |
| SPEC-202 | 页码从 1 开始、越界页返回空列表、非法 `page`/`page_size` 抛 `ValueError` |
| SPEC-212 | `page_size` 上界仍为规格声明的值，越界抛 `ValueError` |
| SPEC-301 / SPEC-302 | 汇总字段集合、空集合不抛除零错误 |
| SPEC-101 / 102 / 103 | 定价逻辑与本任务无关，必须原样保持 |

## 三、操作步骤

```bash
python -m sddctx ingest --root demo_project             # 1. 导入规格/代码/测试
python -m sddctx context --task task-001 --format md     # 2. 生成开发上下文包
python -m sddctx agent --task task-001                   # 3. MiniMax 依据上下文修改代码
python -m sddctx test --task task-001                    # 4. 跑目标 + 回归测试
python -m sddctx state save --task task-001 ...           # 5. 保存任务状态（README §4）
python -m sddctx reset --task task-001                   # 6. 重置回初始状态
```

## 四、预期结果

| 阶段 | 命令 | 预期 |
|---|---|---|
| 修改前 | `pytest demo_project/tests/test_target_task_001.py` | 退出码非 0，7 条目标测试因断言/未抛错失败（不是导入错误） |
| 修改前 | `pytest demo_project/tests -k regression` | 退出码 0，22 条回归测试通过 |
| 修改后 | `pytest demo_project/tests` | 退出码 0，29 条全部通过 |
| 上下文 | `python -m sddctx context --task task-001` | 含 `task-001-checklist.md` 列出的全部来源，且来源可回查 |
| 状态 | 重启模块后 `context --with-state` | 输出含上次保存的已完成/待办/验证结果 |

## 五、重置方法

```bash
python -m sddctx reset --task task-001           # 代码回到改前状态
python -m sddctx reset --task task-001 --state   # 同时清空 PowerContext 状态与 seekdb 记录
```

重置实现见 `sddctx/reset.py`：从 `evidence/snapshots/initial/` 复制实现文件（含 `specs/` 与 `tests/`，用于证明测试集没被动过），不依赖 git 历史。
