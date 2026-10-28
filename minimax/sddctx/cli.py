"""命令行入口（题面 §2.3 允许 CLI/HTTP/MCP/插件；选 CLI 是为了干净环境可复现）。"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from . import agent, config, ingest, render, reset, retrieve, state, store


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        label = path.relative_to(config.ROOT)
    except ValueError:  # --out 指到项目外时只打印绝对路径
        label = path
    print(f"  写出 {label}")
    return path


def _evidence_md(path: Path, title: str, body: str) -> None:
    _write(path, f"# {title}\n\n生成命令：`{shlex.join(sys.argv)}`\n\n{body}\n")


# ---------------------------------------------------------------- ingest


def cmd_ingest(args: argparse.Namespace) -> int:
    if args.root:
        config.DEMO_ROOT = Path(args.root).resolve()
    print(f"导入 {config.DEMO_ROOT} → seekdb {config.SEEKDB_HOST}:{config.SEEKDB_PORT}/{config.SEEKDB_DATABASE}")
    stats = ingest.ingest_all(verbose=not args.quiet)
    print(
        f"完成：文档 {stats['documents']}（新增 {stats.get('imported', 0)} / 未变 {stats.get('unchanged', 0)}）"
        f" · 条目 {stats['items']} · 任务 {stats['tasks']} · 失效清理 {stats['pruned']}"
        f" · FULLTEXT 解析器 {stats['fts_parser']}"
    )
    if not args.no_evidence:
        counts = store.table_counts()
        docs = store.list_documents()
        schema = store.schema_evidence()
        _evidence_md(
            config.EVIDENCE_DIR / "db" / "schema.md",
            "seekdb 表结构与索引",
            f"连接：`{config.SEEKDB_HOST}:{config.SEEKDB_PORT}` · 库：`{config.SEEKDB_DATABASE}`\n\n"
            f"版本：`{store.ping().get('version', '')}`\n\n```sql\n{schema}\n```\n",
        )
        lines = ["| 表 | 行数 |", "| --- | --- |"] + [f"| `{k}` | {v} |" for k, v in counts.items()]
        lines += ["", "| 类型 | 文件 | 条目 | 文件摘要 |", "| --- | --- | --- | --- |"]
        lines += [f"| {row['kind']} | `{row['path']}` | {row['item_count']} | `{row['sha256'][:12]}` |" for row in docs]
        _evidence_md(config.EVIDENCE_DIR / "db" / "counts.md", "seekdb 资料入库统计", "\n".join(lines) + "\n")
    return 0


# ---------------------------------------------------------------- context


def cmd_context(args: argparse.Namespace) -> int:
    if args.root:
        config.DEMO_ROOT = Path(args.root).resolve()
    limits = {}
    for item in args.limit or []:
        key, _, value = item.partition("=")
        limits[key] = int(value)
    bundle = retrieve.build_bundle(args.task, with_state=args.with_state, limits=limits or None)
    check = retrieve.check_bundle(bundle)
    print(
        f"上下文包：规格 {len(bundle['applicable_specs'])} · 代码 {len(bundle['target_code'])}"
        f" · 测试 {len(bundle['verification_tests'])} · 回归名册 {len(bundle['regression_files'])}"
        f" · 状态记录 {len((bundle['task_state'] or {}).get('records', []))}"
    )
    print(f"来源回查：{check['sources']} 条，{'全部通过' if check['ok'] else '异常 ' + ', '.join(check['broken'])}")
    out = Path(args.out) if args.out else config.EVIDENCE_DIR / "context" / f"{args.task}{'.md' if args.format == 'md' else '.json'}"
    if args.format == "json":
        _write(out, render.to_json(bundle))
    elif args.format == "both":
        stem = out.with_suffix("")
        _write(stem.with_suffix(".md"), render.to_markdown(bundle))
        _write(stem.with_suffix(".json"), render.to_json(bundle))
    else:
        _write(out, render.to_markdown(bundle))
    if args.stdout:
        print(render.to_markdown(bundle) if args.format == "md" else render.to_json(bundle))
    return 0


# ---------------------------------------------------------------- state


def cmd_state(args: argparse.Namespace) -> int:
    if args.action == "save":
        records: list[dict[str, str]] = []
        for pair in args.record or []:
            kind, _, text = pair.partition("=")
            records.append({"kind": kind.strip(), "text": text.strip()})
        if args.auto:
            bundle = retrieve.build_bundle(args.task, with_state=False)
            records = state.auto_records(args.task, bundle) + records
        if not records:
            print("没有要写入的状态记录（用 --auto 或 --record kind=文本）", file=sys.stderr)
            return 2
        outcome = state.save(args.task, records)
        print(f"PowerContext 写入 {outcome['written']} 条 · scope `{outcome['scope_id']}`")
        print(f"  数据库 {outcome['database']} · artifact {outcome['artifact_id']}")
        for row in records:
            print(f"  - [{row['kind']}] {row['text'][:90]}")
        _write(
            config.EVIDENCE_DIR / "powercontext" / "state-write.md",
            json.dumps({"records": records, **outcome}, ensure_ascii=False, indent=2) + "\n",
        )
        return 0
    loaded = state.load_for_task(args.task)
    lines = [
        f"# PowerContext 状态读回 · {args.task}",
        "",
        f"- 后端：{loaded['backend']} v{loaded['version']}",
        f"- 数据库：`{loaded['database']}`（本次是**新进程**，只从文件读取）",
        f"- 作用域：`{loaded['scope_id']}` · key `{loaded['idempotency_key']}`",
        f"- 记录 {len(loaded['records'])} 条 · 按任务关键词排序命中 {len(loaded['ranked'])} 条",
        "",
    ]
    for row in loaded["ranked"]:
        lines.append(f"- 命中 `{row['kind']}`（score {row['score']}）：{row['text']}")
    lines.append("")
    lines.append("| kind | 记录 | artifact |")
    lines.append("| --- | --- | --- |")
    for row in loaded["records"]:
        lines.append(f"| {row['kind']} | {row['text']} | `{row['artifact_id']}` r{row['revision']} |")
    if args.out:
        _write(Path(args.out), "\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
    _write(config.EVIDENCE_DIR / "powercontext" / f"state-restart-read-{args.task}.md", "\n".join(lines) + "\n")
    return 0 if loaded["records"] else 1


# ---------------------------------------------------------------- test


def cmd_test(args: argparse.Namespace) -> int:
    rc, log = agent.run_tests(args.task)
    label = args.label or ("after" if args.record else "check")
    for line in log.splitlines():
        if line.startswith("=====") or line.startswith("rc="):
            print("  " + line)
    path = _write(config.EVIDENCE_DIR / "test-logs" / f"{label}-{args.task}.log", log)
    print(f"pytest 最坏返回码 rc={rc} · 日志 {path.relative_to(config.ROOT)}")
    return rc


def cmd_agent(args: argparse.Namespace) -> int:
    outcome = agent.run(
        args.task,
        rounds=args.rounds,
        replay=args.replay,
        dry_run=args.dry_run,
        reset_first=not args.keep_changes,
    )
    print(json.dumps({k: v for k, v in outcome.items() if k != "rounds"}, ensure_ascii=False, indent=2))
    return 0 if args.dry_run else (0 if outcome.get("rc") == 0 else 1)


def cmd_reset(args: argparse.Namespace) -> int:
    if args.capture_initial:
        info = reset.capture_initial(overwrite=True)
        extra = reset.snapshot_specs_and_tests()
        print(f"初始快照：{info['dir']}（实现 {info.get('created', 0)} 个 / 规格测试 {extra['files']} 个）")
        return 0
    if args.state:
        moved = state.reset_runtime()
        store.truncate_all()
        print(f"清空 PowerContext 状态：{', '.join(moved) or '本就是空'} · seekdb 记录已清空（随后重新导入）")
    restored = reset.restore_initial()
    print(f"已恢复实现文件：{', '.join(restored) or '无'}")
    untouched = reset.check_untouched()
    print(f"规格/测试与初始快照一致：{all(not v for v in untouched.values())}")
    if not args.no_reingest:
        print(f"重新导入 seekdb：{agent.ingest_and_report(args.task)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    argv = [sys.executable, str(config.ROOT / "scripts" / "verify_acceptance.py"), *args.items]
    if args.task:
        argv += ["--task", args.task]
    return subprocess.call(argv)


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sddctx", description="SDD 上下文管理模块")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default="", help="验证样例根目录（默认 minimax/demo_project）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", parents=[common], help="规格/代码/测试/任务 → seekdb（按 sha 增量、清理失效）")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--no-evidence", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("context", parents=[common], help="构造并落盘上下文包（只由 seekdb 查询结果组成）")
    p.add_argument("--task", required=True)
    p.add_argument("--format", choices=("md", "json", "both"), default="md")
    p.add_argument("--out", default="")
    p.add_argument("--stdout", action="store_true", help="同时打印到标准输出")
    p.add_argument("--with-state", action="store_true", help="注入 PowerContext 任务状态")
    p.add_argument("--limit", action="append", metavar="KIND=N", help="每类来源上限，如 spec=8")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("state", parents=[common], help="PowerContext 任务状态：save 写入 / show 新进程读回")
    p.add_argument("action", choices=("save", "show"))
    p.add_argument("--task", required=True)
    p.add_argument("--auto", action="store_true", help="从 seekdb 计数、上下文包、测试日志自动生成记录")
    p.add_argument("--record", action="append", metavar="KIND=TEXT", help="追加一条状态，如 todo=实现 since")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("test", parents=[common], help="跑目标/回归测试并把日志写进 evidence/test-logs/")
    p.add_argument("--task", required=True)
    p.add_argument("--suite", choices=("target", "regression", "all"), default="all")
    p.add_argument("--label", default="", help="日志前缀，如 before / after")
    p.add_argument("--record", action="store_true", help="未显式给 --label 时记为 after")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("agent", parents=[common], help="MiniMax 依据上下文包真实改写实现代码")
    p.add_argument("--task", required=True)
    p.add_argument("--rounds", type=int, default=2, help="失败回灌重试次数（默认 2）")
    p.add_argument("--replay", action="store_true", help="不调用 API，复现 evidence/minimax/<task>.jsonl")
    p.add_argument("--dry-run", action="store_true", help="只组装上下文与提示，不发请求")
    p.add_argument("--keep-changes", action="store_true", help="不从初始快照恢复，在当前状态上继续")
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("reset", parents=[common], help="回到验证样例初始状态")
    p.add_argument("--task", default="task-001")
    p.add_argument("--capture-initial", action="store_true", help="把当前状态记为初始快照")
    p.add_argument("--state", action="store_true", help="同时清空 PowerContext 状态与 seekdb 记录")
    p.add_argument("--no-reingest", action="store_true", help="恢复后不重新导入")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("verify", parents=[common], help="跑 scripts/verify_acceptance.py 的六项自检")
    p.add_argument("items", nargs="*", default=["all"])
    p.add_argument("--task", default="")
    p.set_defaults(func=cmd_verify)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config.ensure_dirs()
    if getattr(args, "root", ""):
        config.DEMO_ROOT = Path(args.root).resolve()
    try:
        return int(args.func(args))
    except store.StoreError as exc:
        print(f"数据库错误：{exc}", file=sys.stderr)
        return 3
    except state.StateError as exc:
        print(f"PowerContext 错误：{exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
