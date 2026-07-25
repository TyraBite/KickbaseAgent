"""SQLite storage for Kickbase snapshots.

Jeder Fetch-Lauf schreibt einen Tages-Snapshot (Datum als Primary-Key-Teil).
Mehrfache Laeufe am selben Tag ueberschreiben den Snapshot des Tages
(DELETE+INSERT bzw. INSERT OR REPLACE) - so bleibt die Historie sauber bei
einem Lauf/Tag, ist aber idempotent beim Testen.
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
    name TEXT,
    position TEXT,
    status_code INTEGER,
    status_label TEXT,
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
    name TEXT,
    position TEXT,
    status_code INTEGER,
    status_label TEXT,
    market_value INTEGER,
    price INTEGER,
    average_points INTEGER,
    offering_user_id TEXT,
    offering_username TEXT,
    is_system_offer INTEGER,
    pending_offers_count INTEGER,
    PRIMARY KEY (fetched_at, player_id)
);

CREATE TABLE IF NOT EXISTS league_ranking (
    fetched_at TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT,
    season_points INTEGER,
    matchday_points INTEGER,
    team_value INTEGER,
    season_placement INTEGER,
    matchday_placement INTEGER,
    recent_points TEXT,
    PRIMARY KEY (fetched_at, user_id)
);

CREATE TABLE IF NOT EXISTS own_budget_history (
    fetched_at TEXT PRIMARY KEY,
    user_id TEXT,
    budget REAL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_league_users(conn: sqlite3.Connection, users: list[dict]) -> None:
    if not users:
        return
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
            fetched_at, player_id, name, position, status_code, status_label,
            market_value, market_value_trend, average_points, total_points, team_id
        ) VALUES (
            :fetched_at, :player_id, :name, :position, :status_code, :status_label,
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
            fetched_at, player_id, name, position, status_code, status_label,
            market_value, price, average_points,
            offering_user_id, offering_username, is_system_offer, pending_offers_count
        ) VALUES (
            :fetched_at, :player_id, :name, :position, :status_code, :status_label,
            :market_value, :price, :average_points,
            :offering_user_id, :offering_username, :is_system_offer, :pending_offers_count
        )
        """,
        [{**listing, "fetched_at": fetched_at} for listing in listings],
    )
    conn.commit()


def replace_league_ranking(conn: sqlite3.Connection, fetched_at: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM league_ranking WHERE fetched_at = ?", (fetched_at,))
    conn.executemany(
        """
        INSERT INTO league_ranking (
            fetched_at, user_id, name, season_points, matchday_points,
            team_value, season_placement, matchday_placement, recent_points
        ) VALUES (
            :fetched_at, :user_id, :name, :season_points, :matchday_points,
            :team_value, :season_placement, :matchday_placement, :recent_points
        )
        """,
        [{**r, "fetched_at": fetched_at} for r in rows],
    )
    conn.commit()


def upsert_own_budget(
    conn: sqlite3.Connection, fetched_at: str, user_id: str | None, budget: float | None
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO own_budget_history (fetched_at, user_id, budget) VALUES (?, ?, ?)",
        (fetched_at, user_id, budget),
    )
    conn.commit()
