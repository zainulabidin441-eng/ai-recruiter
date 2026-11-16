"""Tiny SQLite layer: API cache, candidate profiles, shortlist / reject decisions."""
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY, source TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    candidate_id TEXT PRIMARY KEY, status TEXT NOT NULL,
    match_score REAL, query TEXT, updated REAL NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as c:
        c.executescript(SCHEMA)


# ---------------------------------------------------------------- cache
def cache_get(key: str, ttl: float):
    with get_conn() as c:
        row = c.execute("SELECT value, ts FROM cache WHERE key=?", (key,)).fetchone()
    if row and (time.time() - row["ts"]) < ttl:
        return json.loads(row["value"])
    return None


def cache_set(key: str, value) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache(key, value, ts) VALUES (?,?,?)",
            (key, json.dumps(value), time.time()),
        )


# ---------------------------------------------------------- candidates
def save_candidates(profiles: list) -> None:
    now = time.time()
    with get_conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO candidates(id, source, data, updated) VALUES (?,?,?,?)",
            [(p["id"], p["source"], json.dumps(p), now) for p in profiles],
        )


def save_candidate(profile: dict) -> None:
    save_candidates([profile])


def get_candidate(candidate_id: str) -> Optional[dict]:
    with get_conn() as c:
        row = c.execute("SELECT data FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_cv_candidates() -> list:
    with get_conn() as c:
        rows = c.execute("SELECT data FROM candidates WHERE source='cv'").fetchall()
    return [json.loads(r["data"]) for r in rows]


# ----------------------------------------------------------- decisions
def set_decision(candidate_id: str, status: str, score: Optional[float], query: Optional[str]) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO decisions(candidate_id, status, match_score, query, updated) "
            "VALUES (?,?,?,?,?)",
            (candidate_id, status, score, query, time.time()),
        )


def clear_decision(candidate_id: str) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM decisions WHERE candidate_id=?", (candidate_id,))


def ids_with_status(status: str) -> set:
    with get_conn() as c:
        rows = c.execute("SELECT candidate_id FROM decisions WHERE status=?", (status,)).fetchall()
    return {r["candidate_id"] for r in rows}


def reset_rejected() -> int:
    with get_conn() as c:
        cur = c.execute("DELETE FROM decisions WHERE status='rejected'")
        return cur.rowcount


def shortlist_rows() -> list:
    """Shortlisted candidates (oldest first) with their saved match score."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT d.match_score, d.query, d.updated, c.data "
            "FROM decisions d JOIN candidates c ON c.id = d.candidate_id "
            "WHERE d.status='shortlisted' ORDER BY d.updated ASC"
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "candidate": json.loads(r["data"]),
                "match_score": r["match_score"],
                "query": r["query"],
                "updated": r["updated"],
            }
        )
    return out
