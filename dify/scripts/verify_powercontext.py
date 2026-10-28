#!/usr/bin/env python3
"""Verify the PowerContext leg: scope creation, memory write, Chinese search."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request(base: str, method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def main() -> int:
    load_env(ROOT / "gateway" / ".env")
    base = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000")
    token = os.environ.get("POWERCONTEXT_TOKEN", "")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = uuid.uuid4().hex[:8]
    marker = f"验证标记-{run_id}"
    text = f"{marker}：客人在当铺验证了「记忆当票」的跨请求召回，关键词是青花瓷猫。"

    report: dict[str, object] = {"base": base, "run_id": run_id}
    report["health_live"] = request(base, "GET", "/health/live")
    report["health_ready"] = request(base, "GET", "/health/ready")

    scope = request(
        base,
        "POST",
        "/v1/scopes",
        {
            "title": f"记忆当铺·验证 {stamp}",
            "summary": "自动化验证用作用域，可安全删除。",
            "idempotency_key": f"pawnshop-verify-{run_id}",
        },
        token,
    )
    scope_id = scope.get("scope_id", "")
    if not scope_id:
        raise RuntimeError(f"scope response has no scope_id: {scope}")
    report["scope_id"] = scope_id

    request(
        base,
        "POST",
        "/v1/memory/remember",
        {"scope_id": scope_id, "kind": "decision", "text": text, "reason": "端到端验证"},
        token,
    )

    hits = request(base, "POST", "/v1/memory/search", {"scope_id": scope_id, "query": "青花瓷猫", "limit": 5}, token)
    texts = [hit.get("text", "") for hit in hits.get("hits", [])]
    report["search_hits"] = len(texts)
    report["hit_contains_marker"] = any(marker in item for item in texts)
    report["hit_texts"] = texts[:3]
    report["ok"] = bool(report["hit_contains_marker"])

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
