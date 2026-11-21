import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('bilan_resilience',Path(__file__).parents[1]/'bilan_tokens.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class QuotaResilienceTests(unittest.TestCase):
    def test_429_keeps_old_measurement_explicitly_stale(self):
        previous={'used':100,'reset':'2026-11-13T09:40:00+00:00','observed_at':1}
        with patch.object(b,'read_json',side_effect=[previous,{'claudeAiOauth':{'accessToken':'unit-test-placeholder'}}]), patch.object(b,'request_json',side_effect=RuntimeError('Lecture distante refusée : HTTP 429')) as query:
            result=b.quota_usage(refresh=True)
        self.assertTrue(result['stale']);self.assertEqual(result['observed_at'],1)
        self.assertIn('HTTP 429',result['refresh_error']);query.assert_called_once()
    def test_unknown_quota_is_not_replaced_with_zero(self):
        with patch.object(b,'read_json',side_effect=[{}, {'claudeAiOauth':{'accessToken':'unit-test-placeholder'}}]), patch.object(b,'request_json',return_value={}):
            with self.assertRaises(RuntimeError):b.quota_usage(refresh=True)
    def test_stale_measurement_never_sends_alert(self):
        with tempfile.TemporaryDirectory() as d, patch.object(b,'STATE',Path(d)), patch.object(b,'quota_usage',return_value={'stale':True,'refresh_error':'HTTP 429'}),patch.object(b,'notify') as notify:
            with self.assertRaises(RuntimeError):b.check_quota()
            notify.assert_not_called()
            self.assertFalse((Path(d)/'alert-state.json').exists())

if __name__=='__main__':unittest.main()
