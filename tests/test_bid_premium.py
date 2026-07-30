import unittest
from unittest.mock import MagicMock, patch

from src.bid_premium import (
    _compute_premium,
    _days_since_epoch,
    _filter_new_system_purchases,
    _is_system_purchase,
    _market_value_at,
    build_new_entries,
)


def _trade_activity(dt, byr="Fassii", slr=None, trp=1_000_000, pi="p1", pn="Spieler"):
    data = {"byr": byr, "trp": trp, "pi": pi, "pn": pn}
    if slr:
        data["slr"] = slr
    return {"i": f"act_{dt}", "t": 15, "dt": dt, "data": data}


class IsSystemPurchaseTests(unittest.TestCase):
    def test_trade_without_slr_is_system_purchase(self):
        self.assertTrue(_is_system_purchase(_trade_activity("2026-07-01T10:00:00Z")))

    def test_trade_with_slr_is_not_system_purchase(self):
        self.assertFalse(_is_system_purchase(_trade_activity("2026-07-01T10:00:00Z", slr="Rivale")))

    def test_non_trade_activity_type_is_not_system_purchase(self):
        self.assertFalse(_is_system_purchase({"i": "act_1", "t": 22, "dt": "2026-07-01T10:00:00Z", "data": {"bn": 500}}))


class ComputePremiumTests(unittest.TestCase):
    def test_price_above_market_value_is_positive_premium(self):
        self.assertAlmostEqual(_compute_premium(11_000_000, 10_000_000), 0.1)

    def test_price_equal_market_value_is_zero_premium(self):
        self.assertEqual(_compute_premium(10_000_000, 10_000_000), 0.0)

    def test_zero_market_value_returns_none(self):
        self.assertIsNone(_compute_premium(1_000_000, 0))

    def test_none_market_value_returns_none(self):
        self.assertIsNone(_compute_premium(1_000_000, None))


class FilterNewSystemPurchasesTests(unittest.TestCase):
    def test_without_pointer_returns_all_system_purchases(self):
        activities = [
            _trade_activity("2026-07-01T10:00:00Z"),
            _trade_activity("2026-07-02T10:00:00Z", slr="Rivale"),
            _trade_activity("2026-07-03T10:00:00Z"),
        ]
        result = _filter_new_system_purchases(activities, since_dt=None)
        self.assertEqual(len(result), 2)

    def test_with_pointer_only_returns_purchases_on_or_after_pointer(self):
        activities = [
            _trade_activity("2026-07-01T10:00:00Z"),
            _trade_activity("2026-07-03T10:00:00Z"),
        ]
        result = _filter_new_system_purchases(activities, since_dt="2026-07-02T00:00:00Z")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["dt"], "2026-07-03T10:00:00Z")

    def test_pointer_boundary_is_inclusive(self):
        # Inklusiv statt exklusiv gewaehlt: idempotente Firestore-Writes
        # (Doc-Id = Activity-Id) machen ein gelegentliches Re-Verarbeiten
        # der Grenz-Aktivitaet harmlos - lieber das als eine echte neue
        # Aktivitaet exakt auf dem Zeiger-Zeitstempel zu verpassen.
        activities = [_trade_activity("2026-07-02T00:00:00Z")]
        result = _filter_new_system_purchases(activities, since_dt="2026-07-02T00:00:00Z")
        self.assertEqual(len(result), 1)


class DaysSinceEpochTests(unittest.TestCase):
    def test_known_date_matches_kickbase_confirmed_value(self):
        # 2026-07-26 == 20660 Tage seit Epoch, bestaetigt im Docstring von
        # get_market_value_history() (27.07.2026 live gegengecheckt).
        self.assertEqual(_days_since_epoch("2026-07-26T12:00:00Z"), 20660)


class MarketValueAtTests(unittest.TestCase):
    def test_returns_value_for_exact_matching_day(self):
        history = {"it": [{"dt": 20660, "mv": 10_000_000}, {"dt": 20661, "mv": 10_100_000}]}
        self.assertEqual(_market_value_at(history, 20660), 10_000_000)

    def test_returns_none_when_day_not_in_history(self):
        history = {"it": [{"dt": 20660, "mv": 10_000_000}]}
        self.assertIsNone(_market_value_at(history, 20500))

    def test_returns_none_for_empty_history(self):
        self.assertIsNone(_market_value_at({"it": []}, 20660))


class BuildNewEntriesTests(unittest.TestCase):
    def _players_map(self):
        return {"p1": {"player_id": "p1", "position": "Sturm", "average_points": 120}}

    def test_builds_entry_with_premium_and_current_player_attrs(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        def fake_get_history(token, league_id, player_id, timeframe=365):
            return {"it": [{"dt": target_days, "mv": 10_000_000}]}

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=fake_get_history,
        )

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["player_id"], "p1")
        self.assertEqual(entry["position"], "Sturm")
        self.assertEqual(entry["average_points_then"], 120)
        self.assertEqual(entry["market_value_then"], 10_000_000)
        self.assertAlmostEqual(entry["premium_pct"], 0.1)
        self.assertEqual(entry["purchased_at"], "2026-07-01T10:00:00Z")
        self.assertEqual(entry["activity_id"], "act_2026-07-01T10:00:00Z")
        self.assertEqual(pointer, "2026-07-01T10:00:00Z")

    def test_skips_purchase_when_player_not_in_players_map(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", pi="unknown")]

        def fake_get_history(token, league_id, player_id, timeframe=365):
            raise AssertionError("sollte fuer unbekannten Spieler nicht aufgerufen werden")

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=fake_get_history,
        )

        self.assertEqual(entries, [])
        self.assertIsNone(pointer)

    def test_single_failing_history_call_does_not_abort_others(self):
        activities = [
            _trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1"),
            _trade_activity("2026-07-02T10:00:00Z", trp=12_000_000, pi="p1"),
        ]
        target_days = _days_since_epoch("2026-07-02T10:00:00Z")
        call_count = {"n": 0}

        def flaky_get_history(token, league_id, player_id, timeframe=365):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("API down")
            return {"it": [{"dt": target_days, "mv": 10_000_000}]}

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=flaky_get_history,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["purchased_at"], "2026-07-02T10:00:00Z")
        # Zeiger geht trotz des einen Fehlers bis zur letzten VERARBEITETEN
        # Aktivitaet weiter (kein endloses Retry auf einen dauerhaft
        # fehlenden Marktwert - siehe Global Constraints).
        self.assertEqual(pointer, "2026-07-02T10:00:00Z")

    def test_pointer_is_max_dt_not_last_iterated_for_descending_feed(self):
        # Regressionstest fuer den Quota-Bug: get_activities_feed()s Reihenfolge
        # ist UNBESTAETIGT (siehe Docstring dort) - koennte newest-first sein.
        # Aktivitaeten hier bewusst ABSTEIGEND sortiert (newest-first), die
        # letzte Schleifeniteration ist damit die AELTESTE Aktivitaet. Der
        # Zeiger muss trotzdem auf dem NEUESTEN dt landen (max ueber alle
        # verarbeiteten Aktivitaeten), sonst wuerde bei einem newest-first-Feed
        # der komplette Backlog bei jedem 2h-Lauf erneut verarbeitet.
        activities = [
            _trade_activity("2026-07-03T10:00:00Z", trp=13_000_000, pi="p1"),
            _trade_activity("2026-07-02T10:00:00Z", trp=12_000_000, pi="p1"),
            _trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1"),
        ]

        # get_history liefert fuer jede Aktivitaet einen passenden Marktwert
        # am jeweiligen Kauftag, damit alle drei Aktivitaeten als "verarbeitet"
        # zaehlen (kein History-Fehlschlag, der den Test verfaelschen wuerde).
        def fake_get_history(token, league_id, player_id, timeframe=365):
            return {
                "it": [
                    {"dt": _days_since_epoch(a["dt"]), "mv": 10_000_000}
                    for a in activities
                ]
            }

        entries, pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            get_history=fake_get_history,
        )

        self.assertEqual(len(entries), 3)
        self.assertEqual(pointer, "2026-07-03T10:00:00Z")

    def test_no_new_activities_returns_empty_and_none_pointer(self):
        entries, pointer = build_new_entries(
            "tok", "l1", [], since_dt="2026-07-01T00:00:00Z", players_map=self._players_map(),
            get_history=lambda *a, **k: {"it": []},
        )
        self.assertEqual(entries, [])
        self.assertIsNone(pointer)


class UpdateAndLoadTests(unittest.TestCase):
    @patch("src.bid_premium.firestore_db")
    def test_writes_new_entries_and_advances_pointer_when_found(self, mock_fs):
        from src.bid_premium import update_and_load
        mock_fs.get_bid_premium_pointer.return_value = None
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_1", "player_id": "p1", "purchased_at": "2026-07-01T10:00:00Z"}
        ]
        activities = [_trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")
        client = MagicMock()

        result = update_and_load(
            client=client, token="tok", league_id="l1", activities=activities,
            players_map={"p1": {"player_id": "p1", "position": "Sturm", "average_points": 100}},
            get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        mock_fs.upsert_bid_premium_entries.assert_called_once()
        mock_fs.upsert_bid_premium_pointer.assert_called_once_with(client, "2026-07-01T10:00:00Z")
        # activity_id (nur Firestore-Schreib-Doc-Id) wird vor der Rueckgabe
        # entfernt - kein Frontend-Verbraucher braucht ihn (siehe Finding 4).
        self.assertEqual(result, [{"player_id": "p1", "purchased_at": "2026-07-01T10:00:00Z"}])

    @patch("src.bid_premium.firestore_db")
    def test_no_new_purchases_skips_writes_but_still_returns_history(self, mock_fs):
        from src.bid_premium import update_and_load
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_old", "purchased_at": "2026-06-01T00:00:00Z"}
        ]

        result = update_and_load(
            client=MagicMock(), token="tok", league_id="l1", activities=[],
            players_map={}, get_history=lambda *a, **k: {"it": []},
        )

        mock_fs.upsert_bid_premium_entries.assert_not_called()
        mock_fs.upsert_bid_premium_pointer.assert_not_called()
        self.assertEqual(result, [{"purchased_at": "2026-06-01T00:00:00Z"}])

    def test_none_client_is_noop_and_returns_empty(self):
        from src.bid_premium import update_and_load
        result = update_and_load(
            client=None, token="tok", league_id="l1", activities=[{"anything": True}],
            players_map={},
        )
        self.assertEqual(result, [])

    @patch("src.bid_premium.firestore_db")
    def test_history_is_capped_sorted_descending_and_activity_id_stripped(self, mock_fs):
        from src.bid_premium import MAX_HISTORY_ENTRIES_IN_SNAPSHOT, update_and_load
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        # Absichtlich mehr als das Cap UND in aufsteigender Reihenfolge
        # gemockt, um sowohl Deckelung als auch Sortierung zu pruefen.
        unsorted_oversized_history = [
            {"activity_id": f"act_{i}", "player_id": "p1", "purchased_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z"}
            for i in range(MAX_HISTORY_ENTRIES_IN_SNAPSHOT + 50)
        ]
        newest_entry = {"activity_id": "act_newest", "player_id": "p1", "purchased_at": "2099-01-01T00:00:00Z"}
        mock_fs.get_bid_premium_history.return_value = unsorted_oversized_history + [newest_entry]

        result = update_and_load(
            client=MagicMock(), token="tok", league_id="l1", activities=[],
            players_map={}, get_history=lambda *a, **k: {"it": []},
        )

        self.assertEqual(len(result), MAX_HISTORY_ENTRIES_IN_SNAPSHOT)
        self.assertEqual(result[0]["purchased_at"], "2099-01-01T00:00:00Z")
        purchased_ats = [e["purchased_at"] for e in result]
        self.assertEqual(purchased_ats, sorted(purchased_ats, reverse=True))
        self.assertTrue(all("activity_id" not in e for e in result))


if __name__ == "__main__":
    unittest.main()
