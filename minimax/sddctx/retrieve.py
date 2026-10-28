"""检索：上下文包**只由 seekdb 查询结果构造**，再逐条回读磁盘核对来源。

四路信号（每路都是一条真实 SQL，全部写进 `sdd_query_log`）：

1. `fulltext`  —— `MATCH(text) AGAINST(任务关键词)`，seekdb 全文索引排序；
2. `keyword`   —— `name / keywords / text LIKE`，中英混排与符号名的兜底召回；
3. `applies`   —— 规格条目 `Applies-to` 与代码条目 `qualified_path` 的结构关联；
4. `sibling` / `referencers` —— 同规格文件的其它条款、引用了目标符号的测试。

合并用 RRF（`1/(k+rank)`，各路 k 不同），因此任何一路单独失效都不会让必要来源凭空消失。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from . import config, ingest, store

LATIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
CJK_RUN = re.compile(r"[一-鿿]{2,}")
MAX_TERMS = 28

# 各路信号的 RRF 常数：越小表示该信号越被信任。
SIGNAL_K = {
    "fulltext": 60,
    "keyword": 80,
    "applies": 40,
    "referencers": 70,
    "sibling": 120,
    "coverage": 130,
}


def terms_from_task(task: dict[str, Any]) -> list[str]:
    """任务输入只有 front matter 的 statement + keywords（不读 checklist、不读测试）。"""

    text = " ".join(str(task.get(field, "")) for field in ("title", "statement", "keywords"))
    terms: list[str] = []

    def push(term: str) -> None:
        term = term.strip()
        if len(term) >= 3 and term not in terms:
            terms.append(term)

    for match in LATIN.findall(text):
        push(match)
    runs = CJK_RUN.findall(text)
    for run in runs:
        push(run)
    for run in runs:  # 长中文串再切成二元组，兜住全文分词差异
        if len(run) > 4:
            for index in range(len(run) - 1):
                push(run[index : index + 2])
    return terms[:MAX_TERMS]


def _ranked(
    signals: Iterable[tuple[str, Sequence[dict[str, Any]]]],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = {}
    proven: dict[str, list[str]] = {}
    for name, rows in signals:
        base = SIGNAL_K.get(name, 90)
        for rank, row in enumerate(rows, start=1):
            item_id = row["item_id"]
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (base + rank)
            proven.setdefault(item_id, [])
            if name not in proven[item_id]:
                proven[item_id].append(name)
    return scores, proven


def _select(kind: str, scores: dict[str, float], proven: dict[str, list[str]], limit: int) -> list[dict[str, Any]]:
    ids = [item_id for item_id in scores if item_id.startswith(f"{kind}:")]
    ordered = sorted(ids, key=lambda item_id: (-scores[item_id], item_id))[:limit]
    if not ordered:
        return []
    rows = {row["item_id"]: row for row in store.items_by_ids(ordered)}
    return [_source(rows[item_id], scores[item_id], proven[item_id]) for item_id in ordered if item_id in rows]


def _source(row: dict[str, Any], score: float, signals: Sequence[str]) -> dict[str, Any]:
    return {
        "item_id": row["item_id"],
        "kind": row["kind"],
        "name": row["name"],
        "qualified_path": row["qualified_path"],
        "line_range": [int(row["start_line"]), int(row["end_line"])],
        "sha256": row.get("sha256", ""),
        "sha8": (row.get("sha256") or "")[:8],
        "score": round(score, 5),
        "signals": list(signals),
        "applies": row.get("applies") or "",
        "entry_status": row.get("entry_status") or "",
        "keywords": row.get("keywords") or "",
        "text": row["text"],
        "path": "",
        "verified": False,
        "verify_note": "",
    }


def _applies_targets(rows: Sequence[dict[str, Any]]) -> list[str]:
    targets: list[str] = []
    for row in rows:
        for part in str(row.get("applies") or "").split(","):
            token = part.strip()
            if token and token not in targets:
                targets.append(token)
    return targets


def _doc_ids(rows: Sequence[dict[str, Any]]) -> list[str]:
    prov = store.item_provenance([row["item_id"] for row in rows])
    return sorted({meta["doc_id"] for meta in prov.values()})


def _coverage_rows(
    selected: list[dict[str, Any]], task_id: str, roster: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """回归护栏按文件覆盖：索引里的每个测试文件至少保留一条用例（结构补齐，非文本猜测）。"""

    covered = {row["qualified_path"].split("::")[0] for row in selected}
    extra: list[dict[str, Any]] = []
    for doc in roster:
        path = doc["path"]
        if path in covered:
            continue
        rows = store.items_for_paths("test", [f"{path}::"], task_id=task_id)
        if not rows:
            continue
        best = sorted(rows, key=lambda row: int(row["start_line"]))[0]
        extra.append(_source(best, 1.0 / (SIGNAL_K["coverage"] + 1), ["coverage"]))
        covered.add(path)
    return extra


def build_bundle(
    task_id: str,
    *,
    with_state: bool = False,
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    caps = {**config.CONTEXT_LIMITS, **(limits or {})}
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"seekdb 中没有任务 {task_id}，先执行 python -m sddctx ingest")

    terms = terms_from_task(task)
    signals: dict[str, list[tuple[str, list[dict[str, Any]]]]] = {}

    # 1) 规格：全文 + 关键词，再用同文件兄弟条款补「同一规格族的其它约束」
    spec_fulltext = store.fulltext_items("spec", terms, caps["spec"], task_id=task_id)
    spec_keyword = store.keyword_items("spec", terms, caps["spec"], task_id=task_id)
    known = {row["item_id"] for row in spec_fulltext}
    applies_targets = _applies_targets(
        list(spec_fulltext) + [row for row in spec_keyword if row["item_id"] not in known]
    )
    signals["spec"] = [
        ("fulltext", spec_fulltext),
        ("keyword", spec_keyword),
        ("sibling", store.sibling_items("spec", _doc_ids(spec_fulltext + spec_keyword), (), task_id=task_id)),
    ]

    # 2) 代码：文本信号 + 规格 Applies-to 的结构关联
    signals["code"] = [
        ("fulltext", store.fulltext_items("code", terms, caps["code"], task_id=task_id)),
        ("keyword", store.keyword_items("code", terms, caps["code"], task_id=task_id)),
        ("applies", store.applies_items("code", applies_targets, task_id=task_id)),
    ]

    # 3) 测试：文本信号 + 引用了候选代码符号的测试（反向关联）
    code_names = sorted(
        {row["name"] for _, rows in signals["code"] for row in rows if row["name"] != "__module__"}
    )
    signals["test"] = [
        ("fulltext", store.fulltext_items("test", terms, caps["test"], task_id=task_id)),
        ("keyword", store.keyword_items("test", terms, caps["test"], task_id=task_id)),
        (
            "referencers",
            store.symbol_referencers("test", code_names, max(caps["test"], 16), task_id=task_id),
        ),
    ]

    scores: dict[str, float] = {}
    proven: dict[str, list[str]] = {}
    for groups in signals.values():
        kind_scores, kind_provenance = _ranked(groups)
        scores.update(kind_scores)
        for item_id, names in kind_provenance.items():
            proven.setdefault(item_id, []).extend(names)

    roster = store.documents_by_kind("test")
    tests = _select("test", scores, proven, caps["test"])
    tests += _coverage_rows(tests, task_id, roster)

    bundle = {
        "task": _task_block(task_id, task),
        "query": {
            "terms": terms,
            "limits": caps,
            "signals": {kind: [name for name, _ in groups] for kind, groups in signals.items()},
            "applies_targets": applies_targets,
        },
        "applicable_specs": _select("spec", scores, proven, caps["spec"]),
        "target_code": _select("code", scores, proven, caps["code"]),
        "verification_tests": tests,
        "regression_files": roster,
        "db": _db_block(task_id),
        "task_state": None,
    }
    attach_provenance(bundle)
    bundle["task"] = _verify_task(bundle["task"])
    if with_state:
        from . import state as pc_state  # 延迟导入：只在需要状态时初始化 PowerContext

        bundle["task_state"] = pc_state.load_for_task(task_id)
    return bundle


def _task_block(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "title": str(task.get("title", "")),
        "statement": str(task.get("statement", "")),
        "keywords": str(task.get("keywords", "")),
        "source": "seekdb:sdd_tasks",
        "path": "",
        "verified": False,
        "verify_note": "",
    }


def _db_block(task_id: str) -> dict[str, Any]:
    info = store.ping()
    return {
        "engine": "seekdb",
        "version": info.get("version", ""),
        "database": info.get("db", config.SEEKDB_DATABASE),
        "host": f"{config.SEEKDB_HOST}:{config.SEEKDB_PORT}",
        "counts": store.table_counts(),
        "queries": [
            {
                "log_id": int(row["log_id"]),
                "stage": row["stage"],
                "terms": row["terms"],
                "hit_count": int(row["hit_count"]),
                "elapsed_ms": int(row["elapsed_ms"]),
                "sql": row["sql_text"],
            }
            for row in store.read_query_log(task_id, limit=60)
        ],
    }


# ---------------------------------------------------------------- 来源回查


def all_sources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("applicable_specs", "target_code", "verification_tests"):
        out.extend(bundle.get(key, []))
    return out


def attach_provenance(bundle: dict[str, Any]) -> None:
    """补上文件路径，并逐条回读磁盘行区间核对内容摘要（赛题 §4.1「可回查」）。"""

    sources = all_sources(bundle)
    prov = store.item_provenance([row["item_id"] for row in sources])
    cache: dict[str, list[str]] = {}
    for row in sources:
        meta = prov.get(row["item_id"])
        if meta is None:
            row["verify_note"] = "索引里没有该记录"
            continue
        row["path"] = meta["path"]
        start, end = row["line_range"]
        try:
            if meta["path"] not in cache:
                cache[meta["path"]] = (config.DEMO_ROOT.parent / meta["path"]).read_text(
                    encoding="utf-8"
                ).splitlines()
            sliced = ingest.slice_lines(cache[meta["path"]], start, end)
        except OSError as exc:
            row["verify_note"] = f"回读失败：{exc}"
            continue
        actual = ingest.sha256_text(sliced)
        if row["sha256"] and actual != row["sha256"]:
            row["verify_note"] = (
                f"行区间与索引摘要不一致：磁盘 {actual[:8]} ≠ 索引 {row['sha8']}"
            )
            continue
        row["verified"] = True
        row["verify_note"] = "ok"


def _verify_task(task: dict[str, Any]) -> dict[str, Any]:
    key = f"task:{task['task_id']}"
    meta = store.item_provenance([key]).get(key)
    if meta is None:
        task["verify_note"] = "任务文件未入库"
        return task
    task["path"] = meta["path"]
    try:
        text = (config.DEMO_ROOT.parent / meta["path"]).read_text(encoding="utf-8")
    except OSError as exc:
        task["verify_note"] = f"回读失败：{exc}"
        return task
    if task["statement"] and task["statement"] in text:
        task["verified"] = True
        task["verify_note"] = "ok"
    else:
        task["verify_note"] = "任务陈述与文件内容不一致"
    return task


def check_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """上下文包自检：每条来源都要有 path + 行区间 + 记录 ID + 摘要且回查通过。"""

    sources = all_sources(bundle)
    broken = [
        row["item_id"] for row in sources if not row["verified"] or not row["path"] or not row["sha8"]
    ]
    return {
        "ok": not broken and bool(bundle["task"]["verified"]),
        "sources": len(sources),
        "broken": broken,
        "task_verified": bool(bundle["task"]["verified"]),
    }
