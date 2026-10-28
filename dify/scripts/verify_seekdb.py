#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

import pymysql

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


def main() -> int:
    load_env(ROOT / "gateway" / ".env")
    cfg = {
        "host": os.environ.get("SEEKDB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("SEEKDB_PORT", "2881")),
        "user": os.environ.get("SEEKDB_USER", "root"),
        "password": os.environ.get("SEEKDB_PASSWORD", ""),
    }
    report: dict[str, object] = {}
    with pymysql.connect(charset="utf8mb4", autocommit=True, **cfg) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW DATABASES")
            report["databases"] = sorted(row[0] for row in cur.fetchall())

        cur = conn.cursor()
        cur.execute("USE `dify`")
        cur.execute("SHOW TABLES")
        dify_tables = sorted(row[0] for row in cur.fetchall())
        report["dify_table_count"] = len(dify_tables)
        report["dify_core_tables"] = [t for t in dify_tables if t in {"apps", "workflows", "workflow_runs", "conversations", "messages", "accounts", "tenants"}]
        counts = {}
        for table in report["dify_core_tables"]:
            cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            counts[table] = cur.fetchone()[0]
        report["dify_row_counts"] = counts

        cur.execute("USE `pawnshop`")
        cur.execute("SHOW TABLES")
        report["pawnshop_tables"] = sorted(row[0] for row in cur.fetchall())
        cur.execute("SHOW INDEX FROM tickets")
        report["ticket_indexes"] = sorted({f"{row[2]}:{row[4]}" for row in cur.fetchall()})
        cur.execute("SELECT COUNT(*) FROM players")
        report["players"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tickets")
        report["tickets"] = cur.fetchone()[0]
        cur.execute("SELECT ticket_no, player_id, memory, value FROM tickets ORDER BY id DESC LIMIT 5")
        report["latest_tickets"] = [
            {"ticket_no": row[0], "player_id": row[1], "memory": row[2], "value": row[3]}
            for row in cur.fetchall()
        ]
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA='pawnshop' AND TABLE_NAME='tickets' AND INDEX_NAME='ft_ticket'"
        )
        has_ft = cur.fetchone()[0] > 0
        report["fulltext_index"] = has_ft
        if has_ft and report["tickets"]:
            cur.execute(
                "SELECT ticket_no, MATCH(memory, appraisal) AGAINST ('猫 记忆' IN NATURAL LANGUAGE MODE) AS score "
                "FROM tickets WHERE MATCH(memory, appraisal) AGAINST ('猫 记忆' IN NATURAL LANGUAGE MODE) LIMIT 5"
            )
            report["fulltext_probe"] = [{"ticket_no": row[0], "score": float(row[1])} for row in cur.fetchall()]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
