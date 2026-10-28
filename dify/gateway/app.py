#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin

import pymysql
from pymysql.cursors import DictCursor


ROOT = Path(__file__).resolve().parent
WEB_INDEX = ROOT.parent / "web" / "index.html"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Config:
    host: str = env("GATEWAY_HOST", "127.0.0.1")
    port: int = int(env("GATEWAY_PORT", "8099"))
    db_host: str = env("SEEKDB_HOST", "127.0.0.1")
    db_port: int = int(env("SEEKDB_PORT", "2881"))
    db_user: str = env("SEEKDB_USER", "root")
    db_password: str = env("SEEKDB_PASSWORD", "")
    db_name: str = env("SEEKDB_DATABASE", "pawnshop")
    pc_base_url: str = env("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/")
    pc_token: str = env("POWERCONTEXT_TOKEN", "")
    llm_mode: str = env("LLM_MODE", "mock").lower()
    llm_base_url: str = env("LLM_BASE_URL", "").rstrip("/")
    llm_api_key: str = env("LLM_API_KEY", "")
    llm_model: str = env("LLM_MODEL", "gpt-4o-mini")
    llm_timeout: int = int(env("LLM_TIMEOUT", "120"))
    dify_base_url: str = env("DIFY_BASE_URL", "").rstrip("/")
    dify_api_key: str = env("DIFY_API_KEY", "")
    dify_timeout: int = int(env("DIFY_TIMEOUT", "180"))
    request_timeout: int = int(env("REQUEST_TIMEOUT", "15"))


CFG = Config()


class GatewayError(Exception):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.status = status


def db_connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=CFG.db_host,
        port=CFG.db_port,
        user=CFG.db_user,
        password=CFG.db_password,
        database=CFG.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


_FULLTEXT_LOCK = threading.Lock()
_FULLTEXT_READY: bool | None = None


def has_fulltext() -> bool:
    global _FULLTEXT_READY
    with _FULLTEXT_LOCK:
        if _FULLTEXT_READY is not None:
            return _FULLTEXT_READY
        try:
            with db_connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='tickets' AND INDEX_NAME='ft_ticket'",
                    (CFG.db_name,),
                )
                _FULLTEXT_READY = int(cur.fetchone()["n"]) > 0
        except Exception:
            _FULLTEXT_READY = False
        return _FULLTEXT_READY


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
) -> Any:
    data = None
    merged = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged["Content-Type"] = "application/json"
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, data=data, headers=merged, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout or CFG.request_timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise GatewayError(f"upstream {url} returned HTTP {exc.code}: {detail}", 502) from exc
    except urllib.error.URLError as exc:
        raise GatewayError(f"upstream {url} is unreachable: {exc.reason}", 502) from exc
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise GatewayError(f"upstream {url} returned non-JSON content", 502) from exc


def pc_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CFG.pc_token}"} if CFG.pc_token else {}


def pc_scope_key(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:16]
    return f"pawnshop-player-{digest}"


def pc_create_scope(name: str, scope_key: str | None = None) -> str:
    payload = {
        "title": f"记忆当铺·{name}",
        "summary": f"记忆当铺玩家 {name} 的长期记忆：当票摘要、赎回线索与老板的印象。",
        "idempotency_key": scope_key or pc_scope_key(name),
    }
    result = _request_json("POST", f"{CFG.pc_base_url}/v1/scopes", payload, pc_headers())
    scope_id = result.get("scope_id") if isinstance(result, dict) else None
    if not scope_id:
        raise GatewayError("PowerContext did not return a scope_id", 502)
    return str(scope_id)


def pc_remember(scope_id: str, text: str, reason: str) -> None:
    payload = {"scope_id": scope_id, "kind": "decision", "text": text, "reason": reason}
    _request_json("POST", f"{CFG.pc_base_url}/v1/memory/remember", payload, pc_headers())


def pc_search(scope_id: str, query: str, limit: int = 8) -> list[str]:
    payload = {"scope_id": scope_id, "query": query or "当票 记忆", "limit": limit}
    result = _request_json("POST", f"{CFG.pc_base_url}/v1/memory/search", payload, pc_headers())
    hits = result.get("hits", []) if isinstance(result, dict) else []
    texts: list[str] = []
    for hit in hits:
        text = (hit.get("text") or "").strip()
        if text and text not in texts:
            texts.append(text)
    return texts


def ensure_player(name: str) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise GatewayError("player is required", 400)
    if len(name) > 32:
        raise GatewayError("player must be at most 32 characters", 400)
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT IGNORE INTO players (name, scope_id, scope_key) VALUES (%s, '', %s)",
            (name, pc_scope_key(name)),
        )
        cur.execute("SELECT id, name, scope_id, scope_key, created_at FROM players WHERE name=%s", (name,))
        row = cur.fetchone()
        if not row["scope_key"]:
            row["scope_key"] = pc_scope_key(name)
        try:
            scope_id = pc_create_scope(name, row["scope_key"])
        except GatewayError as exc:
            row["pc_error"] = str(exc)
            return row
        if scope_id != row["scope_id"]:
            cur.execute("UPDATE players SET scope_id=%s, scope_key=%s WHERE id=%s", (scope_id, row["scope_key"], row["id"]))
            row["scope_id"] = scope_id
        return row


def ticket_count(player_id: int) -> int:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM tickets WHERE player_id=%s", (player_id,))
        return int(cur.fetchone()["n"])


def recent_tickets(player_id: int, limit: int = 5) -> list[dict[str, Any]]:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ticket_no, memory, appraisal, value, status, created_at "
            "FROM tickets WHERE player_id=%s ORDER BY id DESC LIMIT %s",
            (player_id, limit),
        )
        return list(cur.fetchall())


def search_tickets(player_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    with db_connect() as conn, conn.cursor() as cur:
        if has_fulltext():
            try:
                cur.execute(
                    "SELECT ticket_no, memory, appraisal, value, status, created_at, "
                    "MATCH(memory, appraisal) AGAINST (%s IN NATURAL LANGUAGE MODE) AS score "
                    "FROM tickets WHERE player_id=%s "
                    "AND MATCH(memory, appraisal) AGAINST (%s IN NATURAL LANGUAGE MODE) "
                    "ORDER BY score DESC LIMIT %s",
                    (query, player_id, query, limit),
                )
                rows = list(cur.fetchall())
                if rows:
                    return rows
            except pymysql.MySQLError:
                pass
        like = f"%{query}%"
        cur.execute(
            "SELECT ticket_no, memory, appraisal, value, status, created_at, 0 AS score "
            "FROM tickets WHERE player_id=%s AND (memory LIKE %s OR appraisal LIKE %s) "
            "ORDER BY id DESC LIMIT %s",
            (player_id, like, like, limit),
        )
        return list(cur.fetchall())


def next_ticket_no(player_id: int) -> str:
    seq = ticket_count(player_id) + 1
    return f"P{player_id:03d}-{seq:03d}"


def parse_value(appraisal: str, name: str, memory: str) -> int:
    match = re.search(r"估价\**\s*[：:]\s*\**\s*(\d{1,4})", appraisal)
    if match:
        return max(1, min(9999, int(match.group(1))))
    digest = hashlib.sha1(f"{name}|{memory}".encode("utf-8")).hexdigest()
    return 7 + int(digest[:4], 16) % 993


def short(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize_appraisal(appraisal: str) -> str:
    title = re.search(r"##\s*当票[^\n]*", appraisal)
    comment = re.search(r"老板批注\**\s*[：:]\s*(.+)", appraisal)
    parts = []
    if title:
        parts.append(title.group(0).lstrip("# ").strip())
    if comment:
        parts.append(comment.group(1).strip())
    if parts:
        return short("；".join(parts), 180)
    return short(appraisal, 180)


def fmt_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def pc_search_safe(scope_id: str, query: str, limit: int = 8) -> tuple[list[str], str]:
    if not scope_id:
        return [], "长期记忆作用域尚未建立，本次只查账本"
    try:
        return pc_search(scope_id, query, limit), ""
    except GatewayError as exc:
        return [], f"长期记忆暂不可用：{exc}"


def format_recall(player: dict[str, Any], query: str) -> str:
    tickets = recent_tickets(player["id"], 5)
    memories, warning = pc_search_safe(player["scope_id"], query, 8)
    lines = [
        f"【玩家】{player['name']}",
        f"【光临次数】{ticket_count(player['id'])} 次典当",
    ]
    if tickets:
        lines.append("【最近当票】")
        for ticket in tickets:
            lines.append(
                f"- {ticket['ticket_no']} | {fmt_time(ticket['created_at'])} | "
                f"{ticket['value']} 回忆币 | {short(ticket['memory'], 70)}"
            )
    else:
        lines.append("【最近当票】暂无，这是第一次光临。")
    if memories:
        lines.append("【长期记忆】")
        for memory in memories:
            lines.append(f"- {short(memory, 120)}")
    else:
        lines.append("【长期记忆】还没有留下印象。")
    if warning:
        lines.append(f"【提示】{warning}")
    return "\n".join(lines)


def format_ticket(ticket_no: str, value: int, appraisal: str) -> str:
    return (
        f"{appraisal.strip()}\n\n"
        "---\n"
        f"**当票编号**：{ticket_no}　|　**估价**：{value} 回忆币　|　**状态**：已入库\n\n"
        "> 老板把这张当票记进了账本，也记进了脑子。下次报上名号，他会想起来的。"
    )


def handle_recall(payload: dict[str, Any]) -> str:
    player = ensure_player(str(payload.get("player", "")))
    query = str(payload.get("query", "")).strip()
    return format_recall(player, query)


def handle_pawn(payload: dict[str, Any]) -> str:
    player = ensure_player(str(payload.get("player", "")))
    memory = str(payload.get("memory", "")).strip()
    appraisal = str(payload.get("appraisal", "")).strip()
    if not memory:
        raise GatewayError("memory is required", 400)
    if not appraisal:
        raise GatewayError("appraisal is required", 400)
    value = parse_value(appraisal, player["name"], memory)
    ticket_no = next_ticket_no(player["id"])
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tickets (ticket_no, player_id, memory, appraisal, value) "
            "VALUES (%s, %s, %s, %s, %s)",
            (ticket_no, player["id"], memory, appraisal, value),
        )
    warning = ""
    if player["scope_id"]:
        try:
            pc_remember(
                player["scope_id"],
                f"【当票 {ticket_no}】{player['name']} 典当了记忆：{short(memory, 160)}"
                f" 估价 {value} 回忆币。{summarize_appraisal(appraisal)}",
                f"记忆当铺·当票 {ticket_no}",
            )
        except GatewayError as exc:
            warning = f"\n\n> 注意：长期记忆写入失败（{exc}），本张当票只记入了账本。"
    else:
        reason = player.get("pc_error") or "PowerContext 不可用"
        warning = f"\n\n> 注意：长期记忆服务暂不可用（{reason}），本张当票只记入了账本。"
    return format_ticket(ticket_no, value, appraisal) + warning


STATUS_LABELS = {"pawned": "在库", "redeemed": "已赎回"}


def format_hits(hits: list[dict[str, Any]]) -> str:
    lines = []
    for hit in hits:
        status = STATUS_LABELS.get(str(hit.get("status", "")), str(hit.get("status", "")))
        lines.append(
            f"- {hit['ticket_no']} | {fmt_time(hit['created_at'])} | "
            f"{hit['value']} 回忆币 | 状态：{status} | 记忆：{short(hit['memory'], 80)} | "
            f"批注：{short(hit['appraisal'], 80)}"
        )
    return "\n".join(lines)


def handle_redeem(payload: dict[str, Any]) -> str:
    player = ensure_player(str(payload.get("player", "")))
    keyword = str(payload.get("keyword", "")).strip()
    hits = search_tickets(player["id"], keyword, 3)
    memories, warning = pc_search_safe(player["scope_id"], keyword, 6) if keyword else ([], "")
    lines = [f"【赎回检索】玩家：{player['name']}　关键词：{keyword or '（未填写）'}"]
    if hits:
        lines.append("【账本命中】")
        lines.append(format_hits(hits))
    else:
        lines.append("【账本命中】没有找到完全对应的当票。")
    if memories:
        lines.append("【长期记忆命中】")
        for memory in memories:
            lines.append(f"- {short(memory, 140)}")
    if warning:
        lines.append(f"【提示】{warning}")
    return "\n".join(lines)


def handle_redeem_confirm(payload: dict[str, Any]) -> str:
    player = ensure_player(str(payload.get("player", "")))
    ticket_no = str(payload.get("ticket_no", "")).strip().upper()
    if not ticket_no:
        raise GatewayError("ticket_no is required", 400)
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, ticket_no, memory, appraisal, value, status FROM tickets "
            "WHERE player_id=%s AND ticket_no=%s",
            (player["id"], ticket_no),
        )
        ticket = cur.fetchone()
        if not ticket:
            return (
                f"老板翻了半天账本，抬头说：{player['name']} 名下没有编号 {ticket_no} 的当票。\n"
                "先用「赎回」查一查，再拿准确的当票编号来。"
            )
        if ticket["status"] == "redeemed":
            return (
                f"当票 {ticket_no} 已经赎回去了。老板耸耸肩："
                "一张记忆不能赎两次，不然人会活得太满。"
            )
        cur.execute("UPDATE tickets SET status='redeemed' WHERE id=%s", (ticket["id"],))
    warning = ""
    if player["scope_id"]:
        try:
            pc_remember(
                player["scope_id"],
                f"【赎回 {ticket_no}】{player['name']} 赎回了记忆：{short(ticket['memory'], 160)}。"
                f"{summarize_appraisal(ticket['appraisal']).rstrip('。；; ')}",
                f"记忆当铺·赎回 {ticket_no}",
            )
        except GatewayError as exc:
            warning = f"\n\n> 注意：长期记忆写入失败（{exc}），账本状态已更新。"
    else:
        reason = player.get("pc_error") or "PowerContext 不可用"
        warning = f"\n\n> 注意：长期记忆服务暂不可用（{reason}），账本状态已更新。"
    return (
        f"## 赎回回执 · {ticket_no}\n\n"
        f"**记忆**：{ticket['memory']}\n\n"
        f"**老板交货**：{summarize_appraisal(ticket['appraisal'])}\n\n"
        f"**账面估价**：{ticket['value']} 回忆币（概不退款，回忆也不退）\n\n"
        "> 老板把记忆推回你手里：拿好，别弄丢。下次再当，押金可要翻倍了。"
        + warning
    )


def handle_ledger(payload: dict[str, Any]) -> str:
    player = ensure_player(str(payload.get("player", "")))
    tickets = recent_tickets(player["id"], 10)
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(value), 0) AS total FROM tickets WHERE player_id=%s",
            (player["id"],),
        )
        summary = cur.fetchone()
    lines = [
        f"【记忆当铺·账本】玩家：{player['name']}",
        f"【累计典当】{int(summary['n'])} 张当票　|　【账本估值】{int(summary['total'])} 回忆币",
    ]
    if not tickets:
        lines.append("账本还是空的。先典当一段记忆，老板才有东西可记。")
        return "\n".join(lines)
    lines.append("【最近十张】")
    for t in tickets:
        status = STATUS_LABELS.get(str(t.get("status", "")), str(t.get("status", "")))
        lines.append(
            f"- {t['ticket_no']} | {fmt_time(t['created_at'])} | {t['value']} 回忆币 | "
            f"{status} | {short(t['memory'], 70)}"
        )
    return "\n".join(lines)


def handle_reset(payload: dict[str, Any]) -> str:
    name = str(payload.get("player", "")).strip()
    if not name:
        raise GatewayError("player is required", 400)
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM players WHERE name=%s", (name,))
        row = cur.fetchone()
        if not row:
            return f"玩家 {name} 不在账本里，无需重置。"
        cur.execute("DELETE FROM tickets WHERE player_id=%s", (row["id"],))
        scope_key = f"{pc_scope_key(name)}-{uuid.uuid4().hex[:8]}"
        try:
            scope_id = pc_create_scope(name, scope_key)
        except GatewayError as exc:
            return f"已清空 {name} 的当票；但长期记忆作用域轮换失败（{exc}），旧记忆仍留在原作用域。"
        cur.execute("UPDATE players SET scope_id=%s, scope_key=%s WHERE id=%s", (scope_id, scope_key, row["id"]))
    return f"已清空 {name} 的当票，并启用新的记忆作用域。"


def mock_value(memory: str) -> int:
    return 7 + int(hashlib.sha1(memory.encode("utf-8")).hexdigest()[:4], 16) % 993


def mock_title(memory: str) -> str:
    mapping = [
        (("猫",), "《一只被重新上色的猫》"),
        (("老板", "领导", "同事"), "《关于老板的两三件小事》"),
        (("考试", "答辩", "面试"), "《那次差点改变人生的走神》"),
        (("梦", "梦见"), "《一个不肯醒的梦》"),
        (("分手", "失恋", "前任"), "《过期的晚安》"),
        (("钱", "工资", "奖金", "彩票"), "《那笔没到账的钱》"),
        (("游戏", "存档", "开黑"), "《存档里的另一个我》"),
        (("旅行", "旅游", "海边"), "《一张没寄出的明信片》"),
    ]
    for words, title in mapping:
        if any(word in memory for word in words):
            return title
    suffix = int(hashlib.sha1(memory.encode("utf-8")).hexdigest()[4:6], 16) % 97
    return f"《无人认领的记忆·第{suffix}号》"


def mock_comment(memory: str, visits: int, value: int) -> str:
    options = [
        f"这段记忆的荒诞程度刚好卡在「值得收藏」和「建议报警」之间，我给你 {value} 回忆币，不能再多了。",
        "品相一般，但情绪浓度很高。放进柜台第三天就会自己发光，属于当铺最喜欢的类型。",
        "我见过更离谱的，但那是在上个世纪。你这单，勉强算本月最佳。",
        f"估值 {value} 回忆币。别嫌少，回忆这东西的利息从来不是按钱算的。",
        "你把它当掉的时候笑了，说明它还没真正过去。这种货，我收。",
        "记忆本身不值钱，值钱的是你讲它时停顿的那半秒。",
    ]
    if visits > 1:
        options.append(f"你又来了。上次那张当票还在柜台里发烫，这张我算你 {value} 回忆币，老客价。")
    index = int(hashlib.sha1(f"{memory}{visits}".encode("utf-8")).hexdigest()[6:8], 16) % len(options)
    return options[index]


def mock_pawn(messages: list[dict[str, Any]]) -> str:
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    player_match = re.search(r"玩家[：:]\s*(.+)", user)
    memory_match = re.search(r"记忆[：:]\s*(.+)", user)
    player = (player_match.group(1).strip() if player_match else "无名氏")[:32]
    memory = (memory_match.group(1).strip() if memory_match else "一段没有说出口的记忆")[:400]
    visits_match = re.search(r"光临次数】(\d+)", user)
    visits = int(visits_match.group(1)) if visits_match else 1
    value = mock_value(memory)
    title = mock_title(memory)
    comment = mock_comment(memory, visits, value)
    return (
        f"## 当票 · {title}\n\n"
        f"**典当人**：{player}\n\n"
        f"**典当物**：{memory}\n\n"
        f"**老板批注**：{comment}\n\n"
        f"**估价**：{value} 回忆币\n\n"
        f"**柜台暗号**：{hashlib.sha1(memory.encode('utf-8')).hexdigest()[:6]}"
    )


def mock_redeem(messages: list[dict[str, Any]]) -> str:
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    player_match = re.search(r"玩家[：:]\s*(.+)", user)
    keyword_match = re.search(r"关键词[：:]\s*(.+)", user)
    player = (player_match.group(1).strip() if player_match else "无名氏")[:32]
    keyword = (keyword_match.group(1).strip() if keyword_match else "那张当票")[:80]
    ticket_match = re.search(r"- (P\d{3}-\d{3}) \|", user)
    if not ticket_match:
        return (
            f"老板翻了半天账本，抬头看你：「{player}，账本里没有和『{keyword}』对得上的当票。"
            "是你记错了，还是那段记忆自己跑了？」"
        )
    ticket_no = ticket_match.group(1)
    if re.search(r"- " + re.escape(ticket_no) + r" \|[^\n]*状态：已赎回", user):
        return (
            f"老板把 {ticket_no} 翻过来给你看背面的红章：「『{keyword}』这张已经赎回去了，"
            "一张记忆不能赎两次。要不，再典当点别的？」"
        )
    return (
        f"老板把一张发黄的当票拍在柜台上：「{ticket_no}，『{keyword}』。"
        f"你当初把它当给我，利息是——下次讲起它的时候，不许再笑。"
        "确认赎回的话，就把这段记忆重新认领回去；不确认，它继续在柜台里发热。」"
    )


def mock_reply(messages: list[dict[str, Any]]) -> str:
    joined = "\n".join(str(m.get("content", "")) for m in messages)
    if "模式=赎回" in joined or "模式：赎回" in joined:
        return mock_redeem(messages)
    return mock_pawn(messages)


def llm_chat(messages: list[dict[str, Any]], temperature: float, max_tokens: int) -> str:
    if CFG.llm_mode == "mock":
        return mock_reply(messages)
    if CFG.llm_mode != "openai":
        raise GatewayError(f"unsupported LLM_MODE: {CFG.llm_mode}", 500)
    if not CFG.llm_base_url:
        raise GatewayError("LLM_BASE_URL is required when LLM_MODE=openai", 500)
    url = CFG.llm_base_url
    if not url.endswith("/chat/completions"):
        url = urljoin(url + "/", "chat/completions")
    headers = {}
    if CFG.llm_api_key:
        headers["Authorization"] = f"Bearer {CFG.llm_api_key}"
    payload = {
        "model": CFG.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    result = _request_json("POST", url, payload, headers, CFG.llm_timeout)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GatewayError("model response did not contain choices[0].message.content", 502) from exc
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise GatewayError("model returned empty content", 502)
    return content.strip()


def handle_llm(payload: dict[str, Any]) -> str:
    if "system" in payload or "user" in payload:
        cleaned = []
        if str(payload.get("system", "")).strip():
            cleaned.append({"role": "system", "content": str(payload["system"])})
        cleaned.append({"role": "user", "content": str(payload.get("user", ""))})
        temperature = float(payload.get("temperature", 0.9))
        max_tokens = int(payload.get("max_tokens", 900))
        return llm_chat(cleaned, temperature, max_tokens)
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise GatewayError("messages must be a non-empty array", 400)
    cleaned = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        cleaned.append({"role": role, "content": content})
    if not cleaned:
        raise GatewayError("messages must contain at least one object", 400)
    temperature = float(payload.get("temperature", 0.9))
    max_tokens = int(payload.get("max_tokens", 900))
    return llm_chat(cleaned, temperature, max_tokens)


def handle_run(payload: dict[str, Any]) -> str:
    """Proxy the player action to the published Dify workflow.

    Keeps the Dify service API key on the server; the browser only talks to
    this gateway.
    """
    if not CFG.dify_base_url or not CFG.dify_api_key:
        raise GatewayError("DIFY_BASE_URL and DIFY_API_KEY are not configured", 500)
    player = str(payload.get("player", "")).strip()
    action = str(payload.get("action", "典当")).strip() or "典当"
    content = str(payload.get("content", "")).strip()
    if not player:
        raise GatewayError("player is required", 400)
    if action not in ("典当", "赎回", "确认赎回", "查账"):
        raise GatewayError("unsupported action", 400)
    if action in ("典当", "赎回", "确认赎回") and not content:
        raise GatewayError("content is required for this action", 400)
    request = {
        "inputs": {"player": player[:32], "action": action, "content": content[:600] or "-"},
        "response_mode": "blocking",
        "user": f"web-{player[:24]}",
    }
    result = _request_json(
        "POST",
        f"{CFG.dify_base_url}/v1/workflows/run",
        request,
        {"Authorization": f"Bearer {CFG.dify_api_key}"},
        CFG.dify_timeout,
    )
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, dict):
        raise GatewayError("Dify returned an unexpected response", 502)
    if data.get("status") != "succeeded":
        raise GatewayError(f"Dify workflow failed: {data.get('error') or 'unknown error'}", 502)
    answer = (data.get("outputs") or {}).get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise GatewayError("Dify workflow returned no answer", 502)
    return answer


ROUTES = {
    "/api/recall": handle_recall,
    "/api/pawn": handle_pawn,
    "/api/redeem": handle_redeem,
    "/api/redeem_confirm": handle_redeem_confirm,
    "/api/ledger": handle_ledger,
    "/api/reset": handle_reset,
    "/api/llm": handle_llm,
    "/api/run": handle_run,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "MemoryPawnshopGateway/1.0"
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin", "")
        allowed = {f"http://127.0.0.1:{CFG.port}", f"http://localhost:{CFG.port}"}
        if origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _read_payload(self) -> dict[str, Any]:
        if self.headers.get("Content-Length") in (None, "0"):
            return {}
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2 * 1024 * 1024:
            raise GatewayError("request body too large", 413)
        raw = self.rfile.read(length)
        charset = "utf-8"
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("application/x-www-form-urlencoded"):
            parsed = parse_qs(raw.decode(charset, errors="replace"), keep_blank_values=True)
            return {key: values[-1] for key, values in parsed.items()}
        try:
            payload = json.loads(raw.decode(charset))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayError("request body must be valid JSON or form data", 400) from exc
        if not isinstance(payload, dict):
            raise GatewayError("request body must be a JSON object", 400)
        return payload

    def do_OPTIONS(self) -> None:
        self._send(204, "", "text/plain")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if WEB_INDEX.exists():
                self._send(200, WEB_INDEX.read_text(encoding="utf-8"), "text/html")
            else:
                self._send(404, json.dumps({"error": "web/index.html not found"}), "application/json")
            return
        if path == "/api/health":
            self._send(200, json.dumps(health(), ensure_ascii=False), "application/json")
            return
        self._send(404, json.dumps({"error": "unknown path"}), "application/json")

    def do_POST(self) -> None:
        started = time.time()
        path = self.path.split("?", 1)[0]
        handler = ROUTES.get(path)
        if handler is None:
            self._send(404, json.dumps({"error": "unknown path", "path": path}), "application/json")
            return
        try:
            payload = self._read_payload()
            body = handler(payload)
            self._send(200, body, "text/plain")
        except GatewayError as exc:
            self._send(exc.status, str(exc), "text/plain")
        except pymysql.MySQLError as exc:
            self._send(500, f"seekdb error: {exc}", "text/plain")
        except Exception as exc:
            self._send(500, f"gateway error: {exc}", "text/plain")
        finally:
            elapsed = (time.time() - started) * 1000
            print(f"{datetime.now().isoformat(timespec='seconds')} POST {path} {elapsed:.0f}ms", flush=True)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


def health() -> dict[str, Any]:
    result: dict[str, Any] = {"gateway": "ok", "llm_mode": CFG.llm_mode, "seekdb": "ok", "powercontext": "ok"}
    result["dify_proxy"] = bool(CFG.dify_base_url and CFG.dify_api_key)
    result["web"] = WEB_INDEX.exists()
    try:
        with db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM players")
            result["players"] = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM tickets")
            result["tickets"] = int(cur.fetchone()["n"])
            result["fulltext"] = has_fulltext()
    except Exception as exc:
        result["seekdb"] = f"error: {exc}"
    try:
        with urllib.request.urlopen(f"{CFG.pc_base_url}/health/live", timeout=5) as response:
            result["powercontext_status"] = response.status
    except Exception as exc:
        result["powercontext"] = f"error: {exc}"
    return result


def main() -> None:
    server = ThreadingHTTPServer((CFG.host, CFG.port), Handler)
    server.daemon_threads = True
    print(
        f"memory pawnshop gateway listening on http://{CFG.host}:{CFG.port} "
        f"(seekdb {CFG.db_host}:{CFG.db_port}/{CFG.db_name}, pc {CFG.pc_base_url}, llm {CFG.llm_mode})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
