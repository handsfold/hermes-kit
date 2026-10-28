"""Extrait les crons generiques de ~/.hermes/cron/jobs.json en exemples.

Seuls les jobs de la liste NOMS sortent, sans leur etat d'execution.
Les topics de livraison deviennent des trous (__QG_THREAD__, __COACH_THREAD__).

Un cron n'est actif a l'installation que s'il sert des le premier jour.
Les autres (coach, apprentissage, retro, revues) lisent du vecu que
l'utilisateur n'a pas encore : ils sont poses desactives, a allumer avec
`hermes cron resume <id>` quand focus.md et une semaine de sessions existent.
Les crons lies a un service hors kit (Open WebUI) ne sortent pas.
"""

import json
from pathlib import Path

NOMS = {
    # actifs des l'installation : ils surveillent l'outil lui-meme
    "Veilleur de pannes": True,
    "QG resume des topics": True,
    # poses desactives : ils ont besoin de focus.md ou d'un historique
    "Coach quotidien focus": False,
    "Coach relance midi": False,
    "Apprentissage quotidien": False,
    "Retro agent hebdo": False,
    "Revue du socle - lecons mures": False,
    "Chasse au levier mensuelle": False,
    "Veille IA et GitHub": False,
}
CHAMPS = [
    "name",
    "prompt",
    "schedule",
    "schedule_display",
    "repeat",
    "deliver",
    "model",
    "provider",
    "base_url",
    "enabled_toolsets",
    "skills",
    "skill",
    "script",
    "workdir",
    "context_from",
]
TOPICS = {"2923": "__QG_THREAD__", "635": "__COACH_THREAD__"}

src = Path.home() / ".hermes/cron/jobs.json"
d = json.loads(src.read_text())
jobs = d.get("jobs", d) if isinstance(d, dict) else d
par_nom = {j.get("name"): j for j in jobs}
sortie = []
for nom, actif in NOMS.items():
    j = par_nom.get(nom)
    if not j:
        print("cron absent :", nom)
        continue
    e = {c: j[c] for c in CHAMPS if c in j and j[c] not in (None, "", [], {})}
    e["enabled"] = actif
    liv = str(e.get("deliver", ""))
    if liv.startswith("telegram:"):
        parts = liv.split(":")
        if len(parts) == 3:
            parts[2] = TOPICS.get(parts[2], parts[2])
        e["deliver"] = ":".join(parts)
    sortie.append(e)
dst = Path("hermes/cron/exemples.json")
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps({"jobs": sortie}, indent=2, ensure_ascii=False) + "\n")
print("crons :", len(sortie), "exemples")
