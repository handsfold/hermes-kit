"""Plugin Hermes « mode-objectif » (2026-10-11).

Ajoute au /menu Telegram une ligne « Mode objectif ». Un toucher ouvre l'etat
du topic courant et un interrupteur. L'interrupteur ajoute ou retire l'id du
topic dans ~/.hermes/topics-relais.json, relu par le proxy a chaque requete :
effet immediat, sans redemarrage.

Mode objectif = relais d'outils (claude-proxy/tool-relay.js) : Claude pilote
les outils d'Hermes (kanban, todo, delegate_task, cron) au lieu des siens.
Demande de USER : un bouton simple, pas une commande ni un fichier a editer.

Branchement : on enveloppe telegram_menu.clavier_racine (l'adaptateur le lit
par attribut de module a chaque appel), ou, si le coeur n'a plus ce module
(branche poste/local-sans-menus), on passe par ``ajouter_rangee_racine`` du plugin
telegram-menus (point d'extension public). On ajoute un CallbackQueryHandler
borne au motif ^mo:, pour ne pas avaler les boutons du coeur.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE = Path.home() / ".hermes/topics-relais.json"
JOURNAL = Path.home() / ".hermes/mode-objectif.log"

# Textes visibles (anglais par defaut). La langue est celle de telegram-menus,
# lue par son point d'extension ; sans lui, on lit le meme fichier d'etat.
EN = {
    "mo_root_button": "Goal mode · tool relay",
    "mo_state_on": "ON",
    "mo_state_off": "off",
    "mo_body": (
        "Goal mode in this topic: {etat}.\n\n"
        "On: Claude drives Hermes tools (kanban, todo, sub-agents, cron). "
        "Useful when you set a goal to chain.\n"
        "It loses its Claude Code safeguards (hooks), its CLAUDE.md and its skills. "
        "Only the block on mail and LINE without your approval stays.\n\n"
        "Takes effect at once, no restart."),
    "mo_turn_off": "Turn off goal mode",
    "mo_turn_on": "Turn on goal mode",
    "mo_back": "< Back",
    "mo_toast_on": "Goal mode on.",
    "mo_toast_off": "Goal mode off.",
    "mo_not_authorized": "Not authorized.",
    "mo_only_topic": "Only inside a topic.",
}
FR = {
    "mo_root_button": "Mode objectif · relais d'outils",
    "mo_state_on": "ACTIVE",
    "mo_state_off": "coupe",
    "mo_body": (
        "Mode objectif dans ce topic : {etat}.\n\n"
        "Active : Claude pilote les outils d'Hermes (kanban, todo, sous-agents, cron). "
        "Utile quand tu fixes un objectif a enchainer.\n"
        "Il perd ses garde-fous Claude Code (hooks), son CLAUDE.md et ses skills. "
        "Seul le blocage des mails et LINE sans ton accord reste.\n\n"
        "Effet immediat, aucun redemarrage."),
    "mo_turn_off": "Couper le mode objectif",
    "mo_turn_on": "Activer le mode objectif",
    "mo_back": "< Retour",
    "mo_toast_on": "Mode objectif active.",
    "mo_toast_off": "Mode objectif coupe.",
    "mo_not_authorized": "Non autorise.",
    "mo_only_topic": "Seulement dans un topic.",
}


def _point_extension():
    """Le module telegram-menus charge (celui qui porte POINT_EXTENSION), ou None."""
    for mod in list(sys.modules.values()):
        d = getattr(mod, "__dict__", {})
        if d.get("POINT_EXTENSION") == "telegram-menus" and callable(d.get("ajouter_rangee_racine")):
            return d
    return None


def _langue() -> str:
    ext = _point_extension()
    if ext and callable(ext.get("langue_courante")):
        return ext["langue_courante"]()
    chemin = os.environ.get("TELEGRAM_VJ_ETAT") or str(Path.home() / ".hermes/telegram-menus.json")
    try:
        val = json.loads(Path(chemin).read_text()).get("langue")
    except Exception:  # noqa: BLE001
        return "en"
    return val if val in ("en", "fr") else "en"


def t(cle: str, **kw) -> str:
    texte = (FR if _langue() == "fr" else EN).get(cle) or EN.get(cle, cle)
    return texte.format(**kw) if kw else texte


def lire() -> list[str]:
    try:
        d = json.loads(TABLE.read_text())
        return [str(x) for x in d] if isinstance(d, list) else []
    except Exception:  # noqa: BLE001
        return []


def ecrire(ids: list[str]) -> None:
    tmp = TABLE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(set(ids), key=int)))
    tmp.replace(TABLE)


def basculer(topic: str, on: bool) -> list[str]:
    ids = [i for i in lire() if i != topic]
    if on:
        ids.append(topic)
    ecrire(ids)
    with JOURNAL.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} topic {topic} -> {'on' if on else 'off'}\n")
    return ids


def texte(topic: str, actif: bool) -> str:
    return t("mo_body", etat=t("mo_state_on" if actif else "mo_state_off"))


def clavier(actif: bool):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    bouton = (t("mo_turn_off"), "mo:off") if actif else (t("mo_turn_on"), "mo:on")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(bouton[0], callback_data=bouton[1])],
        [InlineKeyboardButton(t("mo_back"), callback_data="menu:root")],
    ])


def _bouton_racine():
    from telegram import InlineKeyboardButton
    return [InlineKeyboardButton(t("mo_root_button"), callback_data="mo:v")]


def _brancher_telegram_vj() -> bool:
    """Passe par le point d'extension public du plugin telegram-menus, s'il est charge."""
    d = _point_extension()
    if d is None:
        return False
    d["ajouter_rangee_racine"]("mode-objectif", _bouton_racine)
    if callable(d.get("ajouter_textes")):
        d["ajouter_textes"](EN, FR)
    return True


def _envelopper_menu() -> None:
    from plugins.platforms.telegram import telegram_menu as tm
    if getattr(tm.clavier_racine, "_mode_objectif", False):
        return
    origine = tm.clavier_racine

    def clavier_racine(*a, **kw):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        m = origine(*a, **kw)
        rows = [list(r) for r in m.inline_keyboard]
        rows.append(_bouton_racine())
        return InlineKeyboardMarkup(rows)

    clavier_racine._mode_objectif = True
    tm.clavier_racine = clavier_racine


async def _toucher(adapter, update, context) -> None:
    q = update.callback_query
    action = (q.data or "")[3:]
    msg = q.message
    u = q.from_user
    uid = str(getattr(u, "id", ""))
    topic = str(getattr(msg, "message_thread_id", "") or "")
    try:
        ok = adapter._is_callback_user_authorized(
            uid, chat_id=str(msg.chat.id), chat_type=str(getattr(msg.chat, "type", "")),
            thread_id=topic, user_name=getattr(u, "full_name", None))
    except Exception as e:  # noqa: BLE001
        logger.warning("[mode-objectif] controle d'acces : %s", e)
        ok = False
    if not ok:
        await q.answer(text=t("mo_not_authorized")); return
    if not topic:
        await q.answer(text=t("mo_only_topic")); return
    if action in ("on", "off"):
        basculer(topic, action == "on")
        await q.answer(text=t("mo_toast_on" if action == "on" else "mo_toast_off"))
        logger.info("[mode-objectif] topic %s -> %s", topic, action)
    else:
        await q.answer()
    actif = topic in lire()
    try:
        await q.edit_message_text(texte(topic, actif), reply_markup=clavier(actif))
    except Exception as e:  # noqa: BLE001
        if "not modified" not in str(e).lower():
            logger.warning("[mode-objectif] redessin : %s", e)


def register(ctx) -> None:
    def fabrique(app, adapter):
        from telegram.ext import CallbackQueryHandler
        # Menu du coeur s'il existe encore (branchement d'origine), et menu
        # de telegram-menus s'il est charge : deux claviers distincts, pas de doublon.
        try:
            _envelopper_menu()
        except ImportError:
            logger.info("[mode-objectif] telegram_menu du coeur absent")
        except Exception as e:  # noqa: BLE001
            logger.error("[mode-objectif] menu non enveloppe : %s", e)
        try:
            if not _brancher_telegram_vj():
                logger.info("[mode-objectif] telegram-menus non charge")
        except Exception as e:  # noqa: BLE001
            logger.error("[mode-objectif] telegram-menus non branche : %s", e)
        if app is not None:
            async def cb(update, context):
                try:
                    await _toucher(adapter, update, context)
                except Exception as e:  # noqa: BLE001
                    logger.error("[mode-objectif] toucher : %s", e, exc_info=True)
            app.add_handler(CallbackQueryHandler(cb, pattern=r"^mo:"))
    ctx.register_telegram_handler(fabrique)
