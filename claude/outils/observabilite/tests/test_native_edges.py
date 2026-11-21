import json
import sqlite3
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collector as c


class NativeOTLPTests(unittest.TestCase):
    def test_json_long_counters_are_strings(self):
        event=c.sanitize_log({'body': {'stringValue': 'claude_code.api_request'},
                             'attributes':[{'key':'input_tokens','value':{'intValue':'12'}}]})
        self.assertEqual(event['attributes'].get('input_tokens'),12)

    def test_private_content_never_becomes_event_name(self):
        event=c.sanitize_log({'body':{'stringValue':'a private prompt with secret'}})
        self.assertNotIn('private',json.dumps(event))

    def test_traces_keep_parent_tree_without_tool_content(self):
        db=c.open_db(':memory:')
        payload={'resourceSpans':[{'scopeSpans':[{'spans':[{'traceId':'a'*32,
            'spanId':'b'*16,'parentSpanId':'c'*16,'name':'claude_code.tool',
            'startTimeUnixNano':'1','endTimeUnixNano':'2','attributes':[
                {'key':'tool_name_safe','value':{'stringValue':'Read'}},
                {'key':'tool_input','value':{'stringValue':'PRIVATE_FILE_CONTENT'}}]}]}]}]}
        c.ingest_traces(db,payload)
        text=db.execute('select data from events').fetchone()[0]
        self.assertIn('parent_span_id',text)
        self.assertNotIn('PRIVATE_FILE_CONTENT',text)
        c.ingest_traces(db,payload)
        self.assertEqual(db.execute('select count(*) from events').fetchone()[0],1)

    def test_metric_series_replaces_point_but_keeps_token_types(self):
        db=c.open_db(':memory:')
        def payload(t, v, typ):
            return {'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':'claude_code.token.usage',
                'sum':{'dataPoints':[{'startTimeUnixNano':'1','timeUnixNano':t,'asInt':str(v),
                'attributes':[{'key':'type','value':{'stringValue':typ}},
                              {'key':'session.id','value':{'stringValue':'session-test'}}]}]}}]}]}]}
        c.ingest_metrics(db,payload('2',10,'input'))
        c.ingest_metrics(db,payload('3',20,'input'))
        c.ingest_metrics(db,payload('3',7,'output'))
        self.assertEqual(db.execute('select count(*) from metrics').fetchone()[0],2)
        self.assertEqual(db.execute('select sum(value) from metrics').fetchone()[0],27)


if __name__=='__main__': unittest.main()
