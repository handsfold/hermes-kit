#!/usr/bin/env python3
"""Minimal privacy-filtering OTLP HTTP/JSON receiver; stdlib only."""
import argparse, gzip, hashlib, io, json, math, os, re, sqlite3, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 2 * 1024 * 1024
ID_KEYS = {"type", "token.type", "query_source_safe", "tool_name_safe", "tool_name", "app.entrypoint", "model", "session.id", "session_id", "parent_agent_id", "agent_id", "request_id", "client_request_id", "trace_id", "span_id", "parent_span_id", "status_code", "error_class", "success", "stop_reason", "span.type"}
NUM_KEYS = {"input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", "duration_ms", "ttft_ms", "first_content_ms", "attempt", "result_tokens", "cost_usd", "claude_code.session.count", "claude_code.token.usage", "claude_code.cost.usage", "claude_code.api_request.count", "claude_code.tool.duration"}

def safe_value(k, v):
    if k in NUM_KEYS and isinstance(v, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", v): v=float(v) if "." in v else int(v)
    if k in NUM_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v): return v
    if k in ID_KEYS and isinstance(v, (str, int, bool)) and len(str(v)) <= 256 and not re.search(r"[/\\@\s]", str(v)): return v
    return None

def sanitize_log(record):
    name = record.get("name") or (record.get("body") or {}).get("stringValue") or "event"
    if not re.fullmatch(r"(?:claude_code\.)?[a-z_][a-z0-9_.]{0,100}", str(name)): name="redacted_event"
    attrs = record.get("attributes", {})
    if isinstance(attrs, list): attrs = {x.get("key"): ((x.get("value") or {}).get("stringValue", (x.get("value") or {}).get("intValue", (x.get("value") or {}).get("doubleValue")))) for x in attrs if isinstance(x, dict)}
    clean = {k: v for k, val in attrs.items() if (v := safe_value(k, val)) is not None}
    for k in ("timeUnixNano", "observedTimeUnixNano"): 
        if record.get(k) is not None: clean[k] = record[k]
    return {"name": str(name)[:120], "attributes": clean}

def walk_logs(payload):
    for resource in payload.get("resourceLogs", []):
        resource_attrs = attrs_dict((resource.get("resource") or {}).get("attributes", []))
        for scope in resource.get("scopeLogs", []):
            for rec in scope.get("logRecords", []):
                out = sanitize_log(rec)
                out["attributes"].update({k:v for k,v in resource_attrs.items() if k in ID_KEYS and safe_value(k,v) is not None})
                yield out

def attrs_dict(a):
    if isinstance(a, dict): return a
    return {x.get("key"): (x.get("value") or {}).get("stringValue", (x.get("value") or {}).get("intValue", (x.get("value") or {}).get("doubleValue"))) for x in a if isinstance(x,dict)}

def open_db(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        if not os.path.exists(path):
            fd=os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600); os.close(fd)
    db=sqlite3.connect(path, check_same_thread=False, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS metrics (id TEXT PRIMARY KEY, name TEXT NOT NULL, value REAL NOT NULL, data TEXT NOT NULL)")
    return db

def ingest_logs(db, payload):
    n=0
    with db:
        for event in walk_logs(payload):
            data=json.dumps(event,sort_keys=True,separators=(",",":")); ident=hashlib.sha256(data.encode()).hexdigest()
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?)", (str(ident),"log",data)); n+=1
    return n

def ingest_metrics(db, payload):
    n=0
    with db:
        for rm in payload.get("resourceMetrics", []):
            for sm in rm.get("scopeMetrics", []):
                for metric in sm.get("metrics", []):
                    name=metric.get("name", "")
                    data=metric.get("sum") or metric.get("gauge") or metric.get("histogram") or {}
                    for dp in data.get("dataPoints", []):
                        attrs=attrs_dict(dp.get("attributes", [])); val=dp.get("asDouble", dp.get("asInt"))
                        if isinstance(val,str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",val): val=float(val)
                        if not isinstance(val,(int,float)) or isinstance(val,bool) or not math.isfinite(val): continue
                        clean={k:v for k,x in attrs.items() if (v:=safe_value(k,x)) is not None}
                        blob=json.dumps({"attributes":clean,"start":dp.get("startTimeUnixNano"),"time":dp.get("timeUnixNano")},sort_keys=True)
                        if not re.fullmatch(r"claude_code\.[a-z0-9_.]+",name): continue
                        series=json.dumps({"attributes":clean,"start":dp.get("startTimeUnixNano")},sort_keys=True)
                        ident=hashlib.sha256((name+series).encode()).hexdigest()
                        db.execute("INSERT OR REPLACE INTO metrics VALUES(?,?,?,?)",(ident,name,float(val),blob)); n+=1
    return n

def ingest_traces(db, payload):
    for resource in payload.get('resourceSpans', []):
        for scope in resource.get('scopeSpans', []):
            for span in scope.get('spans', []):
                trace, sid, parent = (str(span.get(k, '')) for k in ('traceId','spanId','parentSpanId'))
                if not re.fullmatch(r'[a-fA-F0-9]{32}', trace) or not re.fullmatch(r'[a-fA-F0-9]{16}', sid): continue
                clean=sanitize_log({'body':{'stringValue':span.get('name','redacted_event')},'attributes':span.get('attributes',[])})
                clean.update(trace_id=trace, span_id=sid)
                if re.fullmatch(r'[a-fA-F0-9]{16}',parent): clean['parent_span_id']=parent
                for k in ('startTimeUnixNano','endTimeUnixNano'):
                    if str(span.get(k,'')).isdigit(): clean[k]=str(span[k])
                db.execute('INSERT OR REPLACE INTO events VALUES(?,?,?)',('trace:'+trace+':'+sid,'trace',json.dumps(clean,sort_keys=True)))
    db.commit()


class Handler(BaseHTTPRequestHandler):
    server_version = "PrivateOTLP/1"
    def log_message(self, fmt, *args): pass
    def send_json(self, code, obj):
        data=json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == "/health": self.send_json(200,{"ok":True}); return
        self.send_json(404,{"error":"not found"})
    def do_POST(self):
        if self.path not in ("/v1/logs","/v1/metrics","/v1/traces"): self.send_json(404,{"error":"not found"}); return
        try:
            length=int(self.headers.get("Content-Length","-1"))
            if length < 0 or length > MAX_BODY: self.send_json(413,{"error":"body too large or missing length"}); return
            raw=self.rfile.read(length)
            if self.headers.get("Content-Encoding","").lower()=="gzip":
                raw=gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_BODY+1)
                if len(raw)>MAX_BODY: self.send_json(413,{"error":"body too large"}); return
            payload=json.loads(raw)
            with self.server.db_lock:
                if self.path=="/v1/logs": ingest_logs(self.server.db,payload)
                elif self.path=="/v1/metrics": ingest_metrics(self.server.db,payload)
                elif self.path=="/v1/traces": ingest_traces(self.server.db,payload)
            self.send_json(200,{})
        except (ValueError,UnicodeDecodeError,json.JSONDecodeError,gzip.BadGzipFile,EOFError): self.send_json(400,{"error":"malformed payload"})
        except Exception: self.send_json(400,{"error":"invalid payload"})

def main():
    p=argparse.ArgumentParser(); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--port",type=int,default=4318); p.add_argument("--db",required=True); a=p.parse_args()
    if a.host!="127.0.0.1": p.error("host must be 127.0.0.1")
    srv=ThreadingHTTPServer((a.host,a.port),Handler); srv.db=open_db(a.db); srv.db_lock=threading.RLock(); print(f"listening http://{a.host}:{a.port}",flush=True); srv.serve_forever()
if __name__=="__main__": main()
