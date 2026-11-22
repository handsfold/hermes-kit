import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('bilan_tokens', Path(__file__).resolve().parents[1] / 'bilan_tokens.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class BilanTests(unittest.TestCase):
    def test_cache_ratio_uses_all_anthropic_input_categories(self):
        self.assertEqual(B.cache_ratio(20, 70, 10), 70.0)
        self.assertIsNone(B.cache_ratio(0, 0, 0))

    def test_first_sample_is_a_silent_baseline(self):
        state, alert = B.alert_decision({}, 85, '2026-11-13T06:20:00+00:00')
        self.assertFalse(alert)
        self.assertTrue(state['notified'])

    def test_alert_once_above_80_per_window(self):
        state, alert = B.alert_decision({}, 7, '2026-11-13T06:20:00+00:00')
        self.assertFalse(alert)
        state, alert = B.alert_decision(state, 80, '2026-11-13T06:20:00.100+00:00')
        self.assertFalse(alert)
        state, alert = B.alert_decision(state, 81, '2026-11-13T06:20:00.900+00:00')
        self.assertTrue(alert)
        state, alert = B.alert_decision(state, 95, '2026-11-13T06:20:00+00:00')
        self.assertFalse(alert)

    def test_reset_allows_another_alert(self):
        state, _ = B.alert_decision({}, 85, '2026-11-13T06:20:00+00:00')
        state, alert = B.alert_decision(state, 7, '2026-11-13T11:20:00+00:00')
        self.assertFalse(alert)
        _, alert = B.alert_decision(state, 82, '2026-11-13T11:20:00+00:00')
        self.assertTrue(alert)

    def test_proxy_model_breakdowns_are_not_added_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proxy.jsonl'
            row = {'ts': '2026-11-13T00:00:00Z', 'modele': 'requested-alias', 'source': 'prime',
                   'entree': 10, 'sortie': 3, 'cache_lu': 20, 'cache_ecrit': 5, 'cout_usd': 0.1,
                   'par_modele': {'actual-model': {'entree': 10, 'sortie': 3, 'cache_lu': 20, 'cache_ecrit': 5, 'cout_usd': 0.1}},
                   'outils': {'Read': 2}}
            path.write_text(json.dumps(row) + '\n')
            report = B.load_proxy(path, 0)
        self.assertEqual(list(report['models']), ['actual-model'])
        self.assertEqual(report['models']['actual-model']['input'], 10)
        self.assertEqual(report['models']['actual-model']['output'], 3)
        self.assertEqual(report['tools']['Read'], 2)


if __name__ == '__main__':
    unittest.main()
