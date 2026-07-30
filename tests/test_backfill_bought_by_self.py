import unittest
from unittest.mock import MagicMock, patch

from src.backfill_bought_by_self import backfill


def _trade_activity(activity_id, byr):
    return {"i": activity_id, "t": 15, "data": {"byr": byr}}


class BackfillTests(unittest.TestCase):
    @patch("src.backfill_bought_by_self.firestore_db")
    def test_sets_true_when_buyer_matches_own_name(self, mock_fs):
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_1", "player_id": "p1"}
        ]
        client = MagicMock()

        updated = backfill(
            client, "tok", "l1", own_name="Ich",
            get_activities=lambda token, league_id: [_trade_activity("act_1", "Ich")],
        )

        self.assertEqual(updated, 1)
        client.collection.return_value.document.assert_called_once_with("act_1")
        client.collection.return_value.document.return_value.update.assert_called_once_with(
            {"bought_by_self": True}
        )

    @patch("src.backfill_bought_by_self.firestore_db")
    def test_sets_false_when_buyer_differs(self, mock_fs):
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_1", "player_id": "p1"}
        ]
        client = MagicMock()

        updated = backfill(
            client, "tok", "l1", own_name="Ich",
            get_activities=lambda token, league_id: [_trade_activity("act_1", "Rivale")],
        )

        self.assertEqual(updated, 1)
        client.collection.return_value.document.return_value.update.assert_called_once_with(
            {"bought_by_self": False}
        )

    @patch("src.backfill_bought_by_self.firestore_db")
    def test_skips_entries_that_already_have_the_field(self, mock_fs):
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_1", "player_id": "p1", "bought_by_self": True}
        ]
        client = MagicMock()

        updated = backfill(
            client, "tok", "l1", own_name="Ich",
            get_activities=lambda token, league_id: [_trade_activity("act_1", "Ich")],
        )

        self.assertEqual(updated, 0)
        client.collection.assert_not_called()

    @patch("src.backfill_bought_by_self.firestore_db")
    def test_skips_entry_when_activity_no_longer_in_feed(self, mock_fs):
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_gone", "player_id": "p1"}
        ]
        client = MagicMock()

        updated = backfill(
            client, "tok", "l1", own_name="Ich",
            get_activities=lambda token, league_id: [],
        )

        self.assertEqual(updated, 0)
        client.collection.assert_not_called()

    @patch("src.backfill_bought_by_self.firestore_db")
    def test_missing_own_name_marks_everything_as_not_self(self, mock_fs):
        mock_fs.get_bid_premium_history.return_value = [
            {"activity_id": "act_1", "player_id": "p1"}
        ]
        client = MagicMock()

        updated = backfill(
            client, "tok", "l1", own_name=None,
            get_activities=lambda token, league_id: [_trade_activity("act_1", "Ich")],
        )

        self.assertEqual(updated, 1)
        client.collection.return_value.document.return_value.update.assert_called_once_with(
            {"bought_by_self": False}
        )


if __name__ == "__main__":
    unittest.main()
