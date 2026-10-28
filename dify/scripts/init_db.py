#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
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


def config() -> dict[str, object]:
    load_env(ROOT / "gateway" / ".env")
    return {
        "host": os.environ.get("SEEKDB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("SEEKDB_PORT", "2881")),
        "user": os.environ.get("SEEKDB_USER", "root"),
        "password": os.environ.get("SEEKDB_PASSWORD", ""),
        "database": os.environ.get("SEEKDB_DATABASE", "pawnshop"),
        "dify_db": os.environ.get("DIFY_DB_NAME", "dify"),
        "dify_plugin_db": os.environ.get("DIFY_PLUGIN_DB_NAME", "dify_plugin"),
    }


def quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def connect(cfg: dict[str, object], database: str | None = None) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=str(cfg["host"]),
        port=int(cfg["port"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def main() -> int:
    cfg = config()
    db_name = str(cfg["database"])
    with connect(cfg) as conn, conn.cursor() as cur:
        for meta_db in (str(cfg["dify_db"]), str(cfg["dify_plugin_db"])):
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {quote_ident(meta_db)} DEFAULT CHARACTER SET utf8mb4")
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {quote_ident(db_name)} DEFAULT CHARACTER SET utf8mb4")
        cur.execute(f"USE {quote_ident(db_name)}")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS players ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "name VARCHAR(64) NOT NULL UNIQUE,"
            "scope_id VARCHAR(64) NOT NULL DEFAULT '',"
            "scope_key VARCHAR(128) NOT NULL DEFAULT '',"
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS tickets ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "ticket_no VARCHAR(32) NOT NULL UNIQUE,"
            "player_id BIGINT NOT NULL,"
            "memory TEXT NOT NULL,"
            "appraisal MEDIUMTEXT NOT NULL,"
            "value INT NOT NULL DEFAULT 0,"
            "status VARCHAR(16) NOT NULL DEFAULT 'pawned',"
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "KEY idx_player (player_id))"
        )
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='players' AND COLUMN_NAME='scope_key'",
            (db_name,),
        )
        if cur.fetchone()[0] == 0:
            cur.execute("ALTER TABLE players ADD COLUMN scope_key VARCHAR(128) NOT NULL DEFAULT ''")
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='tickets' AND INDEX_NAME='ft_ticket'",
            (db_name,),
        )
        if cur.fetchone()[0] == 0:
            for clause in (
                "ALTER TABLE tickets ADD FULLTEXT KEY ft_ticket (memory, appraisal) WITH PARSER ik",
                "ALTER TABLE tickets ADD FULLTEXT KEY ft_ticket (memory, appraisal)",
            ):
                try:
                    cur.execute(clause)
                    print(f"fulltext index created: {clause}")
                    break
                except pymysql.MySQLError as exc:
                    print(f"fulltext attempt failed: {exc}", file=sys.stderr)
            else:
                print("fulltext index unavailable; gateway will fall back to LIKE", file=sys.stderr)
    print(f"seekdb ready: {cfg['host']}:{cfg['port']} "
          f"(dify={cfg['dify_db']}, dify_plugin={cfg['dify_plugin_db']}, pawnshop={db_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
