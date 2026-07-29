import datetime
import os
import unittest
from unittest.mock import MagicMock, patch

from src import firestore_db
from src.dashboard_export import (
    _build_alle_spieler,
    _build_budget_plan,
    _build_eigenes_team,
    _build_players_map,
    _build_spekulation,
    _build_transfermarkt,
    _build_transfermarkt_listings,
    _build_wunschkader,
    _estimate_price,
    _finalize_firestore_write,
    _load_wunschkader,
    _resolve_heavy_data,
    _resolve_is_light,
    export,
)


class BuildAlleSpielerTests(unittest.TestCase):
    def test_marks_own_squad_players(self):
        players = [{"player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
                    "team_name": "Bremen", "market_value": 10_000_000,
                    "points_avg": 150, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={}, own_squad_names={"Krauß"}, calibration=None)

        self.assertEqual(rows[0]["owner"], "Eigener Kader")
        self.assertIsNone(rows[0]["status_label"])

    def test_marks_other_manager_ownership(self):
        players = [{"player_id": "p2", "name": "Zentner", "position": "Torwart",
                    "team_name": "Mainz", "market_value": 9_000_000,
                    "points_avg": 100, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={"p2": "Fleischmanns"}, own_squad_names=set(), calibration=None)

        self.assertEqual(rows[0]["owner"], "Fleischmanns")

    def test_marks_free_agent(self):
        players = [{"player_id": "p3", "name": "Heuer Fernandes", "position": "Torwart",
                    "team_name": "Hamburg", "market_value": 11_000_000,
                    "points_avg": 90, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={}, own_squad_names=set(), calibration=None)

        self.assertEqual(rows[0]["owner"], "Frei")


class BuildSpekulationTests(unittest.TestCase):
    def test_passes_through_92d_high_low_for_detail_view(self):
        transfermarkt_rows = [{
            "name": "Woltemade", "position": "Sturm", "team_name": "Stuttgart",
            "is_system_offer": True, "price": 10_000_000, "ml_prediction": 200_000,
            "market_value_change_7d": 50_000, "average_points": 180,
            "market_value_low_92d": 8_500_000, "market_value_high_92d": 10_200_000,
        }]

        rows = _build_spekulation(transfermarkt_rows)

        self.assertEqual(rows[0]["market_value_low_92d"], 8_500_000)
        self.assertEqual(rows[0]["market_value_high_92d"], 10_200_000)

    def test_passes_through_auction_expires_at(self):
        transfermarkt_rows = [{
            "name": "Woltemade", "position": "Sturm", "team_name": "Stuttgart",
            "is_system_offer": True, "price": 10_000_000, "ml_prediction": 200_000,
            "market_value_change_7d": 50_000, "average_points": 180,
            "auction_expires_at": "2026-07-29T12:00:00Z",
        }]

        rows = _build_spekulation(transfermarkt_rows)

        self.assertEqual(rows[0]["auction_expires_at"], "2026-07-29T12:00:00Z")


class BuildTransfermarktTests(unittest.TestCase):
    def test_passes_through_auction_expires_at(self):
        listing = {
            "player_id": "p1", "name": "Woltemade", "position": "Sturm",
            "team_name": "Stuttgart", "status_label": None, "starting_rank": 1,
            "market_value": 10_000_000, "market_value_change_7d": 50_000,
            "market_value_low_92d": 8_500_000, "market_value_high_92d": 10_200_000,
            "average_points": 180, "total_points": 360,
            "is_system_offer": True, "listed_at": "2026-07-27T10:00:00Z",
            "expires_at": "2026-07-29T12:00:00Z", "expiry_is_estimate": False,
            "price": 10_000_000, "price_delta_pct": 0.0, "offering_username": None,
            "pending_offers_count": 0, "leading_bid_username": None, "leading_bid_price": None,
            "is_own_leading_bid": False,
        }
        now = datetime.datetime(2026, 7, 28, tzinfo=datetime.timezone.utc)

        rows = _build_transfermarkt([listing], calibration=None, predictions=None, own_available_budget=None, now=now)

        self.assertEqual(rows[0]["auction_expires_at"], "2026-07-29T12:00:00Z")


class BuildTransfermarktListingsTests(unittest.TestCase):
    def test_extracts_only_raw_listing_fields(self):
        listing = {
            "player_id": "p1", "price": 5_000_000, "price_delta_pct": 2.5,
            "offering_username": None, "is_system_offer": 1, "pending_offers_count": 0,
            "leading_bid_username": None, "leading_bid_price": None, "is_own_leading_bid": 0,
            "listed_at": "2026-07-27T10:00:00Z", "expires_at": "2026-07-29T20:00:00Z",
            "expiry_is_estimate": 0,
        }

        result = _build_transfermarkt_listings([listing])

        self.assertEqual(result[0]["player_id"], "p1")
        self.assertEqual(result[0]["price"], 5_000_000)
        self.assertIs(result[0]["is_system_offer"], True)
        self.assertNotIn("auction_status", result[0])
        self.assertNotIn("affordable", result[0])
        self.assertNotIn("signal", result[0])


class EstimatePriceTests(unittest.TestCase):
    def test_flat_ten_percent_markup(self):
        self.assertEqual(_estimate_price(10_000_000), 11_000_000)

    def test_returns_none_without_market_value(self):
        self.assertIsNone(_estimate_price(None))

    def test_returns_none_for_zero_market_value(self):
        self.assertIsNone(_estimate_price(0))


class BuildBudgetPlanTests(unittest.TestCase):
    def test_pool_has_no_login_bonus(self):
        wunschkader = {"sell_list": []}

        result = _build_budget_plan(wunschkader, wunschkader_rows=[], own_squad=[], own_budget_exact=1_000_000)

        self.assertEqual(result["pool"], 1_000_000)
        self.assertNotIn("login_bonus_projection", result)
        self.assertNotIn("season_start", result)

    def test_committed_excludes_bank_backup_and_own_targets(self):
        wunschkader = {"sell_list": []}
        wunschkader_rows = [
            {"planned_price": 5_000_000, "role": "Starter", "is_own": False},
            {"planned_price": 3_000_000, "role": "Bank/Backup-Option", "is_own": False},
            {"planned_price": 9_000_000, "role": "Starter", "is_own": True},
        ]

        result = _build_budget_plan(wunschkader, wunschkader_rows, own_squad=[], own_budget_exact=0)

        self.assertEqual(result["committed"], 5_000_000)


class LoadWunschkaderTests(unittest.TestCase):
    def test_returns_none_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(_load_wunschkader())

    @patch("src.dashboard_export.firestore_db.get_wunschkader")
    @patch("src.dashboard_export.firestore_db.connect")
    def test_returns_data_from_firestore_when_enabled(self, mock_connect, mock_get):
        mock_get.return_value = {"targets": [{"name": "Krauß"}], "formation": "3-4-3"}
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_wunschkader()
        self.assertEqual(result["formation"], "3-4-3")

    @patch("src.dashboard_export.firestore_db.get_wunschkader")
    @patch("src.dashboard_export.firestore_db.connect")
    def test_propagates_exception_instead_of_swallowing(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            with self.assertRaises(RuntimeError):
                _load_wunschkader()


class FinalizeFirestoreWriteTests(unittest.TestCase):
    @patch("src.dashboard_export.firestore_db.upsert_dashboard_snapshot")
    @patch("src.dashboard_export.firestore_db.connect")
    def test_raises_when_own_write_fails(self, mock_connect, mock_upsert):
        mock_upsert.side_effect = RuntimeError("quota exceeded")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            with self.assertRaises(firestore_db.FirestoreWriteError):
                _finalize_firestore_write({"fetched_at": "2026-07-29"})

    @patch("src.dashboard_export.firestore_db.upsert_dashboard_snapshot")
    @patch("src.dashboard_export.firestore_db.connect")
    def test_no_raise_when_everything_succeeds(self, mock_connect, mock_upsert):
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            _finalize_firestore_write({"fetched_at": "2026-07-29"})

    def test_no_raise_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            _finalize_firestore_write({"fetched_at": "2026-07-29"})


class BuildWunschkaderTests(unittest.TestCase):
    def test_includes_team_name_from_all_players(self):
        all_players = [{"player_id": "p1", "name": "Katic", "team_name": "Schalke",
                        "market_value": 5_000_000, "points_avg": 80, "starting_rank": 1, "status_code": 0}]
        wunschkader = {"targets": [{"name": "Katic", "position": "Abwehr", "role": "Starter"}]}

        rows = _build_wunschkader(wunschkader, all_players, owned_by={}, own_squad_names={"Katic"},
                                   market_by_name={}, calibration=None, predictions=None)

        self.assertEqual(rows[0]["team_name"], "Schalke")

    def test_team_name_is_none_when_player_not_found(self):
        wunschkader = {"targets": [{"name": "Unbekannt", "position": "Sturm", "role": "Starter"}]}

        rows = _build_wunschkader(wunschkader, all_players=[], owned_by={}, own_squad_names=set(),
                                   market_by_name={}, calibration=None, predictions=None)

        self.assertIsNone(rows[0]["team_name"])


class ResolveIsLightTests(unittest.TestCase):
    def test_light_mode_with_cache_is_light(self):
        self.assertTrue(_resolve_is_light("light", {"alle_spieler": []}))

    def test_light_mode_without_cache_falls_back_to_heavy(self):
        self.assertFalse(_resolve_is_light("light", None))

    def test_absent_mode_is_always_heavy_even_with_stray_cache(self):
        self.assertFalse(_resolve_is_light(None, {"alle_spieler": []}))

    def test_absent_mode_without_cache_is_heavy(self):
        self.assertFalse(_resolve_is_light(None, None))


class ResolveHeavyDataTests(unittest.TestCase):
    @patch("src.dashboard_export.player_valuation.resolve_ownership")
    @patch("src.dashboard_export.player_valuation.load_calibration")
    @patch("src.dashboard_export.market_predictor.predict_market_value_changes")
    @patch("src.dashboard_export.player_valuation.fetch_all_players")
    def test_heavy_mode_calls_all_expensive_functions(
        self, mock_fetch_all, mock_predict, mock_calibration, mock_resolve_ownership
    ):
        mock_fetch_all.return_value = [{"player_id": "p1", "starting_rank": 1}]
        mock_predict.return_value = {"metrics": {"accuracy_trend": [1, 2]}, "predictions": {"p1": 50000}}
        mock_calibration.return_value = {"Sturm": 1.0}
        mock_resolve_ownership.return_value = {"p1": "Rivale"}

        result = _resolve_heavy_data(
            is_light=False, cached_snapshot=None, token="tok", league_id="l1",
            competition_id="c1", ranking_rows=[], own_name="Ich",
        )

        mock_fetch_all.assert_called_once_with("tok", "c1")
        mock_predict.assert_called_once()
        mock_resolve_ownership.assert_called_once()
        self.assertEqual(result["starting_rank_by_player_id"], {"p1": 1})
        self.assertEqual(result["ml_metrics"]["accuracy_trend"], [1, 2])
        self.assertEqual(result["owned_by"], {"p1": "Rivale"})

    @patch("src.dashboard_export.player_valuation.resolve_ownership")
    @patch("src.dashboard_export.player_valuation.load_calibration")
    @patch("src.dashboard_export.market_predictor.predict_market_value_changes")
    @patch("src.dashboard_export.player_valuation.fetch_all_players")
    def test_light_mode_skips_all_expensive_functions(
        self, mock_fetch_all, mock_predict, mock_calibration, mock_resolve_ownership
    ):
        cached_snapshot = {
            "alle_spieler": [{"player_id": "p1", "starting_rank": 2, "ml_prediction": 12345}],
            "calibration": {"Sturm": 0.9},
            "ml_metrics": {"accuracy_trend": [3]},
            "ml_accuracy_trend": [3],
        }

        result = _resolve_heavy_data(
            is_light=True, cached_snapshot=cached_snapshot, token="tok", league_id="l1",
            competition_id="c1", ranking_rows=[], own_name="Ich",
        )

        mock_fetch_all.assert_not_called()
        mock_predict.assert_not_called()
        mock_resolve_ownership.assert_not_called()
        self.assertIsNone(result["all_players"])
        self.assertEqual(result["starting_rank_by_player_id"], {"p1": 2})
        self.assertEqual(result["predictions"]["predictions"]["p1"], 12345)
        self.assertEqual(result["calibration"], {"Sturm": 0.9})
        self.assertEqual(result["owned_by"], {})

    def test_light_mode_ml_prediction_flows_into_player_row(self):
        cached_snapshot = {
            "alle_spieler": [{"player_id": "p1", "starting_rank": 1, "ml_prediction": 77777}],
            "calibration": None, "ml_metrics": None, "ml_accuracy_trend": None,
        }
        heavy = _resolve_heavy_data(True, cached_snapshot, "tok", "l1", "c1", [], None)

        own_squad = [{
            "player_id": "p1", "name": "Foo", "position": "Sturm", "team_name": "Bremen",
            "status_label": None, "starting_rank": 1, "market_value": 1_000_000,
            "market_value_change_7d": None, "market_value_low_92d": None,
            "market_value_high_92d": None, "average_points": 100, "total_points": 500,
        }]
        rows = _build_eigenes_team(own_squad, heavy["calibration"], heavy["predictions"])

        self.assertEqual(rows[0]["ml_prediction"], 77777)


FRESH_LISTING_ROW = {
    "player_id": "p_new", "name": "Hajdari", "position": "Abwehr", "team_name": "Freiburg",
    "status_label": None, "starting_rank": 1,
    "market_value": 14_000_000, "market_value_change_7d": None, "market_value_low_92d": None,
    "market_value_high_92d": None, "average_points": 90, "total_points": 300,
    "price": 14_000_000, "price_delta_pct": 0.0,
    "offering_username": None, "is_system_offer": 1, "pending_offers_count": 0,
    "leading_bid_username": None, "leading_bid_price": None, "is_own_leading_bid": 0,
    "listed_at": "2026-07-29T13:28:37Z", "expires_at": "2026-07-30T13:28:37Z",
    "expiry_is_estimate": 0,
}


class ExportLightModeTests(unittest.TestCase):
    """export() im Light-Modus (DASHBOARD_MODE=light, dashboard.yml, alle
    2h) muss Transfermarkt/Spekulation aus den FRISCH gefetchten
    market_listings neu bauen, nicht aus dem letzten Firestore-Snapshot
    uebernehmen - fetcher.run() holt /market bei JEDEM Lauf frisch (kein
    teurer API-Call, kein Grund fuer eine Light-Modus-Ausnahme hier), anders
    als all_players/predictions/owned_by, die echte teure Calls brauchen und
    deshalb im Light-Modus zurecht gecacht bleiben. Bug gefunden 2026-07-29:
    ein frisch gelisteter Spieler (Hajdari) blieb bis zu 24h unsichtbar, weil
    export() im Light-Modus transfermarkt/spekulation komplett aus dem
    Snapshot uebernahm statt _build_transfermarkt/_build_spekulation mit den
    frischen market_listings aufzurufen."""

    def _run_export_in_light_mode(self, cached_snapshot, fresh_market_listings):
        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "DASHBOARD_MODE": "light", "FIRESTORE_ENABLED": "1"},
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-29"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], fresh_market_listings, [], [])
        ), patch("src.dashboard_export.firestore_db.connect", return_value=MagicMock()), patch(
            "src.dashboard_export.firestore_db.get_dashboard_snapshot", return_value=cached_snapshot
        ), patch("src.dashboard_export.firestore_db.upsert_dashboard_snapshot"), patch(
            "src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value=[]):
            return export()

    def test_light_mode_rebuilds_transfermarkt_from_fresh_market_listings(self):
        cached_snapshot = {
            "alle_spieler": [], "calibration": None, "ml_metrics": None, "ml_accuracy_trend": None,
            "transfermarkt": [{"name": "StaleOnly", "player_id": "p_stale"}],
            "spekulation": [{"name": "StaleSpekulation"}],
            "wunschkader": [],
        }

        data = self._run_export_in_light_mode(cached_snapshot, [FRESH_LISTING_ROW])

        names = [r["name"] for r in data["transfermarkt"]]
        self.assertIn("Hajdari", names)
        self.assertNotIn("StaleOnly", names)


class BuildPlayersMapTests(unittest.TestCase):
    def _all_players_row(self, **overrides):
        row = {
            "player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
            "team_id": "t1", "team_name": "Bremen", "market_value": 10_000_000,
            "average_points": 120, "starting_rank": 1, "status_code": 0,
        }
        row.update(overrides)
        return row

    def _light_row(self, **overrides):
        row = {
            "player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
            "team_name": "Bremen", "status_code": 0, "starting_rank": 1,
            "market_value": 10_500_000, "average_points": 122, "total_points": 488,
            "market_value_change_7d": 50_000, "market_value_low_92d": 9_800_000,
            "market_value_high_92d": 10_600_000, "market_value_in_drop_phase": False,
        }
        row.update(overrides)
        return row

    def test_heavy_mode_builds_from_all_players_without_team_id(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[], market_listings=[],
            predictions=None, previous_players=None, is_light=False,
        )
        self.assertNotIn("team_id", result["p1"])
        self.assertEqual(result["p1"]["market_value"], 10_000_000)

    def test_heavy_mode_history_fields_absent_when_not_in_light_path(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[], market_listings=[],
            predictions=None, previous_players=None, is_light=False,
        )
        self.assertNotIn("market_value_change_7d", result["p1"])

    def test_heavy_mode_overlays_own_squad_history_fields(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[self._light_row()],
            market_listings=[], predictions=None, previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["market_value_change_7d"], 50_000)
        self.assertEqual(result["p1"]["market_value"], 10_500_000)

    def test_market_listings_overlay_same_as_own_squad(self):
        result = _build_players_map(
            all_players=[self._all_players_row()], own_squad=[],
            market_listings=[self._light_row(player_id="p1")],
            predictions=None, previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["market_value_change_7d"], 50_000)

    def test_ml_prediction_set_only_for_predicted_ids(self):
        result = _build_players_map(
            all_players=[self._all_players_row(player_id="p1"), self._all_players_row(player_id="p2", name="Foo")],
            own_squad=[], market_listings=[],
            predictions={"predictions": {"p1": 45_000}}, previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["ml_prediction"], 45_000)
        self.assertNotIn("ml_prediction", result["p2"])

    def test_light_mode_untouched_players_carried_forward_unchanged(self):
        previous = {"p9": {"player_id": "p9", "name": "Unberuehrt", "market_value": 1_000_000}}
        result = _build_players_map(
            all_players=None, own_squad=[], market_listings=[],
            predictions=None, previous_players=previous, is_light=True,
        )
        self.assertEqual(result["p9"], previous["p9"])

    def test_light_mode_touched_player_gets_fresh_values_not_stale(self):
        previous = {"p1": {"player_id": "p1", "name": "Krauß", "market_value": 9_000_000,
                            "market_value_change_7d": -100_000}}
        result = _build_players_map(
            all_players=None, own_squad=[self._light_row(market_value_change_7d=50_000)],
            market_listings=[], predictions=None, previous_players=previous, is_light=True,
        )
        self.assertEqual(result["p1"]["market_value_change_7d"], 50_000)
        self.assertEqual(result["p1"]["market_value"], 10_500_000)

    def test_light_mode_preserves_ml_prediction_when_predictions_is_none(self):
        previous = {"p1": {"player_id": "p1", "name": "Krauß", "ml_prediction": 12_345}}
        result = _build_players_map(
            all_players=None, own_squad=[], market_listings=[],
            predictions=None, previous_players=previous, is_light=True,
        )
        self.assertEqual(result["p1"]["ml_prediction"], 12_345)

    def test_light_mode_new_player_not_in_previous_snapshot_does_not_crash(self):
        result = _build_players_map(
            all_players=None, own_squad=[self._light_row(player_id="p_new")],
            market_listings=[], predictions=None, previous_players={}, is_light=True,
        )
        self.assertEqual(result["p_new"]["market_value"], 10_500_000)

    def test_light_mode_preserves_prior_history_field_when_source_is_none(self):
        """Verify that when a source row has an explicit None value for a history
        field, the prior value from base is NOT cleared/overwritten - the
        is not None guard in the overlay loop correctly skips writing None."""
        previous = {
            "p1": {
                "player_id": "p1", "name": "Krauß", "market_value": 9_000_000,
                "market_value_change_7d": 42_000,  # prior value
                "market_value_low_92d": 8_500_000,
            }
        }
        # Simulate a fresh SQLite row where market_value_change_7d happens to be None
        # (e.g. not fetched in this run), but other fields are fresh.
        result = _build_players_map(
            all_players=None,
            own_squad=[self._light_row(player_id="p1", market_value_change_7d=None)],
            market_listings=[],
            predictions=None,
            previous_players=previous,
            is_light=True,
        )
        # The prior value must survive; None in the source should NOT overwrite it
        self.assertEqual(result["p1"]["market_value_change_7d"], 42_000)
        # But other fields from the source row ARE fresh
        self.assertEqual(result["p1"]["market_value"], 10_500_000)
