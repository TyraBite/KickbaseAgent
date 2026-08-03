import sqlite3
import unittest

from src import db


def _memory_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    return conn


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
