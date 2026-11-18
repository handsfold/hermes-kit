import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('ledger_composite',Path(__file__).resolve().parents[1]/'usage_ledger.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
DDL="CREATE TABLE session_model_usage (\n    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,\n    model TEXT NOT NULL,\n    billing_provider TEXT NOT NULL DEFAULT '',\n    billing_base_url TEXT NOT NULL DEFAULT '',\n    billing_mode TEXT NOT NULL DEFAULT '',\n    task TEXT NOT NULL DEFAULT '',\n    api_call_count INTEGER NOT NULL DEFAULT 0,\n    input_tokens INTEGER NOT NULL DEFAULT 0,\n    output_tokens INTEGER NOT NULL DEFAULT 0,\n    cache_read_tokens INTEGER NOT NULL DEFAULT 0,\n    cache_write_tokens INTEGER NOT NULL DEFAULT 0,\n    reasoning_tokens INTEGER NOT NULL DEFAULT 0,\n    estimated_cost_usd REAL NOT NULL DEFAULT 0,\n    actual_cost_usd REAL NOT NULL DEFAULT 0,\n    cost_status TEXT,\n    cost_source TEXT,\n    first_seen REAL,\n    last_seen REAL,\n    PRIMARY KEY (session_id, model, billing_provider, billing_base_url, billing_mode, task)\n)"
class CompositeKeyTests(unittest.TestCase):
    def test_full_billing_identity_preserves_rows(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);(home/'.hermes').mkdir()
            c=sqlite3.connect(home/'.hermes/state.db')
            c.execute('create table sessions(id text primary key, source text,parent_session_id text,thread_id text)')
            c.execute("insert into sessions values('mock-session','cli',null,null)")
            c.execute(DDL)
            for base,mode in [('mock-a','included'),('mock-b','metered')]:
                c.execute('insert into session_model_usage(session_id,model,billing_provider,billing_base_url,billing_mode,task,input_tokens,first_seen,last_seen) values(?,?,?,?,?,?,?,?,?)',('mock-session','mock-model','mock-provider',base,mode,'main',7,1794528000,1794528000))
            c.commit();c.close()
            db=home/'ledger.sqlite';u.import_data(home,db)
            c=sqlite3.connect(db)
            self.assertEqual(c.execute("select count(*),sum(input_tokens) from events where kind='hermes_cumulative'").fetchone(),(2,14))
if __name__=='__main__':unittest.main()
