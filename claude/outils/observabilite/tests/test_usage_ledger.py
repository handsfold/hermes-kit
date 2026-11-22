import json, sqlite3, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import usage_ledger as u

class LedgerTests(unittest.TestCase):
    def test_dedup_max_counters_and_no_sensitive_storage(self):
        rows=[{'type':'assistant','timestamp':'2026-11-13T01:00:00Z','sessionId':'s','message':{'id':'m','model':'claude-x','usage':{'input_tokens':2,'output_tokens':3,'cache_read_input_tokens':5,'cache_creation_input_tokens':1}}}, {'type':'assistant','timestamp':'2026-11-13T01:00:01Z','sessionId':'s','message':{'id':'m','model':'claude-x','usage':{'input_tokens':4,'output_tokens':3,'cache_read_input_tokens':5,'cache_creation_input_tokens':2},'content':[{'text':'secret prompt'}]}}]
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'.claude/projects/test/x.jsonl'; f.parent.mkdir(parents=True); f.write_text('\n'.join(map(json.dumps,rows)))
            db=Path(d)/'db.sqlite'; u.import_data(Path(d),db,day='2026-11-13',state_path=Path(d)/'none',proxy_path=Path(d)/'noneproxy')
            u.import_data(Path(d),db,day='2026-11-13',state_path=Path(d)/'none',proxy_path=Path(d)/'noneproxy')
            c=sqlite3.connect(db)
            data=' '.join(str(x) for x in c.execute('select * from events'))
            self.assertNotIn('secret prompt',data)
            self.assertEqual(c.execute('select count(*) from events').fetchone()[0],1)
            self.assertEqual(c.execute('select input_tokens,output_tokens,cache_read_tokens,cache_write_tokens from events').fetchone(),(4,3,5,2))
    def test_proxy_and_hermes_claude_are_nonadditive(self):
        with tempfile.TemporaryDirectory() as d:
            h=Path(d)/'state'; c=sqlite3.connect(h); c.executescript('create table sessions(id text,source text,parent_session_id text,thread_id text,model text,title text,origin_json text); create table session_model_usage(session_id text,model text,billing_provider text,billing_base_url text,billing_mode text,task text,api_call_count int,input_tokens int,output_tokens int,cache_read_tokens int,cache_write_tokens int,reasoning_tokens int,estimated_cost_usd real,actual_cost_usd real,cost_status text,cost_source text,first_seen real,last_seen real);'); c.execute("insert into sessions values('s','cli',null,'t','claude-x',null,null)"); c.execute("insert into session_model_usage values('s','claude-x','anthropic','','','',1,3,4,5,0,0,0.1,0,'estimated','native',1,2)"); c.commit(); c.close()
            p=Path(d)/'proxy'; p.write_text(json.dumps({'ts':'2026-11-13T01:00:00Z','session':'s','source':'cli','topic':'t','modele':'claude-x','entree':3,'sortie':4,'cache_lu':5,'cache_ecrit':0,'cout_usd':.1})+'\n')
            db=Path(d)/'db'; u.import_data(Path(d),db,day='2026-11-13',state_path=h,proxy_path=p)
            report=u.report(db,'2026-11-13'); self.assertFalse(report['global_total_available']); self.assertEqual(report['coverage']['proxy_views'],1)

    def test_import_other_day_does_not_poison_file_cache(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'.claude/projects/test/x.jsonl'; f.parent.mkdir(parents=True)
            row={'type':'assistant','timestamp':'2026-11-12T01:00:00Z','sessionId':'s','message':{'id':'m','model':'claude-x','usage':{'input_tokens':2,'cache_read_input_tokens':5}}}
            f.write_text(json.dumps(row)+'\n'); db=Path(d)/'db'
            u.import_data(Path(d),db,day='2026-11-13')
            u.import_data(Path(d),db,day='2026-11-12')
            self.assertEqual(u.report(db,'2026-11-12')['coverage']['claude_native_events'],1)

    def test_proxy_cost_is_estimated_and_native_session_gets_topic(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'.claude/projects/test/x.jsonl'; f.parent.mkdir(parents=True)
            f.write_text(json.dumps({'type':'assistant','timestamp':'2026-11-13T01:00:00Z','sessionId':'s','message':{'id':'m','model':'claude-x','usage':{'input_tokens':3}}})+'\n')
            p=Path(d)/'.hermes/proxy-usage.jsonl';p.parent.mkdir();p.write_text(json.dumps({'ts':'2026-11-13T01:00:01Z','session':'s','topic':'635','source':'topic','modele':'claude-x','cout_usd':1.23})+'\n')
            db=Path(d)/'db';u.import_data(Path(d),db)
            rows=u.report(db,'2026-11-13')['groups']
            native=next(r for r in rows if r['source']=='claude-code')
            proxy=next(r for r in rows if r['source']=='proxy')
            self.assertEqual(native['topic'],'635')
            self.assertIsNone(proxy['actual_cost_usd'])
            self.assertEqual(proxy['estimated_cost_usd'],1.23)
if __name__=='__main__': unittest.main()
