import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    ticker  TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id          TEXT PRIMARY KEY,
    company_id  TEXT NOT NULL REFERENCES companies(id),
    year        INTEGER NOT NULL,
    filename    TEXT NOT NULL,
    ingested_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS parent_chunks (
    id          TEXT PRIMARY KEY,
    report_id   TEXT NOT NULL REFERENCES reports(id),
    section     TEXT,
    subsection  TEXT,
    text        TEXT NOT NULL,
    page        INTEGER,
    position    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_parent_report    ON parent_chunks(report_id);
CREATE INDEX IF NOT EXISTS idx_parent_section   ON parent_chunks(report_id, section);
CREATE INDEX IF NOT EXISTS idx_parent_position  ON parent_chunks(report_id, position);

CREATE TABLE IF NOT EXISTS financials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company     TEXT    NOT NULL,
    ticker      TEXT    NOT NULL,
    data_year   INTEGER NOT NULL,
    metric      TEXT    NOT NULL,
    value       REAL,
    section     TEXT,
    period      TEXT    DEFAULT 'annual',
    currency    TEXT    DEFAULT 'USD'
);
"""


def init_db(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.close()


def register_company(company_id: str, ticker: str | None, db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO companies(id, name, ticker) VALUES (?, ?, ?)",
        (company_id, company_id.capitalize(), ticker),
    )
    conn.commit()
    conn.close()


def register_report(report_id: str, company_id: str, year: int, filename: str, db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO reports(id, company_id, year, filename) VALUES (?, ?, ?, ?)",
        (report_id, company_id, year, filename),
    )
    conn.commit()
    conn.close()


def is_already_ingested(report_id: str, db_path: str) -> bool:
    if not Path(db_path).exists():
        return False
    try:
        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM parent_chunks WHERE report_id = ?", (report_id,)
        ).fetchone()[0]
        conn.close()
        return count > 0
    except sqlite3.OperationalError:
        return False


def get_parent(parent_id: str, db_path: str) -> dict | None:
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT text, section, subsection, page, position FROM parent_chunks WHERE id = ?",
            (parent_id,),
        ).fetchone()
        conn.close()
        if row:
            return {
                "text": row[0],
                "section": row[1],
                "subsection": row[2],
                "page": row[3],
                "position": row[4],
            }
    except sqlite3.OperationalError:
        pass
    return None


def get_available_reports(db_path: str) -> list[dict]:
    """Return all ingested reports as a catalog for document routing."""
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT id, company_id, year FROM reports ORDER BY company_id, year"
        ).fetchall()
        conn.close()
        return [{"report_id": r[0], "company": r[1], "year": r[2]} for r in rows]
    except sqlite3.OperationalError:
        return []


def get_siblings(parent_id: str, db_path: str, window: int = 1) -> list[dict]:
    """Return up to `window` parent chunks before and after the given parent."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT report_id, position FROM parent_chunks WHERE id = ?", (parent_id,)
        ).fetchone()
        if not row:
            conn.close()
            return []
        report_id, pos = row
        rows = conn.execute(
            """SELECT text, section, page, position FROM parent_chunks
               WHERE report_id = ? AND position BETWEEN ? AND ?
               ORDER BY position""",
            (report_id, pos - window, pos + window),
        ).fetchall()
        conn.close()
        return [{"text": r[0], "section": r[1], "page": r[2], "position": r[3]} for r in rows]
    except sqlite3.OperationalError:
        return []
