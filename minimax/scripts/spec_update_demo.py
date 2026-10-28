#!/usr/bin/env python3
"""规格变更演示（必做项 3 的后半句：更新规格并重新导入后，模块要用新内容）。

只改 `demo_project/specs/order_queries.md` 的 SPEC-212 一节，不碰实现与测试：
这正是「规格与实现出现偏差」的真实场景，模块的职责是把**最新规格**呈现出来。

    python scripts/spec_update_demo.py --bound 200      # 上界 100 → 200
    python scripts/spec_update_demo.py --restore        # 还原初始文本
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sddctx import config, ingest  # noqa: E402

SPEC_FILE = config.DEMO_ROOT / "specs" / "order_queries.md"
HEADING = "### SPEC-212"
BACKUP = config.RUNTIME_DIR / "spec_order_queries.original"


def _section(text: str) -> tuple[int, int]:
    start = text.index(HEADING)
    tail = text.find("\n### SPEC-", start + len(HEADING))
    return start, len(text) if tail == -1 else tail + 1


def update(bound: int) -> list[str]:
    text = SPEC_FILE.read_text(encoding="utf-8")
    if not BACKUP.exists():
        config.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP.write_text(text, encoding="utf-8")
    start, end = _section(text)
    section = text[start:end]
    replacements = [
        (r"1 <= page_size <= \d+", f"1 <= page_size <= {bound}"),
        (r"上界为 \d+", f"上界为 {bound}"),
        (r"(page_size upper bound, limit, )\d+", rf"\g<1>{bound}"),
    ]
    changed: list[str] = []
    for pattern, replacement in replacements:
        new_section, count = re.subn(pattern, replacement, section)
        if count:
            section = new_section
            changed.append(pattern)
    SPEC_FILE.write_text(text[:start] + section + text[end:], encoding="utf-8")
    return changed


def restore() -> bool:
    if not BACKUP.exists():
        current = SPEC_FILE.read_text(encoding="utf-8")
        if "<= 100" in current:
            print("规格本就是初始状态，无需还原")
            return False
        raise SystemExit(f"缺少备份 {BACKUP}，无法还原；请从 evidence/snapshots/initial/ 恢复")
    SPEC_FILE.write_text(BACKUP.read_text(encoding="utf-8"), encoding="utf-8")
    BACKUP.unlink()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="SPEC-212 上界变更演示")
    parser.add_argument("--bound", type=int, default=200, help="新上界（默认 200）")
    parser.add_argument("--restore", action="store_true", help="还原为初始规格文本")
    parser.add_argument("--no-ingest", action="store_true", help="改完不自动重新导入")
    args = parser.parse_args()

    if args.restore:
        done = restore()
        print("已还原 SPEC-212" if done else "SPEC-212 未处于变更状态")
    else:
        changed = update(args.bound)
        print(f"SPEC-212 已改写：{len(changed)} 处规则 → 上界 {args.bound}")

    if not args.no_ingest:
        stats = ingest.ingest_all(verbose=False)
        print(
            f"重新导入 seekdb：文档 {stats['documents']}"
            f"（新增 {stats.get('imported', 0)} / 未变 {stats.get('unchanged', 0)}）· 清理失效 {stats['pruned']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
