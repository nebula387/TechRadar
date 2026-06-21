import sqlite3
import json
import logging
from datetime import datetime, date
from pathlib import Path
from app.models import PublishedRecord

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str = "./data/techradar.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS published_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_url TEXT UNIQUE NOT NULL,
                    source TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    published_at TEXT NOT NULL,
                    channels TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    instagram_post_id TEXT,
                    reddit_post_id TEXT,
                    tweet_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_count (
                    date TEXT PRIMARY KEY,
                    count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_items (
                    slug TEXT PRIMARY KEY,
                    item_url TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    image_path TEXT,
                    preview_message_id INTEGER,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'pending'
                )
            """)

    def is_published(self, url: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM published_items WHERE item_url = ?", (url,)
            ).fetchone()
            return row is not None

    def get_today_count(self) -> int:
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count FROM daily_count WHERE date = ?", (today,)
            ).fetchone()
            return row["count"] if row else 0

    def increment_today_count(self):
        today = date.today().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO daily_count (date, count) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET count = count + 1
            """, (today,))

    def save_published(self, record: PublishedRecord):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO published_items
                (item_url, source, score, published_at, channels,
                 telegram_message_id, instagram_post_id, reddit_post_id, tweet_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.item_url,
                record.source.value,
                record.score,
                record.published_at.isoformat(),
                json.dumps(record.channels),
                record.telegram_message_id,
                record.instagram_post_id,
                record.reddit_post_id,
                record.tweet_id,
            ))
        self.increment_today_count()
        logger.info(f"Saved published record: {record.item_url}")

    def is_pending_or_published(self, url: str) -> bool:
        with self._connect() as conn:
            p = conn.execute("SELECT slug FROM pending_items WHERE item_url = ? AND status = 'pending'", (url,)).fetchone()
            if p:
                return True
            return self.is_published(url)

    def save_pending(self, slug: str, item_url: str, content_json: str, image_path: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pending_items
                (slug, item_url, content_json, image_path, created_at, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (slug, item_url, content_json, image_path, datetime.utcnow().isoformat()))

    def set_preview_message_id(self, slug: str, message_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE pending_items SET preview_message_id = ? WHERE slug = ?", (message_id, slug))

    def get_all_pending(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pending_items WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_pending_by_slug(self, slug: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pending_items WHERE slug = ?", (slug,)).fetchone()
            return dict(row) if row else None

    def set_pending_status(self, slug: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE pending_items SET status = ? WHERE slug = ?", (status, slug))
        logger.info(f"Pending item '{slug}' → {status}")

    def get_recent_published(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM published_items
                ORDER BY published_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]
