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
    market_value_change_7d INTEGER,
    market_value_low_92d INTEGER,
    market_value_high_92d INTEGER,
    market_value_in_drop_phase INTEGER,
    average_points INTEGER,
    total_points INTEGER,
    team_id TEXT,
    team_name TEXT,
    starting_rank INTEGER,
    purchase_price INTEGER,
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
    market_value_change_7d INTEGER,
    market_value_low_92d INTEGER,
    market_value_high_92d INTEGER,
    market_value_in_drop_phase INTEGER,
    price INTEGER,
    price_delta_pct REAL,
    average_points INTEGER,
    total_points INTEGER,
    team_id TEXT,
    team_name TEXT,
    offering_user_id TEXT,
    offering_username TEXT,
    is_system_offer INTEGER,
    pending_offers_count INTEGER,
    leading_bid_username TEXT,
    leading_bid_price INTEGER,
    is_own_leading_bid INTEGER,
    starting_rank INTEGER,
    listed_at TEXT,
    expires_at TEXT,
    expiry_is_estimate INTEGER,
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
    current_lineup_player_ids TEXT,
    recent_matchday_points TEXT,
    PRIMARY KEY (fetched_at, user_id)
);

CREATE TABLE IF NOT EXISTS own_budget_history (
    fetched_at TEXT PRIMARY KEY,
    user_id TEXT,
    budget REAL
);

CREATE TABLE IF NOT EXISTS season_context (
    fetched_at TEXT PRIMARY KEY,
    season_name TEXT,
    current_matchday INTEGER,
    next_deadline_at TEXT,
    days_until_next_deadline INTEGER,
    market_value_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS manager_budgets (
    fetched_at TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT,
    estimated_budget REAL,
    is_own_exact INTEGER,
    team_value INTEGER,
    max_negative_budget REAL,
    available_budget REAL,
    trade_count INTEGER,
    PRIMARY KEY (fetched_at, user_id)
);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Fuegt eine Spalte nachtraeglich hinzu, falls sie in einer bereits
    committeten DB (data/kickbase.db) noch fehlt - CREATE TABLE IF NOT EXISTS
    aendert ein bestehendes Schema nicht."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    _ensure_column(conn, "own_squad", "starting_rank", "INTEGER")
    _ensure_column(conn, "own_squad", "purchase_price", "INTEGER")
    _ensure_column(conn, "market_listings", "starting_rank", "INTEGER")
    _ensure_column(conn, "market_listings", "listed_at", "TEXT")
    _ensure_column(conn, "market_listings", "expires_at", "TEXT")
    _ensure_column(conn, "market_listings", "expiry_is_estimate", "INTEGER")
    conn.commit()
    return conn


def get_market_value_history_cache(conn: sqlite3.Connection, fetched_at: str) -> dict[str, dict]:
    """Liest bereits HEUTE (fetched_at) erfolgreich abgerufene Marktwert-
    Historie-Felder je Spieler aus own_squad+market_listings. Basis fuer
    fetcher._apply_market_value_history()s Skip-wenn-heute-schon-bekannt-
    Logik: die echte Kickbase-Historie aendert sich ohnehin nur ~1x/Tag,
    frueher wurde sie trotzdem bei jedem 2h-Lauf neu abgerufen (~12x/Tag
    identische Requests). Nur Zeilen mit befuelltem market_value_change_7d
    zaehlen als 'schon abgerufen' (frisch gebaute Rows starten mit None,
    siehe fetcher._squad_item_to_row/_market_item_to_row)."""
    cache: dict[str, dict] = {}
    for table in ("own_squad", "market_listings"):
        rows = conn.execute(
            f"""SELECT player_id, market_value_change_7d, market_value_low_92d,
                       market_value_high_92d, market_value_in_drop_phase
                FROM {table} WHERE fetched_at = ? AND market_value_change_7d IS NOT NULL""",
            (fetched_at,),
        ).fetchall()
        for player_id, change_7d, low_92d, high_92d, drop_phase in rows:
            cache[player_id] = {
                "market_value_change_7d": change_7d,
                "market_value_low_92d": low_92d,
                "market_value_high_92d": high_92d,
                "market_value_in_drop_phase": drop_phase,
            }
    return cache


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
            market_value, market_value_trend, market_value_change_7d,
            market_value_low_92d, market_value_high_92d, market_value_in_drop_phase,
            average_points, total_points, team_id, team_name, starting_rank, purchase_price
        ) VALUES (
            :fetched_at, :player_id, :name, :position, :status_code, :status_label,
            :market_value, :market_value_trend, :market_value_change_7d,
            :market_value_low_92d, :market_value_high_92d, :market_value_in_drop_phase,
            :average_points, :total_points, :team_id, :team_name, :starting_rank, :purchase_price
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
            market_value, market_value_change_7d, market_value_low_92d,
            market_value_high_92d, market_value_in_drop_phase,
            price, price_delta_pct, average_points, total_points, team_id, team_name,
            offering_user_id, offering_username, is_system_offer, pending_offers_count,
            leading_bid_username, leading_bid_price, is_own_leading_bid, starting_rank,
            listed_at, expires_at, expiry_is_estimate
        ) VALUES (
            :fetched_at, :player_id, :name, :position, :status_code, :status_label,
            :market_value, :market_value_change_7d, :market_value_low_92d,
            :market_value_high_92d, :market_value_in_drop_phase,
            :price, :price_delta_pct, :average_points, :total_points, :team_id, :team_name,
            :offering_user_id, :offering_username, :is_system_offer, :pending_offers_count,
            :leading_bid_username, :leading_bid_price, :is_own_leading_bid, :starting_rank,
            :listed_at, :expires_at, :expiry_is_estimate
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
            team_value, season_placement, matchday_placement,
            current_lineup_player_ids, recent_matchday_points
        ) VALUES (
            :fetched_at, :user_id, :name, :season_points, :matchday_points,
            :team_value, :season_placement, :matchday_placement,
            :current_lineup_player_ids, :recent_matchday_points
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


def upsert_season_context(conn: sqlite3.Connection, fetched_at: str, context: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO season_context (
            fetched_at, season_name, current_matchday, next_deadline_at,
            days_until_next_deadline, market_value_updated_at
        ) VALUES (
            :fetched_at, :season_name, :current_matchday, :next_deadline_at,
            :days_until_next_deadline, :market_value_updated_at
        )
        """,
        {**context, "fetched_at": fetched_at},
    )
    conn.commit()


def replace_manager_budgets(conn: sqlite3.Connection, fetched_at: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM manager_budgets WHERE fetched_at = ?", (fetched_at,))
    conn.executemany(
        """
        INSERT INTO manager_budgets (
            fetched_at, user_id, name, estimated_budget, is_own_exact,
            team_value, max_negative_budget, available_budget, trade_count
        ) VALUES (
            :fetched_at, :user_id, :name, :estimated_budget, :is_own_exact,
            :team_value, :max_negative_budget, :available_budget, :trade_count
        )
        """,
        [{**row, "fetched_at": fetched_at} for row in rows],
    )
    conn.commit()
