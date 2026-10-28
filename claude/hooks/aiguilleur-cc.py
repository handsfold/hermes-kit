#!/usr/bin/python3
"""Hook UserPromptSubmit : l'aiguilleur de skills, cote Claude Code.

Pourquoi (2026-10-25) : laisse a lui-meme, le modele charge la bonne skill
environ 1 fois sur 2 (112 sur 211 declenchements sur 30 jours). Hermes demande
deja a Sonnet, avant chaque tour, quelle skill le message appelle (plugin
aiguilleur). Ce hook fait la meme chose dans Claude Code : il envoie le message
et le catalogue des skills Claude au proxy local (Sonnet sans outils), puis
ajoute le SKILL.md choisi au contexte du tour.

Regles :
  - rien dans une session lancee par le proxy (PROXY_TOUR ou CLAUDE_TIMEOUT_MS) :
    c'est un tour Hermes, deja aiguille par le plugin ;
  - le routeur lit aussi les 300 derniers caracteres de la reponse precedente :
    un « oui » se comprend alors (banc du 2026-10-25 : 7 sur 13 au lieu de 2 sur 13) ;
  - rien pour une commande /..., ni pour un message de moins de 3 mots sans reponse precedente ;
  - rien si la skill est deja chargee dans le transcript ;
  - proxy muet apres 15 s : rien (skills-forcees.py garde les mots-cles).
Ne bloque jamais. Logique dans hermes-kit (install/hk-aiguilleur.py).
Journal : ~/.claude/logs/aiguilleur-cc.jsonl, lu par ~/.claude/outils/aiguilleur-bilan.py.
"""
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HOME = Path.home()
SOURCES = [HOME / "Bureau/Projets/perso/agent/hermes-kit/install/hk-aiguilleur.py",
           HOME / ".hermes/scripts/hk-aiguilleur.py"]
JOURNAL = HOME / ".claude/logs/aiguilleur-cc.jsonl"
CACHE = HOME / ".cache/hermes-kit/aiguilleur/cc-choix.json"
REGLAGES = {"modele": "claude-sonnet-5-5-notools", "timeout": 15, "min_mots": 3, "min_mots_contexte": 1,
            "max_chars": 8500, "cache_max": 500}


def module():
    src = next(s for s in SOURCES if s.is_file())
    spec = importlib.util.spec_from_file_location("hk_aiguilleur", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def deja_chargees(transcript, noms):
    """Skills du choix deja presentes dans la session (outil Skill, lecture, ce hook)."""
    try:
        t = Path(transcript).read_text(errors="ignore")
    except Exception:
        return set()
    return {n for n in noms
            if f"{n}/SKILL.md" in t or f'"skill":"{n}"' in t or f'"skill": "{n}"' in t
            or f"the skill '{n}' matches" in t}


def dernier_assistant(transcript):
    """Last text written by the assistant in the session (context for a short message)."""
    try:
        lignes = Path(transcript).read_text(errors="ignore").splitlines()[-400:]
    except Exception:
        return ""
    for l in reversed(lignes):
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        contenu = (d.get("message") or {}).get("content")
        textes = [b.get("text", "") for b in contenu if isinstance(b, dict) and b.get("type") == "text"] \
            if isinstance(contenu, list) else []
        if "".join(textes).strip():
            return "\n".join(textes)
    return ""


def lire_cache():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def ecrire_cache(cache):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        if len(cache) > REGLAGES["cache_max"]:
            cache = dict(list(cache.items())[-REGLAGES["cache_max"]:])
        CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    except OSError:
        pass


def journal(ligne):
    try:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main():
    if os.environ.get("PROXY_TOUR") or os.environ.get("CLAUDE_TIMEOUT_MS"):
        return
    try:
        entree = json.load(sys.stdin)
    except ValueError:
        return
    t0 = time.time()
    ligne = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": entree.get("session_id", ""),
             "cwd": entree.get("cwd", "")}
    try:
        mod = module()
        texte = mod.nettoyer(entree.get("prompt") or "")
        mots = len(texte.split())
        ligne.update(mots=mots, message=texte[:120])
        if not texte or texte.startswith("/"):
            return
        precedent = dernier_assistant(entree.get("transcript_path") or "")
        precedent = " ".join(precedent.split())[-getattr(mod, "CONTEXTE_CHARS", 300):]
        ligne["contexte"] = bool(precedent)
        if mots < (REGLAGES["min_mots_contexte"] if precedent else REGLAGES["min_mots"]):
            ligne.update(voie="court", choix=[])
            return
        # Skills que l'outil Skill de Claude Code connait : celles du projet, puis les globales.
        cwd = Path(entree.get("cwd") or os.getcwd())
        mod.RACINES = [cwd / ".claude" / "skills", HOME / ".claude" / "skills"]
        mod.desactivees = lambda: set()
        idx = type("Idx", (), {})()
        idx.skills = mod.skills()
        systeme = mod.CONSIGNE_LLM + mod.catalogue(idx)
        cle = precedent + "\n" + texte[:600]
        k = hashlib.sha1((hashlib.sha1(systeme.encode()).hexdigest() + cle).encode()).hexdigest()[:20]
        cache = lire_cache()
        if k in cache:
            choix, ligne["voie"] = cache[k], "cache"
        else:
            mod.LLM_MODELE = REGLAGES["modele"]
            mod.LLM_APPELANT = "hk-aiguilleur-cc"
            try:
                txt, _u, _s = mod.appel_llm(systeme, mod.requete(texte, precedent), max_tokens=200,
                                            timeout=REGLAGES["timeout"])
            except Exception as exc:
                ligne.update(voie="muet", choix=[], erreur=f"{type(exc).__name__}: {exc}"[:160])
                return
            choix = mod.lire_choix(txt, 1, idx.skills)[0]
            ligne["voie"] = "llm"
            cache[k] = choix
            ecrire_cache(cache)
        vu = deja_chargees(entree.get("transcript_path") or "", choix)
        neufs = [n for n in choix if n not in vu]
        ligne.update(choix=choix, deja=sorted(vu))
        if not neufs:
            return
        inj = mod.injection(idx, {"choix": neufs, "voie": ligne["voie"]},
                            conf={**mod.config(), "max_chars": REGLAGES["max_chars"]})
        inj = inj.replace("no skill_view needed", "no Skill tool call needed")
        inj = inj.replace("skill_view(name='", "the Skill tool or Read ('")
        ligne["chars"] = len(inj)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": inj}}, ensure_ascii=False))
    except Exception as exc:
        ligne.update(voie="panne", erreur=f"{type(exc).__name__}: {exc}"[:160])
    finally:
        if "voie" in ligne:
            ligne["ms"] = int((time.time() - t0) * 1000)
            journal(ligne)


if __name__ == "__main__":
    main()
