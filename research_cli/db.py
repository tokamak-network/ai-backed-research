"""SQLite database management for researcher applications and API keys."""

import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/research.db")

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS researchers (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            affiliation TEXT,
            research_interests TEXT,  -- JSON array
            sample_works TEXT,        -- JSON array [{type, url, description}]
            bio TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending'  -- pending, approved, rejected, suspended
        );

        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            researcher_id TEXT NOT NULL REFERENCES researchers(id),
            submitted_at TEXT NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, approved, rejected
            reviewed_at TEXT,
            reviewed_by TEXT,
            admin_notes TEXT,
            rejection_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            key TEXT PRIMARY KEY,
            researcher_id TEXT REFERENCES researchers(id),
            label TEXT,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            revocation_reason TEXT,
            daily_quota INTEGER DEFAULT 10,
            is_admin BOOLEAN DEFAULT FALSE
        );

        CREATE TABLE IF NOT EXISTS key_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT NOT NULL REFERENCES api_keys(key),
            endpoint TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            project_id TEXT
        );

        CREATE TABLE IF NOT EXISTS workflow_ownership (
            project_id TEXT PRIMARY KEY,
            api_key TEXT REFERENCES api_keys(key),
            researcher_id TEXT REFERENCES researchers(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            researcher_id TEXT REFERENCES researchers(id),
            api_key TEXT,
            title TEXT NOT NULL,
            category_major TEXT NOT NULL,
            category_subfield TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            -- pending, desk_review, reviewing, awaiting_revision, accepted, rejected, expired
            current_round INTEGER DEFAULT 0,
            max_rounds INTEGER DEFAULT 3,
            revision_deadline TEXT,
            deadline_hours INTEGER DEFAULT 72,
            final_decision TEXT,
            final_score REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS submission_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT NOT NULL REFERENCES submissions(id),
            round_number INTEGER NOT NULL,
            manuscript_version TEXT NOT NULL,
            word_count INTEGER,
            reviews_json TEXT,
            overall_average REAL,
            moderator_decision_json TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(submission_id, round_number)
        );

        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_api_keys_researcher ON api_keys(researcher_id);
        CREATE INDEX IF NOT EXISTS idx_key_usage_key_ts ON key_usage(api_key, timestamp);
        CREATE INDEX IF NOT EXISTS idx_workflow_ownership_researcher ON workflow_ownership(researcher_id);
        CREATE TABLE IF NOT EXISTS job_queue (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT DEFAULT 'queued',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_submissions_api_key ON submissions(api_key);
        CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
        CREATE INDEX IF NOT EXISTS idx_submission_rounds_sub ON submission_rounds(submission_id);
        CREATE INDEX IF NOT EXISTS idx_job_queue_status ON job_queue(status);
    """)
    conn.commit()

    # Migration: add total_quota column
    try:
        conn.execute("ALTER TABLE api_keys ADD COLUMN total_quota INTEGER DEFAULT 3")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: add password_hash column
    try:
        conn.execute("ALTER TABLE researchers ADD COLUMN password_hash TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str) -> str:
    """Hash password with random salt using SHA-256."""
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify password against stored hash."""
    salt, hashed = password_hash.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == hashed


# --- Researcher ---

def create_researcher(
    email: str,
    name: str,
    affiliation: str = "",
    research_interests: list = None,
    sample_works: list = None,
    bio: str = "",
    password: str = "",
) -> dict:
    """Create a researcher profile and an associated application."""
    conn = get_connection()
    researcher_id = secrets.token_urlsafe(12)
    application_id = secrets.token_urlsafe(12)
    now = _now()
    pw_hash = _hash_password(password) if password else ""

    api_key = secrets.token_urlsafe(24)

    try:
        conn.execute(
            """INSERT INTO researchers (id, email, name, affiliation, research_interests, sample_works, bio, created_at, updated_at, status, password_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?)""",
            (
                researcher_id,
                email.lower().strip(),
                name.strip(),
                affiliation.strip(),
                json.dumps(research_interests or []),
                json.dumps(sample_works or []),
                bio.strip(),
                now,
                now,
                pw_hash,
            ),
        )
        conn.execute(
            """INSERT INTO applications (id, researcher_id, submitted_at, status, reviewed_at, reviewed_by)
               VALUES (?, ?, ?, 'approved', ?, 'auto')""",
            (application_id, researcher_id, now, now),
        )
        conn.execute(
            """INSERT INTO api_keys (key, researcher_id, label, created_at, daily_quota, total_quota, is_admin)
               VALUES (?, ?, ?, ?, 10, 3, FALSE)""",
            (api_key, researcher_id, f"{name.strip()} - auto", now),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        if "UNIQUE constraint" in str(e) and "email" in str(e):
            raise ValueError("An application with this email already exists")
        raise

    return {
        "researcher_id": researcher_id,
        "application_id": application_id,
        "email": email.lower().strip(),
        "name": name.strip(),
        "api_key": api_key,
        "status": "approved",
    }


def get_researcher_by_email(email: str) -> Optional[dict]:
    """Look up a researcher by email."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM researchers WHERE email = ?", (email.lower().strip(),)
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def get_researcher(researcher_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM researchers WHERE id = ?", (researcher_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def authenticate_researcher(email: str, password: str) -> Optional[dict]:
    """Verify email+password, return researcher info + api_key if valid."""
    conn = get_connection()
    researcher = get_researcher_by_email(email)
    if not researcher or not researcher.get("password_hash"):
        return None
    if not _verify_password(password, researcher["password_hash"]):
        return None
    # Get active API key
    key_row = conn.execute(
        "SELECT key FROM api_keys WHERE researcher_id=? AND revoked_at IS NULL LIMIT 1",
        (researcher["id"],),
    ).fetchone()
    if not key_row:
        return None
    return {
        "api_key": key_row["key"],
        "name": researcher["name"],
        "email": researcher["email"],
    }


# --- Applications ---

def list_pending_applications() -> list:
    """List all pending applications with researcher info."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, r.name, r.email, r.affiliation, r.research_interests, r.sample_works, r.bio
        FROM applications a
        JOIN researchers r ON a.researcher_id = r.id
        WHERE a.status = 'pending'
        ORDER BY a.submitted_at ASC
    """).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_all_applications() -> list:
    """List all applications with researcher info."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, r.name, r.email, r.affiliation, r.research_interests, r.sample_works, r.bio
        FROM applications a
        JOIN researchers r ON a.researcher_id = r.id
        ORDER BY a.submitted_at DESC
    """).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_application(application_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        """SELECT a.*, r.name, r.email, r.affiliation, r.research_interests, r.sample_works, r.bio
           FROM applications a
           JOIN researchers r ON a.researcher_id = r.id
           WHERE a.id = ?""",
        (application_id,),
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def approve_application(application_id: str, reviewed_by: str = "admin", admin_notes: str = "") -> dict:
    """Approve an application: update status, create API key, return key."""
    conn = get_connection()
    app = get_application(application_id)
    if not app:
        raise ValueError("Application not found")
    if app["status"] != "pending":
        raise ValueError(f"Application already {app['status']}")

    now = _now()
    api_key = secrets.token_urlsafe(24)

    conn.execute(
        """UPDATE applications SET status='approved', reviewed_at=?, reviewed_by=?, admin_notes=?
           WHERE id=?""",
        (now, reviewed_by, admin_notes, application_id),
    )
    conn.execute(
        """UPDATE researchers SET status='approved', updated_at=? WHERE id=?""",
        (now, app["researcher_id"]),
    )
    conn.execute(
        """INSERT INTO api_keys (key, researcher_id, label, created_at, daily_quota, total_quota, is_admin)
           VALUES (?, ?, ?, ?, 10, 3, FALSE)""",
        (api_key, app["researcher_id"], f"{app['name']} - auto", now),
    )
    conn.commit()

    return {"api_key": api_key, "researcher_id": app["researcher_id"]}


def reject_application(application_id: str, reason: str = "", reviewed_by: str = "admin") -> dict:
    """Reject an application."""
    conn = get_connection()
    app = get_application(application_id)
    if not app:
        raise ValueError("Application not found")
    if app["status"] != "pending":
        raise ValueError(f"Application already {app['status']}")

    now = _now()
    conn.execute(
        """UPDATE applications SET status='rejected', reviewed_at=?, reviewed_by=?, rejection_reason=?
           WHERE id=?""",
        (now, reviewed_by, reason, application_id),
    )
    conn.execute(
        """UPDATE researchers SET status='rejected', updated_at=? WHERE id=?""",
        (now, app["researcher_id"]),
    )
    conn.commit()

    return {"status": "rejected", "researcher_id": app["researcher_id"]}


# --- API Keys ---

def get_api_key(key: str) -> Optional[dict]:
    """Look up an API key (returns None if not found or revoked)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE key = ? AND revoked_at IS NULL",
        (key,),
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_api_keys() -> list:
    """List all API keys (for admin)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT k.key, k.label, k.created_at, k.revoked_at, k.daily_quota, k.total_quota, k.is_admin, k.researcher_id,
               r.name, r.email
        FROM api_keys k
        LEFT JOIN researchers r ON k.researcher_id = r.id
        ORDER BY k.created_at DESC
    """).fetchall()
    return [_row_to_dict(r) for r in rows]


def revoke_api_key(key_prefix: str, reason: str = "") -> int:
    """Revoke API keys matching a prefix. Returns count revoked."""
    conn = get_connection()
    now = _now()
    cursor = conn.execute(
        """UPDATE api_keys SET revoked_at=?, revocation_reason=?
           WHERE key LIKE ? AND revoked_at IS NULL""",
        (now, reason, key_prefix + "%"),
    )
    conn.commit()
    return cursor.rowcount


def update_key_quota(key_prefix: str, total_quota: int) -> int:
    """Update total quota for keys matching prefix."""
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE api_keys SET total_quota=? WHERE key LIKE ? AND revoked_at IS NULL",
        (total_quota, key_prefix + "%"),
    )
    conn.commit()
    return cursor.rowcount


def create_legacy_key(key: str, label: str = "", is_admin: bool = False):
    """Insert a legacy key (from migration) with no researcher association."""
    conn = get_connection()
    now = _now()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO api_keys (key, researcher_id, label, created_at, daily_quota, is_admin)
               VALUES (?, NULL, ?, ?, 10, ?)""",
            (key, label, now, is_admin),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass


def create_api_key_direct(label: str = "", daily_quota: int = 10) -> dict:
    """Create an API key directly (admin use, no researcher association)."""
    conn = get_connection()
    now = _now()
    key = secrets.token_urlsafe(24)
    conn.execute(
        """INSERT INTO api_keys (key, researcher_id, label, created_at, daily_quota, is_admin)
           VALUES (?, NULL, ?, ?, ?, FALSE)""",
        (key, label, now, daily_quota),
    )
    conn.commit()
    return {"key": key, "label": label, "created_at": now}


# --- Quota ---

def record_usage(api_key: str, endpoint: str, project_id: str = None):
    """Record an API key usage event."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO key_usage (api_key, endpoint, timestamp, project_id) VALUES (?, ?, ?, ?)",
        (api_key, endpoint, _now(), project_id),
    )
    conn.commit()


def get_daily_usage(api_key: str) -> int:
    """Count today's usage for a key."""
    conn = get_connection()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM key_usage WHERE api_key=? AND timestamp >= ?",
        (api_key, today),
    ).fetchone()
    return row["cnt"] if row else 0


def get_total_usage(api_key: str) -> int:
    """Count total workflow usage (all time) for a key."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM key_usage WHERE api_key=? AND endpoint='/api/start-workflow'",
        (api_key,),
    ).fetchone()
    return row["cnt"] if row else 0


def check_quota(api_key: str) -> dict:
    """Check if a key has remaining total quota. Returns {allowed, used, limit}."""
    key_info = get_api_key(api_key)
    if not key_info:
        return {"allowed": False, "used": 0, "limit": 0, "reason": "Invalid key"}
    total_limit = key_info.get("total_quota") or 3
    used = get_total_usage(api_key)
    return {
        "allowed": used < total_limit,
        "used": used,
        "limit": total_limit,
    }


# --- Ownership ---

def record_ownership(project_id: str, api_key: str):
    """Record who started a workflow."""
    conn = get_connection()
    key_info = get_api_key(api_key)
    researcher_id = key_info["researcher_id"] if key_info else None
    try:
        conn.execute(
            """INSERT OR REPLACE INTO workflow_ownership (project_id, api_key, researcher_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (project_id, api_key, researcher_id, _now()),
        )
        conn.commit()
    except Exception:
        pass


def get_researcher_workflows(researcher_id: str) -> list:
    """Get all workflows owned by a researcher."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM workflow_ownership WHERE researcher_id=? ORDER BY created_at DESC",
        (researcher_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_key_workflows(api_key: str) -> list:
    """Get all workflows started with a specific key."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM workflow_ownership WHERE api_key=? ORDER BY created_at DESC",
        (api_key,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# --- Application Status (public) ---

def get_application_status_by_email(email: str) -> Optional[dict]:
    """Get application status for a given email (public-facing)."""
    researcher = get_researcher_by_email(email)
    if not researcher:
        return None

    conn = get_connection()
    app_row = conn.execute(
        """SELECT id, status, submitted_at, reviewed_at, rejection_reason
           FROM applications WHERE researcher_id=? ORDER BY submitted_at DESC LIMIT 1""",
        (researcher["id"],),
    ).fetchone()

    if not app_row:
        return None

    result = {
        "email": email,
        "name": researcher["name"],
        "status": app_row["status"],
        "submitted_at": app_row["submitted_at"],
        "reviewed_at": app_row["reviewed_at"],
    }

    # Only show API key on first check after approval
    if app_row["status"] == "approved":
        key_row = conn.execute(
            "SELECT key FROM api_keys WHERE researcher_id=? AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (researcher["id"],),
        ).fetchone()
        if key_row:
            result["api_key"] = key_row["key"]

    if app_row["status"] == "rejected":
        result["rejection_reason"] = app_row["rejection_reason"]

    return result


# --- Submissions ---

def create_submission(
    researcher_id: Optional[str],
    api_key: str,
    title: str,
    category_major: str,
    category_subfield: str,
    deadline_hours: int = 24,
) -> dict:
    """Create a new manuscript submission."""
    conn = get_connection()
    submission_id = secrets.token_urlsafe(16)
    now = _now()

    conn.execute(
        """INSERT INTO submissions
           (id, researcher_id, api_key, title, category_major, category_subfield,
            status, current_round, max_rounds, deadline_hours, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, 3, ?, ?, ?)""",
        (submission_id, researcher_id, api_key, title.strip(),
         category_major, category_subfield, deadline_hours, now, now),
    )
    conn.commit()

    return {
        "id": submission_id,
        "title": title.strip(),
        "status": "pending",
        "current_round": 0,
        "created_at": now,
    }


def get_submission(submission_id: str) -> Optional[dict]:
    """Get a submission with all its rounds."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    if not row:
        return None

    sub = dict(row)

    # Load rounds
    round_rows = conn.execute(
        "SELECT * FROM submission_rounds WHERE submission_id = ? ORDER BY round_number",
        (submission_id,),
    ).fetchall()

    rounds = []
    for rr in round_rows:
        rd = dict(rr)
        # Parse JSON fields
        for jfield in ("reviews_json", "moderator_decision_json"):
            if rd.get(jfield) and isinstance(rd[jfield], str):
                try:
                    rd[jfield] = json.loads(rd[jfield])
                except (json.JSONDecodeError, TypeError):
                    pass
        rounds.append(rd)

    sub["rounds"] = rounds
    return sub


def get_submissions_by_key(api_key: str) -> list:
    """Get all submissions for an API key."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM submissions WHERE api_key = ? ORDER BY created_at DESC",
        (api_key,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_submission_status(
    submission_id: str,
    status: str,
    revision_deadline: Optional[str] = None,
    final_decision: Optional[str] = None,
    final_score: Optional[float] = None,
    current_round: Optional[int] = None,
):
    """Update a submission's status and optional fields."""
    conn = get_connection()
    now = _now()
    sets = ["status = ?", "updated_at = ?"]
    params = [status, now]

    if revision_deadline is not None:
        sets.append("revision_deadline = ?")
        params.append(revision_deadline)
    elif status != "awaiting_revision":
        # Clear deadline when not awaiting revision
        sets.append("revision_deadline = NULL")

    if final_decision is not None:
        sets.append("final_decision = ?")
        params.append(final_decision)

    if final_score is not None:
        sets.append("final_score = ?")
        params.append(final_score)

    if current_round is not None:
        sets.append("current_round = ?")
        params.append(current_round)

    params.append(submission_id)
    conn.execute(
        f"UPDATE submissions SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()


def save_submission_round(
    submission_id: str,
    round_number: int,
    reviews: list,
    overall_average: float,
    moderator_decision: dict,
    word_count: int = 0,
):
    """Save review round data for a submission."""
    conn = get_connection()
    now = _now()
    conn.execute(
        """INSERT INTO submission_rounds
           (submission_id, round_number, manuscript_version, word_count,
            reviews_json, overall_average, moderator_decision_json, started_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            submission_id,
            round_number,
            f"v{round_number}",
            word_count,
            json.dumps(reviews),
            overall_average,
            json.dumps(moderator_decision),
            now,
            now,
        ),
    )
    conn.commit()


def expire_overdue_submissions() -> int:
    """Expire submissions past their revision deadline. Returns count expired."""
    conn = get_connection()
    now = _now()
    cursor = conn.execute(
        """UPDATE submissions
           SET status = 'expired', final_decision = 'EXPIRED', updated_at = ?
           WHERE status = 'awaiting_revision'
             AND revision_deadline IS NOT NULL
             AND revision_deadline < ?""",
        (now, now),
    )
    conn.commit()
    return cursor.rowcount


# --- Job Queue ---

def enqueue_job(job_id: str, project_id: str, job_type: str, payload: dict):
    """Persist a job to the DB queue."""
    conn = get_connection()
    now = _now()
    conn.execute(
        """INSERT INTO job_queue (id, project_id, job_type, payload_json, status, created_at)
           VALUES (?, ?, ?, ?, 'queued', ?)""",
        (job_id, project_id, job_type, json.dumps(payload), now),
    )
    conn.commit()


def mark_job_running(job_id: str):
    """Mark a queued job as running."""
    conn = get_connection()
    conn.execute(
        "UPDATE job_queue SET status = 'running', started_at = ? WHERE id = ?",
        (_now(), job_id),
    )
    conn.commit()


def complete_job(job_id: str, status: str = "completed"):
    """Mark a job as completed or failed."""
    conn = get_connection()
    conn.execute(
        "UPDATE job_queue SET status = ?, completed_at = ? WHERE id = ?",
        (status, _now(), job_id),
    )
    conn.commit()


def get_pending_jobs() -> list:
    """Get all queued or running jobs (for startup recovery)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM job_queue WHERE status IN ('queued', 'running') ORDER BY created_at ASC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_original_job(project_id: str) -> dict | None:
    """Get the most recent 'workflow' job for a project (for restart from scratch)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM job_queue WHERE project_id = ? AND job_type = 'workflow' ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    d = _row_to_dict(row)
    if "payload_json" in d and isinstance(d["payload_json"], str):
        try:
            d["payload"] = json.loads(d["payload_json"])
        except (json.JSONDecodeError, TypeError):
            d["payload"] = {}
    return d


# --- Helpers ---

def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict, parsing JSON fields."""
    d = dict(row)
    for key in ("research_interests", "sample_works", "reviews_json", "moderator_decision_json"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
