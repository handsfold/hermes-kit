#!/usr/bin/env python3
"""PostToolUse : previent quand le contexte de la session depasse le seuil.

Seuil 90k tokens (cache-bilan.py : les sessions chères ont 70-90k de contexte).
Un seul rappel par palier de 30 appels, pour ne pas devenir du bruit.
"""
import json, os, sys, tempfile
SEUIL = int(os.environ.get("CONTEXTE_LOURD_SEUIL", "90000"))
PAS = 30

def contexte(chemin):
    dernier = 0
    try:
        with open(chemin, "rb") as f:
            f.seek(0, 2); taille = f.tell(); f.seek(max(0, taille - 400000))
            for ligne in f.read().decode("utf-8", "ignore").splitlines():
                try: u = (json.loads(ligne).get("message") or {}).get("usage")
                except Exception: continue
                if u:
                    dernier = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                               + u.get("cache_creation_input_tokens", 0)) or dernier
    except OSError:
        return 0
    return dernier

def main():
    try: d = json.load(sys.stdin)
    except Exception: return
    chemin, sid = d.get("transcript_path"), d.get("session_id", "x")
    if os.environ.get("CONTEXTE_LOURD_DEBUG"):
        open(os.environ["CONTEXTE_LOURD_DEBUG"], "a").write(f"{sid} {chemin} {contexte(chemin) if chemin else None}\n")
    if not chemin: return
    n = contexte(chemin)
    if n < SEUIL: return
    etat = os.path.join(tempfile.gettempdir(), f"contexte-lourd-{sid}")
    try: compte = int(open(etat).read())
    except Exception: compte = 0
    open(etat, "w").write(str(compte + 1))
    if compte % PAS: return
    msg = (f"Contexte lourd : {n//1000}k tokens. Chaque appel relit tout. "
           "Groupe les commandes indépendantes, délègue les boucles longues à un sous-agent, "
           "et propose à USER un résumé de 10 lignes pour repartir en session neuve.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
main()
