#!/usr/bin/env python3
"""Relance de milieu de journee. Court, une seule question, ou rien du tout.

Le briefing du matin fait le constat. Celui-ci ne re-explique rien :
il relance quand la journee patine, et se tait quand elle roule.
Sortie vide quand il n'y a rien a dire : le cron --no-agent ne poste alors rien.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import focus as taches_mod  # noqa: E402
import journal  # noqa: E402
import coach_questions  # noqa: E402
import coach_qg  # noqa: E402

def _charger_coach():
    """focus-coach.py a un tiret : import par chemin."""
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "focus-coach.py")
    spec = importlib.util.spec_from_file_location("focus_coach", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    fc = _charger_coach()
    cap, actifs, pause, outils = fc.lire_focus()
    if not actifs:
        return 0  # focus.md vide : rien a dire
        return 0

    toutes, _ = taches_mod.charger()
    auj = date.today().isoformat()
    faites_auj = [t for t in toutes if t["fait_le"] == auj]
    ouvertes = [t for t in toutes if not t["faite"]]
    for i, t in enumerate(ouvertes):
        t["n"] = i + 1
        t["jours"] = taches_mod.age(t)

    depots = fc.scan_depots()
    noms = {n for n, _, _ in actifs}
    commits_auj = [n for n in noms if depots.get(n, {}).get("age_j", 99) < 0.6]
    # Une journee passee en conversation ne laisse aucun commit : le QG la voit.
    qg_auj = coach_qg.sujets(10)
    repondu_auj = any(e["type"] == "R" and e["jour"] == auj for e in journal.charger())

    # Journee qui roule : une tache cochee ou du code pousse, et une reponse donnee.
    if (faites_auj or commits_auj or qg_auj) and repondu_auj:
        return 0  # silence : la journee roule
        return 0

    L = []

    if faites_auj:
        L.append(f"**{len(faites_auj)} tache(s) cochee(s) aujourd'hui.** "
                 f"Derniere : {faites_auj[-1]['texte'][:60]}.")
    elif commits_auj:
        L.append(f"**Tu as pousse du code sur {', '.join(commits_auj)} aujourd'hui.** "
                 f"Aucune tache cochee.")
    elif qg_auj:
        gros = sorted(qg_auj, key=lambda s: -s["tours"])[0]
        L.append(f"**{len(qg_auj)} sujet(s) traite(s) depuis ce matin, "
                 f"surtout {gros['nom']}.** Aucune tache cochee.")
    else:
        L.append("**Rien de coche, rien de pousse depuis ce matin.**")

    if journal.sans_reponse() and not repondu_auj:
        q = journal.derniere_question()
        L.append(f"\nMa question de {q['heure']} est restee sans reponse :")
        L.append(q["texte"].strip())
        L.append("\nUne phrase suffit. Meme « je sais pas » est une reponse utile.")
        print("\n".join(L))
        return 0

    ctx = {
        "cap": cap, "actifs": actifs, "depots": depots, "ouvertes": ouvertes,
        "derive": [], "bouge": commits_auj, "faites_hier": faites_auj,
        "qg_sujets": qg_auj, "qg_hors": coach_qg.rattacher(qg_auj, noms)[1],
        "qg_rapports": coach_qg.rapports(10), "qg_non_lus": coach_qg.non_lus(),
    }
    _cle, question = coach_questions.choisir(ctx, journal.questions_recentes(6))
    L.append(f"\n**Question**\n{question}")
    L.append("\n_Reponds a ce message, je le note._")
    journal.ajouter("Q", question)
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
