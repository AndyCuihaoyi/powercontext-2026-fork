"""seekdb 存储层：工程资料（规格/代码/测试/任务）落库、建全文索引、检索、查询留痕。

上下文包的每一条来源都来自本模块的 SELECT 结果，而不是磁盘文件遍历
（磁盘只在「来源可回查校验」时用于核对行区间）。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import pymysql
import pymysql.cursors

from . import config


class StoreError(RuntimeError):
    pass


def _connect(database: str | None = None) -> pymysql.connections.Connection:
    try:
        return pymysql.connect(
            host=config.SEEKDB_HOST,
            port=config.SEEKDB_PORT,
            user=config.SEEKDB_USER,
            password=config.SEEKDB_PASSWORD,
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=config.SEEKDB_CONNECT_TIMEOUT,
            autocommit=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise StoreError(
            f"无法连接 seekdb {config.SEEKDB_HOST}:{config.SEEKDB_PORT}"
            f"（database={database or '<none>'}）：{exc}。请先执行 scripts/start_seekdb.sh"
        ) from exc


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS sdd_documents (
  doc_id VARCHAR(96) PRIMARY KEY,
  kind VARCHAR(16) NOT NULL,
  path VARCHAR(1024) NOT NULL,
  sha256 CHAR(64) NOT NULL,
  item_count INT NOT NULL DEFAULT 0,
  imported_at DATETIME(6) NOT NULL,
  KEY sdd_doc_kind (kind),
  KEY sdd_doc_path (path(191))
) ORGANIZATION = HEAP
"""

_TASKS = """
CREATE TABLE IF NOT EXISTS sdd_tasks (
  task_id VARCHAR(64) PRIMARY KEY,
  title VARCHAR(512) NOT NULL DEFAULT '',
  statement MEDIUMTEXT NOT NULL,
  keywords VARCHAR(1024) NOT NULL DEFAULT '',
  updated_at DATETIME(6) NOT NULL
) ORGANIZATION = HEAP
"""

_QUERY_LOG = """
CREATE TABLE IF NOT EXISTS sdd_query_log (
  log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL DEFAULT '',
  stage VARCHAR(64) NOT NULL,
  sql_text MEDIUMTEXT NOT NULL,
  terms VARCHAR(1024) NOT NULL DEFAULT '',
  hit_count INT NOT NULL DEFAULT 0,
  elapsed_ms INT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL,
  KEY sdd_qlog_task (task_id, created_at)
) ORGANIZATION = HEAP
"""


def _items_ddl(parser: str) -> str:
    fulltext = "FULLTEXT INDEX sdd_item_ft (text)"
    if parser:
        fulltext = f"{fulltext} WITH PARSER {parser}"
    return f"""
CREATE TABLE IF NOT EXISTS sdd_items (
  item_id VARCHAR(191) PRIMARY KEY,
  doc_id VARCHAR(96) NOT NULL,
  kind VARCHAR(16) NOT NULL,
  name VARCHAR(255) NOT NULL,
  qualified_path VARCHAR(1024) NOT NULL,
  start_line INT NOT NULL,
  end_line INT NOT NULL,
  text MEDIUMTEXT NOT NULL,
  keywords VARCHAR(1024) NOT NULL DEFAULT '',
  applies VARCHAR(1024) NOT NULL DEFAULT '',
  entry_status VARCHAR(16) NOT NULL DEFAULT '',
  sha256 CHAR(64) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  {fulltext},
  KEY sdd_item_doc (doc_id),
  KEY sdd_item_kind (kind, name(64))
) ORGANIZATION = HEAP
"""


def init_schema() -> dict[str, Any]:
    """建库建表。返回实际生效的 FULLTEXT 解析器（评审环境可能与开发环境不同）。"""

    admin = _connect(None)
    try:
        with admin.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS {config.SEEKDB_DATABASE} DEFAULT CHARSET utf8mb4"
            )
        admin.commit()
    finally:
        admin.close()

    conn = _connect(config.SEEKDB_DATABASE)
    parser = config.SEEKDB_FTS_PARSER
    try:
        with conn.cursor() as cur:
            cur.execute(_items_ddl(parser))
        conn.commit()
    except pymysql.err.MySQLError:
        conn.rollback()
        parser = ""
        with conn.cursor() as cur:
            cur.execute(_items_ddl(parser))
        conn.commit()
    try:
        with conn.cursor() as cur:
            for ddl in (_DOCUMENTS, _TASKS, _QUERY_LOG):
                cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()
    return {"fts_parser": parser or "default", "database": config.SEEKDB_DATABASE}


def ping() -> dict[str, Any]:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS version, DATABASE() AS db")
            row = cur.fetchone() or {}
            cur.execute("SELECT COUNT(*) AS n FROM sdd_items")
            items = int((cur.fetchone() or {}).get("n", 0))
            cur.execute("SELECT COUNT(*) AS n FROM sdd_documents")
            docs = int((cur.fetchone() or {}).get("n", 0))
        return {**row, "items": items, "documents": docs}
    finally:
        conn.close()


def log_query(
    *,
    task_id: str,
    stage: str,
    sql_text: str,
    terms: Sequence[str] = (),
    hit_count: int = 0,
    elapsed_ms: int = 0,
) -> None:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sdd_query_log (task_id, stage, sql_text, terms, hit_count, elapsed_ms, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (task_id, stage, " ".join(sql_text.split()), " ".join(terms)[:1000], hit_count, elapsed_ms, _now()),
            )
        conn.commit()
    finally:
        conn.close()


def read_query_log(task_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            if task_id:
                cur.execute(
                    "SELECT * FROM sdd_query_log WHERE task_id = %s ORDER BY log_id DESC LIMIT %s",
                    (task_id, limit),
                )
            else:
                cur.execute("SELECT * FROM sdd_query_log ORDER BY log_id DESC LIMIT %s", (limit,))
            return list(cur.fetchall())
    finally:
        conn.close()


# ---------------------------------------------------------------- 写入


def upsert_document(kind: str, path: str, sha256: str, items: Iterable[dict[str, Any]]) -> str:
    """写入一个文件及其条目；同 sha 已存在时跳过重写（幂等）。"""

    doc_id = f"{kind}:{sha256[:24]}:{path[-40:]}"
    conn = _connect(config.SEEKDB_DATABASE)
    rows = list(items)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT sha256 FROM sdd_documents WHERE doc_id = %s", (doc_id,))
            existing = cur.fetchone()
            if existing and existing["sha256"] == sha256:
                cur.execute("SELECT COUNT(*) AS n FROM sdd_items WHERE doc_id = %s", (doc_id,))
                if int((cur.fetchone() or {}).get("n", 0)) == len(rows):
                    return "unchanged"
            # 文件的 sha 变了 → doc_id 也变；必须先按 path 找出旧 doc_id 并删其条目，
            # 否则只在旧版本里出现的符号（如新增函数）会残留成孤儿行。
            cur.execute("SELECT doc_id FROM sdd_documents WHERE path = %s", (path,))
            for row in cur.fetchall():
                cur.execute("DELETE FROM sdd_items WHERE doc_id = %s", (row["doc_id"],))
            cur.execute("DELETE FROM sdd_items WHERE doc_id = %s", (doc_id,))
            cur.execute("DELETE FROM sdd_documents WHERE path = %s", (path,))
            cur.execute(
                "REPLACE INTO sdd_documents (doc_id, kind, path, sha256, item_count, imported_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (doc_id, kind, path, sha256, len(rows), _now()),
            )
            for item in rows:
                cur.execute(
                    "REPLACE INTO sdd_items (item_id, doc_id, kind, name, qualified_path, start_line, end_line,"
                    " text, keywords, applies, entry_status, sha256, updated_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        item["item_id"],
                        doc_id,
                        item["kind"],
                        item["name"],
                        item["qualified_path"],
                        item["start_line"],
                        item["end_line"],
                        item["text"],
                        item["keywords"],
                        item["applies"],
                        item["entry_status"],
                        item["sha256"],
                        _now(),
                    ),
                )
        conn.commit()
        return "imported"
    finally:
        conn.close()


def upsert_task(task_id: str, title: str, statement: str, keywords: str) -> None:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "REPLACE INTO sdd_tasks (task_id, title, statement, keywords, updated_at) VALUES (%s, %s, %s, %s, %s)",
                (task_id, title[:500], statement, keywords[:1000], _now()),
            )
        conn.commit()
    finally:
        conn.close()


def prune(paths: Sequence[str]) -> int:
    """删除本次采集未再出现的文件记录，并清掉「没有父文档」的孤儿条目。

    规格被改/删后旧内容不得残留在上下文里；文本变了但符号名没变时 item_id
    相同、靠 REPLACE 覆盖，孤儿清理兜住「只在旧版本出现过的符号」。
    """

    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT doc_id, path FROM sdd_documents")
            existing = {row["doc_id"]: row["path"] for row in cur.fetchall()}
            keep = set(paths)
            stale = [doc_id for doc_id, path in existing.items() if path not in keep]
            for doc_id in stale:
                cur.execute("DELETE FROM sdd_items WHERE doc_id = %s", (doc_id,))
                cur.execute("DELETE FROM sdd_documents WHERE doc_id = %s", (doc_id,))
            cur.execute(
                "SELECT item_id FROM sdd_items WHERE doc_id NOT IN (SELECT doc_id FROM sdd_documents)"
            )
            orphans = [row["item_id"] for row in cur.fetchall()]
            for start in range(0, len(orphans), 200):
                batch = orphans[start : start + 200]
                cur.execute(
                    f"DELETE FROM sdd_items WHERE item_id IN ({', '.join(['%s'] * len(batch))})",
                    tuple(batch),
                )
        conn.commit()
        return len(stale) + len(orphans)
    finally:
        conn.close()


def truncate_all() -> None:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            for table in ("sdd_items", "sdd_documents", "sdd_tasks", "sdd_query_log"):
                cur.execute(f"DELETE FROM {table}")  # noqa: S608 - 表名固定
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- 读取


def table_counts() -> dict[str, int]:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            result: dict[str, int] = {}
            for table in ("sdd_items", "sdd_documents", "sdd_tasks", "sdd_query_log"):
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608 - 表名固定
                result[table] = int((cur.fetchone() or {}).get("n", 0))
            cur.execute("SELECT kind, COUNT(*) AS n FROM sdd_items GROUP BY kind")
            result.update({f"items_{row['kind']}": int(row["n"]) for row in cur.fetchall()})
        return result
    finally:
        conn.close()


def fulltext_items(kind: str, terms: Sequence[str], limit: int, task_id: str = "") -> list[dict[str, Any]]:
    """seekdb 全文检索：MATCH … AGAINST，返回带 score 的有序候选。"""

    phrase = " ".join(terms).strip()
    if not phrase:
        return []
    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        " MATCH(text) AGAINST (%s) AS score, text, keywords"
        " FROM sdd_items WHERE kind = %s AND MATCH(text) AGAINST (%s)"
        " ORDER BY score DESC LIMIT %s"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (phrase, kind, phrase, limit))
            rows = list(cur.fetchall())
    finally:
        conn.close()
    elapsed = int((time.perf_counter() - started) * 1000)
    log_query(
        task_id=task_id,
        stage=f"fulltext:{kind}",
        sql_text=sql,
        terms=list(terms),
        hit_count=len(rows),
        elapsed_ms=elapsed,
    )
    return rows


def keyword_items(
    kind: str, terms: Sequence[str], limit: int, task_id: str = ""
) -> list[dict[str, Any]]:
    """LIKE 兜底召回：全文分词对中英混排/符号名可能不命中时补充候选。"""

    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        " text, keywords FROM sdd_items"
        " WHERE kind = %s AND (name LIKE %s OR keywords LIKE %s OR text LIKE %s)"
        " LIMIT %s"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        with conn.cursor() as cur:
            for term in terms:
                needle = f"%{term}%"
                cur.execute(sql, (kind, needle, needle, needle, limit))
                for row in cur.fetchall():
                    if row["item_id"] in seen:
                        continue
                    seen.add(row["item_id"])
                    rows.append(row)
    finally:
        conn.close()
    elapsed = int((time.perf_counter() - started) * 1000)
    log_query(
        task_id=task_id,
        stage=f"keyword:{kind}",
        sql_text=sql,
        terms=list(terms),
        hit_count=len(rows),
        elapsed_ms=elapsed,
    )
    return rows


def items_by_ids(item_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not item_ids:
        return []
    placeholders = ", ".join(["%s"] * len(item_ids))
    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        f" text, keywords, sha256 FROM sdd_items WHERE item_id IN ({placeholders})"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(item_ids))
            return list(cur.fetchall())
    finally:
        conn.close()


def items_for_paths(kind: str, paths: Sequence[str], task_id: str = "") -> list[dict[str, Any]]:
    """按 qualified_path 前缀取条目（用于 applies-to 结构关联，而非文本相似度）。"""

    if not paths:
        return []
    clauses = " OR ".join(["qualified_path LIKE %s"] * len(paths))
    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        f" text, keywords, sha256 FROM sdd_items WHERE kind = %s AND ({clauses})"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (kind, *[f"{path}%" for path in paths]))
            rows = list(cur.fetchall())
    finally:
        conn.close()
    log_query(
        task_id=task_id,
        stage=f"applies:{kind}",
        sql_text=sql,
        terms=list(paths),
        hit_count=len(rows),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    return rows


def applies_items(kind: str, targets: Sequence[str], task_id: str = "") -> list[dict[str, Any]]:
    """结构关联：规格 `Applies-to` 写的是 `app/x.py::name`，与 qualified_path 后缀对齐。"""

    if not targets:
        return []
    clauses = " OR ".join(["qualified_path LIKE %s"] * len(targets))
    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        " text, keywords, sha256 FROM sdd_items"
        f" WHERE kind = %s AND ({clauses})"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (kind, *[f"%{target}" for target in targets]))
            rows = list(cur.fetchall())
    finally:
        conn.close()
    log_query(
        task_id=task_id,
        stage=f"applies:{kind}",
        sql_text=sql,
        terms=list(targets),
        hit_count=len(rows),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    return rows


def symbol_referencers(kind: str, symbols: Sequence[str], limit: int, task_id: str = "") -> list[dict[str, Any]]:
    """反向关联：哪些条目（通常是测试）在文本里引用了这些符号。"""

    if not symbols:
        return []
    clauses = " OR ".join(["text LIKE %s"] * len(symbols))
    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        " text, keywords, sha256 FROM sdd_items"
        f" WHERE kind = %s AND ({clauses}) LIMIT %s"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (kind, *[f"%{symbol}%" for symbol in symbols], limit))
            rows = list(cur.fetchall())
    finally:
        conn.close()
    log_query(
        task_id=task_id,
        stage=f"referencers:{kind}",
        sql_text=sql,
        terms=list(symbols),
        hit_count=len(rows),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    return rows


def sibling_items(kind: str, doc_ids: Sequence[str], exclude: Sequence[str], task_id: str = "") -> list[dict[str, Any]]:
    """同文档兄弟条目：一份规格文件里的其它条款通常是同一行为族约束。"""

    if not doc_ids:
        return []
    placeholders = ", ".join(["%s"] * len(doc_ids))
    sql = (
        "SELECT item_id, kind, name, qualified_path, start_line, end_line, applies, entry_status,"
        " text, keywords, sha256, doc_id FROM sdd_items"
        f" WHERE kind = %s AND doc_id IN ({placeholders})"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (kind, *doc_ids))
            rows = [row for row in cur.fetchall() if row["item_id"] not in set(exclude)]
    finally:
        conn.close()
    log_query(
        task_id=task_id,
        stage=f"sibling:{kind}",
        sql_text=sql,
        terms=list(doc_ids),
        hit_count=len(rows),
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    return rows


def documents_by_kind(kind: str) -> list[dict[str, Any]]:
    """按文件聚合的索引清单（测试目录的回归护栏名册即由此导出，而非磁盘遍历）。"""

    sql = (
        "SELECT d.path AS path, d.kind AS kind, d.sha256 AS sha256, d.item_count AS item_count,"
        " i.terms AS names FROM sdd_documents d"
        " LEFT JOIN (SELECT doc_id, GROUP_CONCAT(name ORDER BY start_line SEPARATOR ',') AS terms"
        " FROM sdd_items GROUP BY doc_id) i ON i.doc_id = d.doc_id"
        " WHERE d.kind = %s ORDER BY d.path"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (kind,))
            return list(cur.fetchall())
    finally:
        conn.close()


def doc_ids_for_items(item_ids: Sequence[str]) -> dict[str, str]:
    if not item_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(item_ids))
    sql = f"SELECT item_id, doc_id FROM sdd_items WHERE item_id IN ({placeholders})"
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(item_ids))
            return {row["item_id"]: row["doc_id"] for row in cur.fetchall()}
    finally:
        conn.close()


def item_provenance(item_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """索引记录 → 所在文件与文件摘要（上下文包的 path/sha 字段由此而来）。"""

    if not item_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(item_ids))
    sql = (
        "SELECT i.item_id AS item_id, i.doc_id AS doc_id, d.path AS path, d.sha256 AS doc_sha256,"
        " d.kind AS doc_kind"
        f" FROM sdd_items i JOIN sdd_documents d ON d.doc_id = i.doc_id WHERE i.item_id IN ({placeholders})"
    )
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(item_ids))
            return {row["item_id"]: row for row in cur.fetchall()}
    finally:
        conn.close()


def schema_evidence() -> str:
    """导出真实建表语句与索引定义（A4 证据：全文索引确实存在于库里）。"""

    conn = _connect(config.SEEKDB_DATABASE)
    chunks: list[str] = []
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cur.fetchall()]
            for table in sorted(tables):
                if not table.startswith("sdd_"):
                    continue
                cur.execute(f"SHOW CREATE TABLE `{table}`")
                row = cur.fetchone() or {}
                chunks.append(str(row.get("Create Table") or list(row.values())[-1]))
                cur.execute(f"SHOW INDEX FROM `{table}`")
                index_rows = cur.fetchall()
                listing = "\n".join(
                    f"  -- 索引 {r['Key_name']} 列 {r['Column_name']} 类型 {r['Index_type']}"
                    for r in index_rows
                )
                chunks.append(f"-- {table}\n{listing}")
    finally:
        conn.close()
    return "\n\n".join(chunks)


def get_task(task_id: str) -> dict[str, Any] | None:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM sdd_tasks WHERE task_id = %s", (task_id,))
            return cur.fetchone()
    finally:
        conn.close()


def list_documents() -> list[dict[str, Any]]:
    conn = _connect(config.SEEKDB_DATABASE)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT kind, path, sha256, item_count, imported_at FROM sdd_documents ORDER BY kind, path")
            return list(cur.fetchall())
    finally:
        conn.close()
