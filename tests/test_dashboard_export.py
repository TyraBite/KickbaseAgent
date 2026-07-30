import os
import unittest
from unittest.mock import patch

from src import firestore_db
from src.dashboard_export import (
    _build_ligaanalyse,
    _build_players_map,
    _build_transfermarkt_listings,
    _build_wunschkader_targets,
    _finalize_firestore_write,
    _load_wunschkader,
    _resolve_heavy_data,
    _resolve_is_light,
    export,
)


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


class BuildWunschkaderTargetsTests(unittest.TestCase):
    def test_passes_through_player_id_and_overlay_fields(self):
        wunschkader = {"targets": [{"player_id": "p1", "role": "Starter", "note": "geprüft"}]}
        players_map = {"p1": {"player_id": "p1", "name": "Krauß"}}

        rows = _build_wunschkader_targets(wunschkader, players_map)

        self.assertEqual(rows[0], {"player_id": "p1", "role": "Starter", "note": "geprüft"})

    def test_keeps_target_even_when_player_id_unknown(self):
        wunschkader = {"targets": [{"player_id": "p_missing", "role": "Starter", "note": None}]}

        rows = _build_wunschkader_targets(wunschkader, players_map={})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_id"], "p_missing")

    def test_empty_targets_returns_empty_list(self):
        self.assertEqual(_build_wunschkader_targets({"targets": []}, players_map={}), [])


class ResolveIsLightTests(unittest.TestCase):
    def test_light_mode_with_cache_is_light(self):
        self.assertTrue(_resolve_is_light("light", {"players": {}}))

    def test_light_mode_without_cache_falls_back_to_heavy(self):
        self.assertFalse(_resolve_is_light("light", None))

    def test_light_mode_with_old_shape_snapshot_falls_back_to_heavy(self):
        old_shape_snapshot = {"alle_spieler": []}  # kein "players"-Key
        self.assertFalse(_resolve_is_light("light", old_shape_snapshot))

    def test_absent_mode_is_always_heavy_even_with_stray_cache(self):
        self.assertFalse(_resolve_is_light(None, {"players": {}}))

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
            "players": {"p1": {"player_id": "p1"}},
            "calibration": {"Sturm": 0.9},
            "ml_metrics": {"accuracy_trend": [3]},
            "ml_accuracy_trend": [3],
            "owned_by": {"p2": "Rivale"},
        }

        result = _resolve_heavy_data(
            is_light=True, cached_snapshot=cached_snapshot, token="tok", league_id="l1",
            competition_id="c1", ranking_rows=[], own_name="Ich",
        )

        mock_fetch_all.assert_not_called()
        mock_predict.assert_not_called()
        mock_resolve_ownership.assert_not_called()
        self.assertIsNone(result["all_players"])
        self.assertIsNone(result["predictions"])
        self.assertEqual(result["calibration"], {"Sturm": 0.9})
        self.assertEqual(result["owned_by"], {"p2": "Rivale"})
        self.assertNotIn("starting_rank_by_player_id", result)


FRESH_MARKET_LISTING = {
    "player_id": "p_new", "name": "Hajdari", "position": "Abwehr", "team_name": "Freiburg",
    "status_code": 0, "starting_rank": 1,
    "market_value": 14_000_000, "market_value_change_7d": None, "market_value_low_92d": None,
    "market_value_high_92d": None, "market_value_in_drop_phase": None,
    "average_points": 90, "total_points": 300,
    "price": 14_000_000, "price_delta_pct": 0.0,
    "offering_username": None, "is_system_offer": 1, "pending_offers_count": 0,
    "leading_bid_username": None, "leading_bid_price": None, "is_own_leading_bid": 0,
    "listed_at": "2026-07-29T13:28:37Z", "expires_at": "2026-07-30T13:28:37Z",
    "expiry_is_estimate": 0,
}


class ExportLightModeFreshnessTests(unittest.TestCase):
    """export() im Light-Modus darf 'players'/'transfermarkt_listings' NIE aus
    dem gecachten Snapshot uebernehmen - beide werden in JEDEM Modus (Heavy
    UND Light) frisch aus own_squad/market_listings gebaut, siehe
    _build_players_map()/_build_transfermarkt_listings(). Ersetzt die im
    selben Dispatch geloeschte ExportLightModeTests (testete dieselbe
    Frische-Invariante gegen das alte transfermarkt/spekulation-Schema,
    urspruenglicher Bugfund: commit 1923c05 - ein frisch gelisteter Spieler
    blieb bis zu 24h unsichtbar). Das alte Bugbild ist im neuen Design
    strukturell unmoeglich (kein gecachter Array-Pfad mehr fuer diese
    Felder) - aber export() selbst braucht trotzdem MINDESTENS einen Test,
    der es end-to-end aufruft: sonst faellt es niemandem auf, wenn ein
    kuenftiger Edit fetcher.run()/_load_snapshot() versehentlich unter einen
    is_light-Zweig verschiebt oder einen cached_snapshot[...]-Read fuer
    transfermarkt_listings/players wieder einfuehrt."""

    def _run_export_in_light_mode(self, cached_snapshot, fresh_market_listings):
        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "DASHBOARD_MODE": "light", "FIRESTORE_ENABLED": "1"},
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-29"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], fresh_market_listings, [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.get_dashboard_snapshot", return_value=cached_snapshot
        ), patch("src.dashboard_export.firestore_db.upsert_dashboard_snapshot"), patch(
            "src.dashboard_export.get_activities_feed", return_value=[]
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}):
            return export()

    def _cached_snapshot_with_stale_player_only(self):
        return {
            "players": {
                "p_stale": {"player_id": "p_stale", "name": "StaleOnly", "market_value": 1_000_000, "starting_rank": 1},
            },
            "calibration": None, "ml_metrics": None, "ml_accuracy_trend": None, "owned_by": {},
        }

    def test_light_mode_serves_freshly_listed_player_absent_from_cache(self):
        cached_snapshot = self._cached_snapshot_with_stale_player_only()

        data = self._run_export_in_light_mode(cached_snapshot, [FRESH_MARKET_LISTING])

        listing_ids = [r["player_id"] for r in data["transfermarkt_listings"]]
        self.assertIn("p_new", listing_ids)
        self.assertIn("p_new", data["players"])
        self.assertEqual(data["players"]["p_new"]["market_value"], 14_000_000)

    def test_light_mode_leaves_untouched_cached_player_unchanged(self):
        cached_snapshot = self._cached_snapshot_with_stale_player_only()

        data = self._run_export_in_light_mode(cached_snapshot, [FRESH_MARKET_LISTING])

        self.assertEqual(data["players"]["p_stale"], cached_snapshot["players"]["p_stale"])


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


class BuildLigaanalyseTests(unittest.TestCase):
    def _players_map(self):
        return {
            "p1": {"player_id": "p1", "position": "Torwart", "starting_rank": 1},
            "p2": {"player_id": "p2", "position": "Abwehr", "starting_rank": 1},
            "p3": {"player_id": "p3", "position": "Abwehr", "starting_rank": 3},
            "p4": {"player_id": "p4", "position": "Mittelfeld", "starting_rank": 2},
        }

    def _ranking_row(self, user_id, name, lineup_ids, is_self=False):
        return {
            "user_id": user_id, "name": name, "season_points": 0, "matchday_points": 0,
            "team_value": 0, "season_placement": 1, "matchday_placement": 1,
            "current_lineup_player_ids": ",".join(lineup_ids),
            "recent_matchday_points": "",
        }

    def test_rival_full_coverage_at_position(self):
        # Rivale hat 1 Torwart in der Startelf, players_map zeigt ihn als
        # Stammspieler (starting_rank 1) -> Deckungsgrad 100% fuer Torwart.
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p1"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False, "estimated_budget": None, "available_budget": None, "trade_count": None}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p1", "mv": 10_000_000}], "nps": 1}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertEqual(result["position_need"]["Torwart"]["avg_coverage"], 1.0)
        self.assertEqual(result["position_need"]["Torwart"]["n_rivals"], 1)

    def test_rival_partial_coverage_at_position(self):
        # 2 Abwehrspieler in der Startelf (p2, p3), aber nur p2 ist
        # Stammspieler (starting_rank 1) -> Deckungsgrad 50%.
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p2", "p3"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False, "estimated_budget": None, "available_budget": None, "trade_count": None}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p2"}, {"pi": "p3"}], "nps": 2}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertEqual(result["position_need"]["Abwehr"]["avg_coverage"], 0.5)

    def test_coverage_is_capped_at_one(self):
        # 1 Stammspieler-Torwart im ganzen Kader, aber die Startelf enthaelt
        # ihn nur einmal -> Deckungsgrad darf trotz theoretisch "mehr
        # Stammspieler als Startelf-Plaetze" nicht ueber 1.0 gehen.
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p1"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False, "estimated_budget": None, "available_budget": None, "trade_count": None}]
        players_map = {**self._players_map(), "p1b": {"player_id": "p1b", "position": "Torwart", "starting_rank": 2}}

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p1"}, {"pi": "p1b"}], "nps": 2}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=players_map,
            )

        self.assertLessEqual(result["position_need"]["Torwart"]["avg_coverage"], 1.0)

    def test_own_row_excluded_from_position_need(self):
        # is_self=True -> zaehlt NICHT in position_need (nur "Gegner"
        # relevant fuer die Markt-Konkurrenz-Einschaetzung).
        ranking_rows = [self._ranking_row("u_self", "Ich", ["p1"])]
        budget_rows = [{"user_id": "u_self", "is_own_exact": True, "estimated_budget": None, "available_budget": None, "trade_count": None}]

        result = _build_ligaanalyse(
            "tok", "l1", ranking_rows, budget_rows, market_listings=[],
            own_squad=[{"player_id": "p1", "market_value": 1, "starting_rank": 1}],
            players_map=self._players_map(),
        )

        self.assertNotIn("Torwart", result["position_need"])

    def test_rival_with_zero_lineup_players_at_position_excluded_from_average(self):
        # Rivale hat gar keinen Spieler dieser Position in der Startelf -
        # darf den Durchschnitt nicht per Division-durch-Null verzerren.
        ranking_rows = [self._ranking_row("u1", "Rivale", [])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False, "estimated_budget": None, "available_budget": None, "trade_count": None}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [], "nps": 0}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertNotIn("Torwart", result["position_need"])

    def test_rows_key_preserves_existing_ligaanalyse_row_shape(self):
        ranking_rows = [self._ranking_row("u_self", "Ich", ["p1"])]
        budget_rows = [{"user_id": "u_self", "is_own_exact": True, "estimated_budget": 1, "available_budget": 1, "trade_count": 0}]

        result = _build_ligaanalyse(
            "tok", "l1", ranking_rows, budget_rows, market_listings=[],
            own_squad=[{"player_id": "p1", "market_value": 1, "starting_rank": 1}],
            players_map=self._players_map(),
        )

        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["name"], "Ich")
        self.assertTrue(result["rows"][0]["is_self"])

    def test_self_row_does_not_contribute_to_position_need(self):
        # Sowohl Ich (self) als auch ein Rivale stellen p1 (Torwart) in der
        # Startelf auf. n_rivals muss trotzdem 1 bleiben (nicht 2) - der
        # eigene Kader darf die Deckungsgrad-Aggregation nicht mitzaehlen.
        # Anders als test_own_row_excluded_from_position_need (dort bleibt
        # position_need bei nur einer self-Zeile ohnehin komplett leer,
        # unabhaengig davon ob der Selbst-Ausschluss korrekt greift) gibt es
        # hier einen echten Rivalen, der "Torwart" real in position_need
        # einbringt - ein Regressions-Bug (Self faelschlich mitgezaehlt)
        # wuerde hier n_rivals=2 statt 1 liefern und faellt damit auf.
        ranking_rows = [
            self._ranking_row("u_self", "Ich", ["p1"]),
            self._ranking_row("u1", "Rivale", ["p1"]),
        ]
        budget_rows = [
            {"user_id": "u_self", "is_own_exact": True, "estimated_budget": 1, "available_budget": 1, "trade_count": 0},
            {"user_id": "u1", "is_own_exact": False, "estimated_budget": None, "available_budget": None, "trade_count": None},
        ]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p1"}], "nps": 1}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[],
                own_squad=[{"player_id": "p1", "market_value": 1, "starting_rank": 1}],
                players_map=self._players_map(),
            )

        self.assertEqual(result["position_need"]["Torwart"]["n_rivals"], 1)
