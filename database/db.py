"""
database/db.py — Conexão SQLite e CRUD do ConciliaAI
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "concilia.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Cria as tabelas se não existirem."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflows (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            description TEXT,
            tags        TEXT    DEFAULT '[]',
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL,
            version     INTEGER NOT NULL DEFAULT 1,
            code        TEXT    NOT NULL,
            schema_info TEXT    DEFAULT '{}',
            agent_summary TEXT,
            sample_pct  REAL    DEFAULT 0.2,
            llm_provider TEXT,
            llm_model   TEXT
        );

        CREATE TABLE IF NOT EXISTS executions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id      INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            executed_at      TEXT    NOT NULL,
            status           TEXT    NOT NULL,
            duration_seconds REAL,
            input_files      TEXT    DEFAULT '[]',
            output_path      TEXT,
            stats            TEXT    DEFAULT '{}',
            agent2_analysis  TEXT,
            error_message    TEXT,
            log_path         TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_executions_workflow ON executions(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_executions_status   ON executions(status);
    """)
    conn.commit()
    conn.close()


# ─── Workflows ───────────────────────────────────────────────────────────────

def save_workflow(name: str, description: str, tags: list, code: str,
                  schema_info: dict, agent_summary: str, sample_pct: float,
                  llm_provider: str, llm_model: str) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO workflows
                (name, description, tags, created_at, updated_at, version, code,
                 schema_info, agent_summary, sample_pct, llm_provider, llm_model)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
        """, (name, description, json.dumps(tags), now, now, code,
              json.dumps(schema_info), agent_summary, sample_pct, llm_provider, llm_model))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_workflow(workflow_id: int, name: str = None, description: str = None,
                    tags: list = None, code: str = None) -> bool:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        if not row:
            return False
        now = datetime.utcnow().isoformat()
        new_name = name if name is not None else row["name"]
        new_desc = description if description is not None else row["description"]
        new_tags = json.dumps(tags) if tags is not None else row["tags"]
        new_code = code if code is not None else row["code"]
        new_version = row["version"] + (1 if code is not None else 0)
        conn.execute("""
            UPDATE workflows SET name=?, description=?, tags=?, updated_at=?,
                                 version=?, code=?
            WHERE id=?
        """, (new_name, new_desc, new_tags, now, new_version, new_code, workflow_id))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_workflow(workflow_id: int) -> bool:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()


def get_workflow(workflow_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        return _workflow_row_to_dict(row) if row else None
    finally:
        conn.close()


def get_workflow_by_name(name: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM workflows WHERE name = ?", (name,)).fetchone()
        return _workflow_row_to_dict(row) if row else None
    finally:
        conn.close()


def list_workflows(search: str = "", tag_filter: str = "") -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT w.*,
                   COUNT(e.id) as exec_count,
                   MAX(e.executed_at) as last_exec,
                   (SELECT e2.status FROM executions e2
                    WHERE e2.workflow_id = w.id
                    ORDER BY e2.executed_at DESC LIMIT 1) as last_status
            FROM workflows w
            LEFT JOIN executions e ON e.workflow_id = w.id
            GROUP BY w.id
            ORDER BY w.updated_at DESC
        """).fetchall()
        results = []
        for row in rows:
            d = _workflow_row_to_dict(row)
            d["exec_count"] = row["exec_count"]
            d["last_exec"] = row["last_exec"]
            d["last_status"] = row["last_status"]
            if search and search.lower() not in d["name"].lower() and \
               search.lower() not in (d["description"] or "").lower():
                continue
            if tag_filter and tag_filter not in d["tags"]:
                continue
            results.append(d)
        return results
    finally:
        conn.close()


def _workflow_row_to_dict(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["schema_info"] = json.loads(d.get("schema_info") or "{}")
    return d


# ─── Executions ──────────────────────────────────────────────────────────────

def save_execution(workflow_id: int, status: str, duration_seconds: float,
                   input_files: list, output_path: str, stats: dict,
                   agent2_analysis: str, error_message: str, log_path: str) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO executions
                (workflow_id, executed_at, status, duration_seconds, input_files,
                 output_path, stats, agent2_analysis, error_message, log_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (workflow_id, now, status, duration_seconds,
              json.dumps(input_files), output_path, json.dumps(stats),
              agent2_analysis, error_message, log_path))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_executions(workflow_id: int = None, status_filter: str = None,
                    limit: int = 200) -> list[dict]:
    conn = get_connection()
    try:
        query = """
            SELECT e.*, w.name as workflow_name
            FROM executions e
            JOIN workflows w ON w.id = e.workflow_id
            WHERE 1=1
        """
        params = []
        if workflow_id:
            query += " AND e.workflow_id = ?"
            params.append(workflow_id)
        if status_filter:
            query += " AND e.status = ?"
            params.append(status_filter)
        query += " ORDER BY e.executed_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [_execution_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_execution(execution_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT e.*, w.name as workflow_name
            FROM executions e JOIN workflows w ON w.id = e.workflow_id
            WHERE e.id = ?
        """, (execution_id,)).fetchone()
        return _execution_row_to_dict(row) if row else None
    finally:
        conn.close()


def _execution_row_to_dict(row) -> dict:
    d = dict(row)
    d["input_files"] = json.loads(d.get("input_files") or "[]")
    d["stats"] = json.loads(d.get("stats") or "{}")
    return d


def get_stats() -> dict:
    """Retorna métricas gerais para a tela Home."""
    conn = get_connection()
    try:
        total_workflows = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
        total_executions = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
        last_exec = conn.execute(
            "SELECT executed_at FROM executions ORDER BY executed_at DESC LIMIT 1"
        ).fetchone()
        return {
            "total_workflows": total_workflows,
            "total_executions": total_executions,
            "last_execution": last_exec[0] if last_exec else None,
        }
    finally:
        conn.close()
