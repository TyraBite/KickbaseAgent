import os
import unittest
from unittest.mock import patch

from src import firestore_db
from src.fetcher import _write_firestore


class WriteFirestoreTests(unittest.TestCase):
    def test_returns_without_firestore_enabled(self):
        with patch("src.fetcher.firestore_db.connect") as mock_connect:
            with patch.dict(os.environ, {}, clear=True):
                _write_firestore("2026-07-29", [], [], [], None, None, {}, [])
            mock_connect.assert_not_called()

    @patch("src.fetcher.firestore_db.replace_own_squad")
    @patch("src.fetcher.firestore_db.connect")
    def test_raises_firestore_write_error_with_fetched_at_on_failure(self, mock_connect, mock_replace):
        mock_replace.side_effect = RuntimeError("quota exceeded")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            with self.assertRaises(firestore_db.FirestoreWriteError) as ctx:
                _write_firestore("2026-07-29", [], [], [], None, None, {}, [])
        self.assertEqual(ctx.exception.fetched_at, "2026-07-29")
