"""Skill router, Hermes side: the skill a message needs is chosen BEFORE the model.

Why (2026-10-25): left to choose, the model loads the right skill about once in
two. On 1 017 labelled messages, Sonnet reading the whole catalogue picked 208
right against 96 for the keywords of declencheurs.json (fiche
contexte/projets/handsfold-skills.md). This hook asks Sonnet through the local
proxy, then appends the chosen SKILL.md to the user message of the turn.

Rules:
  - nothing for a message under min_mots words: a skill injected on an earlier
    turn is still in the history (the injection is replayed every turn);
  - nothing for a slash command, a subagent, or a platform outside the list;
  - a skill already in the last 30 messages (injected or skill_view) is not
    injected again;
  - proxy silent after `timeout` seconds: keywords of declencheurs.json.

Logic lives in hermes-kit (install/hk-aiguilleur.py, path in HK_AIGUILLEUR),
settings in ~/.hermes/aiguilleur.json, one line per turn in
~/.hermes/logs/aiguilleur.jsonl (read by ~/.claude/outils/aiguilleur-bilan.py).
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger("hermes.plugins.aiguilleur")

HERMES = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
# The author's live copy first, then the one hermes-kit installs in HERMES_HOME/scripts.
_SOURCES = [os.environ.get("HK_AIGUILLEUR", ""),
            str(Path.home() / "Bureau/Projets/perso/agent/hermes-kit/install/hk-aiguilleur.py"),
            str(HERMES / "scripts" / "hk-aiguilleur.py")]
SOURCE = next((Path(s) for s in _SOURCES if s and Path(s).is_file()), Path(_SOURCES[-1]))
REGLAGES = HERMES / "aiguilleur.json"
JOURNAL = HERMES / "logs" / "aiguilleur.jsonl"
DEFAUT = {"actif": True, "timeout": 15, "min_mots": 3,
          # With the end of the previous reply as context, a bare "yes" can be routed
          # (bench of 43 short messages, 2026-10-25: right skill 7/13 instead of 2/13).
          "contexte": True, "min_mots_contexte": 1, "plateformes": ["telegram", "api_server"],
          "fenetre": 30, "index_ttl": 600, "cache_max": 500, "max_chars": 8500,
          # -notools: the proxy runs claude -p without tools, CLAUDE.md nor hooks.
          # Bench of 20 calls (2026-10-25): same choices, cache written 540
          # tokens instead of 24 900, 0.003 $ instead of 0.065 $, 3.9 s instead of 5.1 s.
          "modele": "claude-sonnet-5-5-notools"}

_verrou = threading.Lock()
_etat = {"mod": None, "idx": None, "t_idx": 0.0, "systeme": "", "cache": {}}


def reglages():
    r = dict(DEFAUT)
    try:
        r.update(json.loads(REGLAGES.read_text()))
    except (OSError, ValueError):
        pass
    return r


def _module():
    if _etat["mod"] is None:
        spec = importlib.util.spec_from_file_location("hk_aiguilleur", SOURCE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _etat["mod"] = mod
    return _etat["mod"]


def _index(ttl):
    """Index of installed skills, rebuilt every ttl seconds so a new skill joins on its own."""
    with _verrou:
        if _etat["idx"] is None or time.time() - _etat["t_idx"] > ttl:
            mod = _module()
            idx = mod.Index()
            _etat.update(idx=idx, t_idx=time.time(), systeme=mod.CONSIGNE_LLM + mod.catalogue(idx), cache={})
        return _etat["mod"], _etat["idx"], _etat["systeme"]


def _texte(m):
    """(text of a message, names passed to skill_view in its tool calls)."""
    if not isinstance(m, dict):
        return "", []
    parts, vues = [], []
    for cle in ("content", "api_content"):
        c = m.get(cle)
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            parts += [b.get("text", "") for b in c if isinstance(b, dict)]
    for tc in m.get("tool_calls") or []:
        f = (tc or {}).get("function") or {}
        if f.get("name") == "skill_view":
            a = f.get("arguments")
            try:
                a = json.loads(a) if isinstance(a, str) else (a or {})
                vues.append(str(a.get("name", "")))
            except (ValueError, AttributeError):
                pass
    return "\n".join(parts), vues


def dernier_assistant(historique):
    """Text of the last assistant reply in the history (context for a short message)."""
    for m in reversed(historique or []):
        if isinstance(m, dict) and m.get("role") == "assistant":
            t, _v = _texte(m)
            if t.strip():
                return t
    return ""


def deja_vues(historique, fenetre):
    """Skills already in context: injected by this hook or loaded by skill_view."""
    vu = set()
    for m in (historique or [])[-fenetre:]:
        t, vues = _texte(m)
        vu.update(re.findall(r"\[Skill router: the skill '([^']+)'", t))
        vu.update(vues)
    return vu


def _journal(ligne):
    try:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except OSError:
        pass


def router(session_id="", user_message=None, conversation_history=None, platform="",
           parent_session_id="", **_kw):
    r = reglages()
    if not r["actif"] or parent_session_id or (platform or "") not in r["plateformes"]:
        return None
    t0 = time.time()
    ligne = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": session_id, "plateforme": platform}
    try:
        mod, idx, systeme = _index(r["index_ttl"])
        texte = mod.nettoyer(user_message or "")
        mots = len(texte.split())
        ligne.update(mots=mots, message=texte[:120])
        if not texte or texte.startswith("/"):
            return None
        precedent = dernier_assistant(conversation_history) if r["contexte"] else ""
        precedent = " ".join(precedent.split())[-getattr(mod, "CONTEXTE_CHARS", 300):]
        ligne["contexte"] = bool(precedent)
        if mots < (r["min_mots_contexte"] if precedent else r["min_mots"]):
            ligne.update(voie="court", choix=[])
            return None
        cle = (precedent, texte[:600])
        choix = _etat["cache"].get(cle)
        if choix is not None:
            ligne["voie"] = "cache"
        else:
            try:
                mod.LLM_MODELE = r["modele"]
                txt, usage, _s = mod.appel_llm(systeme, mod.requete(texte, precedent), max_tokens=200, timeout=r["timeout"])
                choix = mod.lire_choix(txt, 1, idx.skills)[0]
                ligne["voie"] = "llm"
                if len(_etat["cache"]) < r["cache_max"]:
                    _etat["cache"][cle] = choix
            except Exception as exc:
                choix = mod.choisir(idx, texte).get("choix", [])
                ligne.update(voie="repli", erreur=f"{type(exc).__name__}: {exc}"[:160])
        vu = deja_vues(conversation_history, r["fenetre"])
        neufs = [n for n in choix if n not in vu]
        ligne.update(choix=choix, deja=sorted(set(choix) & vu))
        if not neufs:
            return None
        texte_inj = mod.injection(idx, {"choix": neufs, "voie": ligne["voie"]}, conf={**mod.config(), "max_chars": r["max_chars"]})
        ligne["chars"] = len(texte_inj)
        return {"context": texte_inj}
    except Exception as exc:
        ligne.update(voie="panne", erreur=f"{type(exc).__name__}: {exc}"[:160])
        logger.warning("aiguilleur : %s", exc)
        return None
    finally:
        if "voie" in ligne:
            ligne["ms"] = int((time.time() - t0) * 1000)
            _journal(ligne)


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", router)
    logger.info("aiguilleur : actif (source %s)", SOURCE)
