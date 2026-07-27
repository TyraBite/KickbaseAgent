"""Tests fuer die reine Berechnungslogik in src/manager_budgets.py.

Feed-Strukturen als Fixtures sind an echte, am 27.07.2026 gegen den echten
Account verifizierte Activity-Feed-Eintraege angelehnt (siehe Plan-Dokument):
Trades referenzieren Manager per NAME ("byr"/"slr"), nicht per User-Id.
"""

import unittest

from src import manager_budgets as mb


def _trade(t, price, byr=None, slr=None):
    data = {"t": t, "trp": price, "pi": "1", "pn": "Spieler"}
    if byr:
        data["byr"] = byr
    if slr:
        data["slr"] = slr
    return {"i": "1", "t": 15, "coc": 0, "data": data, "dt": "2026-07-27T07:00:00Z"}


def _login_bonus(amount, dt="2026-07-27T06:00:00Z"):
    return {"i": "2", "t": 22, "coc": 0, "data": {"bn": amount, "day": 1}, "dt": dt}


def _achievement(achievement_id, dt="2026-07-25T12:00:00Z"):
    return {"i": "3", "t": 26, "coc": 0, "data": {"t": achievement_id}, "dt": dt}


class ParseTradesTests(unittest.TestCase):
    def test_filters_only_trade_type(self):
        activities = [_trade(1, 100, byr="A"), _login_bonus(20)]
        trades = mb._parse_trades(activities, league_start_date=None)
        self.assertEqual(len(trades), 1)

    def test_applies_date_cutoff(self):
        old = _trade(1, 100, byr="A")
        old["dt"] = "2025-01-01T00:00:00Z"
        new = _trade(1, 100, byr="A")
        new["dt"] = "2026-08-01T00:00:00Z"
        trades = mb._parse_trades([old, new], league_start_date="2026-07-01")
        self.assertEqual(len(trades), 1)


class ReplayTradeLedgerTests(unittest.TestCase):
    def test_system_purchase_deducts_from_buyer_only(self):
        trades = [_trade(1, 1000, byr="A")["data"]]
        budgets = mb._replay_trade_ledger(trades, {"A", "B"}, start_budget=10_000)
        self.assertEqual(budgets["A"], 9_000)
        self.assertEqual(budgets["B"], 10_000)

    def test_system_sale_credits_seller_only(self):
        trades = [_trade(2, 1000, slr="B")["data"]]
        budgets = mb._replay_trade_ledger(trades, {"A", "B"}, start_budget=10_000)
        self.assertEqual(budgets["A"], 10_000)
        self.assertEqual(budgets["B"], 11_000)

    def test_manager_to_manager_trade_moves_between_both(self):
        trades = [_trade(1, 1000, byr="A", slr="B")["data"]]
        budgets = mb._replay_trade_ledger(trades, {"A", "B"}, start_budget=10_000)
        self.assertEqual(budgets["A"], 9_000)
        self.assertEqual(budgets["B"], 11_000)

    def test_seeds_all_known_managers_even_without_trades(self):
        # Referenz-Bug-Fix: ein Manager ohne jeden Trade darf nicht fehlen.
        budgets = mb._replay_trade_ledger([], {"A", "B", "C"}, start_budget=5_000)
        self.assertEqual(set(budgets), {"A", "B", "C"})
        self.assertEqual(budgets["C"], 5_000)

    def test_ignores_unknown_participant_names(self):
        trades = [_trade(1, 1000, byr="Unknown")["data"]]
        budgets = mb._replay_trade_ledger(trades, {"A"}, start_budget=5_000)
        self.assertEqual(budgets["A"], 5_000)


class LoginBonusTests(unittest.TestCase):
    def test_sums_only_login_bonus_entries(self):
        activities = [_login_bonus(20_000), _login_bonus(5_000), _trade(1, 1000, byr="A")]
        self.assertEqual(mb._login_bonus_total(activities), 25_000)

    def test_empty_feed_is_zero(self):
        self.assertEqual(mb._login_bonus_total([]), 0)


class UniqueAchievementIdsTests(unittest.TestCase):
    def test_dedupes_repeated_achievement_ids(self):
        # Referenz-Bug-Fix: wiederholt ausgeloeste Achievements nicht doppelt zaehlen.
        activities = [_achievement(500), _achievement(500), _achievement(601)]
        self.assertEqual(mb.unique_achievement_ids(activities), {500, 601})

    def test_ignores_non_achievement_entries(self):
        activities = [_trade(1, 1000, byr="A"), _achievement(500)]
        self.assertEqual(mb.unique_achievement_ids(activities), {500})


class ScaleAchievementBonusTests(unittest.TestCase):
    def test_anchor_user_gets_full_bonus(self):
        self.assertEqual(mb._scale_achievement_bonus(1000, own_points=50, target_points=50), 1000)

    def test_scales_proportionally_to_points_ratio(self):
        self.assertEqual(mb._scale_achievement_bonus(1000, own_points=50, target_points=25), 500)

    def test_zero_own_points_returns_anchor_unscaled(self):
        self.assertEqual(mb._scale_achievement_bonus(1000, own_points=0, target_points=25), 1000)

    def test_missing_target_points_returns_zero(self):
        self.assertEqual(mb._scale_achievement_bonus(1000, own_points=50, target_points=None), 0.0)


class OverdraftTests(unittest.TestCase):
    def test_matches_kickbase_33_percent_rule(self):
        max_negative, available = mb._overdraft(budget=1_000_000, team_value=10_000_000)
        self.assertAlmostEqual(max_negative, -3_630_000)
        self.assertAlmostEqual(available, 4_630_000)

    def test_missing_team_value_falls_back_to_zero(self):
        max_negative, available = mb._overdraft(budget=1_000_000, team_value=None)
        self.assertAlmostEqual(max_negative, -330_000)
        self.assertAlmostEqual(available, 1_330_000)


class EstimateAllTests(unittest.TestCase):
    def setUp(self):
        self.ranking_rows = [
            {"user_id": "1", "name": "Tyra", "team_value": 80_000_000, "season_points": 100},
            {"user_id": "2", "name": "Bobetinho", "team_value": 60_000_000, "season_points": 50},
        ]

    def test_own_row_is_synced_to_exact_budget_not_estimate(self):
        activities = [_trade(1, 5_000_000, byr="Tyra")]
        results = mb.estimate_all(
            activities=activities,
            ranking_rows=self.ranking_rows,
            own_name="Tyra",
            own_budget=87_832_916,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_bonus_total=0,
        )
        own_row = next(r for r in results if r["name"] == "Tyra")
        self.assertEqual(own_row["estimated_budget"], 87_832_916)
        self.assertEqual(own_row["is_own_exact"], 1)

    def test_other_manager_is_marked_as_estimate(self):
        results = mb.estimate_all(
            activities=[],
            ranking_rows=self.ranking_rows,
            own_name="Tyra",
            own_budget=50_000_000,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_bonus_total=0,
        )
        other_row = next(r for r in results if r["name"] == "Bobetinho")
        self.assertEqual(other_row["is_own_exact"], 0)
        self.assertEqual(other_row["estimated_budget"], 50_000_000)

    def test_trade_count_reflects_participation(self):
        activities = [
            _trade(1, 1_000_000, byr="Bobetinho"),
            _trade(2, 500_000, slr="Bobetinho"),
        ]
        results = mb.estimate_all(
            activities=activities,
            ranking_rows=self.ranking_rows,
            own_name="Tyra",
            own_budget=50_000_000,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_bonus_total=0,
        )
        other_row = next(r for r in results if r["name"] == "Bobetinho")
        self.assertEqual(other_row["trade_count"], 2)

    def test_sorted_by_available_budget_descending(self):
        results = mb.estimate_all(
            activities=[],
            ranking_rows=self.ranking_rows,
            own_name="Tyra",
            own_budget=50_000_000,
            start_budget=50_000_000,
            league_start_date=None,
            achievement_bonus_total=0,
        )
        available = [r["available_budget"] for r in results]
        self.assertEqual(available, sorted(available, reverse=True))


if __name__ == "__main__":
    unittest.main()
