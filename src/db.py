"""SQLite storage for Kickbase snapshots.

Jeder Fetch-Lauf schreibt einen Tages-Snapshot (Datum als Primary-Key-Teil).
Mehrfache Laeufe am selben Tag ueberschreiben den Snapshot des Tages
(INSERT OR REPLACE) - so bleibt die Historie sauber bei einem Lauf/Tag,
ist aber idempotent beim Testen.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "kickbase.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS league_users (
    user_id TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE IF NOT EXISTS own_squad (
    fetched_at TEXT NOT NULL,
    player_id TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    status TEXT,
    market_value INTEGER,
    market_value_trend INTEGER,
    average_points INTEGER,
    total_points INTEGER,
    team_id TEXT,
    PRIMARY KEY (fetched_at, player_id)
);

CREATE TABLE IF NOT EXISTS market_listings (
    fetched_at TEXT NOT NULL,
    player_id TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    status TEXT,
    market_value INTEGER,
    price INTEGER,
    expiry INTEGER,
    average_points INTEGER,
    total_points INTEGER,
    offering_user_id TEXT,
    offering_username TEXT,
    is_system_offer INTEGER,
    PRIMARY KEY (fetched_at, player_id)
);

CREATE TABLE IF NOT EXISTS league_matchday_stats (
    day INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    day_points INTEGER,
    day_placement INTEGER,
    team_value INTEGER,
    points INTEGER,
    placement INTEGER,
    PRIMARY KEY (day, user_id)
);

CREATE TABLE IF NOT EXISTS own_status_history (
    fetched_at TEXT PRIMARY KEY,
    budget REAL,
    team_value REAL,
    placement INTEGER,
    points INTEGER
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_league_users(conn: sqlite3.Connection, users: list[dict]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO league_users (user_id, name) VALUES (:user_id, :name)",
        users,
    )
    conn.commit()


def replace_own_squad(conn: sqlite3.Connection, fetched_at: str, players: list[dict]) -> None:
    conn.execute("DELETE FROM own_squad WHERE fetched_at = ?", (fetched_at,))
    conn.executemany(
        """
        INSERT INTO own_squad (
            fetched_at, player_id, first_name, last_name, position, status,
            market_value, market_value_trend, average_points, total_points, team_id
        ) VALUES (
            :fetched_at, :player_id, :first_name, :last_name, :position, :status,
            :market_value, :market_value_trend, :average_points, :total_points, :team_id
        )
        """,
        [{**p, "fetched_at": fetched_at} for p in players],
    )
    conn.commit()


def replace_market_listings(conn: sqlite3.Connection, fetched_at: str, listings: list[dict]) -> None:
    conn.execute("DELETE FROM market_listings WHERE fetched_at = ?", (fetched_at,))
    conn.executemany(
        """
        INSERT INTO market_listings (
            fetched_at, player_id, first_name, last_name, position, status,
            market_value, price, expiry, average_points, total_points,
            offering_user_id, offering_username, is_system_offer
        ) VALUES (
            :fetched_at, :player_id, :first_name, :last_name, :position, :status,
            :market_value, :price, :expiry, :average_points, :total_points,
            :offering_user_id, :offering_username, :is_system_offer
        )
        """,
        [{**listing, "fetched_at": fetched_at} for listing in listings],
    )
    conn.commit()


def upsert_matchday_stats(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO league_matchday_stats (
            day, user_id, day_points, day_placement, team_value, points, placement
        ) VALUES (
            :day, :user_id, :day_points, :day_placement, :team_value, :points, :placement
        )
        """,
        rows,
    )
    conn.commit()


def upsert_own_status(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO own_status_history (
            fetched_at, budget, team_value, placement, points
        ) VALUES (:fetched_at, :budget, :team_value, :placement, :points)
        """,
        row,
    )
    conn.commit()
