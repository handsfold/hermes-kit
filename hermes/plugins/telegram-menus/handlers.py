"""Commandes et boutons Telegram de USER : /menu et /supp.

Ex-retouches R14, R16, R18 et R19 du coeur (adapter.py). Chaque fonction prend
l'adaptateur en premier argument ; le coeur n'est jamais modifie.

Dependances vers des methodes privees de TelegramAdapter (pas d'equivalent
public a ce jour) : _callback_ctx, _callback_authorized, _effective_update_message,
_should_process_message, _is_user_authorized_from_message, _log_blocked_user,
_ensure_forum_commands, _build_message_event. Si l'une manque, la garde refuse :
on ne laisse jamais passer une action sensible sans garde.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional

from gateway.platforms.base import MessageType

from . import langue
from . import menu as tm
from . import supp as ts
from .langue import t

logger = logging.getLogger(__name__)

PATTERN_CALLBACKS = r"^(menu|supp):"


# --- Garde d'autorisation (la meme que le coeur) ---------------------------

async def callback_autorise(adapter, query, refus: str) -> bool:
    """Garde d'un bouton : liste d'autorises du coeur, ``refus`` repondu si non."""
    ctx = getattr(adapter, "_callback_ctx", None)
    garde = getattr(adapter, "_callback_authorized", None)
    if ctx is None or garde is None:
        with contextlib.suppress(Exception):
            await query.answer(text=refus)
        return False
    return bool(await garde(query, ctx(query), refus))


async def commande_autorisee(adapter, update) -> Optional[object]:
    """Message de la commande si elle passe la garde du coeur, sinon None.

    Reprend l'enchainement de ``_handle_command`` du coeur : message utile,
    filtre de groupe, utilisateur autorise (refus journalise), commandes du forum.
    """
    lire = getattr(adapter, "_effective_update_message", None)
    msg = lire(update) if lire else getattr(update, "effective_message", None)
    if not msg or not getattr(msg, "text", None):
        return None
    filtre = getattr(adapter, "_should_process_message", None)
    autorise = getattr(adapter, "_is_user_authorized_from_message", None)
    if filtre is None or autorise is None:
        return None
    if not filtre(msg, is_command=True):
        return None
    if not autorise(msg):
        journal = getattr(adapter, "_log_blocked_user", None)
        if journal:
            journal(msg)
        return None
    forum = getattr(adapter, "_ensure_forum_commands", None)
    if forum:
        with contextlib.suppress(Exception):
            await forum(msg)
    return msg


# --- Envoi des ecrans racine ------------------------------------------------

async def envoyer_menu(adapter, message) -> None:
    """Envoie le menu racine a boutons (commande /menu)."""
    try:
        await message.reply_text(tm.texte_racine(), reply_markup=tm.clavier_racine())
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] send_menu failed: %s", adapter.name, e)


async def envoyer_supp(adapter, message) -> None:
    """Envoie la liste des sessions a boutons (commande /supp)."""
    try:
        sessions = ts._lister_sessions()
        ts.memoriser(sessions)
        await message.reply_text(
            ts.texte_liste(sessions), reply_markup=ts.clavier_liste(sessions))
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] send_supp failed: %s", adapter.name, e)


# --- Boutons ----------------------------------------------------------------

async def bouton_supp(adapter, query, data: str) -> None:
    """Suppression de session a boutons (callback_data ``supp:...``)."""
    # Meme garde que les autres boutons sensibles : un inconnu dans un
    # groupe partage ne doit pas pouvoir effacer une session.
    if not await callback_autorise(adapter, query, t("not_authorized")):
        return

    reste = data[len("supp:"):]

    if reste == "x":
        with contextlib.suppress(Exception):
            await query.edit_message_text(text=t("supp_cancelled"), parse_mode=None)
        await query.answer()
        return

    if reste.startswith("s:"):
        try:
            i = int(reste[2:])
        except ValueError:
            await query.answer(text=t("supp_stale")); return
        cible = ts.cible(i)
        if cible is None:
            await query.answer(text=t("supp_stale")); return
        titre = cible["titre"][:60]
        with contextlib.suppress(Exception):
            await query.edit_message_text(
                text=t("supp_confirm", titre=titre),
                parse_mode=None, reply_markup=ts.clavier_confirme(i))
        await query.answer()
        return

    if reste.startswith("del:"):
        try:
            i = int(reste[4:])
        except ValueError:
            await query.answer(text=t("supp_stale")); return
        cible = ts.cible(i)
        if cible is None:
            await query.answer(text=t("supp_stale")); return
        titre = cible["titre"][:60]
        await query.answer(text=t("supp_deleting"))
        res = await asyncio.to_thread(ts._supprimer, cible["id"])
        if res.get("ok"):
            ts.retirer(i)
            texte = t("supp_done", titre=titre)
        else:
            texte = t("supp_failed", erreur=res.get("erreur"))
        with contextlib.suppress(Exception):
            await query.edit_message_text(text=texte, parse_mode=None)
        return

    await query.answer()


async def appliquer_effort(adapter, query, idx: int, global_: bool) -> None:
    """Applique un niveau d'effort choisi par bouton, puis coche ce niveau.

    Le meme chemin que `/reasoning <n>` tape a la main ; ensuite le clavier
    est redessine avec la coche sur le niveau retenu.
    """
    try:
        _l, niveau = tm.EFFORTS[idx]
    except (ValueError, IndexError):
        await query.answer(text=t("unknown_level")); return
    cmd = f"/reasoning {niveau} --global" if global_ else f"/reasoning {niveau}"
    await appliquer_commande(adapter, query, cmd)
    with contextlib.suppress(Exception):
        await query.edit_message_reply_markup(
            reply_markup=tm.clavier_effort(niveau, prefixe="menu:e", prefixe_global="menu:eg", retour=True))


async def bouton_menu(adapter, query, data: str) -> None:
    """Navigation du menu a boutons (callback_data ``menu:...``)."""
    if not await callback_autorise(adapter, query, t("not_for_you")):
        return
    reste = data[len("menu:"):]
    if reste == "root":
        texte, clavier = tm.texte_racine(), tm.clavier_racine()
    elif reste == "lang":
        langue.basculer()
        texte, clavier = tm.texte_racine(), tm.clavier_racine()
        with contextlib.suppress(Exception):
            await query.edit_message_text(text=texte, reply_markup=clavier)
        await query.answer(text=t("menu_lang_done")); return
    elif reste == "pyrit":
        texte, clavier = tm.texte_pyrit(), tm.clavier_pyrit()
    elif reste == "effort":
        texte, clavier = tm.texte_effort(), tm.clavier_effort()
    elif reste.startswith("c:"):
        try:
            idx = int(reste[2:]); tm.categories()[idx]
        except (ValueError, IndexError):
            await query.answer(text=t("unknown_category")); return
        texte, clavier = tm.texte_categorie(idx), tm.clavier_categorie(idx)
    elif reste.startswith("x:"):
        try:
            _ci, _i = reste[2:].split(":", 1)
            ci, i = int(_ci), int(_i)
            cmd, _desc = tm.categories()[ci][1][i]
        except (ValueError, IndexError):
            await query.answer(text=t("unknown_command")); return
        await appliquer_commande(adapter, query, f"/{cmd}"); return
    elif reste.startswith("m:"):
        try:
            idx = int(reste[2:]); _l, modele = tm.MODELES_PYRIT[idx]
        except (ValueError, IndexError):
            await query.answer(text=t("unknown_model")); return
        await appliquer_commande(adapter, query, f"/model {modele}"); return
    elif reste.startswith("eg:") or reste.startswith("e:"):
        global_ = reste.startswith("eg:")
        try:
            idx = int(reste.split(":", 1)[1])
        except ValueError:
            await query.answer(text=t("unknown_level")); return
        await appliquer_effort(adapter, query, idx, global_); return
    elif reste == "banc" or reste.startswith("b:"):
        await menu_banc(adapter, query, reste); return
    else:
        await query.answer(); return
    with contextlib.suppress(Exception):
        await query.edit_message_text(text=texte, reply_markup=clavier)
    await query.answer()


async def menu_banc(adapter, query, reste: str) -> None:
    """Sous-menu Banc de modeles (voir menu.py, section Banc).

    Supprimer une question et activer un modele se font ici, sans agent.
    Lancer, ajouter et modifier passent a l'agent : il faut une phrase de
    USER ou une execution longue, donc un vrai tour de conversation.
    """
    note, texte, clavier = "", None, None
    try:
        if reste == "banc":
            pass
        elif reste in ("b:run", "b:add") or reste.startswith("b:m:"):
            n = int(reste[4:]) if reste.startswith("b:m:") else 0
            action = "mod" if n else reste[2:]
            await appliquer_commande(
                adapter, query, tm.consigne_banc(action, n), MessageType.TEXT,
                toast=t({"run": "bench_toast_run", "add": "bench_toast_add", "mod": "bench_toast_mod"}[action]))
            return
        elif reste == "b:mod":
            texte, clavier = t("bench_pick_edit"), tm.clavier_banc_liste("menu:b:m")
        elif reste == "b:del":
            texte, clavier = t("bench_pick_delete"), tm.clavier_banc_liste("menu:b:d")
        elif reste == "b:mdl":
            texte, clavier = (t("bench_models_title"),
                              tm.clavier_banc_modeles())
        elif reste.startswith("b:d:"):
            titre, _q = tm.banc().supprimer(int(reste[4:]))
            note = t("bench_deleted", titre=titre)
        elif reste.startswith("b:t:"):
            modele, actif = tm.banc().basculer_modele(int(reste[4:]))
            await query.answer(text=t("bench_model_on" if actif else "bench_model_off", modele=modele))
            with contextlib.suppress(Exception):
                await query.edit_message_reply_markup(reply_markup=tm.clavier_banc_modeles())
            return
        else:
            await query.answer(); return
        if texte is None:
            texte, clavier = tm.texte_banc(note), tm.clavier_banc()
    except (ValueError, IndexError):
        await query.answer(text=t("not_found")); return
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] menu banc (%s) failed: %s", adapter.name, reste, e)
        await query.answer(text=t("bench_unavailable")); return
    with contextlib.suppress(Exception):
        await query.edit_message_text(text=texte, reply_markup=clavier)
    await query.answer(text=note[:190] if note else None)


async def appliquer_commande(adapter, query, command_text: str,
                             message_type=None, toast: Optional[str] = None) -> None:
    """Applique une commande (/model, /reasoning) choisie par bouton.

    Fabrique un event COMMAND via le pipeline normal, re-attribue a
    l'utilisateur qui a touche le bouton (le message porte le bot comme
    auteur), puis reutilise handle_message : meme chemin que la commande
    tapee a la main.
    """
    msg = getattr(query, "message", None)
    if msg is None:
        await query.answer(text=t("context_unavailable")); return
    try:
        event = adapter._build_message_event(msg, message_type or MessageType.COMMAND)
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] menu apply build failed: %s", adapter.name, e)
        await query.answer(text=t("error")); return
    u = getattr(query, "from_user", None)
    uid = str(getattr(u, "id", "")) or None
    uname = getattr(u, "full_name", None) or getattr(u, "first_name", None)
    event.text = command_text
    if uid:
        event.user_id = uid
        event.user_name = uname
        if getattr(event, "source", None) is not None:
            event.source.user_id = uid
            event.source.user_name = uname
    await query.answer(text=(toast or command_text)[:190])
    try:
        await adapter.handle_message(event)
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] menu apply (%s) failed: %s", adapter.name, command_text, e)
