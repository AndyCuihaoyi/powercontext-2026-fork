"""采集：把 demo_project 的规格、代码、测试、任务陈述切块写入 seekdb。

三类资料的切块口径：
- spec  → `### SPEC-<id>` 一条规格一个条目（保留原始行区间与 Applies-to/Keywords）
- code  → Python 顶层 `def` / `class` / 模块级常量赋值，一个符号一个条目
- test  → `def test_*` 一个测试函数一个条目（含所在文件与断言文本）
- task  → `tasks/task-*.md` 的 front matter（statement + keywords）；`*-checklist.md` 明确排除
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterator, Sequence

from . import config, store

SPEC_HEADING = re.compile(r"^###\s+(SPEC-\d+)\s*·?\s*(.*)$")
META_LINE = re.compile(r"^-\s*(Status|Applies-to|Keywords)\s*:\s*(.*)$")
TOP_LEVEL = re.compile(r"^(?:def|class)\s+([A-Za-z_]\w*)|^([A-Z][A-Z0-9_]*)\s*=")
TEST_DEF = re.compile(r"^def\s+(test_[A-Za-z0-9_]+)")
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
EXCLUDED_NAMES = ("-checklist.md",)
EXCLUDED_PARTS = ("__pycache__", ".venv", "runtime", "evidence")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rel_path(path: Path) -> str:
    return path.relative_to(config.DEMO_ROOT.parent).as_posix()


def _lines(text: str) -> list[str]:
    return text.splitlines()


def slice_lines(lines: Sequence[str], start: int, end: int) -> str:
    return "\n".join(lines[max(start, 1) - 1 : min(end, len(lines))])


def iter_files() -> Iterator[tuple[str, Path]]:
    """采集白名单：specs / app / tests / tasks，排除评审核对清单。"""

    for kind, sub, suffix in (
        ("spec", "specs", {".md"}),
        ("code", "app", {".py"}),
        ("test", "tests", {".py"}),
        ("task", "tasks", {".md"}),
    ):
        base = config.DEMO_ROOT / sub
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffix:
                continue
            if any(part in EXCLUDED_PARTS for part in path.parts):
                continue
            if kind == "task" and any(path.name.endswith(bad) for bad in EXCLUDED_NAMES):
                continue
            yield kind, path


# ---------------------------------------------------------------- 切块


def chunk_spec(text: str) -> list[dict[str, Any]]:
    lines = _lines(text)
    heads = [(i, m) for i, line in enumerate(lines, start=1) if (m := SPEC_HEADING.match(line))]
    items: list[dict[str, Any]] = []
    for pos, (start, match) in enumerate(heads):
        end = heads[pos + 1][0] - 1 if pos + 1 < len(heads) else len(lines)
        body = slice_lines(lines, start, end)
        spec_id, title = match.group(1), match.group(2).strip()
        status, applies, keywords = "", "", ""
        for line in body.splitlines():
            meta = META_LINE.match(line.strip())
            if not meta:
                continue
            label, value = meta.group(1), meta.group(2).strip()
            if label == "Status":
                status = value.split()[0] if value else ""
            elif label == "Applies-to":
                applies = re.sub(r"[`*]", "", value)
            elif label == "Keywords":
                keywords = re.sub(r"[`*]", "", value)
        items.append(
            {
                "item_id": f"spec:{spec_id}",
                "kind": "spec",
                "name": spec_id,
                "qualified_path": f"{title}",
                "start_line": start,
                "end_line": end,
                "text": f"{spec_id} {title}\n{body}",
                "keywords": keywords,
                "applies": applies,
                "entry_status": status,
                "sha256": sha256_text(body),
            }
        )
    return items


def chunk_python(text: str, *, tests: bool) -> list[dict[str, Any]]:
    lines = _lines(text)
    blocks: list[tuple[int, int, str]] = []
    current: tuple[int, str] | None = None
    for index, line in enumerate(lines, start=1):
        if line and not line[0].isspace():
            match = (TEST_DEF if tests else TOP_LEVEL).match(line)
            if match:
                current = (index, match.group(1) or match.group(2))
                blocks.append((index, index, current[1]))
                continue
            if tests:
                current = None
                continue
            current = None
        # 模块 docstring 与顶层注释归入文件级条目，避免「代码里没有上下文」。
    items: list[dict[str, Any]] = []
    for pos, (start, _line_no, name) in enumerate(blocks):
        end = blocks[pos + 1][0] - 1 if pos + 1 < len(blocks) else len(lines)
        while end > start and not lines[end - 1].strip():
            end -= 1
        body = slice_lines(lines, start, end + 1)
        items.append(
            {
                "item_id": f"{'test' if tests else 'code'}:{name}",
                "kind": "test" if tests else "code",
                "name": name,
                "qualified_path": "",  # 由调用方补文件路径
                "start_line": start,
                "end_line": end + 1,
                "text": body,
                "keywords": _identifier_terms(body),
                "applies": "",
                "entry_status": "",
                "sha256": sha256_text(body),
            }
        )
    if not tests:
        module_doc = _module_docstring(lines)
        if module_doc:
            items.append(
                {
                    "item_id": "code:__module__",
                    "kind": "code",
                    "name": "__module__",
                    "qualified_path": "",
                    "start_line": 1,
                    "end_line": len(module_doc.splitlines()),
                    "text": module_doc,
                    "keywords": "",
                    "applies": "",
                    "entry_status": "",
                    "sha256": sha256_text(module_doc),
                }
            )
    return items


def _module_docstring(lines: list[str]) -> str:
    for index, line in enumerate(lines[:8], start=1):
        if line.lstrip().startswith(('"""', "'''")):
            quote = '"""' if line.lstrip().startswith('"""') else "'''"
            if len(line.strip()) > 3 and line.strip().endswith(quote):
                return line.strip()
            end = index
            for cursor in range(index, min(len(lines), index + 12)):
                end = cursor + 1
                if lines[cursor].strip().endswith(quote) and cursor + 1 > index:
                    break
            return slice_lines(lines, index, end)
    return ""


def _identifier_terms(body: str) -> str:
    terms = sorted({token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", body)})
    return " ".join(terms[:60])[:1000]


def chunk_front_matter(text: str) -> dict[str, str] | None:
    match = FRONT_MATTER.match(text)
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


# ---------------------------------------------------------------- 入库


def ingest_all(*, verbose: bool = True) -> dict[str, Any]:
    info = store.init_schema()
    paths: list[str] = []
    stats = {"imported": 0, "unchanged": 0, "items": 0, "tasks": 0}
    for kind, path in iter_files():
        text = path.read_text(encoding="utf-8")
        relative = rel_path(path)
        paths.append(relative)
        if kind == "spec":
            items = chunk_spec(text)
        elif kind == "task":
            fields = chunk_front_matter(text)
            items = []
            if fields and fields.get("id"):
                store.upsert_task(fields["id"], fields.get("title", ""), fields.get("statement", ""), fields.get("keywords", ""))
                statement = fields.get("statement", "")
                items = [
                    {
                        "item_id": f"task:{fields['id']}",
                        "kind": "task",
                        "name": fields["id"],
                        "qualified_path": relative,
                        "start_line": 1,
                        "end_line": len(_lines(text)),
                        "text": f"{fields.get('title', '')}\n{statement}",
                        "keywords": fields.get("keywords", ""),
                        "applies": "",
                        "entry_status": "",
                        "sha256": sha256_text(statement),
                    }
                ]
                stats["tasks"] += 1
        elif kind == "code":
            items = _qualify(chunk_python(text, tests=False), relative)
        else:
            items = _qualify(chunk_python(text, tests=True), relative)
        if not items and kind != "task":
            continue
        outcome = store.upsert_document(kind, relative, sha256_text(text), items)
        stats[outcome] = stats.get(outcome, 0) + 1
        stats["items"] += len(items)
        if verbose:
            print(f"  [{outcome:>9}] {kind:<5} {relative} ({len(items)} 条)")
    stats["pruned"] = store.prune(paths)
    stats.update(info)
    stats["documents"] = len(paths)
    if verbose:
        print(f"  清理失效文件与孤儿条目: {stats['pruned']} · FULLTEXT 解析器: {info['fts_parser']}")
    return stats


def _qualify(items: list[dict[str, Any]], relative: str) -> list[dict[str, Any]]:
    for item in items:
        item["qualified_path"] = f"{relative}::{item['name']}"
        stem = Path(relative).stem
        item["item_id"] = f"{item['kind']}:{stem}:{item['name']}"
    return items


def task_statements() -> list[str]:
    conn = store._connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT task_id FROM sdd_tasks ORDER BY task_id")
            return [row["task_id"] for row in cur.fetchall()]
    finally:
        conn.close()
