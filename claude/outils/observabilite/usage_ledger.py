#!/usr/bin/env python3
"""Registre local précis; aucune donnée de contenu n'est conservée."""
import argparse, datetime as dt, glob, json, os, sqlite3
from pathlib import Path
from hashlib import sha256
from zoneinfo import ZoneInfo
COUNTERS=('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens')

def stamp_day(v):
    try:
        x=dt.datetime.fromisoformat(v.replace('Z','+00:00')); return (x.astimezone(ZoneInfo('Asia/Bangkok')) if x.tzinfo else x).date().isoformat()
    except Exception:return None

def init(db):
    Path(db).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not Path(db).exists():
        fd=os.open(db, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600); os.close(fd)
    c=sqlite3.connect(db)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('''create table if not exists events(event_id text primary key,day text,source text,model text,session text,parent text,topic text,caller text,input_tokens integer,output_tokens integer,cache_read_tokens integer,cache_write_tokens integer,estimated_cost_usd real,actual_cost_usd real,cost_status text,cost_source text,first_seen text,last_seen text,kind text,prompt_len integer,sys_len integer,ms integer,reprise integer)''')
    c.execute('''create table if not exists file_state(path text primary key,inode integer,size integer,mtime_ns integer,offset integer)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_session ON events(kind,session,last_seen)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_day ON events(day)')
    return c

def number(v):
    try:return max(0,int(v or 0))
    except:return 0

def import_data(home,db,day=None,state_path=None,proxy_path=None):
    home=Path(home).expanduser(); sp=Path(state_path or home/'.hermes/state.db'); pp=Path(proxy_path or home/'.hermes/proxy-usage.jsonl'); c=init(db); inserted=0
    # Scan known JSONL, skipping files whose inode/size/mtime are unchanged. Re-scan changed files
    # for correct deduplication across truncation and copied transcript files.
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    files=glob.iglob(str(home/'.claude/projects/**/*.jsonl'),recursive=True)
    for name in files:
        try: st=os.stat(name)
        except OSError: continue
        prev=con.execute('select inode,size,mtime_ns from file_state where path=?',(name,)).fetchone()
        if prev and (prev['inode'],prev['size'],prev['mtime_ns'])==(st.st_ino,st.st_size,st.st_mtime_ns):continue
        try:
            with open(name,encoding='utf-8') as f:
                for line in f:
                    try:r=json.loads(line)
                    except:continue
                    m=r.get('message') or {}; u=m.get('usage') or {}
                    if not isinstance(u,dict) or not (m.get('id') or r.get('requestId')):continue
                    d=stamp_day(r.get('timestamp',''))
                    if r.get('type')!='assistant' or not d: continue
                    mid=str(m.get('id') or r.get('requestId'))
                    vals=[number(u.get('input_tokens')),number(u.get('output_tokens')),number(u.get('cache_read_input_tokens',u.get('cache_read_tokens'))),number(u.get('cache_creation_input_tokens',u.get('cache_write_tokens')))]
                    eid='claude:'+mid
                    old=con.execute('select input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,first_seen,last_seen from events where event_id=?',(eid,)).fetchone()
                    vals=[max(a,b) for a,b in zip(vals,[old[k] or 0 for k in COUNTERS])] if old else vals
                    first=min(filter(None,[old['first_seen'] if old else None,r.get('timestamp')]),default=None); last=max(filter(None,[old['last_seen'] if old else None,r.get('timestamp')]),default=None)
                    parent=Path(name).parent.parent.name if Path(name).parent.name=='subagents' else None
                    session=('agent:'+str(r.get('agentId') or Path(name).stem)) if parent else str(r.get('sessionId') or '')
                    con.execute('insert or replace into events values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,d,'claude-code',str(m.get('model') or 'inconnu'),session,parent,None,None,*vals,None,None,'unknown','claude_native',first,last,'claude_native',None,None,None,None)); inserted+=1
            con.execute('insert or replace into file_state values(?,?,?,?,?)',(name,st.st_ino,st.st_size,st.st_mtime_ns,st.st_size))
        except (OSError,UnicodeError):continue
    con.commit()
    if sp.exists():
        try:
            s=sqlite3.connect('file:'+str(sp)+'?mode=ro',uri=True); s.row_factory=sqlite3.Row
            for r in s.execute('select u.*,s.parent_session_id,s.source,s.thread_id from session_model_usage u left join sessions s on s.id=u.session_id'):
                first=dt.datetime.fromtimestamp(r['first_seen'],dt.timezone.utc).isoformat() if r['first_seen'] else None; last=dt.datetime.fromtimestamp(r['last_seen'],dt.timezone.utc).isoformat() if r['last_seen'] else None; d=stamp_day(last or first or '')
                if day and d!=day:continue
                claude='claude' in ((r['billing_provider'] or '')+' '+(r['model'] or '')).lower(); kind='overlap_claude' if claude else 'hermes_cumulative'
                eid='hermes-v2:'+sha256(json.dumps([r[k] if k in r.keys() else '' for k in ('session_id','model','billing_provider','billing_base_url','billing_mode','task')],separators=(',',':')).encode()).hexdigest()
                est=r['estimated_cost_usd'] if r['cost_status']=='estimated' else None
                actual=r['actual_cost_usd'] if r['cost_status'] in ('actual','recorded','billed') else None
                con.execute('insert or replace into events values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,d,'hermes',r['model'],r['session_id'],r['parent_session_id'],r['thread_id'],None,number(r['input_tokens']),number(r['output_tokens']),number(r['cache_read_tokens']),number(r['cache_write_tokens']),est,actual,r['cost_status'] or 'unknown',r['cost_source'],first,last,kind,None,None,None,None)); inserted+=1
            s.close()
        except sqlite3.Error:pass
    if pp.exists():
        try:
            with open(pp,encoding='utf-8') as f:
                for line in f:
                    try:r=json.loads(line)
                    except:continue
                    d=stamp_day(r.get('ts',''))
                    if day and d!=day:continue
                    eid='proxy:'+':'.join(str(r.get(k) or '') for k in ('session','ts','tour'))
                    con.execute('insert or replace into events values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(eid,d,'proxy',str(r.get('modele') or 'inconnu'),str(r.get('session') or ''),None,r.get('topic'),r.get('appelant') or r.get('source'),number(r.get('entree')),number(r.get('sortie')),number(r.get('cache_lu')),number(r.get('cache_ecrit')),r.get('cout_usd') if isinstance(r.get('cout_usd'),(int,float)) else None,None,'proxy_estimate','proxy-log',r.get('ts'),r.get('ts'),'proxy_view',number(r.get('prompt_len')),number(r.get('sys_len')),number(r.get('ms')),int(bool(r.get('reprise'))))); inserted+=1
        except (OSError,UnicodeError):pass
    # Lien démontrable uniquement : identifiant de session Claude natif = session du journal proxy.
    for row in con.execute("SELECT event_id,session,parent FROM events WHERE kind='claude_native'").fetchall():
        meta=con.execute("SELECT topic,caller FROM events WHERE kind='proxy_view' AND session=? ORDER BY last_seen DESC LIMIT 1",(row['parent'] or row['session'],)).fetchone()
        if meta: con.execute('UPDATE events SET topic=?,caller=? WHERE event_id=?',(meta['topic'],meta['caller'],row['event_id']))
    con.commit(); con.close(); c.close(); return inserted

def report(db,day):
    c=sqlite3.connect(db); c.row_factory=sqlite3.Row; rows=list(c.execute("select * from events where day=? AND NOT (kind='claude_native' AND model='<synthetic>') AND event_id NOT LIKE 'hermes:%'",(day,)))
    groups={}
    for r in rows:
        key=(r['source'],r['model'],r['session'],r['parent'],r['topic'],r['caller'],r['kind']); a=groups.setdefault(key,{**{x:0 for x in COUNTERS},'estimated_cost_usd':None,'actual_cost_usd':None,'cost_statuses':set(),'cost_sources':set(),'first_seen':None,'last_seen':None,'prompt_len':0,'sys_len':0,'ms':0,'reprises':0})
        for x in COUNTERS:a[x]+=r[x] or 0
        for col in ('estimated_cost_usd','actual_cost_usd'):
            if r[col] is not None:a[col]=(a[col] or 0)+r[col]
        if r['cost_status']:a['cost_statuses'].add(r['cost_status'])
        if r['cost_source']:a['cost_sources'].add(r['cost_source'])
        for col,fn in (('first_seen',min),('last_seen',max)):
            a[col]=fn(filter(None,[a[col],r[col]]),default=None)
        a['prompt_len']+=r['prompt_len'] or 0;a['sys_len']+=r['sys_len'] or 0;a['ms']+=r['ms'] or 0;a['reprises']+=r['reprise'] or 0
    groups=[dict(zip(('source','model','session','parent_session','topic','caller','kind'),k),**{**v,'cost_statuses':sorted(v['cost_statuses']),'cost_sources':sorted(v['cost_sources'])}) for k,v in groups.items()]
    overlap=any(r['kind']=='overlap_claude' for r in rows) and any(r['kind']=='claude_native' for r in rows)
    return {'schema_version':1,'day':day,'timezone':'Asia/Bangkok','coverage':{'claude_native_events':sum(r['kind']=='claude_native' for r in rows),'hermes_cumulative_rows':sum(r['kind']=='hermes_cumulative' for r in rows),'hermes_claude_overlap_rows':sum(r['kind']=='overlap_claude' for r in rows),'proxy_views':sum(r['kind']=='proxy_view' for r in rows),'quota_percent':'non_observe','claude_events_with_topic':sum(r['kind']=='claude_native' and r['topic'] is not None for r in rows),'claude_events_with_caller':sum(r['kind']=='claude_native' and r['caller'] is not None for r in rows),'attribution_note':'Lien par égalité exacte de session; absence de lien = non attribué, pas nécessairement direct.'},'overlap_uncertain':overlap,'global_total_available':False,'groups':groups}

def main():
    p=argparse.ArgumentParser();p.add_argument('--home',default=str(Path.home()));p.add_argument('--db',required=True);p.add_argument('--day',default=dt.datetime.now(ZoneInfo('Asia/Bangkok')).date().isoformat());p.add_argument('--json',action='store_true');p.add_argument('--refresh',action='store_true');p.add_argument('--collect-only',action='store_true');a=p.parse_args()
    if a.refresh or a.collect_only:import_data(Path(a.home),Path(a.db),a.day)
    if a.collect_only:return
    out=report(Path(a.db),a.day)
    if a.json:print(json.dumps(out,ensure_ascii=False,indent=2))
    else:
        print(f"Registre {a.day} — Claude {out['coverage']['claude_native_events']}; Hermès cumuls {out['coverage']['hermes_cumulative_rows']}; proxy vues {out['coverage']['proxy_views']}; quotas % non observé")
        print('Total global indisponible: chevauchement' if out['overlap_uncertain'] else 'Sources présentées séparément; aucune addition globale.')
        for g in out['groups'][:25]:print(f"{g['source']} | {g['model']} | session={g['session']} parent={g['parent_session']} topic={g['topic']} appelant={g['caller']} | in={g['input_tokens']} out={g['output_tokens']} cache_lu={g['cache_read_tokens']} cache_ecrit={g['cache_write_tokens']} estimé={g['estimated_cost_usd']} réel={g['actual_cost_usd']} coûts={g['cost_statuses']}/{g['cost_sources']} [{g['kind']}]")
if __name__=='__main__':main()
