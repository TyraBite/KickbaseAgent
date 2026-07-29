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
            "team_id": "t1", "team_name": "Bremen", "starting_rank": 1,
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
            "team_id": "t2", "team_name": "Koeln", "starting_rank": 2,
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
            "team_id": "t3", "team_name": "Leipzig", "starting_rank": 3,
        }])

        cache = db.get_market_value_history_cache(conn, "2026-07-29")

        self.assertNotIn("p3", cache)
