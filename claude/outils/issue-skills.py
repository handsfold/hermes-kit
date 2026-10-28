#!/usr/bin/env python3
"""Issue des skills : apres chaque chargement, USER a-t-il corrige, l'outil a-t-il echoue ?

Lit le journal du hook `~/.claude/hooks/journal-skills.py` (~/.claude/journal-skills/).
`--remplir N` reconstruit le meme journal pour les N derniers jours a partir des
transcripts (fichier retro.jsonl, ecrase a chaque fois) : la mesure a donc un
passe des le premier jour. Une session presente dans le journal du hook prime
sur sa version reconstruite.

Le drapeau `correction` est une heuristique (regex FR, EN, TH) : un signal a
trier, pas un verdict. Le temps 2 de la boucle le fera relire par un modele.

`--relire` fait relire chaque message signale par un modele (Sonnet via le proxy,
appelant `issue-skills-relire`) avec la reponse de l'agent qui le precede. Verdict
dans relu.jsonl (cle session + heure, jamais relu deux fois). Une correction ne compte
alors que si le modele l'attribue a la skill : la colonne `confirmees` le montre.

Usage : issue-skills.py [jours=30] [--remplir] [--relire] [--exemples SKILL]
"""
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/hooks"))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "journal_skills", Path.home() / ".claude/hooks/journal-skills.py")
js = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(js)

RACINE = js.RACINE
TRANSCRIPTS = Path.home() / ".claude/projects"
IGNORER = re.compile(r"^(<command-|<local-command|Caveat:|This session is being continued|"
                     r"\[Request interrupted|<task-notification)")


def texte_utilisateur(contenu):
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in contenu):
            return None
        return " ".join(b.get("text", "") for b in contenu
                        if isinstance(b, dict) and b.get("type") == "text")
    return None


def remplir(jours):
    limite = time.time() - jours * 86400
    sortie = []
    for f in TRANSCRIPTS.rglob("*.jsonl"):
        try:
            if f.stat().st_mtime < limite:
                continue
            brut = f.read_bytes()
        except OSError:
            continue
        if not any(m in brut for m in js_marqueurs()):
            continue
        actives, reste = [], 0
        for l in brut.splitlines():
            try:
                ligne = json.loads(l)
            except ValueError:
                continue
            if not isinstance(ligne, dict) or ligne.get("isMeta"):
                continue
            msg = ligne.get("message") or {}
            base = {"t": (ligne.get("timestamp") or "")[:19], "session": f.stem,
                    "cwd": ligne.get("cwd", ""), "source": "retro"}
            if ligne.get("type") == "assistant":
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        s = js.nom_skill(b.get("name"), b.get("input") or {})
                        if s:
                            if s not in actives:
                                actives.append(s)
                            reste = js.SUIVI
                            sortie.append({**base, "type": "charge", "skill": s})
            elif ligne.get("type") == "user" and actives:
                contenu = msg.get("content")
                if isinstance(contenu, list):
                    for b in contenu:
                        if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                            sortie.append({**base, "type": "echec", "skills": list(actives),
                                           "outil": "", "extrait": str(b.get("content"))[:200]})
                brut_txt = texte_utilisateur(contenu)
                if brut_txt is None or reste <= 0 or IGNORER.match(brut_txt.strip()):
                    continue
                texte = js.nettoyer(brut_txt)
                if not texte or js.MACHINE.match(texte):
                    continue
                reste -= 1
                sortie.append({**base, "type": "prompt", "skills": list(actives),
                               "rang": js.SUIVI - reste, "extrait": texte[:300],
                               "correction": bool(js.CORRECTION.search(texte))})
    RACINE.mkdir(parents=True, exist_ok=True)
    with open(RACINE / "retro.jsonl", "w", encoding="utf-8") as fo:
        for e in sortie:
            fo.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"retro.jsonl : {len(sortie)} evenements reconstruits sur {jours} jours\n")


RELU = RACINE / "relu.jsonl"
LLM_URL = "http://localhost:8000/anthropic/v1/messages"
CONSIGNE = (
    "Tu juges si un message de USER (utilisateur) corrige une erreur imputable a une SKILL "
    "(un mode d'emploi charge par l'agent avant de travailler).\n"
    "On te donne : la skill et sa description, la fin de la reponse de l'agent, puis le message de USER.\n"
    "Verdicts possibles :\n"
    "- skill : USER corrige un comportement que la skill aurait du empecher ou qu'elle a cause "
    "(mauvaise methode, regle de la skill ignoree ou fausse, mauvais outil prescrit).\n"
    "- agent : USER corrige l'agent, mais la skill n'y est pour rien (bug du code produit, "
    "malentendu, oubli sans lien avec la skill).\n"
    "- aucune : ce n'est pas une correction (demande nouvelle, precision, accord, info).\n"
    "Reponds en JSON seul : {\"verdict\": \"skill|agent|aucune\", \"raison\": \"<15 mots en francais>\"}"
)


def lire_relu():
    out = {}
    if RELU.exists():
        for l in RELU.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(l)
                out[(e["session"], e["t"], e["skill"])] = e
            except (ValueError, KeyError):
                pass
    return out


def description_skill(nom):
    for base in (Path.home() / ".claude/skills", Path.home() / ".hermes/skills", Path.home() / ".agents/skills"):
        for f in list(base.glob(f"{nom}/SKILL.md")) + list(base.glob(f"*/{nom}/SKILL.md")):
            m = re.search(r"^description:\s*(.+)$", f.read_text(encoding="utf-8", errors="ignore"), re.M)
            if m:
                return m.group(1).strip().strip("\"'")[:600]
    return "(description introuvable)"


def contexte(session, t, extrait):
    """Fin de la derniere reponse texte de l'agent avant le message, et le message complet."""
    for f in TRANSCRIPTS.rglob(f"{session}.jsonl"):
        dernier = ""
        for l in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                ligne = json.loads(l)
            except ValueError:
                continue
            if not isinstance(ligne, dict):
                continue
            msg = ligne.get("message") or {}
            if ligne.get("type") == "assistant":
                txt = " ".join(b.get("text", "") for b in msg.get("content") or []
                               if isinstance(b, dict) and b.get("type") == "text").strip()
                if txt:
                    dernier = txt
            elif ligne.get("type") == "user" and (ligne.get("timestamp") or "")[:19] == t:
                brut = texte_utilisateur(msg.get("content"))
                if brut and js.nettoyer(brut)[:60] == extrait[:60]:
                    return dernier[-1500:], js.nettoyer(brut)[:1500]
    return None, None


def appel(texte):
    import urllib.request
    corps = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 200, "system": CONSIGNE,
                        "metadata": {"user_id": "systemd:issue-skills-relire"},
                        "messages": [{"role": "user", "content": texte}]}).encode()
    req = urllib.request.Request(LLM_URL, corps, {"content-type": "application/json", "x-api-key": "x",
                                                  "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as r:
        rep = json.loads(r.read())
    txt = "".join(b.get("text", "") for b in rep.get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else {"verdict": "?", "raison": txt[:80]}


def relire(evts):
    deja = lire_relu()
    a_faire = [(e, s) for e in evts if e["type"] == "prompt" and e.get("correction")
               for s in e.get("skills", []) if (e["session"], e["t"], s) not in deja]
    print(f"relecture : {len(a_faire)} couples message-skill a juger ({len(deja)} deja juges)")
    with open(RELU, "a", encoding="utf-8") as fo:
        for e, s in a_faire:
            agent, message = contexte(e["session"], e["t"], e["extrait"])
            if message is None:
                agent, message = "(introuvable)", e["extrait"]
            texte = (f"SKILL : {s}\nDESCRIPTION : {description_skill(s)}\n\n"
                     f"FIN DE LA REPONSE DE L'AGENT :\n{agent}\n\nMESSAGE DE USER :\n{message}")
            try:
                v = appel(texte)
            except Exception as ex:  # panne du proxy : on garde pour la prochaine fois
                print(f"  echec {s} {e['t']} : {ex}")
                continue
            ligne = {"session": e["session"], "t": e["t"], "skill": s,
                     "verdict": v.get("verdict", "?"), "raison": v.get("raison", ""),
                     "extrait": e["extrait"][:200]}
            fo.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            fo.flush()
            print(f"  {ligne['verdict']:7s} {s} : {ligne['raison']}")
    print()


def js_marqueurs():
    return (b'"Skill"', b'skill_view', b'SKILL.md')


def charger(jours):
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    hook, retro = [], []
    for f in sorted(RACINE.glob("*.jsonl")):
        for l in f.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if e.get("t", "") >= limite:
                (retro if f.name == "retro.jsonl" else hook).append(e)
    vues = {e["session"] for e in hook}
    return hook + [e for e in retro if e["session"] not in vues]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jours = int(args[0]) if args and args[0].isdigit() else 30
    if "--remplir" in sys.argv:
        remplir(jours)
    evts = charger(jours)
    if "--relire" in sys.argv:
        relire(evts)
    relu = lire_relu()
    confirmees, jugees = defaultdict(set), defaultdict(set)
    charges = defaultdict(int)
    sessions = defaultdict(set)
    suivies, corrigees, echecs = defaultdict(set), defaultdict(set), defaultdict(int)
    exemples = defaultdict(list)
    for e in evts:
        if "type" not in e:   # ligne du journal sans type : ignoree, ne coupe plus l'outil
            continue
        if e["type"] == "charge":
            charges[e["skill"]] += 1
            sessions[e["skill"]].add(e["session"])
        for s in e.get("skills", []):
            if e["type"] == "prompt":
                suivies[s].add(e["session"])
                if e.get("correction"):
                    corrigees[s].add(e["session"])
                    exemples[s].append(e["extrait"])
                    v = relu.get((e["session"], e["t"], s))
                    if v:
                        jugees[s].add(e["session"])
                        if v["verdict"] == "skill":
                            confirmees[s].add(e["session"])
            elif e["type"] == "echec":
                echecs[s] += 1

    if "--exemples" in sys.argv:
        cible = sys.argv[sys.argv.index("--exemples") + 1]
        for x in exemples.get(cible, [])[-15:]:
            print("-", x[:200])
        return

    print(f"{len(evts)} evenements sur {jours} jours\n")
    print("Charg. · sessions · suivies · corrigees · confirmees · echecs/session · skill")
    for s in sorted(charges, key=charges.get, reverse=True)[:30]:
        n, suiv, corr = len(sessions[s]), len(suivies[s]), len(corrigees[s])
        taux = f"{100 * corr / suiv:3.0f} %" if suiv else "   -"
        conf = (f"{len(confirmees[s]):3d}/{len(jugees[s]):<3d}" if jugees[s] else "    -  ")
        print(f"{charges[s]:6d} · {n:8d} · {suiv:7d} · {corr:3d} ({taux}) · {conf:>10s} · "
              f"{echecs[s] / n:14.1f} · {s}")


if __name__ == "__main__":
    main()
