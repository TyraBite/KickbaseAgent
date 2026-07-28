"""Tests fuer src/firestore_db.py: reine Row-Dict -> Firestore-Dokument-Formung,
gegen einen gemockten Firestore-Client (kein echter Netzwerkzugriff, siehe
Spec docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md,
Phase 1 Verifikationspunkt 3)."""

import unittest
from unittest.mock import MagicMock

from src import firestore_db


def _doc_ids(client):
    """Alle an client.collection(...).document(...) uebergebenen Doc-Ids, in
    Aufrufreihenfolge - da MagicMock().document(x) immer dasselbe Objekt
    zurueckgibt (unabhaengig von x), muss die Id ueber call_args_list
    ausgelesen werden, nicht ueber den Rueckgabewert."""
    return [c.args[0] for c in client.collection.return_value.document.call_args_list]


def _batch_set_payloads(batch):
    return [c.args[1] for c in batch.set.call_args_list]


class ReplaceOwnSquadTests(unittest.TestCase):
    def test_writes_one_batched_doc_per_player_with_composite_id(self):
        client = MagicMock()
        batch = client.batch.return_value
        players = [
            {"player_id": "p1", "name": "Foo", "market_value": 1000},
            {"player_id": "p2", "name": "Bar", "market_value": 2000},
        ]

        firestore_db.replace_own_squad(client, "2026-07-27", players)

        client.collection.assert_any_call("own_squad")
        self.assertEqual(_doc_ids(client), ["2026-07-27_p1", "2026-07-27_p2"])
        payloads = _batch_set_payloads(batch)
        self.assertEqual(payloads[0]["name"], "Foo")
        self.assertEqual(payloads[0]["fetched_at"], "2026-07-27")
        self.assertEqual(payloads[1]["market_value"], 2000)
        batch.commit.assert_called_once()

    def test_empty_players_writes_nothing(self):
        client = MagicMock()

        firestore_db.replace_own_squad(client, "2026-07-27", [])

        client.batch.assert_not_called()

    def test_splits_into_multiple_batches_over_500_ops(self):
        client = MagicMock()
        batch = client.batch.return_value
        players = [{"player_id": f"p{i}", "market_value": i} for i in range(501)]

        firestore_db.replace_own_squad(client, "2026-07-27", players)

        self.assertEqual(client.batch.call_count, 2)
        self.assertEqual(batch.commit.call_count, 2)
        self.assertEqual(batch.set.call_count, 501)


class ReplaceMarketListingsTests(unittest.TestCase):
    def test_writes_docs_keyed_by_fetched_at_and_player_id(self):
        client = MagicMock()
        batch = client.batch.return_value
        listings = [{"player_id": "p9", "price": 5000}]

        firestore_db.replace_market_listings(client, "2026-07-27", listings)

        client.collection.assert_any_call("market_listings")
        self.assertEqual(_doc_ids(client), ["2026-07-27_p9"])
        self.assertEqual(_batch_set_payloads(batch)[0]["price"], 5000)
        batch.commit.assert_called_once()


class ReplaceLeagueRankingTests(unittest.TestCase):
    def test_writes_docs_keyed_by_fetched_at_and_user_id(self):
        client = MagicMock()
        batch = client.batch.return_value
        rows = [{"user_id": "u1", "season_points": 42}]

        firestore_db.replace_league_ranking(client, "2026-07-27", rows)

        client.collection.assert_any_call("league_ranking")
        self.assertEqual(_doc_ids(client), ["2026-07-27_u1"])
        self.assertEqual(_batch_set_payloads(batch)[0]["season_points"], 42)
        batch.commit.assert_called_once()


class ReplaceManagerBudgetsTests(unittest.TestCase):
    def test_writes_docs_keyed_by_fetched_at_and_user_id(self):
        client = MagicMock()
        batch = client.batch.return_value
        rows = [{"user_id": "u2", "estimated_budget": 12.5}]

        firestore_db.replace_manager_budgets(client, "2026-07-27", rows)

        client.collection.assert_any_call("manager_budgets")
        self.assertEqual(_doc_ids(client), ["2026-07-27_u2"])
        self.assertEqual(_batch_set_payloads(batch)[0]["estimated_budget"], 12.5)
        batch.commit.assert_called_once()


class UpsertOwnBudgetTests(unittest.TestCase):
    def test_writes_single_doc_keyed_by_fetched_at(self):
        client = MagicMock()

        firestore_db.upsert_own_budget(client, "2026-07-27", "u1", 1234.5)

        client.collection.assert_any_call("own_budget_history")
        client.collection.return_value.document.assert_called_once_with("2026-07-27")
        doc_ref = client.collection.return_value.document.return_value
        doc_ref.set.assert_called_once_with(
            {"fetched_at": "2026-07-27", "user_id": "u1", "budget": 1234.5}
        )


class UpsertSeasonContextTests(unittest.TestCase):
    def test_writes_single_doc_keyed_by_fetched_at(self):
        client = MagicMock()
        context = {
            "season_name": "2026/2027",
            "current_matchday": 3,
            "next_deadline_at": "2026-07-28T18:30:00Z",
            "days_until_next_deadline": 1,
            "market_value_updated_at": "2026-07-27T22:00:00Z",
        }

        firestore_db.upsert_season_context(client, "2026-07-27", context)

        client.collection.assert_any_call("season_context")
        client.collection.return_value.document.assert_called_once_with("2026-07-27")
        doc_ref = client.collection.return_value.document.return_value
        written = doc_ref.set.call_args.args[0]
        self.assertEqual(written["fetched_at"], "2026-07-27")
        self.assertEqual(written["season_name"], "2026/2027")
        self.assertEqual(written["current_matchday"], 3)


class UpsertPredictionLogEntriesTests(unittest.TestCase):
    def test_writes_docs_keyed_by_date_and_player_id_and_model_type(self):
        client = MagicMock()
        batch = client.batch.return_value
        entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 15000},
            {"date": "2026-07-27", "player_id": "p2", "model_type": "HistGradientBoosting", "predicted_delta": -3000},
        ]

        firestore_db.upsert_prediction_log_entries(client, entries)

        client.collection.assert_any_call("ml_prediction_log")
        self.assertEqual(_doc_ids(client), ["2026-07-27_p1_RandomForest", "2026-07-27_p2_HistGradientBoosting"])
        payloads = _batch_set_payloads(batch)
        self.assertEqual(payloads[0]["predicted_delta"], 15000)
        self.assertEqual(payloads[1]["player_id"], "p2")
        batch.commit.assert_called_once()

    def test_empty_entries_writes_nothing(self):
        client = MagicMock()

        firestore_db.upsert_prediction_log_entries(client, [])

        client.batch.assert_not_called()


class UpsertDashboardSnapshotTests(unittest.TestCase):
    def test_writes_whole_dict_as_single_doc_named_latest(self):
        client = MagicMock()
        data = {"fetched_at": "2026-07-27T20:00:00Z", "transfermarkt": [{"player_id": "p1"}]}

        firestore_db.upsert_dashboard_snapshot(client, data)

        client.collection.assert_any_call("dashboard_snapshot")
        client.collection.return_value.document.assert_called_once_with("latest")
        client.collection.return_value.document.return_value.set.assert_called_once_with(data)


class GetWunschkaderTests(unittest.TestCase):
    def test_returns_none_when_document_missing(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False

        result = firestore_db.get_wunschkader(client)

        self.assertIsNone(result)

    def test_returns_dict_when_document_exists(self):
        client = MagicMock()
        doc_snapshot = client.collection.return_value.document.return_value.get.return_value
        doc_snapshot.exists = True
        doc_snapshot.to_dict.return_value = {"targets": [{"name": "Krauß"}], "formation": "3-4-3"}

        result = firestore_db.get_wunschkader(client)

        client.collection.assert_any_call("wunschkader")
        client.collection.return_value.document.assert_called_with("current")
        self.assertEqual(result["formation"], "3-4-3")


class UpsertWunschkaderTests(unittest.TestCase):
    def test_writes_whole_dict_as_single_doc_named_current(self):
        client = MagicMock()
        data = {"targets": [{"name": "Krauß", "position": "Mittelfeld", "role": "Starter"}], "formation": "3-4-3"}

        firestore_db.upsert_wunschkader(client, data)

        client.collection.assert_any_call("wunschkader")
        client.collection.return_value.document.assert_called_once_with("current")
        client.collection.return_value.document.return_value.set.assert_called_once_with(data)


class GetPredictionLogEntriesTests(unittest.TestCase):
    def test_returns_all_documents_as_dicts(self):
        client = MagicMock()
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.to_dict.return_value = {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}
        doc2.to_dict.return_value = {"date": "2026-07-27", "player_id": "p1", "model_type": "HistGradientBoosting", "predicted_delta": 90}
        client.collection.return_value.stream.return_value = [doc1, doc2]

        result = firestore_db.get_prediction_log_entries(client)

        client.collection.assert_any_call("ml_prediction_log")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["model_type"], "RandomForest")


class UpsertPredictionLogEntriesModelTypeDocIdTests(unittest.TestCase):
    def test_doc_id_includes_model_type(self):
        client = MagicMock()
        entries = [{"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}]

        firestore_db.upsert_prediction_log_entries(client, entries)

        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-27_p1_RandomForest", doc_ids)
