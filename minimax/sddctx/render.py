"""上下文包渲染：md（人读，进 evidence/context/）与 json（机读，进 MiniMax）。"""

from __future__ import annotations

import json
from typing import Any

from . import retrieve

JSON_KEY_ORDER = (
    "task",
    "query",
    "applicable_specs",
    "target_code",
    "verification_tests",
    "regression_files",
    "task_state",
    "db",
)


def to_json(bundle: dict[str, Any], *, include_sql: bool = True) -> str:
    data = {key: bundle[key] for key in JSON_KEY_ORDER if key in bundle}
    if not include_sql:
        data["db"] = {**data.get("db", {}), "queries": [
            {k: row[k] for k in ("log_id", "stage", "terms", "hit_count", "elapsed_ms")}
            for row in data.get("db", {}).get("queries", [])
        ]}
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _source_block(row: dict[str, Any]) -> list[str]:
    start, end = row["line_range"]
    title = row["qualified_path"].split("::")[-1] if row["kind"] != "spec" else row["name"]
    out = [
        f"### {title}",
        "",
        f"- 来源：`{row['path']}:{start}-{end}`",
        f"- 索引记录：`{row['item_id']}` · 内容摘要 `sha256:{row['sha8']}` · 回查 "
        f"{'✅' if row['verified'] else '❌ ' + row['verify_note']}",
        f"- 命中信号：{', '.join(row['signals']) or '-'} · RRF `{row['score']}`",
    ]
    if row["applies"]:
        out.append(f"- Applies-to：`{row['applies']}`")
    if row["entry_status"]:
        out.append(f"- Status：{row['entry_status']}")
    out += ["", "```text", row["text"].rstrip(), "```", ""]
    return out


def to_markdown(bundle: dict[str, Any]) -> str:
    task = bundle["task"]
    db = bundle["db"]
    lines = [
        f"# 上下文包 · {task['task_id']}",
        "",
        f"> 由 `python -m sddctx context --task {task['task_id']}` 生成。",
        "> 每条来源都来自 seekdb 查询结果，并逐条回读磁盘行区间核对内容摘要。",
        "",
        "## 一、任务（输入只有 front matter）",
        "",
        f"- 标题：{task['title']}",
        f"- 陈述：{task['statement']}",
        f"- 关键词：{task['keywords']}",
        f"- 来源：`{task['source']}` → `{task['path']}` · 回查 "
        f"{'✅' if task['verified'] else '❌ ' + task['verify_note']}",
        "",
        "## 二、检索信号",
        "",
        f"- 查询词（{len(bundle['query']['terms'])}）：{', '.join(bundle['query']['terms'])}",
        f"- 各路信号：{json.dumps(bundle['query']['signals'], ensure_ascii=False)}",
        f"- 规格 Applies-to 展开：{', '.join(bundle['query'].get('applies_targets', [])) or '-'}",
        f"- 每类上限：{json.dumps(bundle['query']['limits'], ensure_ascii=False)}",
        "",
        f"## 三、适用规格（{len(bundle['applicable_specs'])} 条）",
        "",
    ]
    for row in bundle["applicable_specs"]:
        lines += _source_block(row)
    lines += [f"## 四、需要修改的代码（{len(bundle['target_code'])} 处）", ""]
    for row in bundle["target_code"]:
        lines += _source_block(row)
    lines += [f"## 五、验证测试（{len(bundle['verification_tests'])} 条）", ""]
    for row in bundle["verification_tests"]:
        lines += _source_block(row)
    lines += [
        "## 六、回归护栏名册（seekdb 里的全部测试文件）",
        "",
        "| 文件 | 用例数 | 文件摘要 |",
        "| --- | --- | --- |",
    ]
    for row in bundle["regression_files"]:
        lines.append(f"| `{row['path']}` | {row['item_count']} | `{str(row['sha256'])[:8]}` |")
    lines += ["", "## 七、任务状态（PowerContext）", ""]
    task_state = bundle.get("task_state")
    if not task_state:
        lines += ["_未加 `--with-state`，本次不注入任务状态。_", ""]
    else:
        lines += [
            f"- 后端：{task_state['backend']} v{task_state['version']} · 库 `{task_state['database']}`",
            f"- 作用域：`{task_state['scope_id']}`（idempotency key `{task_state['idempotency_key']}`）",
            f"- 读回记录：{len(task_state['records'])} 条，其中按查询排序命中 {len(task_state['ranked'])} 条",
            "",
        ]
        for row in task_state["ranked"]:
            terms = ", ".join(row.get("matched_terms") or [row["matched_by_query"]])
            lines.append(
                f"- 命中 `{row['kind']}`（powercontext 相关度 {row['score']}，命中词：{terms}）：{row['text']}"
            )
        for row in task_state["records"]:
            lines.append(
                f"- `{row['kind']}` · artifact `{row['artifact_id']}` r{row['revision']}：{row['text']}"
            )
        lines.append("")
    lines += [
        "## 八、数据库参与证据",
        "",
        f"- 引擎：seekdb `{db['version']}` · 库 `{db['database']}` · 地址 `{db['host']}`",
        f"- 表计数：{json.dumps(db['counts'], ensure_ascii=False)}",
        "",
        "| log_id | 阶段 | 查询词 | 命中 | 耗时(ms) | SQL |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in db["queries"]:
        sql = row["sql"].replace("|", "\\|")
        lines.append(
            f"| {row['log_id']} | {row['stage']} | `{row['terms'][:60]}` | {row['hit_count']}"
            f" | {row['elapsed_ms']} | `{sql[:120]}` |"
        )
    check = retrieve.check_bundle(bundle)
    lines += [
        "",
        "## 九、来源回查结论",
        "",
        f"- 来源 {check['sources']} 条，全部可回查：{'是' if check['ok'] else '否'}",
        f"- 异常条目：{', '.join(check['broken']) or '无'}",
        "",
    ]
    return "\n".join(lines)


def prompt_text(bundle: dict[str, Any]) -> str:
    """给 MiniMax 的提示正文：只包含上下文包内容，不含 checklist、不含固定答案。"""

    parts = [
        f"任务：{bundle['task']['title']}",
        f"要求：{bundle['task']['statement']}",
        "",
        "== 适用规格（来自数据库检索） ==",
    ]
    for row in bundle["applicable_specs"]:
        parts.append(f"[{row['item_id']} {row['path']}:{row['line_range'][0]}-{row['line_range'][1]}]\n{row['text']}")
    parts.append("")
    parts.append("== 需要修改的代码（现状） ==")
    for row in bundle["target_code"]:
        parts.append(f"[{row['path']}]\n{row['text']}")
    parts.append("")
    parts.append("== 验证测试（不得修改，必须改后全绿） ==")
    for row in bundle["verification_tests"]:
        parts.append(f"[{row['path']}::{row['name']}]\n{row['text']}")
    task_state = bundle.get("task_state")
    if task_state and task_state.get("records"):
        parts.append("")
        parts.append("== 既有任务状态（PowerContext 读回） ==")
        for row in task_state["records"]:
            parts.append(f"- [{row['kind']}] {row['text']}")
    return "\n".join(parts) + "\n"
