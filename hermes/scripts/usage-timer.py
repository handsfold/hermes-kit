#!/usr/bin/env python3
"""Note dans ~/.hermes/proxy-usage.jsonl la consommation d'un appel `claude -p` fait HORS proxy
par un timer systemd (amorce-quota, dj-autocritique). Meme format que les lignes du proxy,
source `systemd`, champ `hors_proxy`. Le cockpit (bloc cout_routines) les attribue au timer.

Usage en tube :  claude -p ... --output-format json | usage-timer.py   (rend le texte de la reponse)
Usage en module : usage_timer.noter_json(sortie_json_du_cli)
L'unite est lue dans /proc/self/cgroup : hors systemd, rien n'est ecrit.
"""
import json
import os
import sys
from datetime import datetime, timezone

JOURNAL = os.path.expanduser("~/.hermes/proxy-usage.jsonl")


def unite():
    try:
        u = open("/proc/self/cgroup").read().strip().rsplit("/", 1)[-1]
    except OSError:
        return None
    return u[:-8] if u.endswith(".service") else None


def noter_json(brut, ms=None):
    """Ecrit la ligne d'usage d'une sortie `--output-format json` du CLI ; rend le texte de la reponse."""
    try:
        r = json.loads(brut)
    except (json.JSONDecodeError, TypeError):
        return brut or ""
    nom = unite()
    if nom:
        u = r.get("usage") or {}
        pm = {m: {"entree": v.get("inputTokens", 0), "sortie": v.get("outputTokens", 0),
                  "cache_lu": v.get("cacheReadInputTokens", 0), "cache_ecrit": v.get("cacheCreationInputTokens", 0),
                  "cout_usd": v.get("costUSD", 0)} for m, v in (r.get("modelUsage") or {}).items()}
        ligne = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                 "ms": ms if ms is not None else r.get("duration_ms"),
                 "source": "systemd", "appelant": nom, "hors_proxy": True, "topic": None,
                 "session": r.get("session_id"), "modele": next(iter(pm), None),
                 "entree": u.get("input_tokens", 0), "sortie": u.get("output_tokens", 0),
                 "cache_lu": u.get("cache_read_input_tokens", 0), "cache_ecrit": u.get("cache_creation_input_tokens", 0),
                 "cout_usd": r.get("total_cost_usd", 0), "par_modele": pm,
                 "statut": "erreur" if r.get("is_error") else "ok"}
        try:
            with open(JOURNAL, "a") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"usage-timer : ecriture impossible ({e})", file=sys.stderr)
    return r.get("result") or ""


if __name__ == "__main__":
    print(noter_json(sys.stdin.read()))
