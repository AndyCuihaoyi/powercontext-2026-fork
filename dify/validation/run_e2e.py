#!/usr/bin/env python3
"""End-to-end validation for the Memory Pawnshop Dify app.

Runs the four player actions through Dify's workflow API, then checks the
seekdb ledger and PowerContext memory through the gateway. Evidence is written
as timestamped JSON/Markdown under dify/evidence/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class CheckError(RuntimeError):
    pass


def http_json(method: str, url: str, payload: dict | None = None, headers: dict | None = None, timeout: int = 180) -> dict:
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise CheckError(f"{method} {url} -> HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise CheckError(f"{method} {url} -> unreachable: {exc}") from exc
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        raise CheckError(f"{method} {url} returned non-JSON: {body[:300]}") from exc


def http_form(url: str, form: dict[str, str], timeout: int = 30) -> str:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise CheckError(f"POST {url} -> HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise CheckError(f"POST {url} -> unreachable: {exc}") from exc


def run_workflow(dify_base: str, api_key: str, player: str, action: str, content: str) -> tuple[dict, dict]:
    url = dify_base.rstrip("/") + "/v1/workflows/run"
    payload = {
        "inputs": {"player": player, "action": action, "content": content},
        "response_mode": "blocking",
        "user": f"validator-{player}",
    }
    result = http_json("POST", url, payload, {"Authorization": f"Bearer {api_key}"})
    data = result.get("data") or {}
    if data.get("status") != "succeeded":
        raise CheckError(f"workflow action {action} failed: {data.get('error') or result}")
    return data, data.get("outputs") or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dify-base", default=os.environ.get("DIFY_BASE", "http://127.0.0.1:5001"))
    parser.add_argument("--api-key", default=os.environ.get("DIFY_API_KEY", ""))
    parser.add_argument("--gateway-base", default=os.environ.get("GATEWAY_BASE", "http://127.0.0.1:8099"))
    parser.add_argument("--player", default="")
    parser.add_argument("--evidence-dir", default=str(Path(__file__).resolve().parent.parent / "evidence"))
    parser.add_argument("--cleanup", action="store_true", help="reset the validation player at the end")
    args = parser.parse_args()

    if not args.api_key:
        print("DIFY_API_KEY or --api-key is required (see scripts/publish_app.py)", file=sys.stderr)
        return 2

    stamp = time.strftime("%Y%m%d-%H%M%S")
    player = args.player or f"验证员{stamp[-6:]}"
    memory_text = "我把高中时偷偷看完的漫画藏进书包夹层，第二天数学考砸了。"
    redeem_keyword = "漫画"
    steps: list[dict[str, Any]] = []
    answers: dict[str, str] = {}

    def record(name: str, ok: bool, detail: str, answer: str = "") -> None:
        steps.append({"step": name, "ok": ok, "detail": detail})
        if answer:
            answers[name] = answer
        print(("PASS " if ok else "FAIL ") + name + (f" | {detail}" if detail else ""))

    try:
        health = http_json("GET", args.gateway_base.rstrip("/") + "/api/health")
        record(
            "gateway-health",
            health.get("gateway") == "ok" and health.get("seekdb") == "ok" and health.get("powercontext") == "ok",
            f"fulltext={health.get('fulltext')} players={health.get('players')} tickets={health.get('tickets')}",
        )

        _, out = run_workflow(args.dify_base, args.api_key, player, "典当", memory_text)
        pawn_answer = out.get("answer", "")
        ticket_match = re.search(r"当票编号\**\s*[：:]\s*(P\d{3,}-\d{3})", pawn_answer)
        record(
            "dify-pawn",
            bool(ticket_match) and "估价" in pawn_answer,
            f"ticket={ticket_match.group(1) if ticket_match else 'missing'}",
            pawn_answer,
        )
        if not ticket_match:
            raise CheckError("no ticket number in pawn answer")
        ticket_no = ticket_match.group(1)

        recall = http_form(args.gateway_base.rstrip("/") + "/api/recall", {"player": player, "query": redeem_keyword})
        record(
            "powercontext-recall",
            ticket_no in recall and "【长期记忆】" in recall and "长期记忆写入失败" not in recall,
            "seekdb ledger + PowerContext memory both recalled",
            recall,
        )

        _, out = run_workflow(args.dify_base, args.api_key, player, "赎回", redeem_keyword)
        redeem_answer = out.get("answer", "")
        record("dify-redeem-search", ticket_no in redeem_answer, f"ticket {ticket_no} surfaced", redeem_answer)

        _, out = run_workflow(args.dify_base, args.api_key, player, "确认赎回", ticket_no)
        confirm_answer = out.get("answer", "")
        record(
            "dify-redeem-confirm",
            "赎回回执" in confirm_answer and ticket_no in confirm_answer,
            "ticket redeemed and receipt returned",
            confirm_answer,
        )

        _, out = run_workflow(args.dify_base, args.api_key, player, "确认赎回", ticket_no)
        again_answer = out.get("answer", "")
        record("dify-redeem-idempotent", "已经赎回" in again_answer, "second confirm rejected", again_answer)

        _, out = run_workflow(args.dify_base, args.api_key, player, "查账", "-")
        ledger_answer = out.get("answer", "")
        record(
            "dify-ledger",
            "账本" in ledger_answer and ticket_no in ledger_answer,
            "ledger lists the ticket",
            ledger_answer,
        )

        if args.cleanup:
            cleanup_text = http_form(args.gateway_base.rstrip("/") + "/api/reset", {"player": player})
            record("cleanup", "已清空" in cleanup_text, cleanup_text[:120])
    except CheckError as exc:
        record("aborted", False, str(exc))

    ok = all(step["ok"] for step in steps)
    evidence = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "player": player,
        "dify_base": args.dify_base,
        "gateway_base": args.gateway_base,
        "memory_text": memory_text,
        "ok": ok,
        "steps": steps,
        "answers": answers,
    }
    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / f"e2e-{stamp}.json"
    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        f"# 端到端验证 {stamp}",
        "",
        f"- 玩家：{player}",
        f"- Dify：{args.dify_base}",
        f"- 结果：{'通过' if ok else '失败'}",
        "",
        "| 步骤 | 结果 | 说明 |",
        "|---|---|---|",
    ]
    for step in steps:
        md_lines.append(f"| {step['step']} | {'PASS' if step['ok'] else 'FAIL'} | {step['detail'].replace('|', '/')} |")
    md_path = evidence_dir / f"e2e-{stamp}.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": ok, "player": player, "json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
