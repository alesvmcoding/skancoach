"""SQLite for local use and PostgreSQL (Neon) when DATABASE_URL is configured."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env.local")
except ImportError:
    pass

try:
    import psycopg
    POSTGRES_ERROR = psycopg.Error
except ImportError:  # PostgreSQL support is optional for local SQLite use.
    psycopg = None
    class _MissingPostgresDriverError(Exception):
        pass
    POSTGRES_ERROR = _MissingPostgresDriverError

DATABASE_ERRORS = (sqlite3.Error, POSTGRES_ERROR)


class HybridRow(dict):
    """Mapping row that also supports SQLite-style integer indexes."""
    def __init__(self, values, columns):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def hybrid_row_factory(cursor):
    columns = [column.name for column in cursor.description]
    return lambda values: HybridRow(values, columns)


def _postgres_sql(sql: str) -> str:
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    sql = sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    sql = sql.replace("last_insert_rowid()", "lastval()")
    sql = sql.replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT (CURRENT_TIMESTAMP::text)")
    sql = sql.replace("confirmed_at=CURRENT_TIMESTAMP", "confirmed_at=CURRENT_TIMESTAMP::text")
    sql = sql.replace("ORDER BY rowid DESC", "ORDER BY ctid DESC")
    sql = sql.replace(
        "group_concat(DISTINCT CASE WHEN p.vocation != 'CHANNEL' THEN p.vocation END)",
        "STRING_AGG(DISTINCT CASE WHEN p.vocation != 'CHANNEL' THEN p.vocation END, ',')",
    )
    sql = sql.replace(
        "group_concat(DISTINCT p.name)", "STRING_AGG(DISTINCT p.name, ',')"
    )
    if "INSERT INTO managed_sources" in sql and "SELECT CASE WHEN vocation" in sql:
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    sql = re.sub(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql)
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    @property
    def row_factory(self):
        return self._connection.row_factory

    @row_factory.setter
    def row_factory(self, value):
        # App code assigns sqlite3.Row; retain the hybrid row factory instead.
        self._connection.row_factory = hybrid_row_factory

    def execute(self, sql, parameters=None):
        sql = _postgres_sql(sql)
        parameters = () if parameters is None else parameters
        cursor = self._connection.cursor()
        cursor.execute(sql, parameters)
        return cursor

    def executemany(self, sql, parameters):
        cursor = self._connection.cursor()
        cursor.executemany(_postgres_sql(sql), parameters)
        return cursor

    def close(self):
        self._connection.close()

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._connection.__exit__(exc_type, exc, traceback)
        finally:
            self._connection.close()


def connect_database(path: str | Path | None = None):
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return sqlite3.connect(path or ":memory:")
    if psycopg is None:
        raise RuntimeError("Instale as dependências PostgreSQL de requirements.txt.")
    # Neon requires TLS; adding sslmode when the provider omitted it is safe.
    if "sslmode=" not in url:
        url += "&sslmode=require" if "?" in url else "?sslmode=require"
    connection = psycopg.connect(url, row_factory=hybrid_row_factory)
    return PostgresConnection(connection)


def initialize_postgres_catalog(sqlite_path: str | Path) -> None:
    """Create catalog tables and seed them once from the bundled SQLite catalog."""
    with connect_database() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY, position INTEGER, title TEXT NOT NULL,
            description TEXT, published_at TEXT, channel_title TEXT,
            video_url TEXT NOT NULL, hunt_type TEXT, players_count INTEGER,
            needs_review INTEGER NOT NULL DEFAULT 0, review_reason TEXT,
            xp_raw_per_hour DOUBLE PRECISION, xp_raw_display TEXT,
            xp_source_display TEXT, xp_multiplier_percent DOUBLE PRECISION,
            xp_raw_status TEXT, xp_raw_note TEXT, profit_per_hour DOUBLE PRECISION,
            profit_display TEXT, profit_source_display TEXT, profit_assumption TEXT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS playlists (
            playlist_id TEXT PRIMARY KEY, vocation TEXT NOT NULL,
            name TEXT NOT NULL, playlist_url TEXT NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS playlist_videos (
            playlist_id TEXT NOT NULL, video_id TEXT NOT NULL, position INTEGER,
            PRIMARY KEY (playlist_id, video_id)
        )""")
        count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        if count:
            return
        source = sqlite3.connect(sqlite_path)
        source.row_factory = sqlite3.Row
        try:
            for table, columns in (
                ("videos", "video_id,position,title,description,published_at,channel_title,video_url,hunt_type,players_count,needs_review,review_reason,xp_raw_per_hour,xp_raw_display,xp_source_display,xp_multiplier_percent,xp_raw_status,xp_raw_note,profit_per_hour,profit_display,profit_source_display,profit_assumption"),
                ("playlists", "playlist_id,vocation,name,playlist_url"),
                ("playlist_videos", "playlist_id,video_id,position"),
            ):
                records = source.execute(f"SELECT {columns} FROM {table}").fetchall()
                names = columns.split(",")
                params = ",".join("%s" for _ in names)
                connection.executemany(
                    f"INSERT INTO {table} ({columns}) VALUES ({params}) ON CONFLICT DO NOTHING",
                    [tuple(record[name] for name in names) for record in records],
                )
        finally:
            source.close()


def seed_postgres_community_data(sqlite_path: str | Path) -> None:
    """Copy existing local community records into a new Neon database once."""
    if psycopg is None:
        return
    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    try:
        existing_tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with connect_database() as connection:
            for table, columns in (
                ("hunt_feedback", "id,video_id,nickname,vocation,player_level,tested,outdated,xp_raw,profit,difficulty,result,created_at"),
                ("tc_donations", "id,nickname,amount_tc,show_in_ranking,status,created_at,confirmed_at"),
                ("managed_sources", "id,source_type,source_key,name,vocation,source_url,promotion_status,created_at"),
                ("promotion_requests", "id,creator_name,youtube_url,vocation,note,status,created_at"),
            ):
                if table not in existing_tables:
                    continue
                records = source.execute(f"SELECT {columns} FROM {table}").fetchall()
                names = columns.split(",")
                params = ",".join("%s" for _ in names)
                connection.executemany(
                    f"INSERT INTO {table} ({columns}) VALUES ({params}) ON CONFLICT DO NOTHING",
                    [tuple(record[name] for name in names) for record in records],
                )
                if table != "managed_sources":
                    connection.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), EXISTS(SELECT 1 FROM {table}))"
                    )
    finally:
        source.close()
