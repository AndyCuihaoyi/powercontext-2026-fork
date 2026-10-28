"""运行时配置：全部来自环境变量，密钥不写入仓库（见 README「配置」）。"""

from __future__ import annotations

import os
from pathlib import Path

def _path(name: str, default: Path) -> Path:
    """空字符串等于「没设置」：.env.example 里的占位空值不该把路径变成 `.`。"""

    value = os.environ.get(name, "").strip()
    return Path(value).resolve() if value else default


ROOT = _path("SDDCTX_ROOT", Path(__file__).resolve().parent.parent)
DEMO_ROOT = _path("SDDCTX_DEMO_ROOT", ROOT / "demo_project")
RUNTIME_DIR = _path("SDDCTX_RUNTIME_DIR", ROOT / "runtime")
EVIDENCE_DIR = _path("SDDCTX_EVIDENCE_DIR", ROOT / "evidence")
SNAPSHOT_DIR = EVIDENCE_DIR / "snapshots"

SEEKDB_HOST = os.environ.get("SDDCTX_SEEKDB_HOST", "127.0.0.1")
SEEKDB_PORT = int(os.environ.get("SDDCTX_SEEKDB_PORT", "2893"))
SEEKDB_USER = os.environ.get("SDDCTX_SEEKDB_USER", "root")
SEEKDB_PASSWORD = os.environ.get("SDDCTX_SEEKDB_PASSWORD", "")
SEEKDB_DATABASE = os.environ.get("SDDCTX_SEEKDB_DATABASE", "sdd_eco")
SEEKDB_CONNECT_TIMEOUT = int(os.environ.get("SDDCTX_SEEKDB_CONNECT_TIMEOUT", "8"))

# seekdb FULLTEXT 解析器；`ik` 不可用时自动回退默认解析器（见 store._fulltext_ddl）。
SEEKDB_FTS_PARSER = os.environ.get("SDDCTX_FTS_PARSER", "ik")

POWERCONTEXT_DB = _path("SDDCTX_PC_DB", RUNTIME_DIR / "powercontext" / "state.db")
POWERCONTEXT_SCOPE_KEY_PREFIX = os.environ.get("SDDCTX_PC_PREFIX", "sddctx")

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M3.1-Flash")
MINIMAX_TIMEOUT = float(os.environ.get("MINIMAX_TIMEOUT", "180"))
MINIMAX_MAX_TOKENS = int(os.environ.get("MINIMAX_MAX_TOKENS", "16000"))
MINIMAX_TEMPERATURE = float(os.environ.get("MINIMAX_TEMPERATURE", "0.1"))

CONTEXT_LIMITS = {
    "spec": int(os.environ.get("SDDCTX_LIMIT_SPEC", "8")),
    "code": int(os.environ.get("SDDCTX_LIMIT_CODE", "8")),
    "test": int(os.environ.get("SDDCTX_LIMIT_TEST", "8")),
}

# 代码修改只允许作用在这些相对路径前缀上（红线：不得改测试与规格）。
WRITABLE_PREFIXES = ("demo_project/app/",)
READABLE_ROOTS = ("demo_project/specs/", "demo_project/app/", "demo_project/tests/", "demo_project/tasks/")

QUERY_LOG_TABLE = "sdd_query_log"


def ensure_dirs() -> None:
    for path in (RUNTIME_DIR, EVIDENCE_DIR, POWERCONTEXT_DB.parent):
        path.mkdir(parents=True, exist_ok=True)


def minimax_configured() -> bool:
    return bool(MINIMAX_API_KEY)
