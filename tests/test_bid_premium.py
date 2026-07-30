import unittest
from unittest.mock import MagicMock, patch

from src.bid_premium import (
    _compute_premium,
    _days_since_epoch,
    _filter_new_system_purchases,
    _is_system_purchase,
    _market_value_at,
    build_new_entries,
    detect_unsold_listings,
    update_and_load,
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

    def test_marks_entry_as_bought_by_self_when_buyer_matches_own_name(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", byr="Ich", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        entries, _pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            own_name="Ich", get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        self.assertTrue(entries[0]["bought_by_self"])

    def test_marks_entry_as_not_bought_by_self_when_buyer_differs(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", byr="Rivale", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        entries, _pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            own_name="Ich", get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        self.assertFalse(entries[0]["bought_by_self"])

    def test_bought_by_self_is_false_when_own_name_not_provided(self):
        activities = [_trade_activity("2026-07-01T10:00:00Z", byr="Rivale", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")

        entries, _pointer = build_new_entries(
            "tok", "l1", activities, since_dt=None, players_map=self._players_map(),
            own_name=None, get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        self.assertFalse(entries[0]["bought_by_self"])


class UpdateAndLoadTests(unittest.TestCase):
    @patch("src.bid_premium.firestore_db")
    def test_writes_new_entries_and_advances_pointer_when_found(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = None
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_1", "player_id": "p1", "position": "Sturm", "purchased_at": "2026-07-01T10:00:00Z"}
        ]
        mock_fs.get_bid_premium_last_seen_listing_ids.return_value = []
        mock_fs.get_unsold_log.return_value = []
        activities = [_trade_activity("2026-07-01T10:00:00Z", trp=11_000_000, pi="p1")]
        target_days = _days_since_epoch("2026-07-01T10:00:00Z")
        client = MagicMock()

        history, outcome_counts = update_and_load(
            client=client, token="tok", league_id="l1", activities=activities,
            players_map={"p1": {"player_id": "p1", "position": "Sturm", "average_points": 100}},
            market_listings=[], own_name="Ich", detected_at="2026-07-01",
            get_history=lambda *a, **k: {"it": [{"dt": target_days, "mv": 10_000_000}]},
        )

        mock_fs.upsert_bid_premium_entries.assert_called_once()
        mock_fs.upsert_bid_premium_pointer.assert_called_once_with(client, "2026-07-01T10:00:00Z")
        # activity_id (nur Firestore-Schreib-Doc-Id) wird vor der Rueckgabe
        # entfernt - unveraendertes Verhalten, siehe update_and_load()-Docstring.
        self.assertEqual(history, [{"player_id": "p1", "position": "Sturm", "purchased_at": "2026-07-01T10:00:00Z"}])
        self.assertEqual(outcome_counts, {"Sturm": {"rival_purchases": 1, "self_purchases": 0, "unsold": 0}})

    @patch("src.bid_premium.firestore_db")
    def test_no_new_purchases_skips_writes_but_still_returns_history(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_old", "position": "Sturm", "purchased_at": "2026-06-01T00:00:00Z"}
        ]
        mock_fs.get_bid_premium_last_seen_listing_ids.return_value = []
        mock_fs.get_unsold_log.return_value = []

        history, _outcome_counts = update_and_load(
            client=MagicMock(), token="tok", league_id="l1", activities=[],
            players_map={}, market_listings=[], own_name=None, detected_at="2026-07-05",
            get_history=lambda *a, **k: {"it": []},
        )

        mock_fs.upsert_bid_premium_entries.assert_not_called()
        mock_fs.upsert_bid_premium_pointer.assert_not_called()
        # activity_id (nur Firestore-Schreib-Doc-Id) wird vor der Rueckgabe
        # entfernt - unveraendertes Verhalten, siehe update_and_load()-Docstring.
        self.assertEqual(history, [{"position": "Sturm", "purchased_at": "2026-06-01T00:00:00Z"}])

    def test_none_client_is_noop_and_returns_empty(self):
        history, outcome_counts = update_and_load(
            client=None, token="tok", league_id="l1", activities=[{"anything": True}],
            players_map={}, market_listings=[], own_name=None, detected_at="2026-07-05",
        )
        self.assertEqual(history, [])
        self.assertEqual(outcome_counts, {})

    @patch("src.bid_premium.firestore_db")
    def test_unsold_detection_writes_entry_and_shows_up_in_outcome_counts(self, mock_fs):
        mock_fs.get_bid_premium_pointer.return_value = "2026-07-05T00:00:00Z"
        mock_fs.get_bid_premium_history.return_value = []
        mock_fs.get_bid_premium_last_seen_listing_ids.return_value = ["p1"]
        mock_fs.get_unsold_log.return_value = [{"player_id": "p1", "position": "Sturm", "detected_at": "2026-07-06"}]
        client = MagicMock()

        _history, outcome_counts = update_and_load(
            client=client, token="tok", league_id="l1", activities=[],
            players_map={"p1": {"player_id": "p1", "position": "Sturm", "market_value": 1, "average_points": 1}},
            market_listings=[], own_name=None, detected_at="2026-07-06",
            get_history=lambda *a, **k: {"it": []},
        )

        mock_fs.upsert_unsold_log_entries.assert_called_once()
        mock_fs.upsert_bid_premium_last_seen_listing_ids.assert_called_once_with(client, [])
        self.assertEqual(outcome_counts, {"Sturm": {"rival_purchases": 0, "self_purchases": 0, "unsold": 1}})


class DetectUnsoldListingsTests(unittest.TestCase):
    def _players_map(self):
        return {"p1": {"player_id": "p1", "position": "Sturm", "market_value": 5_000_000, "average_points": 90}}

    def test_disappeared_id_without_matching_trade_is_unsold(self):
        entries, current_ids = detect_unsold_listings(
            market_listings=[],  # p1 ist jetzt NICHT mehr gelistet
            activities=[],  # kein Trade fuer p1
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["player_id"], "p1")
        self.assertEqual(entries[0]["position"], "Sturm")
        self.assertEqual(entries[0]["market_value_then"], 5_000_000)
        self.assertEqual(entries[0]["detected_at"], "2026-07-30")
        self.assertEqual(current_ids, [])

    def test_disappeared_id_with_matching_system_purchase_is_not_unsold(self):
        activities = [_trade_activity("2026-07-29T10:00:00Z", pi="p1")]
        entries, _current_ids = detect_unsold_listings(
            market_listings=[],
            activities=activities,
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])

    def test_disappeared_id_with_matching_manager_to_manager_trade_is_not_unsold(self):
        # Verkauft an einen Mitspieler (slr vorhanden) ist kein Systemkauf,
        # zaehlt fuer detect_unsold_listings() trotzdem als "erklaertes
        # Verschwinden" - der Spieler war ja jemandes Wunschkader-Ziel und
        # wurde regulaer weitergehandelt, kein Hinweis auf einen zu niedrigen
        # Gebotsvorschlag.
        activities = [_trade_activity("2026-07-29T10:00:00Z", pi="p1", slr="Rivale")]
        entries, _current_ids = detect_unsold_listings(
            market_listings=[],
            activities=activities,
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])

    def test_still_listed_id_is_not_unsold_and_stays_in_current_ids(self):
        entries, current_ids = detect_unsold_listings(
            market_listings=[{"player_id": "p1", "is_system_offer": True}],
            activities=[],
            last_seen_ids=["p1"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])
        self.assertEqual(current_ids, ["p1"])

    def test_newly_listed_id_not_in_last_seen_is_added_to_current_ids(self):
        _entries, current_ids = detect_unsold_listings(
            market_listings=[{"player_id": "p_new", "is_system_offer": True}],
            activities=[],
            last_seen_ids=[],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(current_ids, ["p_new"])

    def test_non_system_listing_is_ignored_for_current_ids(self):
        _entries, current_ids = detect_unsold_listings(
            market_listings=[{"player_id": "p1", "is_system_offer": False}],
            activities=[],
            last_seen_ids=[],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(current_ids, [])

    def test_disappeared_id_unknown_in_players_map_is_skipped_not_crashed(self):
        entries, current_ids = detect_unsold_listings(
            market_listings=[],
            activities=[],
            last_seen_ids=["p_unknown"],
            players_map=self._players_map(),
            detected_at="2026-07-30",
        )
        self.assertEqual(entries, [])
        self.assertEqual(current_ids, [])


if __name__ == "__main__":
    unittest.main()
