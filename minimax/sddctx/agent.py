"""改造执行器：上下文包 → MiniMax → 白名单落盘 → pytest 验证 → 失败回灌重试。

对应必做项 2（MiniMax 实际参与）：每一次调用的请求与原始响应都追加进
`evidence/minimax/<task>.jsonl`，改后的代码由 `difflib` 生成补丁留在 `evidence/diffs/`。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import config, minimax_client, render, reset, retrieve, state, store

FILE_BLOCK = re.compile(r"<<<FILE\s+(?P<path>[^\n>]+?)\s*>>>\n(?P<body>.*?)\n<<<END FILE>>>", re.DOTALL)
MAX_FEEDBACK_CHARS = 4000


def parse_files(text: str) -> list[dict[str, str]]:
    return [{"path": m.group("path").strip(), "content": m.group("body")} for m in FILE_BLOCK.finditer(text)]


def validate_path(relative: str) -> tuple[bool, str]:
    """只允许 `demo_project/app/*.py`：测试与规格改了就判红线。"""

    cleaned = relative.lstrip("./")
    if ".." in Path(cleaned).parts:
        return False, "路径包含 .."
    if not cleaned.startswith(f"{config.DEMO_ROOT.name}/app/") or not cleaned.endswith(".py"):
        return False, f"不在白名单 {config.WRITABLE_PREFIXES} 内"
    target = config.ROOT / cleaned
    if not str(target.resolve()).startswith(str(config.ROOT.resolve())):
        return False, "解析后逃出样例根目录"
    return True, cleaned


def write_files(files: list[dict[str, str]]) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    for item in files:
        ok, value = validate_path(item["path"])
        if not ok:
            raise ValueError(f"模型返回了不允许修改的文件 {item['path']}：{value}")
        target = config.ROOT / value
        target.parent.mkdir(parents=True, exist_ok=True)
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(item["content"].rstrip() + "\n", encoding="utf-8")
        written.append({"path": value, "bytes": len(item["content"]), "existed": bool(before)})
    return written


def test_suites(task_id: str) -> list[tuple[str, list[str]]]:
    """目标用例 / 仅回归 / 全量：三段都跑，才能同时证明 A6 的两句话。"""

    tests = config.DEMO_ROOT / "tests"
    names = sorted(path.name for path in tests.glob("test_*.py"))
    stem = re.sub(r"[^0-9A-Za-z_]", "_", task_id)
    target = f"test_target_{stem}.py"
    suites: list[tuple[str, list[str]]] = []
    if target in names:
        suites.append(("target", [target]))
    regression = [name for name in names if name != target]
    if regression:
        suites.append(("regression", regression))
    suites.append(("full", names))
    return [(label, [f"demo_project/tests/{name}" for name in group]) for label, group in suites]


def run_tests(task_id: str) -> tuple[int, str]:
    """跑 pytest 并返回（最坏返回码, 分段日志）；日志由调用方写进 evidence/test-logs/。"""

    rc_worst = 0
    outputs: list[str] = []
    for label, paths in test_suites(task_id):
        cmd = [sys.executable, "-m", "pytest", "-q", *paths]
        proc = subprocess.run(cmd, cwd=config.ROOT, text=True, capture_output=True, check=False)
        rc_worst = max(rc_worst, proc.returncode)
        outputs.append(
            f"===== {label} =====\n$ {' '.join(cmd)}\nrc={proc.returncode}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return rc_worst, "\n\n".join(outputs) + "\n"


def target_rc(log: str) -> int:
    for line in log.splitlines():
        if line.startswith("rc="):
            return int(line[3:])
    return 1


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _replay_rounds(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"没有可复现的开发记录：{path}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def run(
    task_id: str,
    *,
    rounds: int = 2,
    replay: bool = False,
    dry_run: bool = False,
    reset_first: bool = True,
) -> dict[str, Any]:
    evidence_dir = config.EVIDENCE_DIR / "minimax"
    log_path = evidence_dir / f"{task_id}.jsonl"
    if reset_first:
        restored = reset.restore_initial()
        if restored:
            print(f"  回到改前状态：{', '.join(restored)}")
        store_outcome = ingest_and_report(task_id)
        print(f"  重新导入 seekdb：{store_outcome}")

    bundle = retrieve.build_bundle(task_id, with_state=True)
    messages = [
        {"role": "system", "content": minimax_client.SYSTEM_PROMPT},
        {"role": "user", "content": render.prompt_text(bundle)},
    ]
    # 上下文包与「实际发送的提示」同源写出，评审核对的是同一次调用的输入。
    ctx_dir = config.EVIDENCE_DIR / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    (ctx_dir / f"{task_id}-prompt.txt").write_text(messages[1]["content"], encoding="utf-8")
    (ctx_dir / f"{task_id}.md").write_text(render.to_markdown(bundle), encoding="utf-8")
    (ctx_dir / f"{task_id}.json").write_text(render.to_json(bundle), encoding="utf-8")
    print(f"  写出 evidence/context/{task_id}-prompt.txt（{len(messages[1]['content'])} 字符）")
    summary: dict[str, Any] = {
        "task_id": task_id,
        "context_sources": len(retrieve.all_sources(bundle)),
        "rounds": [],
        "written": [],
        "rc": None,
        "backend": "replay" if replay else ("dry-run" if dry_run else "minimax"),
    }
    if dry_run:
        sizes = {role: len(row["content"]) for role, row in [(m["role"], m) for m in messages]}
        summary["prompt_chars"] = sizes
        print(f"DRY-RUN：上下文 {sizes.get('user', 0)} 字符，来源 {summary['context_sources']} 条，未调用 MiniMax")
        return summary

    if replay:
        rows = _replay_rounds(log_path)
        contents = [row["response"]["content"] for row in rows]
    else:
        contents = []

    for index in range(1, max(rounds, len(contents)) + 1):
        if replay:
            if index > len(contents):
                break
            content = contents[index - 1]
            record = {"round": index, "replayed_from": str(log_path), "response": {"content": content}}
        else:
            started = time.perf_counter()
            response = minimax_client.chat(messages)
            record = {
                "round": index,
                "task_id": task_id,
                "created_at": response["created_at"],
                "model": response["model"],
                "endpoint": response["endpoint"],
                "elapsed_ms": response["elapsed_ms"],
                "usage": response["usage"],
                "request_id": response["request_id"],
                "finish_reason": response["finish_reason"],
                "messages": messages,
                "response": {"content": response["content"]},
            }
            _append_jsonl(log_path, record)
            content = response["content"]
            (evidence_dir / f"{task_id}-round-{index}.md").write_text(content, encoding="utf-8")

        files = parse_files(content)
        outcome = {"round": index, "files": [row["path"] for row in files]}
        try:
            written = write_files(files)
        except ValueError as exc:
            outcome.update({"error": str(exc), "rc": None})
            summary["rounds"].append(outcome)
            print(f"  第 {index} 轮拒绝落盘：{exc}")
            if replay:
                break
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"上一次输出不合法：{exc}。请只按协议重新输出整文件块。"})
            continue
        outcome["written"] = written
        rc, log = run_tests(task_id)
        outcome["rc"] = rc
        summary["rounds"].append(outcome)
        summary["written"].extend(written)
        print(f"  第 {index} 轮：落盘 {len(written)} 个文件 · pytest rc={rc}")
        if rc == 0:
            break
        if not replay and index < rounds:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": "测试仍未通过。下面是 pytest 输出，请只修改实现文件并继续按协议输出整文件块：\n"
                    + log[-MAX_FEEDBACK_CHARS:],
                }
            )
        if replay:
            break

    # 代码已变，索引必须跟上：否则后续 context 的回查会命中旧行区间
    summary["reingest"] = ingest_and_report(task_id)
    print(f"  改写后重新导入：{summary['reingest']}")

    patch, status = reset.diff_against_initial()
    (config.EVIDENCE_DIR / "diffs").mkdir(parents=True, exist_ok=True)
    patch_path = config.EVIDENCE_DIR / "diffs" / f"{task_id}.patch"
    patch_path.write_text(patch or "", encoding="utf-8")
    rc, log = run_tests(task_id)
    (config.EVIDENCE_DIR / "test-logs" / f"after-{task_id}.log").parent.mkdir(parents=True, exist_ok=True)
    (config.EVIDENCE_DIR / "test-logs" / f"after-{task_id}.log").write_text(log, encoding="utf-8")
    changed = [name for name, same in status.items() if not same]
    untouched = reset.check_untouched()
    summary.update(
        {
            "rc": rc,
            "patch": str(patch_path.relative_to(config.ROOT)),
            "changed_files": changed,
            "specs_tests_untouched": {k: v for k, v in untouched.items()},
        }
    )
    records = state.auto_records(
        task_id,
        bundle,
    ) + [
        {
            "kind": "verified",
            "text": f"[{task_id}] MiniMax {'复现' if replay else '改写'} {len(changed)} 个实现文件后 pytest rc={rc}",
        },
        {
            "kind": "done",
            "text": f"[{task_id}] 后端 {summary['backend']}；补丁 evidence/diffs/{task_id}.patch",
        },
    ]
    if not replay:
        try:
            saved = state.save(task_id, records)
            summary["powercontext_scope"] = saved["scope_id"]
        except state.StateError as exc:
            summary["powercontext_error"] = str(exc)
    print(f"  改动文件：{', '.join(changed) or '无'} · 补丁 {patch_path.relative_to(config.ROOT)}")
    print(f"  最终 pytest rc={rc} · 规格/测试未改动：{all(not v for v in untouched.values())}")
    return summary


def ingest_and_report(task_id: str) -> str:
    from . import ingest

    stats = ingest.ingest_all(verbose=False)
    return (
        f"文档 {stats['documents']}（新增 {stats.get('imported', 0)} / 未变 {stats.get('unchanged', 0)}）"
        f" · 条目 {stats['items']} · 清理 {stats['pruned']}"
    )
