"""
database.py
===========
SQLite-backed persistence layer for IdeaDB.
Stores extracted keywords and metadata for every collected Discord message,
and exposes query helpers used by the bot commands.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class Database:
    """
    Thin wrapper around a local SQLite database.

    Each row in the ``entries`` table represents one parsed Discord message
    (or attachment / link event) and stores:
      - guild_id / channel_id / author for traceability
      - content_type  : 'message' | 'file' | 'link'
      - keywords      : JSON-encoded list produced by MetadataParser
      - metadata      : JSON-encoded nested dict produced by MetadataParser
      - raw_content   : first 2 000 chars of the original message text
      - created_at    : UTC ISO-8601 timestamp
    """

    def __init__(self, db_path: str = "ideadb.sqlite") -> None:
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id     TEXT    NOT NULL,
                    channel_id   TEXT    NOT NULL,
                    author       TEXT    NOT NULL,
                    content_type TEXT    NOT NULL,
                    keywords     TEXT    NOT NULL DEFAULT '[]',
                    metadata     TEXT    NOT NULL DEFAULT '{}',
                    raw_content  TEXT             DEFAULT '',
                    created_at   TEXT    NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_guild ON entries(guild_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_guild_type "
                "ON entries(guild_id, content_type)"
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store_entry(
        self,
        guild_id: str,
        channel_id: str,
        author: str,
        content_type: str,
        keywords: List[str],
        metadata: Dict[str, Any],
        raw_content: str = "",
    ) -> None:
        """Persist one parsed message entry."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO entries
                    (guild_id, channel_id, author, content_type,
                     keywords, metadata, raw_content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    channel_id,
                    author,
                    content_type,
                    json.dumps(keywords),
                    json.dumps(metadata),
                    raw_content[:2000],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def clear_guild(self, guild_id: str) -> None:
        """Delete all entries for a specific guild."""
        with self._connect() as conn:
            conn.execute("DELETE FROM entries WHERE guild_id = ?", (guild_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_recent_entries(
        self,
        guild_id: str,
        limit: int = 100,
        content_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return up to *limit* most-recent entries for a guild."""
        with self._connect() as conn:
            if content_type:
                rows = conn.execute(
                    """
                    SELECT * FROM entries
                    WHERE guild_id = ? AND content_type = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (guild_id, content_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM entries
                    WHERE guild_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (guild_id, limit),
                ).fetchall()

        result = []
        for row in rows:
            entry = dict(row)
            entry["keywords"] = json.loads(entry["keywords"])
            entry["metadata"] = json.loads(entry["metadata"])
            result.append(entry)
        return result

    def get_top_keywords(
        self, guild_id: str, limit: int = 20
    ) -> List[Tuple[str, int]]:
        """
        Return the *limit* most-frequent keywords across all entries for a guild,
        as a list of (keyword, count) tuples.
        """
        entries = self.get_recent_entries(guild_id, limit=1000)
        freq: Dict[str, int] = {}
        for entry in entries:
            for kw in entry["keywords"]:
                freq[kw] = freq.get(kw, 0) + 1
        return sorted(freq.items(), key=lambda x: -x[1])[:limit]

    def get_stats(self, guild_id: str) -> Dict[str, int]:
        """Return aggregate counts per content type for a guild."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM entries WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()[0]

            rows = conn.execute(
                """
                SELECT content_type, COUNT(*) AS cnt
                FROM entries
                WHERE guild_id = ?
                GROUP BY content_type
                """,
                (guild_id,),
            ).fetchall()

        _type_to_key = {"message": "messages", "file": "files", "link": "links"}
        stats: Dict[str, int] = {
            "total": total,
            "messages": 0,
            "files": 0,
            "links": 0,
        }
        for row in rows:
            ct, cnt = row["content_type"], row["cnt"]
            key = _type_to_key.get(ct)
            if key:
                stats[key] = cnt
        return stats

    def count_entries(self, guild_id: str) -> int:
        """Return the total number of stored entries for a guild."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM entries WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()[0]
