"""
Lightweight SQLite persistence.

Three tables:
  users        - one row per Telegram user
  resumes      - resume versions (base + tailored copies), linked to a user
  applications - the application tracker: one row per job a user applied to

This is intentionally simple (MVP). Swap to Postgres later by replacing
the connection helper and using the same SQL (mostly portable).
"""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    kind TEXT NOT NULL,              -- 'base' or 'tailored'
    content TEXT NOT NULL,           -- plain text resume
    score REAL,                      -- ATS/quality score, 0-100
    score_feedback TEXT,             -- JSON blob of strengths/gaps
    job_description TEXT,            -- set only for 'tailored' rows
    created_at TEXT NOT NULL,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    job_title TEXT NOT NULL,
    company TEXT,
    job_url TEXT,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft -> ready -> applied -> rejected/interview/offer
    resume_id INTEGER,               -- FK to resumes.id (the tailored version used)
    cover_letter TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
    FOREIGN KEY (resume_id) REFERENCES resumes(id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat()


def upsert_user(telegram_id: int, username: str | None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO users (telegram_id, username, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username""",
            (telegram_id, username, _now()),
        )


def save_resume(telegram_id: int, content: str, kind: str = "base",
                 score: float | None = None, score_feedback: dict | None = None,
                 job_description: str | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO resumes
               (telegram_id, kind, content, score, score_feedback, job_description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (telegram_id, kind, content, score,
             json.dumps(score_feedback) if score_feedback else None,
             job_description, _now()),
        )
        return cur.lastrowid


def get_latest_base_resume(telegram_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM resumes WHERE telegram_id=? AND kind='base'
               ORDER BY created_at DESC LIMIT 1""",
            (telegram_id,),
        ).fetchone()


def create_application(telegram_id: int, job_title: str, company: str | None,
                        job_url: str | None, resume_id: int | None = None,
                        cover_letter: str | None = None, status: str = "draft") -> int:
    with get_conn() as conn:
        now = _now()
        cur = conn.execute(
            """INSERT INTO applications
               (telegram_id, job_title, company, job_url, status, resume_id, cover_letter,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (telegram_id, job_title, company, job_url, status, resume_id, cover_letter, now, now),
        )
        return cur.lastrowid


def update_application_status(application_id: int, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE applications SET status=?, updated_at=? WHERE id=?",
            (status, _now(), application_id),
        )


def list_applications(telegram_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM applications WHERE telegram_id=?
               ORDER BY updated_at DESC""",
            (telegram_id,),
        ).fetchall()