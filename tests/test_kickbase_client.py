import unittest

from src.kickbase_client import status_label


class StatusLabelTests(unittest.TestCase):
    def test_zero_is_fit_no_label(self):
        self.assertIsNone(status_label(0))

    def test_one_is_verletzt(self):
        self.assertEqual(status_label(1), "Verletzt")

    def test_four_is_im_aufbau(self):
        self.assertEqual(status_label(4), "Im Aufbau")

    def test_unconfirmed_code_falls_back_to_placeholder(self):
        self.assertEqual(status_label(2), "Status-Code 2 (Bedeutung in v4-API nicht zweifelsfrei bestaetigt)")
