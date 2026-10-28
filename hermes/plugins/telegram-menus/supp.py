"""Suppression de session a boutons (plugin telegram-menus, ex-retouche R16 du coeur).

Tout se fait au doigt, comme menu.py. Aucune commande a taper.

Flux : /supp affiche les sessions en boutons (1 par session) -> un tap ouvre
« Supprimer ? » (Supprimer / Annuler) -> un tap supprime.

Contrat des callback_data (Telegram limite a 64 octets) :
  supp:s:<i>    -> ouvre la confirmation pour la session n°i de la liste
  supp:del:<i>  -> supprime la session n°i (apres confirmation)
  supp:x        -> annule / referme

Suppression via le CLI canonique `hermes sessions delete <id> --yes` (reutilise
la logique testee : nettoie toutes les tables + l'index FTS).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .langue import t

logger = logging.getLogger(__name__)

NB_LISTE = 10
DELAI_SUPPRESSION_S = 60

# Mapping index -> {id, titre} du dernier /supp. Bot mono-utilisateur : un seul
# mapping global suffit.
_listing: List[Dict[str, str]] = []


def _hermes_home() -> Path:
    val = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(val).resolve() if val else (Path.home() / ".hermes").resolve()


def _fichier_state() -> Path:
    return _hermes_home() / "state.db"


def _age(ts: Optional[float]) -> str:
    if not ts:
        return "?"
    delta = max(0, int(time.time() - ts))
    if delta < 90:
        return t("age_now")
    if delta < 3600:
        return t("age_min", n=delta // 60)
    if delta < 86400:
        return t("age_h", n=delta // 3600)
    return t("age_d", n=delta // 86400)


def _lister_sessions(nombre: int = NB_LISTE) -> List[Dict[str, Any]]:
    chemin = _fichier_state()
    if not chemin.exists():
        return []
    requete = """
        SELECT s.id,
               COALESCE(NULLIF(s.title, ''), '') AS titre,
               COALESCE(s.last_activity_at,
                        (SELECT MAX(timestamp) FROM messages m WHERE m.session_id = s.id),
                        0) AS quand
        FROM sessions s
        WHERE s.source = 'telegram' AND COALESCE(s.archived, 0) = 0
        ORDER BY quand DESC
        LIMIT ?
    """
    try:
        con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, timeout=5)
        try:
            lignes = con.execute(requete, (nombre,)).fetchall()
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram-menus supp : lecture state.db impossible : %s", exc)
        return []
    return [{"id": r[0], "titre": r[1] or t("untitled"), "quand": r[2]} for r in lignes]


def _session_existe(session_id: str) -> bool:
    chemin = _fichier_state()
    if not chemin.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, timeout=5)
        try:
            row = con.execute(
                "SELECT 1 FROM sessions WHERE id = ? LIMIT 1", (session_id,)
            ).fetchone()
        finally:
            con.close()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def _supprimer(session_id: str) -> Dict[str, Any]:
    """Suppression bloquante via le CLI canonique. A appeler dans un thread."""
    env = dict(os.environ)
    env.setdefault("HERMES_HOME", str(_hermes_home()))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "hermes_cli.main",
             "sessions", "delete", session_id, "--yes"],
            capture_output=True, text=True,
            timeout=DELAI_SUPPRESSION_S, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "erreur": t("supp_timeout", s=DELAI_SUPPRESSION_S)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erreur": f"{type(exc).__name__}: {exc}"}
    if _session_existe(session_id):
        detail = (proc.stderr or proc.stdout or "").strip()[-200:]
        return {"ok": False, "erreur": detail or t("supp_still_there")}
    return {"ok": True}


# --- Textes + claviers ---

def texte_liste(sessions: List[Dict[str, Any]]) -> str:
    if not sessions:
        return t("supp_none")
    return t("supp_list")


def clavier_liste(sessions: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Un bouton par session : « n. titre · age » -> supp:s:<i>."""
    rows = []
    for i, s in enumerate(sessions):
        titre = str(s["titre"])[:40]
        label = f"{i + 1}. {titre} · {_age(s['quand'])}"
        rows.append([InlineKeyboardButton(label[:60], callback_data=f"supp:s:{i}")])
    if not rows:
        rows = [[InlineKeyboardButton(t("supp_none_button"), callback_data="supp:x")]]
    return InlineKeyboardMarkup(rows)


def clavier_confirme(i: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("supp_delete"), callback_data=f"supp:del:{i}"),
        InlineKeyboardButton(t("supp_cancel"), callback_data="supp:x"),
    ]])


def memoriser(sessions: List[Dict[str, Any]]) -> None:
    global _listing
    _listing = [{"id": s["id"], "titre": str(s["titre"])} for s in sessions]


def cible(i: int) -> Optional[Dict[str, str]]:
    try:
        return _listing[i]
    except (IndexError, TypeError):
        return None


def retirer(i: int) -> None:
    try:
        _listing.pop(i)
    except (IndexError, TypeError):
        pass
