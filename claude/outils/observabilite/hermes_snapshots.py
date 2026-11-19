#!/usr/bin/env python3
"""Deltas de cumuls Hermès. Zéro modèle, zéro réseau, aucune donnée de prompt.
Le premier relevé est une base, jamais une dépense du jour reconstituée.
Un intervalle traversant minuit reste explicitement incertain.
"""
import json
import hashlib
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

COUNTERS=('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens')


def snapshot(db, rows, observed_at):
    db.execute('CREATE TABLE IF NOT EXISTS hermes_baselines_v2 (key TEXT PRIMARY KEY, observed_at TEXT, counters TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS hermes_deltas_v2 (key TEXT, observed_at TEXT, previous_at TEXT, day TEXT, model TEXT, provider TEXT, input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER, boundary_uncertain INTEGER, counter_reset INTEGER, PRIMARY KEY(key,observed_at))')
    db.execute('CREATE TABLE IF NOT EXISTS hermes_tracking_v2 (id INTEGER PRIMARY KEY CHECK(id=1), started_at TEXT)')
    previous_start=db.execute('SELECT MIN(observed_at) FROM hermes_baselines_v2').fetchone()[0]
    db.execute('INSERT OR IGNORE INTO hermes_tracking_v2 VALUES(1,?)',(previous_start or observed_at,))
    started_at=db.execute('SELECT started_at FROM hermes_tracking_v2 WHERE id=1').fetchone()[0]
    for r in rows:
        key=hashlib.sha256(json.dumps([r.get(k,'') for k in ('session_id','model','billing_provider','billing_base_url','billing_mode','task')],separators=(',',':')).encode()).hexdigest()
        current=[int(r[k] or 0) for k in COUNTERS]
        old=db.execute('SELECT observed_at,counters FROM hermes_baselines_v2 WHERE key=?',(key,)).fetchone()
        if not old and observed_at>started_at and r.get('first_seen') is not None:
            try:
                first=r['first_seen']
                created=(datetime.fromtimestamp(first,ZoneInfo('Asia/Bangkok')) if isinstance(first,(int,float)) else datetime.fromisoformat(first.replace('Z','+00:00')))
                if created>=datetime.fromisoformat(started_at): old=(created.isoformat(),json.dumps([0]*4))
            except (ValueError,TypeError,OverflowError): pass
        if old:
            previous=json.loads(old[1]); reset=any(a<b for a,b in zip(current,previous))
            delta=[a-b for a,b in zip(current,previous)] if not reset else [0]*4
            if any(delta) or reset:
                boundary=old[0][:10]!=observed_at[:10]
                db.execute('INSERT OR IGNORE INTO hermes_deltas_v2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,observed_at,old[0],observed_at[:10],r['model'],r.get('billing_provider'),*delta,int(boundary),int(reset)))
        db.execute('INSERT OR REPLACE INTO hermes_baselines_v2 VALUES(?,?,?)',(key,observed_at,json.dumps(current)))
    db.commit()


def collect(home, db_path):
    from pathlib import Path
    source=sqlite3.connect('file:'+str(Path(home)/'.hermes/state.db')+'?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    try: rows=[dict(r) for r in source.execute('SELECT * FROM session_model_usage')]
    finally: source.close()
    db=sqlite3.connect(db_path)
    try: snapshot(db,rows,datetime.now(ZoneInfo('Asia/Bangkok')).isoformat())
    finally: db.close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--db',required=True);a=p.parse_args()
    collect(a.home,a.db)
