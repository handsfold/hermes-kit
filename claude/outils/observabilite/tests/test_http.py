import gzip, http.client, json, os, socket, subprocess, sys, tempfile, time, unittest

class HTTPIntegration(unittest.TestCase):
    def test_health_and_mock_log_ingest(self):
        with tempfile.TemporaryDirectory() as d:
            sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]; sock.close()
            proc=subprocess.Popen([sys.executable,os.path.join(os.path.dirname(os.path.dirname(__file__)),'collector.py'),'--port',str(port),'--db',os.path.join(d,'db.sqlite')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try:
                        c=http.client.HTTPConnection('127.0.0.1',port,timeout=1); c.request('GET','/health'); r=c.getresponse(); self.assertEqual(r.status,200); break
                    except OSError: time.sleep(.05)
                mock={"resourceLogs":[{"scopeLogs":[{"logRecords":[{"timeUnixNano":"9","body":{"stringValue":"api_request"},"attributes":[{"key":"request_id","value":{"stringValue":"mock-r"}},{"key":"model","value":{"stringValue":"mock-model"}},{"key":"input_tokens","value":{"intValue":7}},{"key":"prompt","value":{"stringValue":"TOP SECRET"}}]}]}]}]}
                c=http.client.HTTPConnection('127.0.0.1',port); c.request('POST','/v1/logs',json.dumps(mock),{'Content-Type':'application/json'}); self.assertEqual(c.getresponse().status,200)
                import sqlite3
                db=sqlite3.connect(os.path.join(d,'db.sqlite')); data=json.loads(db.execute('select data from events').fetchone()[0]); self.assertEqual(data['attributes']['input_tokens'],7); self.assertNotIn('prompt',data['attributes'])
            finally: proc.terminate(); proc.wait(timeout=3)

if __name__=='__main__': unittest.main()
