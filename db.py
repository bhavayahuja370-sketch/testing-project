"""Supabase PostgreSQL storage for role-based chat messages."""

import logging
import os
from contextlib import contextmanager
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger("stars.db")
_pool = None


def _database_url() -> str:
    """Return the Supabase URL with SSL required unless already specified."""
    # Accept the legacy lowercase name as well, so existing deployments keep working.
    value = (os.environ.get("DATABASE_URL") or os.environ.get("database_url") or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query.setdefault("sslmode", ["require"])
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _create_pool() -> bool:
    global _pool
    if _pool is not None:
        return True
    if not _database_url():
        logger.warning("DATABASE_URL is not set; chat persistence is disabled.")
        return False
    try:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(conninfo=_database_url(), min_size=0, max_size=5, timeout=10)
        return True
    except Exception:
        logger.exception("Could not initialize the Supabase connection pool.")
        _pool = None
        return False


@contextmanager
def _connection():
    if not _create_pool():
        raise RuntimeError("Database unavailable")
    with _pool.connection() as conn:
        yield conn


def init_db() -> bool:
    """Create the message table. A database outage never stops the chatbot."""
    try:
        with _connection() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                ON chat_messages (session_id, created_at, id)
            """)
            # Upgrade the older one-row-per-exchange schema when it exists.
            # The NOT EXISTS checks make repeated application starts safe.
            cur.execute("SELECT to_regclass('public.chat_history')")
            if cur.fetchone()[0]:
                cur.execute("""
                    INSERT INTO chat_messages (session_id, role, content, created_at)
                    SELECT legacy.session_id, 'user', legacy.user_message, legacy.created_at
                    FROM chat_history AS legacy
                    WHERE NOT EXISTS (
                        SELECT 1 FROM chat_messages AS current
                        WHERE current.session_id = legacy.session_id
                          AND current.role = 'user'
                          AND current.content = legacy.user_message
                          AND current.created_at = legacy.created_at
                    )
                """)
                cur.execute("""
                    INSERT INTO chat_messages (session_id, role, content, created_at)
                    SELECT legacy.session_id, 'assistant', legacy.assistant_response,
                           legacy.created_at + INTERVAL '1 microsecond'
                    FROM chat_history AS legacy
                    WHERE NOT EXISTS (
                        SELECT 1 FROM chat_messages AS current
                        WHERE current.session_id = legacy.session_id
                          AND current.role = 'assistant'
                          AND current.content = legacy.assistant_response
                          AND current.created_at = legacy.created_at + INTERVAL '1 microsecond'
                    )
                """)
            conn.commit()
        return True
    except Exception:
        logger.exception("Could not initialize the chat_messages table.")
        return False


def check_connection() -> bool:
    """Return whether Supabase accepts a lightweight database query."""
    try:
        with _connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)
    except Exception:
        return False


def save_message(session_id: str, role: str, content: str) -> bool:
    """Persist one user or assistant message."""
    if role not in {"user", "assistant"} or not session_id or not content:
        return False
    try:
        with _connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
            conn.commit()
        return True
    except Exception:
        logger.exception("Could not save chat message.")
        return False


def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Return the newest messages in chronological (oldest-to-newest) order."""
    if not session_id:
        return []
    try:
        limit = max(1, min(int(limit), 100))
        with _connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, role, content, created_at
                FROM (
                    SELECT id, role, content, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                ) AS recent
                ORDER BY created_at ASC, id ASC
            """, (session_id, limit))
            rows = cur.fetchall()
        return [
            {"id": row[0], "role": row[1], "content": row[2], "created_at": row[3].isoformat()}
            for row in rows
        ]
    except Exception:
        logger.exception("Could not load chat history.")
        return []
