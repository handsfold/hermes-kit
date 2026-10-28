#!/usr/bin/env python3
"""Boucle d'apprentissage a deux agents sur la FORME des reponses.

Agent 1, le proposeur : lit les signaux bruts captes par capter.py et en tire
des regles de redaction generalisables.
Agent 2, l'adversaire : essaie de refuter chaque proposition. Par defaut il
rejette. Une regle ne survit que si elle changerait concretement une reponse
future et qu'on peut verifier objectivement qu'elle a ete suivie.

Rien n'est injecte dans le prompt tant qu'une regle n'est pas ACTIVE :
soit deux confirmations independantes (deux JOURS distincts, pas deux occurrences
du meme agacement), soit un ordre explicite de USER.
C'est la meme discipline que `focus appris` : deux occurrences avant de graver.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

BASE = os.path.expanduser("~/.hermes/apprentissage")
SIGNAUX = os.path.join(BASE, "signaux.jsonl")
REGLES = os.path.join(BASE, "regles.json")
JOURNAL = os.path.join(BASE, "JOURNAL.md")
NEUTRE = "/tmp/hermes-apprentissage-run"

MAX_ACTIVES = 14          # au-dela, le prompt enfle et l'adherence tombe
SEUIL_ACTIF = 2           # confirmations independantes


def _noter_conso(d, modele):
    """Mesure (2026-10-27) : ces appels claude -p ne passent par aucun journal du proxy.
    On garde l'usage rendu par la CLI, un appel par ligne, sans aucun contenu."""
    try:
        u = d.get("usage") or {}
        ligne = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "appelant": os.environ.get("BOUCLE_APPELANT", "apprentissage"),
                 "modele": modele, "entree": u.get("input_tokens", 0), "sortie": u.get("output_tokens", 0),
                 "cache_lu": u.get("cache_read_input_tokens", 0), "cache_ecrit": u.get("cache_creation_input_tokens", 0),
                 "cout_usd": d.get("total_cost_usd"), "ms": d.get("duration_ms")}
        with open(os.path.expanduser("~/.hermes/logs/boucle-conso.jsonl"), "a") as f:
            f.write(json.dumps(ligne) + "\n")
    except Exception:
        pass


def llm(prompt, modele="sonnet", timeout=300):
    """Un tour, sans outil, sans contexte de projet. Sortie texte brute."""
    os.makedirs(NEUTRE, exist_ok=True)
    cmd = [
        "claude", "-p", "--output-format", "json", "--model", modele,
        "--max-turns", "1", "--setting-sources", "", "--strict-mcp-config",
        "--no-session-persistence",
    ]
    derniere = ""
    for essai in range(3):
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               timeout=timeout, cwd=NEUTRE)
        except subprocess.TimeoutExpired:
            derniere = "timeout"
            continue
        if r.returncode == 0:
            try:
                d = json.loads(r.stdout)
            except Exception:
                return r.stdout
            _noter_conso(d, modele)
            if d.get("is_error"):
                derniere = f'erreur api : {str(d.get("result"))[:300]}'
                continue
            return d.get("result") or d.get("content") or r.stdout
        # Deux appels rapproches se marchent parfois dessus : on laisse retomber.
        derniere = f'rc={r.returncode} err={r.stderr[:200]} out={r.stdout[:200]}'
        time.sleep(4 * (essai + 1))
    raise RuntimeError(f"claude -p a echoue 3 fois : {derniere}")


def json_de(texte):
    """Extrait le premier objet JSON d'une reponse de LLM."""
    texte = re.sub(r"^```(?:json)?|```$", "", texte.strip(), flags=re.M).strip()
    i, j = texte.find("{"), texte.rfind("}")
    if i < 0 or j <= i:
        raise ValueError(f"pas de JSON dans la reponse : {texte[:300]}")
    return json.loads(texte[i:j + 1])


def charger_regles():
    if os.path.exists(REGLES):
        return json.load(open(REGLES))
    return {"regles": [], "signaux_traites": [], "maj": None}


def signaux_neufs(traites, lot):
    if not os.path.exists(SIGNAUX):
        return []
    out = []
    vus = set(traites)
    for line in open(SIGNAUX, errors="replace"):
        try:
            s = json.loads(line)
        except Exception:
            continue
        if s["id"] not in vus:
            out.append(s)
    return out[:lot]


def rendu_regles(regles, statuts=("active", "candidate")):
    if not regles:
        return "(aucune regle enregistree pour l'instant)"
    return "\n".join(
        f'- [{r["id"]}] ({r["statut"]}, {r["confirmations"]} conf.) {r["regle"]}'
        for r in regles if r["statut"] in statuts
    ) or "(aucune)"


PROMPT_PROPOSEUR = """Tu analyses les reactions d'un utilisateur, USER, aux reponses de son agent Hermes.
Ton seul objet d'etude est la FORME et la PERTINENCE des reponses : longueur, structure,
ce qui est affiche, ce qui est tu, le fait de repondre ou non a la question posee.

Tu ne t'occupes JAMAIS du contenu metier d'une tache (un port, un chemin, une commande).
Ces faits-la vont dans la memoire de l'agent, pas ici.

REGLES DEJA ENREGISTREES (ne pas les redire) :
{regles}

SIGNAUX A ANALYSER :
{signaux}

Trois classes de signaux, et la troisieme se lit autrement :
- [negatif] USER reproche quelque chose. Le reproche est dans ses mots.
- [positif] USER valide. Cherche ce qui a marche, pas ce qui a rate.
- [relance] USER demande ou en est le travail (« ca en est ou ? », « alors ? »). Il ne
  reproche rien : le signal est qu'il a DU demander. Regarde la reponse d'Hermes juste
  avant et demande-toi ce qu'elle aurait du annoncer pour rendre la question inutile.
  Une regle valable ici porte sur ce qu'on annonce AVANT et PENDANT un travail long :
  l'etape en cours, la duree attendue, ce qui reste. Pas sur la longueur du texte.

Pour chaque signal, demande-toi : « quelle consigne de redaction, si l'agent l'avait
suivie, aurait evite cette reaction ? » Si la reponse n'est pas generalisable au-dela
de ce cas precis, ne propose rien pour ce signal. Le silence est une sortie valide.

Contraintes sur une regle :
- une seule phrase imperative, en francais, moins de 25 mots
- actionnable au moment de rediger : elle change ce que l'agent ecrit
- verifiable : un lecteur doit pouvoir dire si elle a ete suivie, sans deviner
- jamais de tiret cadratin ni demi-cadratin, jamais d'emoji

Reponds UNIQUEMENT par ce JSON, sans commentaire autour :
{{"propositions": [
  {{"regle": "...", "signaux": ["id1"], "confirme": null,
    "explicite": false, "justification": "citation courte de USER"}}
]}}

Champ "confirme" : mets l'identifiant d'une regle deja enregistree si le signal ne fait
que la confirmer, au lieu d'en creer une nouvelle. Sinon null.
Champ "explicite" : true seulement si USER a formule un ordre direct et sans ambiguite
sur la forme des reponses, du genre « ne fais plus X » ou « je veux que tu fasses Y »."""

PROMPT_ADVERSAIRE = """Tu es le contradicteur d'un systeme d'apprentissage. Ton travail n'est pas
d'approuver : c'est de refuter. Par defaut, tu rejettes.

Une regle de redaction proposee ne survit que si les quatre conditions sont reunies :
1. elle changerait concretement la redaction d'une reponse future
2. on peut verifier objectivement qu'elle a ete suivie, sans interpretation
3. elle n'est pas deja couverte par une regle enregistree
4. elle generalise au-dela du cas unique qui l'a produite

Rejette sans hesiter : les truismes (« sois clair »), les regles qui decrivent une
tache et pas une maniere de repondre, les regles qui contredisent une regle active,
et celles tirees d'un signal ambigu ou d'une phrase de USER sortie de son contexte.

REGLES ENREGISTREES :
{regles}

PROPOSITIONS A JUGER :
{propositions}

Reponds UNIQUEMENT par ce JSON :
{{"verdicts": [
  {{"index": 0, "verdict": "adopter|rejeter", "explicite_confirme": false,
    "raison": "une phrase", "reformulation": null, "confirme": null}}
]}}

"confirme" : si tu rejettes UNIQUEMENT parce que la proposition redit une regle deja
enregistree, mets ici son identifiant (ex. "r001"). Le signal comptera alors comme une
confirmation de cette regle au lieu d'etre perdu. Sinon null.

"index" est la position de la proposition dans la liste ci-dessus, a partir de 0.
"reformulation" : propose une phrase plus nette si tu adoptes mais que la formulation
est faible. Sinon null.
"explicite_confirme" : true seulement si tu confirmes que USER a donne un ordre direct,
ce qui rend la regle active immediatement au lieu d'attendre une seconde occurrence."""


def journaliser(lignes):
    entete = f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    with open(JOURNAL, "a") as f:
        f.write(entete + "\n".join(f"- {l}" for l in lignes) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lot", type=int, default=12)
    ap.add_argument("--modele", default="sonnet")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    etat = charger_regles()
    neufs = signaux_neufs(etat["signaux_traites"], a.lot)
    if not neufs:
        print(json.dumps({"traites": 0, "message": "aucun signal neuf"}))
        return 0

    # Le poids d'une proposition, c'est le nombre de JOURS distincts ou le meme
    # motif est apparu. Deux occurrences le meme jour peuvent n'etre qu'un seul
    # agacement repete ; deux jours differents sont deux confirmations.
    jours = {s["id"]: str(s.get("ts", ""))[:10] for s in neufs}

    vue = "\n".join(
        f'#{s["id"]} [{s["classe"]}/{",".join(s["motifs"])}]\n'
        f'  reponse d\'Hermes (fin, {s["taille_reponse"]} caracteres au total) : '
        f'{s["reponse_avant"][-450:]}\n'
        f'  reaction de USER : {s["user"][:400]}'
        for s in neufs
    )

    brut1 = llm(PROMPT_PROPOSEUR.format(regles=rendu_regles(etat["regles"]), signaux=vue),
                a.modele)
    props = json_de(brut1).get("propositions", [])

    adoptees, rejets = [], []
    if props:
        vue_p = "\n".join(
            f'{i}. {p["regle"]}\n   justification : {p.get("justification","")}\n'
            f'   confirme : {p.get("confirme")} | explicite annonce : {p.get("explicite")}'
            for i, p in enumerate(props)
        )
        brut2 = llm(PROMPT_ADVERSAIRE.format(regles=rendu_regles(etat["regles"]),
                                             propositions=vue_p), a.modele)
        verdicts = json_de(brut2).get("verdicts", [])

        for v in verdicts:
            i = v.get("index")
            if not isinstance(i, int) or i >= len(props):
                continue
            p = props[i]
            if v.get("verdict") != "adopter":
                # Un rejet « deja couvert par rXXX » reste une confirmation : sans ce
                # routage, une regle candidate ne pourrait jamais etre promue par un
                # signal que l'adversaire reclasse au lieu d'adopter.
                vise = next((r for r in etat["regles"]
                             if r["id"] == v.get("confirme")), None)
                if vise:
                    vise["confirmations"] += 1
                    vise["signaux"] = list(dict.fromkeys(
                        vise["signaux"] + p.get("signaux", [])))
                    if vise["confirmations"] >= SEUIL_ACTIF and vise["statut"] == "candidate":
                        vise["statut"] = "active"
                        adoptees.append(f'PROMUE ACTIVE : {vise["regle"]}')
                    else:
                        adoptees.append(
                            f'confirmee ({vise["confirmations"]}) : {vise["regle"]}')
                    continue
                rejets.append((p["regle"], v.get("raison", "")))
                continue
            texte = (v.get("reformulation") or p["regle"]).strip()
            texte = texte.replace("\u2014", " : ").replace("\u2013", "-")

            cible = None
            if p.get("confirme"):
                cible = next((r for r in etat["regles"] if r["id"] == p["confirme"]), None)
            if cible:
                cible["confirmations"] += 1
                cible["signaux"] = list(dict.fromkeys(cible["signaux"] + p.get("signaux", [])))
                if cible["confirmations"] >= SEUIL_ACTIF and cible["statut"] == "candidate":
                    cible["statut"] = "active"
                    adoptees.append(f'PROMUE ACTIVE : {cible["regle"]}')
                else:
                    adoptees.append(f'confirmee ({cible["confirmations"]}) : {cible["regle"]}')
                continue

            explicite = bool(p.get("explicite")) and bool(v.get("explicite_confirme"))
            sig = p.get("signaux", [])
            poids = len({jours.get(x) for x in sig if jours.get(x)}) or 1
            conf = SEUIL_ACTIF if explicite else min(poids, SEUIL_ACTIF)
            nums = [int(m.group(1)) for r in etat["regles"]
                    if (m := re.fullmatch(r"r(\d+)", r.get("id", "")))]
            nid = f'r{(max(nums) + 1) if nums else 1:03d}'
            etat["regles"].append({
                "id": nid,
                "regle": texte,
                "statut": "active" if conf >= SEUIL_ACTIF else "candidate",
                "confirmations": conf,
                "signaux": sig,
                "source": p.get("justification", "")[:200],
                "cree_le": datetime.now().strftime("%Y-%m-%d"),
            })
            if explicite:
                etiq = "ACTIVE (ordre explicite) : "
            elif conf >= SEUIL_ACTIF:
                etiq = f"ACTIVE ({poids} jours distincts) : "
            else:
                etiq = "candidate : "
            adoptees.append(etiq + texte)

    etat["signaux_traites"] = list(dict.fromkeys(
        etat["signaux_traites"] + [s["id"] for s in neufs]))[-2000:]
    etat["maj"] = datetime.now().isoformat(timespec="seconds")

    if not a.dry_run:
        json.dump(etat, open(REGLES, "w"), ensure_ascii=False, indent=2)
        journaliser(
            [f"{len(neufs)} signaux analyses, {len(props)} propositions, "
             f"{len(adoptees)} retenues, {len(rejets)} rejetees"]
            + adoptees + [f"rejet : {r} ({m})" for r, m in rejets])

    actives = [r for r in etat["regles"] if r["statut"] == "active"]
    print(json.dumps({
        "traites": len(neufs), "propositions": len(props),
        "adoptees": adoptees, "rejets": [r for r, _ in rejets],
        "actives": len(actives), "candidates": len(etat["regles"]) - len(actives),
    }, ensure_ascii=False, indent=2))
    if len(actives) > MAX_ACTIVES:
        print(f"ATTENTION : {len(actives)} regles actives, plafond {MAX_ACTIVES}. "
              "Les plus faibles doivent etre fusionnees ou retirees.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
