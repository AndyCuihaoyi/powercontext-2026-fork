"""快照与重置：验证样例的「初始数据」与「改后状态」都留在 evidence/ 里，仓库交付改前状态。"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path
from typing import Any

from . import config

APP_SUBDIR = "app"
INITIAL_DIR = config.SNAPSHOT_DIR / "initial"


def app_files(root: Path | None = None) -> list[Path]:
    base = (root or config.DEMO_ROOT) / APP_SUBDIR
    return sorted(path for path in base.glob("*.py"))


def snapshot_current(label: str) -> Path:
    target = config.SNAPSHOT_DIR / label
    target.mkdir(parents=True, exist_ok=True)
    for path in app_files():
        shutil.copy2(path, target / path.name)
    return target


def capture_initial(*, overwrite: bool = False) -> dict[str, Any]:
    """把 `demo_project/app/` 记为初始状态（evidence/snapshots/initial/，交付物的一部分）。"""

    target = INITIAL_DIR / APP_SUBDIR
    if target.exists() and not overwrite:
        return {"created": 0, "dir": str(target), "note": "已存在，未覆盖"}
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for path in app_files():
        shutil.copy2(path, target / path.name)
    return {"created": len(app_files()), "dir": str(target), "note": "写入初始快照"}


def restore_initial() -> list[str]:
    """回到改前状态：用初始快照覆盖 `demo_project/app/`（测试与规格本来就不该被动过）。"""

    source = INITIAL_DIR / APP_SUBDIR
    if not source.exists():
        raise FileNotFoundError(f"缺少初始快照：{source}")
    restored: list[str] = []
    for path in sorted(source.glob("*.py")):
        shutil.copy2(path, config.DEMO_ROOT / APP_SUBDIR / path.name)
        restored.append(f"{APP_SUBDIR}/{path.name}")
    for name in ("specs", "tests"):
        snap_source = INITIAL_DIR / name
        if not snap_source.exists():
            continue
        for path in sorted(snap_source.rglob("*")):
            if not path.is_file():
                continue
            target = config.DEMO_ROOT / name / path.relative_to(snap_source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            restored.append(target.relative_to(config.DEMO_ROOT).as_posix())
    return restored


def diff_against_initial() -> tuple[str, dict[str, bool]]:
    """用 difflib 生成统一差异（不是模型写的 diff，因此行号一定对得上）。"""

    import difflib

    source = INITIAL_DIR / APP_SUBDIR
    chunks: list[str] = []
    status: dict[str, bool] = {}
    for path in app_files():
        original = (source / path.name).read_text(encoding="utf-8").splitlines(keepends=True)
        current = path.read_text(encoding="utf-8").splitlines(keepends=True)
        same = filecmp.cmp(path, source / path.name, shallow=False)
        status[path.name] = same
        if same:
            continue
        diff = difflib.unified_diff(
            original,
            current,
            fromfile=f"a/demo_project/{APP_SUBDIR}/{path.name}",
            tofile=f"b/demo_project/{APP_SUBDIR}/{path.name}",
        )
        chunks.append("".join(diff))
    return "\n".join(chunks), status


def check_untouched(dirs: tuple[str, ...] = ("specs", "tests")) -> dict[str, list[str]]:
    """确认规格与测试目录没有被改过（A6 红线的机器可核对形式）。"""

    baseline = INITIAL_DIR
    changed: dict[str, list[str]] = {}
    for name in dirs:
        base = config.DEMO_ROOT / name
        snap = baseline / name
        dirty: list[str] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            counterpart = snap / path.relative_to(base)
            if not counterpart.exists() or not filecmp.cmp(path, counterpart, shallow=False):
                dirty.append(path.relative_to(config.DEMO_ROOT.parent).as_posix())
        changed[name] = dirty
    return changed


def snapshot_specs_and_tests() -> dict[str, Any]:
    """初始快照也要包含 specs/ 与 tests/，否则无法证明「测试集前后一致」。"""

    created = 0
    for name in ("specs", "tests"):
        source = config.DEMO_ROOT / name
        target = INITIAL_DIR / name
        target.mkdir(parents=True, exist_ok=True)
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            shutil.copy2(path, target / path.relative_to(source))
            created += 1
    return {"files": created, "dir": str(INITIAL_DIR)}
