"""Tests fuer src/discord_notify.py: reine 429-Retry-Logik gegen einen
gemockten requests.post (kein echter Netzwerkzugriff, kein echtes Warten -
time.sleep wird ebenfalls gemockt)."""

import unittest
from unittest.mock import MagicMock, patch

from src.discord_notify import _MAX_RETRIES, _post_with_retry


class PostWithRetryTests(unittest.TestCase):
    @patch("src.discord_notify.time.sleep")
    @patch("src.discord_notify.requests.post")
    def test_retries_once_after_429_then_succeeds(self, mock_post, mock_sleep):
        rate_limited = MagicMock(status_code=429)
        rate_limited.json.return_value = {"retry_after": 0.5}
        ok = MagicMock(status_code=200)
        mock_post.side_effect = [rate_limited, ok]

        _post_with_retry("https://example.test/webhook", data={"x": 1})

        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(0.6)

    @patch("src.discord_notify.time.sleep")
    @patch("src.discord_notify.requests.post")
    def test_permanent_429_raises_runtime_error_after_max_retries(self, mock_post, mock_sleep):
        rate_limited = MagicMock(status_code=429)
        rate_limited.json.return_value = {"retry_after": 0.1}
        mock_post.return_value = rate_limited

        with self.assertRaises(RuntimeError):
            _post_with_retry("https://example.test/webhook", data={"x": 1})

        self.assertEqual(mock_post.call_count, _MAX_RETRIES)
