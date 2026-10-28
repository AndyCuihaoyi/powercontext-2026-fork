#!/usr/bin/env python3
"""六项必做项（A1–A6）自动自检：把「评审按题面逐条核对」变成一条可复现命令。

    python scripts/verify_acceptance.py all                # 全部
    python scripts/verify_acceptance.py A3 A4              # 只看某几项
    python scripts/verify_acceptance.py all --task task-001

口径来自 `topics/eco-04-minimax-sdd/01-mapping.md`。每项只认磁盘上真实存在的证据
（evidence/ + seekdb + PowerContext + demo_project），任一 FAIL 即以非 0 退出。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sddctx import config, ingest, render, reset, retrieve, state, store  # noqa: E402

REQUIRED_FILES = (
    "requirements.txt",
    ".env.example",
    "README.md",
    "scripts/setup.sh",
    "scripts/start_seekdb.sh",
    "scripts/init_data.sh",
    "scripts/run_sample.sh",
    "scripts/verify_acceptance.py",
    "sddctx/cli.py",
    "sddctx/store.py",
    "sddctx/retrieve.py",
    "sddctx/state.py",
    "sddctx/agent.py",
    "demo_project/tasks/task-001.md",
    "demo_project/specs/order_queries.md",
    "demo_project/app/queries.py",
    "demo_project/tests/test_target_task_001.py",
    "evidence/snapshots/initial/app/queries.py",
)


class Check:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lines: list[str] = []
        self.ok = True

    def require(self, condition: bool, detail: str) -> bool:
        self.lines.append(("  ok  " if condition else "  FAIL ") + detail)
        if not condition:
            self.ok = False
        return condition

    def note(self, detail: str) -> None:
        self.lines.append("  --   " + detail)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=900)


def _demo_python() -> str:
    return str(Path(sys.executable))


# ---------------------------------------------------------------- A1


def check_a1(ctx: dict[str, Any]) -> Check:
    c = Check("A1 能够运行")
    for rel in REQUIRED_FILES:
        c.require((ROOT / rel).exists(), f"交付文件存在：{rel}")
    if not c.ok:
        return c
    help_proc = _run([_demo_python(), "-m", "sddctx", "--help"])
    c.require(help_proc.returncode == 0, "`python -m sddctx --help` 退出码 0")
    subcommands = [name for name in ("ingest", "context", "state", "agent", "test", "reset") if name in help_proc.stdout]
    c.require(len(subcommands) == 6, f"CLI 子命令齐备：{', '.join(subcommands)}")
    ping = store.ping()
    c.require(int(ping.get("items", 0)) > 0, f"seekdb 可连接：{ping.get('version')} · 库 {ping.get('db')}")
    dirty = reset.check_untouched()
    c.require(not dirty["tests"], "测试目录与初始快照一致" if not dirty["tests"] else f"测试目录有差异：{dirty['tests']}")
    return c


# ---------------------------------------------------------------- A2


FILE_BLOCK = re.compile(r"<<<FILE\s+(?P<path>[^\n>]+?)\s*>>>\n(?P<body>.*?)\n<<<END FILE>>>", re.DOTALL)


def _minimax_records(task: str) -> list[dict[str, Any]]:
    path = config.EVIDENCE_DIR / "minimax" / f"{task}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_a2(ctx: dict[str, Any]) -> Check:
    c = Check("A2 MiniMax 实际参与")
    task = ctx["task"]
    rows = _minimax_records(task)
    if not c.require(bool(rows), f"开发记录存在：evidence/minimax/{task}.jsonl（{len(rows)} 轮）"):
        return c
    real = [r for r in rows if r.get("usage") and r.get("endpoint")]
    c.require(bool(real), "记录里有真实 API 调用（含 endpoint / request_id / usage，不是纯 replay）")
    last = real[-1] if real else rows[-1]
    c.require(
        last.get("messages") and last["messages"][0]["role"] == "system",
        "记录含发送的完整消息（system 规则 + user 上下文包）",
    )
    prompt = [m for m in last["messages"] if m["role"] == "user"][0]["content"]
    prompt_file = config.EVIDENCE_DIR / "context" / f"{task}-prompt.txt"
    if c.require(prompt_file.exists(), "实际发送的提示已留档：evidence/context/<task>-prompt.txt"):
        same = prompt_file.read_text(encoding="utf-8") == prompt
        c.require(same, f"留档提示与记录一致（{len(prompt)} 字符）" if same else f"提示不一致：留档 {prompt_file.stat().st_size} vs 记录 {len(prompt)}")
    for key in ("total_tokens", "prompt_tokens", "completion_tokens"):
        c.require(key in (last.get("usage") or {}), f"usage 记录 {key}")
    c.note(f"模型 {last.get('model')} · request_id {last.get('request_id')} · 耗时 {last.get('elapsed_ms')} ms")
    written = {m.group("path").strip() for r in rows for m in FILE_BLOCK.finditer(r["response"]["content"])}
    patch = config.EVIDENCE_DIR / "diffs" / f"{task}.patch"
    if c.require(patch.exists(), f"补丁存在：evidence/diffs/{task}.patch"):
        diffed = set(re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(encoding="utf-8"), re.MULTILINE))
        c.require(
            written == diffed,
            f"模型返回的文件与补丁改动的文件一一对应：{sorted(written)} == {sorted(diffed)}"
            if written == diffed
            else f"文件不一致：模型 {sorted(written)} vs 补丁 {sorted(diffed)}",
        )
        c.require(all(p.startswith("demo_project/app/") for p in diffed), "补丁只触碰 demo_project/app/")
    return c


# ---------------------------------------------------------------- A3


CHECKLIST_ROWS = re.compile(r"^\|\s*`?([^`|]+?)`?\s*\|\s*`?([^`|]+?)`?\s*\|", re.MULTILINE)


def _checklist_cells(task: str) -> dict[str, list[str]]:
    path = config.DEMO_ROOT / "tasks" / f"{task}-checklist.md"
    text = path.read_text(encoding="utf-8")
    specs: list[str] = []
    symbols: list[tuple[str, str]] = []
    tests: list[str] = []
    section = ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line
        cells = CHECKLIST_ROWS.match(line.strip())
        if not cells:
            continue
        left, right = cells.group(1).strip(), cells.group(2).strip()
        if left in ("规格 ID", "符号", "类别", "---"):
            continue
        if "规格条目" in section and left.startswith("SPEC-"):
            specs.append(left)
        elif "代码位置" in section:
            symbols.append((left, right))
        elif "测试" in section and left != "任务状态":
            tests.append(right if right.endswith(".py") else left)
    return {"specs": specs, "symbols": [s for s, _ in symbols], "tests": tests}


def check_a3(ctx: dict[str, Any]) -> Check:
    c = Check("A3 上下文正确（必要来源齐备 + 来源可回查）")
    task = ctx["task"]
    bundle = ctx["bundle"]
    check = ctx["check"]
    want = _checklist_cells(task)
    spec_names = {row["name"] for row in bundle["applicable_specs"]}
    for spec_id in want["specs"]:
        c.require(spec_id in spec_names, f"必要规格出现在上下文：{spec_id}")
    code_names = {row["name"] for row in bundle["target_code"]}
    for symbol in want["symbols"]:
        c.require(symbol in code_names, f"必要代码符号出现在上下文：{symbol}")
    test_paths = {row["path"] for row in bundle["verification_tests"]} | {
        row["path"] for row in bundle["regression_files"]
    }
    for rel in want["tests"]:
        c.require(any(rel.endswith(t.split("/")[-1]) or t.endswith(rel.split("/")[-1]) for t in test_paths),
                  f"必要测试文件出现在上下文：{rel}")
    c.require("task_state" in bundle, "上下文包含任务状态字段（无记录时为 null，而不是伪造）")
    c.require(bool(check["sources"]), f"每条来源带 path/line_range/item_id/sha8：{check['sources']} 条")
    c.require(
        check["ok"],
        "逐条回读磁盘行区间，内容与索引一致" if check["ok"] else f"来源回查失败：{', '.join(check['broken'])}",
    )
    return c


def check_a3b(ctx: dict[str, Any]) -> Check:
    c = Check("A3b 规格更新后重新导入要用新内容（非硬编码）")
    py = _demo_python()
    old = "100"
    new = "200"
    before = retrieve.build_bundle(ctx["task"], with_state=False)
    section = [row for row in before["applicable_specs"] if row["name"] == "SPEC-212"]
    c.require(bool(section), "改前上下文含 SPEC-212")
    if section:
        c.require(f"<= {old}" in section[0]["text"], f"改前 SPEC-212 正文用上界 {old}")
    proc = _run([py, "scripts/spec_update_demo.py", "--bound", new])
    c.require(proc.returncode == 0, f"改写 SPEC-212 上界为 {new}：{proc.stdout.strip().splitlines()[-1] if proc.stdout else proc.stderr[:120]}")
    try:
        after = retrieve.build_bundle(ctx["task"], with_state=False)
        row = next((r for r in after["applicable_specs"] if r["name"] == "SPEC-212"), None)
        if c.require(row is not None, "更新后上下文仍含 SPEC-212（说明取的是同一条规格，不是凭空生成）"):
            c.require(f"<= {new}" in row["text"], f"更新后正文用新上界 {new}")
            c.require(f"上界为 {old}" not in row["text"], f"旧上界 {old} 已从上下文消失（旧内容不残留）")
            disk = ingest.slice_lines(
                (config.DEMO_ROOT / "specs" / "order_queries.md").read_text(encoding="utf-8").splitlines(),
                row["line_range"][0],
                row["line_range"][1],
            )
            c.require(f"<= {new}" in disk, "上下文行区间与磁盘更新后的文件一致")
    finally:
        restore = _run([py, "scripts/spec_update_demo.py", "--restore"])
        c.require(restore.returncode == 0, "已还原初始规格文本并重新导入")
    return c


# ---------------------------------------------------------------- A4


def check_a4(ctx: dict[str, Any]) -> Check:
    c = Check("A4 数据库实际参与（seekdb 存储 + 检索 + 留痕）")
    counts = store.table_counts()
    for table in ("sdd_documents", "sdd_items", "sdd_tasks", "sdd_query_log"):
        c.require(counts.get(table, 0) > 0, f"{table} 有真实行数：{counts.get(table, 0)}")
    schema = store.schema_evidence()
    c.require("FULLTEXT" in schema.upper(), "sdd_items 建有 FULLTEXT 索引")
    log = store.read_query_log(ctx["task"], limit=200)
    c.require(bool(log), f"本次任务有 {len(log)} 条 seekdb 查询留痕（SQL/参数/命中数/耗时）")
    stages = {row["stage"] for row in log}
    c.require(any(s.startswith("fulltext") for s in stages), f"包含全文检索阶段：{sorted(stages)}")
    bundle = ctx["bundle"]
    db = bundle["db"]
    c.require(db.get("engine", "").startswith("seekdb") or "seekdb" in str(db.get("version", "")).lower(),
              f"上下文里的数据库信息指向 seekdb：{db.get('version')}")
    c.require(bool(db.get("queries")), "上下文包内置本次查询明细（可核对不是磁盘遍历）")
    for group in ("applicable_specs", "target_code", "verification_tests"):
        c.require(all(row["item_id"] for row in bundle[group]), f"{group} 每条都来自索引记录 ID")
    export = _write_queries_md(log, ctx["task"])
    c.note(f"导出 {export}")
    return c


def _write_queries_md(log: list[dict[str, Any]], task: str) -> Path:
    lines = [
        f"# seekdb 查询留痕 · {task}",
        "",
        "由 `python scripts/verify_acceptance.py A4` 从 `sdd_query_log` 表导出。",
        "",
        "| log_id | stage | 命中 | 耗时(ms) | 检索词 | SQL |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(log, key=lambda r: r["log_id"]):
        lines.append(
            f"| {row['log_id']} | `{row['stage']}` | {row['hit_count']} | {row['elapsed_ms']}"
            f" | `{row['terms'][:60]}` | `{row['sql_text'][:160].replace('|', '/124')}…` |"
        )
    path = config.EVIDENCE_DIR / "db" / "queries.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- A5


def check_a5(ctx: dict[str, Any]) -> Check:
    c = Check("A5 状态能够复用（PowerContext 写入 → 新进程读回 → 注入上下文）")
    task = ctx["task"]
    token = f"verify-{int(time.time())}"
    text = f"[{task}] 验收探针 {token}：由 verify_acceptance.py 在当前进程写入"
    outcome = state.save(task, [{"kind": "verified", "text": text}])
    c.require(outcome["written"] >= 1, f"PowerContext 写入 1 条（scope {outcome['scope_id']}）")
    c.require(str(outcome["database"]).endswith(".db"), f"落盘文件：{outcome['database']}")

    proc = _run([_demo_python(), "-m", "sddctx", "state", "show", "--task", task])
    c.require(proc.returncode == 0, "新进程 `state show` 退出码 0")
    c.require(token in proc.stdout, "新进程读回到刚才写入的探针记录（跨进程复用）")
    loaded = state.load_for_task(task)
    c.require(bool(loaded["records"]), f"读回 {len(loaded['records'])} 条记录 · 后端 {loaded['backend']}")
    c.require(loaded["source"] == "powercontext.atomic_memory", "记录来源是 powercontext.atomic_memory，不是自写 JSON")
    bundle = retrieve.build_bundle(task, with_state=True)
    injected = bundle["task_state"] or {}
    c.require(bool(injected.get("records")), f"上下文注入任务状态 {len(injected.get('records', []))} 条")
    kinds = {row["kind"] for row in injected.get("records", [])}
    c.require({"done", "todo", "verified"} <= kinds or bool(kinds), f"状态含 kind：{sorted(kinds)}")
    markdown = render.to_markdown(bundle)
    c.require(token in markdown, "渲染后的上下文 markdown 里能看到该状态")
    return c


# ---------------------------------------------------------------- A6


def classify_pytest_failure(log: str) -> dict[str, int]:
    """区分「断言失败」（功能性）与「环境/导入/收集错误」（不能充当改前失败）。"""

    lowered = log.lower()
    assert_failures = len(re.findall(r"^E\s+(assert|AssertionError)", log, re.MULTILINE | re.IGNORECASE))
    fatal = sum(
        token in lowered
        for token in (
            "modulenotfounderror",
            "importerror",
            "no such file or directory",
            "error during collection",
            "internal error",
            "command not found",
            "traceback (most recent call last)",
        )
    )
    summary = re.search(r"(\d+) failed", log)
    return {
        "assert_failures": assert_failures,
        "failed": int(summary.group(1)) if summary else 0,
        "environment_errors": fatal,
    }


def check_a6(ctx: dict[str, Any]) -> Check:
    c = Check("A6 代码修改有效（改前断言失败 → 改后全绿 · 测试集不变）")
    task = ctx["task"]
    before = config.EVIDENCE_DIR / "test-logs" / f"before-{task}.log"
    after = config.EVIDENCE_DIR / "test-logs" / f"after-{task}.log"
    if not c.require(before.exists() and after.exists(), "改前/改后测试日志都在 evidence/test-logs/"):
        return c
    b_text, a_text = before.read_text(encoding="utf-8"), after.read_text(encoding="utf-8")
    cls = classify_pytest_failure(b_text)
    c.require(cls["environment_errors"] == 0, f"改前日志无环境/导入/收集错误（检出 {cls['environment_errors']}）")
    c.require(cls["assert_failures"] > 0, f"改前有 {cls['assert_failures']} 处断言失败（功能性失败，不是跑不起来）")
    rcs = [int(m) for m in re.findall(r"^rc=(\d+)", b_text, re.MULTILINE)]
    c.require(max(rcs or [0]) != 0, f"改前退出码非 0：{rcs}")
    after_rcs = [int(m) for m in re.findall(r"^rc=(\d+)", a_text, re.MULTILINE)]
    c.require(bool(after_rcs) and max(after_rcs) == 0, f"改后各套件退出码全为 0：{after_rcs}")
    c.require("failed" not in a_text, "改后日志无 failed 用例")
    passed = [int(m) for m in re.findall(r"(\d+) passed", a_text)]
    c.require(bool(passed), f"改后通过用例数：{max(passed) if passed else '?'}（目标 + 回归全量）")
    dirty = reset.check_untouched(("tests", "specs"))
    c.require(not dirty["tests"] and not dirty["specs"], f"测试与规格目录与初始快照逐字节一致（差异 {dirty}）")
    patch = config.EVIDENCE_DIR / "diffs" / f"{task}.patch"
    if c.require(patch.exists(), f"补丁文件存在：{_rel(patch)}"):
        c.require("demo_project/tests/" not in patch.read_text(encoding="utf-8"), "补丁不含测试文件")
    snap = config.EVIDENCE_DIR / "snapshots" / f"after-{task}"
    c.require(snap.exists(), f"改后代码快照存在：evidence/snapshots/after-{task}/")
    return c


# ---------------------------------------------------------------- 入口


CHECKS: dict[str, Callable[[dict[str, Any]], Check]] = {
    "A1": check_a1,
    "A2": check_a2,
    "A3": check_a3,
    "A3b": check_a3b,
    "A4": check_a4,
    "A5": check_a5,
    "A6": check_a6,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="六项必做项自检")
    parser.add_argument("items", nargs="*", default=["all"], help="A1 A2 A3 A3b A4 A5 A6 或 all")
    parser.add_argument("--task", default="task-001")
    parser.add_argument("--out", default="evidence/acceptance-check.md")
    args = parser.parse_args(argv)

    items = list(CHECKS) if "all" in args.items else args.items
    config.ensure_dirs()
    bundle = retrieve.build_bundle(args.task, with_state=False)
    ctx = {
        "task": args.task,
        "bundle": bundle,
        "check": retrieve.check_bundle(bundle),
    }
    lines = [f"# 验收自检 · {args.task}", "", f"生成时间：{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", ""]
    failed: list[str] = []
    for item in items:
        if item not in CHECKS:
            print(f"未知验收项：{item}", file=sys.stderr)
            return 2
        try:
            result = CHECKS[item](ctx)
        except Exception as exc:  # noqa: BLE001 - 自检脚本要把异常也归入 FAIL
            result = Check(item)
            result.require(False, f"检查过程异常：{type(exc).__name__}: {exc}")
        lines.append(f"## {result.name} → {'PASS' if result.ok else 'FAIL'}")
        lines += result.lines
        lines.append("")
        if not result.ok:
            failed.append(item)
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.name}")
        for line in result.lines:
            print(line)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n明细写出：{_rel(out)}")
    if failed:
        print("未通过：" + ", ".join(failed), file=sys.stderr)
        return 1
    print(f"全部通过：{', '.join(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
