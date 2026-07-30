"""Tests fuer src/firestore_db.py: reine Row-Dict -> Firestore-Dokument-Formung,
gegen einen gemockten Firestore-Client (kein echter Netzwerkzugriff)."""

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
        data = {"fetched_at": "2026-07-27T20:00:00Z", "transfermarkt_listings": [{"player_id": "p1"}]}

        firestore_db.upsert_dashboard_snapshot(client, data)

        client.collection.assert_any_call("dashboard_snapshot")
        client.collection.return_value.document.assert_called_once_with("latest")
        client.collection.return_value.document.return_value.set.assert_called_once_with(data)


class GetDashboardSnapshotTests(unittest.TestCase):
    def test_returns_none_when_document_missing(self):
        client = MagicMock()
        client.collection.return_value.document.return_value.get.return_value.exists = False

        result = firestore_db.get_dashboard_snapshot(client)

        self.assertIsNone(result)

    def test_returns_dict_when_document_exists(self):
        client = MagicMock()
        doc_snapshot = client.collection.return_value.document.return_value.get.return_value
        doc_snapshot.exists = True
        doc_snapshot.to_dict.return_value = {"fetched_at": "2026-07-28T22:10:00Z", "alle_spieler": []}

        result = firestore_db.get_dashboard_snapshot(client)

        client.collection.assert_any_call("dashboard_snapshot")
        client.collection.return_value.document.assert_called_with("latest")
        self.assertEqual(result["fetched_at"], "2026-07-28T22:10:00Z")


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


class GetRecentPredictionLogEntriesTests(unittest.TestCase):
    def test_filters_by_date_range_server_side(self):
        client = MagicMock()
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}
        client.collection.return_value.where.return_value.where.return_value.stream.return_value = [doc1]

        result = firestore_db.get_recent_prediction_log_entries(client, "2026-07-25", "2026-07-28")

        client.collection.assert_any_call("ml_prediction_log")
        client.collection.return_value.where.assert_called_once()
        client.collection.return_value.where.return_value.where.assert_called_once()
        self.assertEqual(len(result), 1)


class UpsertAccuracyDailyTests(unittest.TestCase):
    def test_doc_id_is_date_and_model_type(self):
        client = MagicMock()
        entries = [{"date": "2026-07-27", "model_type": "RandomForest", "n": 450, "sign_correct": 300, "abs_error_sum": 12345.0}]

        firestore_db.upsert_accuracy_daily(client, entries)

        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-27_RandomForest", doc_ids)


class GetAccuracyDailyTests(unittest.TestCase):
    def test_returns_all_documents(self):
        client = MagicMock()
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"date": "2026-07-27", "model_type": "RandomForest", "n": 450, "sign_correct": 300, "abs_error_sum": 12345.0}
        client.collection.return_value.stream.return_value = [doc1]

        result = firestore_db.get_accuracy_daily(client)

        client.collection.assert_any_call("ml_accuracy_daily")
        self.assertEqual(len(result), 1)


class UpsertPredictionLogEntriesModelTypeDocIdTests(unittest.TestCase):
    def test_doc_id_includes_model_type(self):
        client = MagicMock()
        entries = [{"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}]

        firestore_db.upsert_prediction_log_entries(client, entries)

        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-27_p1_RandomForest", doc_ids)
