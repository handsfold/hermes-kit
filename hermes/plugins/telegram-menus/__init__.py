"""Plugin telegram-menus : /menu et /supp a boutons sur Telegram.

Remplace les retouches R14, R16, R18 et R19 du coeur, ainsi que les plugins
menu-cmd et session-supp (a desactiver : ils declarent les memes commandes).

- Telegram : une factory ajoute, en groupe -1 (avant le coeur, groupes 0 et 99),
  les 2 commandes et un CallbackQueryHandler borne par ``pattern=``. Chaque
  handler leve ApplicationHandlerStop : le coeur ne retraite pas l'update.
- Hors Telegram : ``register_command`` donne un repli texte, et fait entrer
  les 2 commandes dans la liste native de Telegram.
- Ordre de la liste native : ``_tete_de_liste`` place menu, supp en tete,
  dans cet ordre, sans toucher a config.yaml (voir la fonction).

Point d'extension public : ``ajouter_rangee_racine(nom, fabrique)``.
Un autre plugin ajoute une rangee de boutons au menu racine de /menu.
``fabrique()`` est appelee a chaque affichage et rend une liste de
``InlineKeyboardButton`` (ou None). Meme ``nom`` : la rangee est remplacee.
Les callbacks de ces boutons restent a la charge du plugin appelant, avec son
propre ``CallbackQueryHandler`` borne par ``pattern=`` (hors ``menu:`` et ``supp:``). Textes : ``langue.py`` (en par defaut, fr en option, bouton « Language / Langue »
a la racine de /menu). Un autre plugin y ajoute ses textes avec
``ajouter_textes(en, fr)`` et lit la langue avec ``langue_courante()``.
Le module porte ``POINT_EXTENSION = "telegram-menus"`` : un plugin le
retrouve en cherchant dans ``sys.modules`` un module qui porte cette marque.
"""
from __future__ import annotations

import logging

from . import handlers as h
from . import langue
from . import menu as tm
from . import supp as ts
from .langue import t

logger = logging.getLogger(__name__)

GROUPE = -1
POINT_EXTENSION = "telegram-menus"
ajouter_rangee_racine = tm.ajouter_rangee_racine
ajouter_textes = langue.ajouter_textes
langue_courante = langue.langue
COMMANDES = ("menu", "supp")


def _fabrique(app, adapter) -> None:
    """Pose les handlers dans l'application PTB (appelee par connect())."""
    from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler

    async def _commande(update, context):
        msg = await h.commande_autorisee(adapter, update)
        if msg is None:
            return
        texte = (msg.text or "").lstrip("/")
        nom = texte.split("@", 1)[0].split(None, 1)[0].lower()
        envoi = {"menu": h.envoyer_menu, "supp": h.envoyer_supp}.get(nom)
        if envoi is None:
            return
        await envoi(adapter, msg)
        raise ApplicationHandlerStop()

    async def _bouton(update, context):
        query = update.callback_query
        data = (getattr(query, "data", "") or "")
        if data.startswith("menu:"):
            await h.bouton_menu(adapter, query, data)
        elif data.startswith("supp:"):
            await h.bouton_supp(adapter, query, data)
        else:
            return
        raise ApplicationHandlerStop()

    app.add_handler(CommandHandler(list(COMMANDES), _commande), group=GROUPE)
    app.add_handler(CallbackQueryHandler(_bouton, pattern=h.PATTERN_CALLBACKS), group=GROUPE)


# --- Tete de la liste native de Telegram -----------------------------------

def _tete_de_liste() -> bool:
    """Met menu, supp en tete de la liste native des commandes Telegram.

    Le coeur trie les plugins par ordre alphabetique, puis applique
    ``platforms.telegram.extra.command_menu.priority`` (liste de config). Pour
    ne pas dependre de config.yaml, on enveloppe la lecture de cette config :
    nos 3 noms passent devant la priorite configuree, quel que soit le mode.
    Idempotent. Si le coeur change et que la fonction disparait, on le dit dans
    le journal et la liste garde son ordre normal (rien ne casse).
    """
    try:
        from hermes_cli import commands_platforms as cp
        lire = cp._telegram_command_menu_config
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram-menus : ordre de la liste native non applique (%s)", exc)
        return False
    if getattr(lire, "_telegram_vj", False):
        return True

    def lire_avec_tete():
        cfg = dict(lire())
        reste = [n for n in cfg.get("priority", []) if n not in COMMANDES]
        cfg["priority"] = list(COMMANDES) + reste
        return cfg

    lire_avec_tete._telegram_vj = True
    cp._telegram_command_menu_config = lire_avec_tete
    return True


# --- Repli texte (hors Telegram) -------------------------------------------

def _texte_menu(raw_args: str) -> str:
    lignes = [t("text_menu_title")]
    for cat, commandes in tm.categories():
        lignes.append(f"\n{tm.titre_categorie(cat)}")
        lignes.extend(f"/{cmd} : {desc}" for cmd, desc in commandes)
    return "\n".join(lignes)


def _texte_supp(raw_args: str) -> str:
    sessions = ts._lister_sessions()
    arg = (raw_args or "").split()
    if not arg:
        ts.memoriser(sessions)
        if not sessions:
            return ts.texte_liste(sessions)
        lignes = [ts.texte_liste(sessions)]
        lignes += [f"{i + 1}. {s['titre'][:60]}" for i, s in enumerate(sessions)]
        lignes.append(t("supp_text_howto"))
        return "\n".join(lignes)
    try:
        i = int(arg[0]) - 1
    except ValueError:
        return t("supp_usage")
    cible = ts.cible(i)
    if cible is None:
        return t("supp_stale")
    if len(arg) < 2 or arg[1].lower() != "ok":
        return t("supp_text_confirm", titre=cible["titre"][:60], n=i + 1)
    res = ts._supprimer(cible["id"])
    if res.get("ok"):
        ts.retirer(i)
        return t("supp_text_done", titre=cible["titre"][:60])
    return t("supp_text_failed", erreur=res.get("erreur"))


def register(ctx) -> None:
    _tete_de_liste()
    ctx.register_telegram_handler(_fabrique)
    ctx.register_command("menu", _texte_menu, description=t("cmd_menu_desc"))
    ctx.register_command("supp", _texte_supp, description=t("cmd_supp_desc"),
                         args_hint="[N] [ok]")
