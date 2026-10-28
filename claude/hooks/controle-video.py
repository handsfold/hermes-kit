#!/usr/bin/env python3
"""Teste le début de chaque Short dès qu'il sort du montage (ordre de USER, 2026-10-27).

PostToolUse sur Bash. Cherche les MP4 neufs de
personal-brand/contenu/videos/*/montage/ (racine du dossier montage seulement,
les copies d'envoi et les anciennes versions sont ignorées). Pour chacun :
  1. attention/controle_debut.py : 5 points mesurés sur les 5 premières secondes ;
  2. attention/predire.py video : rétention prédite à 1, 3 et 5 s.
Le résultat revient à l'agent dans le contexte, pour qu'il le dise à USER.
Un fichier déjà testé (même chemin, même date de modification) ne l'est pas 2 fois.
"""
import json, pathlib, subprocess, sys, time

PB = pathlib.Path.home() / "Bureau/Projets/business/contenu/personal-brand"
ATT = PB / "attention"
ETAT = pathlib.Path.home() / ".claude/hooks/config/controle-video.json"
RECENT = 900  # secondes : un MP4 plus vieux n'est pas « neuf »


def lancer(cmd, t=240):
    try:
        r = subprocess.run(cmd, cwd=ATT, capture_output=True, text=True, timeout=t)
        return r.stdout
    except Exception as e:
        return f"erreur : {e}"


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    try:
        etat = json.loads(ETAT.read_text())
    except Exception:
        etat = {}
    maintenant = time.time()
    neufs = []
    for f in PB.glob("contenu/videos/*/montage/*.mp4"):
        m = f.stat().st_mtime
        if maintenant - m < RECENT and maintenant - m > 3 and etat.get(str(f)) != m:
            neufs.append((f, m))
    if not neufs:
        return
    lignes = []
    for f, m in neufs[:3]:
        debut = lancer(["python3", "controle_debut.py", str(f)]).strip()
        pred = lancer(["python3", "predire.py", "video", str(f)])
        try:
            d = json.loads(pred[pred.find('{'):])
            p = d["points"]
            alertes = "; ".join(f"{a['seconde']} s « {a['mots']} » -{a['perte_pct']} % ({a['cause']})"
                                for a in d.get("alertes", [])[:3])
            pred = (f"rétention prédite : 1 s {p['1s']:.0%}, 3 s {p['3s']:.0%}, 5 s {p['5s']:.0%}, "
                    f"fin {p['fin']:.0%} · verdict {d['verdict']} (seuil 3 s {d['seuil_3s']:.0%}) · pertes : {alertes}")
        except Exception:
            pred = "prédiction illisible : " + pred[-300:]
        lignes.append(f"{f.name}\n{debut}\n{pred}")
        etat[str(f)] = m
    ETAT.parent.mkdir(parents=True, exist_ok=True)
    ETAT.write_text(json.dumps(etat, indent=1))
    texte = ("TEST AUTOMATIQUE DU DÉBUT (hook controle-video, à dire à USER avec la vidéo) :\n"
             + "\n\n".join(lignes)
             + "\nRepères réels TikTok : vidéo A 48 % restent à 5 s, v1 29 %.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": texte}}))


if __name__ == "__main__":
    main()
