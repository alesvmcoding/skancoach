"""SQLite helper for storing a classified YouTube title on a video row.

Expected table: videos(video_id TEXT PRIMARY KEY, hunt_type TEXT,
players_count INTEGER, needs_review INTEGER, review_reason TEXT).
"""

from __future__ import annotations

import sqlite3

from title_classifier import classify_hunt_title


def ensure_classification_columns(connection: sqlite3.Connection) -> None:
    """Add classification columns to an existing `videos` table if missing."""
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(videos)")
    }
    if not existing:
        raise sqlite3.OperationalError("videos table does not exist")
    for name, sql_type in (
        ("hunt_type", "TEXT"),
        ("players_count", "INTEGER"),
        ("needs_review", "INTEGER NOT NULL DEFAULT 0"),
        ("review_reason", "TEXT"),
    ):
        if name not in existing:
            connection.execute(f"ALTER TABLE videos ADD COLUMN {name} {sql_type}")


def store_title_classification(
    connection: sqlite3.Connection, video_id: str, title: str, description: str = ""
) -> None:
    """Update classification fields for an already-imported video."""
    result = classify_hunt_title(title, description)
    cursor = connection.execute(
        """UPDATE videos
           SET hunt_type = ?, players_count = ?, needs_review = ?, review_reason = ?
           WHERE video_id = ?""",
        (
            result.hunt_type,
            result.players_count,
            int(result.needs_review),
            result.review_reason,
            video_id,
        ),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"video_id not found: {video_id}")
