import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collector

class SanitizerTests(unittest.TestCase):
    def test_event_redacts_prompt_and_keeps_allowlisted_values(self):
        event = {"name":"claude_code.api_request", "attributes": {"model":"m-x", "session.id":"sess1", "input_tokens":12, "cost_usd":0.02, "prompt":"secret", "tool_input":"secret", "email":"a@b"}}
        result = collector.sanitize_log(event)
        self.assertEqual(result["attributes"], {"model":"m-x", "session.id":"sess1", "input_tokens":12, "cost_usd":0.02})
    def test_cumulative_metric_idempotency(self):
        db = collector.open_db(":memory:")
        payload = {"resourceLogs":[{"scopeLogs":[{"logRecords":[{"timeUnixNano":"1","body":{"stringValue":"api_request"},"attributes":[{"key":"request_id","value":{"stringValue":"r1"}},{"key":"model","value":{"stringValue":"m"}}]}]}]}]}
        collector.ingest_logs(db, payload)
        collector.ingest_logs(db, payload)
        self.assertEqual(db.execute("select count(*) from events").fetchone()[0], 1)

if __name__ == '__main__': unittest.main()
