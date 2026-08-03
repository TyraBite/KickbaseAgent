"""Tests fuer src/main.py: reines Env-Var-Parsing von
_predict_market_values() (der eigentliche ML-Aufruf/Import bleibt gemockt/
ungetestet - siehe Audit, geringe Prio, aktuell nicht auf dem Live-Cron
bestaetigt notwendig)."""

import builtins
import os
import unittest
from unittest.mock import patch

from src.main import _predict_market_values


class PredictMarketValuesDisabledEnvVarTests(unittest.TestCase):
    """MARKET_PREDICTOR_ENABLED="0"/"false"/"no" (case-insensitiv) soll
    _predict_market_values() sofort None zurueckgeben lassen, OHNE dass
    'from src import market_predictor' (der optionale, potenziell teure
    ML-Import) je ausgefuehrt wird - geprueft per __import__-Spy statt
    sys.modules (letzteres ist unzuverlaessig, weil test_market_predictor.py
    das Modul im selben Testlauf ohnehin schon laedt)."""

    def _call_with_import_spy(self, env_value):
        calls = []
        original_import = builtins.__import__

        def spy(name, globals=None, locals=None, fromlist=(), level=0):
            if fromlist and "market_predictor" in fromlist:
                calls.append(name)
            return original_import(name, globals, locals, fromlist, level)

        with patch.dict(os.environ, {"MARKET_PREDICTOR_ENABLED": env_value}), \
                patch("builtins.__import__", side_effect=spy):
            result = _predict_market_values()
        return result, calls

    def test_zero_disables_without_importing_market_predictor(self):
        result, import_calls = self._call_with_import_spy("0")
        self.assertIsNone(result)
        self.assertEqual(import_calls, [])

    def test_false_case_insensitive_disables_without_importing(self):
        result, import_calls = self._call_with_import_spy("FALSE")
        self.assertIsNone(result)
        self.assertEqual(import_calls, [])

    def test_no_disables_without_importing(self):
        result, import_calls = self._call_with_import_spy("no")
        self.assertIsNone(result)
        self.assertEqual(import_calls, [])
