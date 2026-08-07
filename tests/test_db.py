import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import db


def _memory_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    return conn


class ConnectMigratesLegacyOwnSquadSchemaTests(unittest.TestCase):
    """Regression: eine bereits bestehende data/kickbase.db aus der Zeit vor
    dem purchase_price-Feld hat own_squad OHNE diese Spalte. CREATE TABLE
    IF NOT EXISTS aendert das bestehende Schema nicht - ohne einen
    _ensure_column()-Eintrag crasht replace_own_squad() live mit 'table
    own_squad has no column named purchase_price', sobald jemand db.connect()
    gegen eine so alte, lokal liegen gebliebene Datei aufruft (2026-08-07,
    live in der Sandbox reproduziert)."""

    def test_connect_adds_purchase_price_to_pre_existing_own_squad_table(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            legacy_db_path = Path(tmp_dir) / "kickbase.db"
            legacy_conn = sqlite3.connect(legacy_db_path)
            legacy_conn.executescript("""
                CREATE TABLE own_squad (
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
                    PRIMARY KEY (fetched_at, player_id)
                );
            """)
            legacy_conn.commit()
            legacy_conn.close()

            with patch.object(db, "DB_PATH", legacy_db_path):
                conn = db.connect()
                db.replace_own_squad(conn, "2026-08-07", [{
                    "player_id": "p1", "name": "Foo", "position": "Sturm",
                    "status_code": 0, "status_label": None, "market_value": 1_000_000,
                    "market_value_trend": 0, "market_value_change_7d": 50_000,
                    "market_value_low_92d": 900_000, "market_value_high_92d": 1_100_000,
                    "market_value_in_drop_phase": 0, "average_points": 100, "total_points": 500,
                    "team_id": "t1", "team_name": "Bremen", "starting_rank": 1,
                    "purchase_price": 950_000,
                }])

                row = conn.execute(
                    "SELECT purchase_price FROM own_squad WHERE player_id = ?", ("p1",)
                ).fetchone()

        self.assertEqual(row[0], 950_000)


class GetMarketValueHistoryCacheTests(unittest.TestCase):
    def test_returns_fields_for_player_already_enriched_today_in_own_squad(self):
        conn = _memory_conn()
        db.replace_own_squad(conn, "2026-07-29", [{
            "player_id": "p1", "name": "Foo", "position": "Sturm",
            "status_code": 0, "status_label": None, "market_value": 1_000_000,
            "market_value_trend": 0, "market_value_change_7d": 50_000,
            "market_value_low_92d": 900_000, "market_value_high_92d": 1_100_000,
            "market_value_in_drop_phase": 0, "average_points": 100, "total_points": 500,
            "team_id": "t1", "team_name": "Bremen", "starting_rank": 1, "purchase_price": None,
        }])

        cache = db.get_market_value_history_cache(conn, "2026-07-29")

        self.assertEqual(cache["p1"]["market_value_change_7d"], 50_000)
        self.assertEqual(cache["p1"]["market_value_low_92d"], 900_000)

    def test_ignores_rows_not_yet_enriched(self):
        conn = _memory_conn()
        db.replace_own_squad(conn, "2026-07-29", [{
            "player_id": "p2", "name": "Bar", "position": "Abwehr",
            "status_code": 0, "status_label": None, "market_value": 500_000,
            "market_value_trend": 0, "market_value_change_7d": None,
            "market_value_low_92d": None, "market_value_high_92d": None,
            "market_value_in_drop_phase": None, "average_points": 80, "total_points": 400,
            "team_id": "t2", "team_name": "Koeln", "starting_rank": 2, "purchase_price": None,
        }])

        cache = db.get_market_value_history_cache(conn, "2026-07-29")

        self.assertNotIn("p2", cache)

    def test_ignores_other_days(self):
        conn = _memory_conn()
        db.replace_own_squad(conn, "2026-07-28", [{
            "player_id": "p3", "name": "Baz", "position": "Mittelfeld",
            "status_code": 0, "status_label": None, "market_value": 2_000_000,
            "market_value_trend": 0, "market_value_change_7d": 10_000,
            "market_value_low_92d": 1_900_000, "market_value_high_92d": 2_100_000,
            "market_value_in_drop_phase": 0, "average_points": 120, "total_points": 600,
            "team_id": "t3", "team_name": "Leipzig", "starting_rank": 3, "purchase_price": None,
        }])

        cache = db.get_market_value_history_cache(conn, "2026-07-29")

        self.assertNotIn("p3", cache)


def _market_listing_row(**overrides):
    row = {
        "player_id": "p1", "name": "Foo", "position": "Sturm",
        "status_code": 0, "status_label": None, "market_value": 1_000_000,
        "market_value_change_7d": 50_000, "market_value_low_92d": 900_000,
        "market_value_high_92d": 1_100_000, "market_value_in_drop_phase": 0,
        "price": 1_050_000, "price_delta_pct": 5.0, "average_points": 100, "total_points": 500,
        "team_id": "t1", "team_name": "Bremen",
        "offering_user_id": "u1", "offering_username": "Rivale",
        "is_system_offer": 0, "pending_offers_count": 1,
        "leading_bid_username": "Rivale", "leading_bid_price": 1_050_000,
        "is_own_leading_bid": 0, "starting_rank": 1,
        "listed_at": "2026-08-03T10:00:00Z", "expires_at": "2026-08-04T10:00:00Z",
        "expiry_is_estimate": 0,
    }
    row.update(overrides)
    return row


class ReplaceMarketListingsRoundTripTests(unittest.TestCase):
    def test_written_row_reads_back_unchanged(self):
        conn = _memory_conn()
        db.replace_market_listings(conn, "2026-08-03", [_market_listing_row()])

        row = conn.execute(
            "SELECT player_id, name, market_value, price_delta_pct, offering_username "
            "FROM market_listings WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()

        self.assertEqual(row, ("p1", "Foo", 1_000_000, 5.0, "Rivale"))

    def test_writing_same_fetched_at_twice_stays_idempotent(self):
        # replace_market_listings loescht vor dem Insert per fetched_at -
        # ein erneuter Lauf desselben Tages (z.B. Retry) darf die Tabelle
        # nicht auf 2N Zeilen verdoppeln.
        conn = _memory_conn()
        rows = [_market_listing_row(player_id="p1"), _market_listing_row(player_id="p2")]

        db.replace_market_listings(conn, "2026-08-03", rows)
        db.replace_market_listings(conn, "2026-08-03", rows)

        count = conn.execute(
            "SELECT COUNT(*) FROM market_listings WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()[0]
        self.assertEqual(count, 2)


class UpsertOwnBudgetRoundTripTests(unittest.TestCase):
    def test_written_values_read_back_unchanged(self):
        conn = _memory_conn()
        db.upsert_own_budget(conn, "2026-08-03", "u1", 25_000_000.0)

        row = conn.execute(
            "SELECT fetched_at, user_id, budget FROM own_budget_history WHERE fetched_at = ?",
            ("2026-08-03",),
        ).fetchone()

        self.assertEqual(row, ("2026-08-03", "u1", 25_000_000.0))

    def test_writing_same_fetched_at_twice_stays_idempotent(self):
        # INSERT OR REPLACE mit fetched_at als PRIMARY KEY - ein zweiter
        # Schreibvorgang fuer denselben Tag ersetzt die Zeile statt eine
        # zweite anzulegen.
        conn = _memory_conn()

        db.upsert_own_budget(conn, "2026-08-03", "u1", 25_000_000.0)
        db.upsert_own_budget(conn, "2026-08-03", "u1", 26_000_000.0)

        count = conn.execute(
            "SELECT COUNT(*) FROM own_budget_history WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()[0]
        self.assertEqual(count, 1)
        budget = conn.execute(
            "SELECT budget FROM own_budget_history WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()[0]
        self.assertEqual(budget, 26_000_000.0)


class UpsertSeasonContextRoundTripTests(unittest.TestCase):
    CONTEXT = {
        "season_name": "2026/27", "current_matchday": 3, "next_deadline_at": "2026-08-08T17:30:00Z",
        "days_until_next_deadline": 5, "market_value_updated_at": "2026-08-03T20:00:00Z",
    }

    def test_written_values_read_back_unchanged(self):
        conn = _memory_conn()
        db.upsert_season_context(conn, "2026-08-03", self.CONTEXT)

        row = conn.execute(
            "SELECT season_name, current_matchday, days_until_next_deadline "
            "FROM season_context WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()

        self.assertEqual(row, ("2026/27", 3, 5))

    def test_writing_same_fetched_at_twice_stays_idempotent(self):
        conn = _memory_conn()

        db.upsert_season_context(conn, "2026-08-03", self.CONTEXT)
        db.upsert_season_context(conn, "2026-08-03", {**self.CONTEXT, "current_matchday": 4})

        count = conn.execute(
            "SELECT COUNT(*) FROM season_context WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()[0]
        self.assertEqual(count, 1)
        matchday = conn.execute(
            "SELECT current_matchday FROM season_context WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()[0]
        self.assertEqual(matchday, 4)


def _manager_budget_row(**overrides):
    row = {
        "user_id": "u1", "name": "Rivale", "estimated_budget": 30_000_000.0,
        "is_own_exact": 0, "team_value": 200_000_000, "max_negative_budget": -5_000_000.0,
        "available_budget": 30_000_000.0, "trade_count": 4,
    }
    row.update(overrides)
    return row


class ReplaceManagerBudgetsRoundTripTests(unittest.TestCase):
    def test_written_row_reads_back_unchanged(self):
        conn = _memory_conn()
        db.replace_manager_budgets(conn, "2026-08-03", [_manager_budget_row()])

        row = conn.execute(
            "SELECT user_id, name, estimated_budget, trade_count "
            "FROM manager_budgets WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()

        self.assertEqual(row, ("u1", "Rivale", 30_000_000.0, 4))

    def test_writing_same_fetched_at_twice_stays_idempotent(self):
        conn = _memory_conn()
        rows = [_manager_budget_row(user_id="u1"), _manager_budget_row(user_id="u2")]

        db.replace_manager_budgets(conn, "2026-08-03", rows)
        db.replace_manager_budgets(conn, "2026-08-03", rows)

        count = conn.execute(
            "SELECT COUNT(*) FROM manager_budgets WHERE fetched_at = ?", ("2026-08-03",)
        ).fetchone()[0]
        self.assertEqual(count, 2)
