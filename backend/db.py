from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "mes.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_connection() -> sqlite3.Connection:
    # 统一开启外键约束，避免业务代码绕过表关系导致脏数据。
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    # schema.sql 负责完整重建结构（含 drop/create），用于开发阶段一键初始化。
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(schema)


def query_all(
    conn: sqlite3.Connection, sql: str, params: Iterable[Any] | None = None
) -> list[dict[str, Any]]:
    # 对外统一返回 dict，便于 FastAPI 直接序列化为 JSON。
    cursor = conn.execute(sql, tuple(params or []))
    return [dict(row) for row in cursor.fetchall()]


def query_one(
    conn: sqlite3.Connection, sql: str, params: Iterable[Any] | None = None
) -> dict[str, Any] | None:
    row = conn.execute(sql, tuple(params or [])).fetchone()
    return dict(row) if row else None
