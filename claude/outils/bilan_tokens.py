#!/usr/bin/env python3
"""Compteurs locaux, ccusage hors ligne et quota OAuth. Aucun appel de modèle.

Les sources se recouvrent : ne jamais additionner Claude, Hermes et proxy.
Le coût ccusage/proxy est un équivalent API, pas une facture d'abonnement.
Hermes conserve des cumuls par session/modèle, pas un journal horaire complet.
"""
import argparse
import collections
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

HOME = Path.home()
STATE = HOME / '.local/state/bilan-tokens'
CONFIG = HOME / '.config/bilan-tokens/config.json'
TZ = ZoneInfo('Asia/Bangkok')


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def timestamp(value):
    if isinstance(value, (float, int)):
        return float(value)
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def cache_ratio(input_tokens, cache_read, cache_write):
    total = input_tokens + cache_read + cache_write
    return 100 * cache_read / total if total > 0 else None


def alert_decision(previous, used, reset):
    # L'API peut décaler resets_at de quelques millisecondes : une clé à la minute.
    window = int(timestamp(reset) // 60)
    first = not previous or previous.get('window') is None
    notified = bool(previous.get('notified')) if previous.get('window') == window else False
    alert = used > 80 and not notified and not first
    return {'window': window, 'used': used, 'reset': reset,
            'notified': notified or alert or (first and used > 80),
            'observed_at': time.time()}, alert


def request_json(url, headers=None, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError('Lecture distante refusée : HTTP ' + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise RuntimeError('Lecture distante indisponible, aucun compteur inventé') from None


def quota_usage(refresh=False):
    cached = read_json(STATE / 'quota.json')
    if not refresh and time.time() - cached.get('observed_at', 0) < 300:
        return cached
    credentials = read_json(HOME / '.claude/.credentials.json')
    oauth = credentials.get('claudeAiOauth') or {}
    token = oauth.get('accessToken')
    if not token:
        raise RuntimeError('Identifiants OAuth Claude absents')
    try:
        raw = request_json('https://api.anthropic.com/api/oauth/usage', headers={
            'Authorization': 'Bearer ' + token, 'anthropic-beta': 'oauth-2025-04-20'})
        five = raw.get('five_hour') or {}
        if five.get('utilization') is None or not five.get('resets_at'):
            raise RuntimeError('Fenêtre de 5 heures absente de la réponse native')
    except RuntimeError as exc:
        if 'used' in cached and cached.get('reset'):
            return {**cached, 'stale': True, 'refresh_error': str(exc)}
        raise
    used = float(five['utilization'])
    if not 0 <= used <= 100:
        raise RuntimeError('Pourcentage natif invalide')
    value = {'used': used, 'reset': five['resets_at'], 'observed_at': time.time(),
             'weekly': raw.get('seven_day'), 'source': 'Claude OAuth /api/oauth/usage'}
    save_json(STATE / 'quota.json', value)
    return value


def telegram_token():
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if token:
        return token
    for line in (HOME / '.hermes/.env').read_text().splitlines():
        key, separator, value = line.partition('=')
        if separator and key.strip() == 'TELEGRAM_BOT_TOKEN':
            return value.strip().strip('\"\'')
    raise RuntimeError('Jeton Telegram absent')


def notify(quota):
    settings = read_json(CONFIG)
    address = read_json(HOME / '.hermes/qg-adresse.json')
    chat = str(settings.get('chat_id') or address.get('chat') or '')
    thread = settings.get('thread_id') or address.get('thread')
    if not chat or not thread:
        raise RuntimeError('Destination Telegram incomplète')
    reset = dt.datetime.fromtimestamp(timestamp(quota['reset']), TZ).strftime('%H:%M')
    text = f"Quota Claude : fenêtre de 5 heures à {quota['used']:.0f} %.\nRemise à zéro à {reset} (Thaïlande)."
    payload = {'chat_id': chat, 'message_thread_id': int(thread), 'text': text,
               'disable_notification': False, 'protect_content': False}
    result = request_json('https://api.telegram.org/bot' + telegram_token() + '/sendMessage',
                          headers={'Content-Type': 'application/json'}, payload=payload)
    message = result.get('result') or {}
    if (not result.get('ok') or str((message.get('chat') or {}).get('id')) != chat
            or message.get('message_thread_id') != int(thread) or message.get('text') != text):
        raise RuntimeError('Telegram : cible et contenu de la réponse non confirmés')
    return message.get('message_id')


def check_quota():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(STATE / 'monitor.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        quota = quota_usage(refresh=True)
        if quota.get('stale'):
            raise RuntimeError('Quota ancien : aucune alerte émise; '+quota.get('refresh_error',''))
        previous = read_json(STATE / 'alert-state.json')
        state, alert = alert_decision(previous, quota['used'], quota['reset'])
        if alert:
            # L'état n'est marqué envoyé qu'après confirmation Telegram.
            state['message_id'] = notify(quota)
        save_json(STATE / 'alert-state.json', state)
    return 0


def blank_model():
    return {'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0, 'equivalent_usd': 0}


def load_proxy(path, since):
    result = {'models': {}, 'sources': {}, 'tools': {}, 'calls': 0, 'errors': 0,
              'malformed_rows': 0, 'source': str(path), 'since': since}
    if not Path(path).exists():
        result['unavailable'] = True
        return result
    sources, tools = collections.Counter(), collections.Counter()
    with open(path) as stream:
        for line in stream:
            try:
                row = json.loads(line)
                if timestamp(row['ts']) < since:
                    continue
            except (ValueError, TypeError, KeyError):
                result['malformed_rows'] += 1
                continue
            result['calls'] += 1
            if row.get('erreur'):
                result['errors'] += 1
            sources[str(row.get('source') or 'inconnue')] += 1
            for tool, count in (row.get('outils') or {}).items():
                if isinstance(count, (float, int)):
                    tools[tool] += count
            breakdown = row.get('par_modele')
            if not isinstance(breakdown, dict) or not breakdown:
                breakdown = {str(row.get('modele') or 'inconnu'): row}
            for model, usage in breakdown.items():
                if not isinstance(usage, dict):
                    continue
                values = result['models'].setdefault(model, blank_model())
                for target, origin in [('input', 'entree'), ('output', 'sortie'),
                                       ('cache_read', 'cache_lu'), ('cache_write', 'cache_ecrit'),
                                       ('equivalent_usd', 'cout_usd')]:
                    value = usage.get(origin, 0)
                    if isinstance(value, (int, float)):
                        values[target] += value
    result['sources'], result['tools'] = dict(sources), dict(tools)
    return result


def hermes_usage(since):
    db = HOME / '.hermes/state.db'
    connection = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        sql = '''SELECT model, billing_provider, billing_mode,
          SUM(input_tokens) AS input, SUM(output_tokens) AS output,
          SUM(cache_read_tokens) AS cache_read, SUM(cache_write_tokens) AS cache_write,
          SUM(estimated_cost_usd) AS equivalent_usd,
          MIN(first_seen) AS first_seen, MAX(last_seen) AS last_seen,
          COUNT(*) AS session_model_rows
          FROM session_model_usage GROUP BY model, billing_provider, billing_mode'''
        models = [dict(row) for row in connection.execute(sql)]
        tools = {row[0]: row[1] for row in connection.execute(
            "SELECT tool_name, COUNT(*) FROM messages WHERE timestamp >= ? "
            "AND role='tool' AND tool_name IS NOT NULL GROUP BY tool_name", (since,))}
        return {'models': models, 'tools_today': tools, 'source': str(db),
                'period': 'Cumul intégral des compteurs session/modèle, pas un flux journalier',
                'cost_note': 'Coûts estimés si renseignés ; tokens normalisés selon fournisseur'}
    finally:
        connection.close()


def ccusage_usage(day, refresh=False):
    cached = read_json(STATE / 'ccusage.json')
    if (not refresh and cached.get('day') == day
            and time.time() - cached.get('observed_at', 0) < 300):
        return cached['data']
    executable = HOME / '.local/bin/ccusage'
    args = [str(executable), 'claude', 'daily', '--json', '--offline', '--breakdown',
            '--since', day.replace('-', ''), '--until', day.replace('-', ''),
            '--timezone', str(TZ), '--single-thread']
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('ccusage hors ligne a échoué, aucun coût remplacé par zéro')
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('ccusage : JSON invalide') from None
    save_json(STATE / 'ccusage.json', {'day': day, 'observed_at': time.time(), 'data': data})
    return data


def ledger_usage(refresh=False):
    import importlib.util
    path = HOME / '.claude/outils/observabilite/usage_ledger.py'
    spec = importlib.util.spec_from_file_location('local_usage_ledger', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if refresh:
        result = subprocess.run([sys.executable, str(path.parent / 'collect.py')],
                                capture_output=True, text=True, timeout=180)
        if result.returncode: raise RuntimeError('Import du registre en échec; détails dans le journal local')
    out = module.report(STATE / 'ledger.sqlite', dt.datetime.now(TZ).date().isoformat())
    odb = STATE / 'otel.sqlite'
    if odb.exists():
        db = sqlite3.connect('file:' + str(odb) + '?mode=ro', uri=True)
        try:
            out['otel'] = {'events': db.execute("SELECT COUNT(*) FROM events WHERE kind='log'").fetchone()[0],
                           'spans': db.execute("SELECT COUNT(*) FROM events WHERE kind='trace'").fetchone()[0],
                           'metric_series': db.execute('SELECT COUNT(*) FROM metrics').fetchone()[0]}
        finally: db.close()
    db = sqlite3.connect('file:' + str(STATE / 'ledger.sqlite') + '?mode=ro', uri=True)
    try:
        out['hermes_tracking_v2_started_at'] = db.execute('SELECT started_at FROM hermes_tracking_v2 WHERE id=1').fetchone()[0]
        out['hermes_deltas_v2'] = [dict(zip(('model','input','output','cache_read','cache_write','uncertain_intervals','counter_resets'),row))
          for row in db.execute('SELECT model,SUM(input_tokens),SUM(output_tokens),SUM(cache_read_tokens),SUM(cache_write_tokens),SUM(boundary_uncertain),SUM(counter_reset) FROM hermes_deltas_v2 WHERE day=? GROUP BY model',(out['day'],))]
    finally: db.close()
    return out


def build_report(refresh=False):
    now = dt.datetime.now(TZ)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    report = {'generated_at': now.isoformat(), 'day': now.strftime('%Y-%m-%d'),
              'timezone': str(TZ), 'warnings': [], 'no_combined_total': True}
    for name, callback in [('claude', lambda: ccusage_usage(report['day'], refresh)),
                           ('hermes', lambda: hermes_usage(since)),
                           ('proxy', lambda: load_proxy(HOME / '.hermes/proxy-usage.jsonl', since)),
                           ('quota', lambda: quota_usage(refresh)),
                           ('ledger', lambda: ledger_usage(refresh))]:
        try:
            report[name] = callback()
        except (RuntimeError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
            report[name] = None
            report['warnings'].append(name + ' : ' + str(exc))
    return report


def number(value):
    return f'{value:,.0f}'.replace(',', ' ')


def render_report(report):
    lines = ['Bilan tokens · ' + report['day'] + ' · Thaïlande']
    claude = report.get('claude')
    if claude is not None:
        total = claude.get('totals') or {}
        ratio = cache_ratio(total.get('inputTokens', 0), total.get('cacheReadTokens', 0),
                            total.get('cacheCreationTokens', 0))
        cache = '?' if ratio is None else f'{ratio:.1f} %'
        lines.append(f"Claude Code aujourd'hui : {number(total.get('totalTokens', 0))} tokens · cache {cache}")
        lines.append(f"Équivalent API Claude : {total.get('totalCost', 0):.2f} $ · pas une facture d'abonnement")
        for row in claude.get('daily', []):
            for model in row.get('modelBreakdowns', []):
                tokens = sum(model.get(k, 0) for k in ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheCreationTokens'))
                lines.append(f"  {model['modelName']} : {number(tokens)} tokens · {model.get('cost', 0):.2f} $")
    hermes = report.get('hermes')
    if hermes is not None:
        lines.append('Hermès : cumuls historiques par session/modèle, pas uniquement aujourd’hui')
        rows = sorted(hermes['models'], key=lambda row: (row['input'] or 0) + (row['output'] or 0), reverse=True)
        for model in rows:
            lines.append(f"  {model['model']} [{model['billing_provider'] or '?'}] : entrée {number(model['input'] or 0)} · sortie {number(model['output'] or 0)} · cache lu {number(model['cache_read'] or 0)}")
        tools = sorted(hermes['tools_today'].items(), key=lambda item: item[1], reverse=True)
        if tools:
            lines.append('Outils Hermès aujourd’hui (appels) : ' + ', '.join(f'{k} {v}' for k, v in tools[:6]))
    proxy = report.get('proxy')
    if proxy is not None and not proxy.get('unavailable'):
        lines.append(f"Proxy aujourd'hui : {proxy['calls']} appels · {proxy['errors']} erreurs")
        for name, model in sorted(proxy['models'].items(), key=lambda item: item[1]['equivalent_usd'], reverse=True):
            total = sum(model[k] for k in ('input', 'output', 'cache_read', 'cache_write'))
            ratio = cache_ratio(model['input'], model['cache_read'], model['cache_write'])
            cache = '?' if ratio is None else f'{ratio:.1f} %'
            lines.append(f"  {name} : {number(total)} tokens · cache {cache} · équivalent API {model['equivalent_usd']:.2f} $")
        if proxy['sources']:
            lines.append('Origines proxy : ' + ', '.join(f'{k} {v}' for k, v in sorted(proxy['sources'].items())))
    ledger = report.get('ledger')
    if ledger:
        coverage = ledger['coverage']
        lines.append(f"Registre dédupliqué : {coverage['claude_native_events']} événements Claude aujourd'hui; {coverage['claude_events_with_topic']} rattachés à un topic")
        lines.append('Hermès deltas mesurés depuis : ' + str(ledger.get('hermes_tracking_v2_started_at')) + ' ; avant ce relevé, seulement des cumuls')
        for row in ledger.get('hermes_deltas_v2', []):
            lines.append(f"  Delta {row['model']} : entrée {row['input']} · sortie {row['output']} · intervalles incertains {row['uncertain_intervals']} · compteurs remis à zéro {row['counter_resets']}")
        otel = ledger.get('otel', {})
        lines.append(f"Collecte native locale : {otel.get('events', 0)} événements · {otel.get('spans', 0)} spans · {otel.get('metric_series', 0)} séries; vues non additives")
    quota = report.get('quota')
    if quota:
        reset = dt.datetime.fromtimestamp(timestamp(quota['reset']), TZ).strftime('%H:%M')
        age = max(0, int((time.time() - quota['observed_at']) // 60))
        label = 'Dernière mesure Claude' if quota.get('stale') else 'Fenêtre Claude 5 h'
        lines.append(f"{label} : {quota['used']:.0f} % utilisés · remise à zéro {reset} · mesure native {age} min")
        if quota.get('stale'): lines.append('Quota actuel non vérifié : ' + quota.get('refresh_error', 'lecture indisponible'))
    lines.append('Sources recouvrantes : aucun total additionné. Abonnements ≠ coûts API équivalents.')
    lines.extend('ATTENTION : ' + warning for warning in report['warnings'])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--refresh', action='store_true', help='Recalculer ccusage et relire le quota natif')
    parser.add_argument('--check', action='store_true', help='Vérifier uniquement le quota et alerter au-dessus de 80 %%')
    args = parser.parse_args()
    if args.check:
        try:
            return check_quota()
        except Exception as exc:
            # Jamais de message Telegram pour une erreur de collecte.
            print(dt.datetime.now(TZ).isoformat(), type(exc).__name__, str(exc), file=sys.stderr)
            return 1
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(STATE / 'report.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        report = build_report(args.refresh)
        save_json(STATE / 'last-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_report(report))
    return 1 if report['warnings'] else 0


if __name__ == '__main__':
    sys.exit(main())
