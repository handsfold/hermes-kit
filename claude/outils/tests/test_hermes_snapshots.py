import importlib.util
from pathlib import Path
import sqlite3
import unittest

p=Path('$HOME/.claude/outils/observabilite/hermes_snapshots.py')
spec=importlib.util.spec_from_file_location('snapshots',p)
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class SnapshotTests(unittest.TestCase):
    def row(self,n):
        return {'session_id':'s','model':'gpt-test','billing_provider':'openai-codex',
                'input_tokens':n,'output_tokens':2,'cache_read_tokens':5,'cache_write_tokens':0}
    def test_baseline_is_never_backfilled_as_today(self):
        db=sqlite3.connect(':memory:');h.snapshot(db,[self.row(100)],'2026-11-13T10:00:00+07:00')
        self.assertEqual(db.execute('select count(*) from hermes_deltas_v2').fetchone()[0],0)
        h.snapshot(db,[self.row(105)],'2026-11-13T10:10:00+07:00')
        h.snapshot(db,[self.row(105)],'2026-11-13T10:20:00+07:00')
        self.assertEqual(db.execute('select sum(input_tokens),count(*) from hermes_deltas_v2').fetchone(),(5,1))
    def test_midnight_and_counter_reset_are_explicit(self):
        db=sqlite3.connect(':memory:');h.snapshot(db,[self.row(100)],'2026-11-13T23:55:00+07:00')
        h.snapshot(db,[self.row(105)],'2026-11-14T00:05:00+07:00')
        self.assertEqual(db.execute('select boundary_uncertain from hermes_deltas_v2').fetchone()[0],1)
        h.snapshot(db,[self.row(1)],'2026-11-14T00:15:00+07:00')
        self.assertEqual(db.execute('select counter_reset,input_tokens from hermes_deltas_v2 order by observed_at desc').fetchone(),(1,0))

    def test_distinct_tasks_and_billing_routes_never_mix_counters(self):
        db=sqlite3.connect(':memory:')
        a=self.row(100); a.update(task='main',billing_base_url='route-a',billing_mode='subscription')
        b=self.row(2); b.update(task='compression',billing_base_url='route-a',billing_mode='subscription')
        c=self.row(50); c.update(task='main',billing_base_url='route-b',billing_mode='api')
        h.snapshot(db,[a,b,c],'2026-11-13T10:00:00+07:00')
        h.snapshot(db,[a,b,c],'2026-11-13T10:10:00+07:00')
        self.assertEqual(db.execute('select count(*) from hermes_deltas_v2').fetchone()[0],0)
        b['input_tokens']+=3
        h.snapshot(db,[a,b,c],'2026-11-13T10:20:00+07:00')
        self.assertEqual(db.execute('select sum(input_tokens),sum(counter_reset) from hermes_deltas_v2').fetchone(),(3,0))

    def test_new_session_after_tracking_start_is_counted(self):
        db=sqlite3.connect(':memory:')
        h.snapshot(db,[self.row(100)],'2026-11-13T10:00:00+07:00')
        new=self.row(7);new['session_id']='new';new['first_seen']='2026-11-13T10:05:00+07:00'
        h.snapshot(db,[self.row(100),new],'2026-11-13T10:10:00+07:00')
        self.assertEqual(db.execute('select sum(input_tokens) from hermes_deltas_v2').fetchone()[0],7)
        self.assertEqual(db.execute('select started_at from hermes_tracking_v2').fetchone()[0],'2026-11-13T10:00:00+07:00')

if __name__=='__main__':unittest.main()
