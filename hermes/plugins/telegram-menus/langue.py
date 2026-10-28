"""Textes bilingues (en, fr) des plugins Telegram de USER.

Anglais par defaut. La langue vient d'un fichier d'etat, cle ``langue``
(``~/.hermes/telegram-menus.json``). Pour changer d'emplacement, definir la
variable d'environnement ``TELEGRAM_VJ_ETAT`` (utile aux tests).

    t("cle")            -> texte dans la langue courante
    t("cle", n=3)       -> idem, avec ``str.format``
    basculer()          -> passe en <-> fr, rend la nouvelle langue

Un autre plugin (mode-objectif) ajoute ses textes avec
``ajouter_textes(en, fr)``. Une cle absente de la langue courante retombe sur
l'anglais, puis sur le nom de la cle : un texte manquant ne casse jamais un menu.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

LANGUES = ("en", "fr")
DEFAUT = "en"


def fichier() -> Path:
    val = (os.environ.get("TELEGRAM_VJ_ETAT") or "").strip()
    return Path(val) if val else Path.home() / ".hermes" / "telegram-menus.json"


def langue() -> str:
    """Langue courante ; anglais si le fichier manque, est illisible ou invalide."""
    try:
        val = json.loads(fichier().read_text()).get("langue")
    except Exception:  # noqa: BLE001
        return DEFAUT
    return val if val in LANGUES else DEFAUT


def definir(lang: str) -> str:
    """Ecrit la langue en gardant les autres cles du fichier."""
    if lang not in LANGUES:
        raise ValueError(lang)
    chemin = fichier()
    try:
        etat = json.loads(chemin.read_text())
        if not isinstance(etat, dict):
            etat = {}
    except Exception:  # noqa: BLE001
        etat = {}
    etat["langue"] = lang
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text(json.dumps(etat, ensure_ascii=False))
    tmp.replace(chemin)
    return lang


def basculer() -> str:
    return definir("fr" if langue() == "en" else "en")


EN: Dict[str, str] = {
    # menu racine
    "menu_root_title": "Hermes menu, tap a category:",
    "menu_root_body": "{total} commands, all one tap away. Nothing to type.",
    "menu_category_title": "{titre}, tap a command:",
    "menu_back": "< Back",
    "menu_pin": "pin",
    "menu_lang_button": "Language / Langue",
    "menu_lang_done": "Language: English",
    "cat_Session": "Session",
    "cat_Configuration": "Settings",
    "cat_Tools & Skills": "Tools and skills",
    "cat_Info": "Info",
    "btn_pyrit": "PyRIT · models",
    "btn_effort": "Effort · reasoning",
    "btn_banc": "Bench · compare models",
    "pyrit_title": "PyRIT, tap an attack (switches the model in 1 tap):",
    "pyrit_auto_hermes_deepseek": "auto · Hermes -> DeepSeek (recommended)",
    "pyrit_auto_hermes_claude": "auto · Hermes -> Claude",
    "pyrit_auto_dolphin_claude": "auto · Dolphin -> Claude",
    "pyrit_auto_hermes_grok": "auto · Hermes -> Grok",
    "pyrit_crescendo_hermes_deepseek": "crescendo · Hermes -> DeepSeek",
    "pyrit_tap_hermes_deepseek": "tap · Hermes -> DeepSeek",
    "effort_title": (
        "Effort, tap a reasoning level (1 tap):\n\n"
        "Left column: this topic only.\n"
        "Right column (pin): new default everywhere."),
    "effort_low": "Light · low",
    "effort_medium": "Balanced · medium",
    "effort_high": "Deep · high",
    "effort_xhigh": "Very deep · xhigh",
    "effort_max": "Maximum · max (Astra)",
    # garde et erreurs communes
    "not_for_you": "Not for you.",
    "not_authorized": "Not authorized.",
    "unknown_action": "Unknown action.",
    "unknown_category": "Unknown category.",
    "unknown_command": "Unknown command.",
    "unknown_model": "Unknown model.",
    "unknown_level": "Unknown level.",
    "context_unavailable": "Context unavailable.",
    "error": "Error.",
    "not_found": "Item not found.",
    "bench_unavailable": "Bench unavailable.",
    # banc
    "bench_summary": "Model bench: {nq} questions, {nm} active models.",
    "bench_no_question": "No question.",
    "bench_last": "Last bench ({date}):",
    "bench_row": "· {modele} : {c2}, {c3}, score {c5}",
    "bench_chosen": "Chosen model: {modele}",
    "bench_run": "Run the bench",
    "bench_add": "Add",
    "bench_edit": "Edit",
    "bench_delete": "Delete",
    "bench_models": "Models to compare",
    "bench_pick_edit": "Edit which question?",
    "bench_pick_delete": "Delete which question?",
    "bench_models_title": "Compared models ([x] = active). Tap to turn on or off:",
    "bench_deleted": "Question deleted: {titre}.",
    "bench_model_on": "{modele} on",
    "bench_model_off": "{modele} off",
    "bench_toast_run": "Bench started",
    "bench_toast_add": "Adding",
    "bench_toast_mod": "Editing",
    "bench_task_run": (
        "[Bench menu] Run the model bench: `cd {dossier} && python3 banc.py --juge z-ai/glm-5.3-flashx`. "
        "Give me the table (model, cost, time, score), then your opinion in 3 lines."),
    "bench_task_add": (
        "[Bench menu] I want to add a question to the bench. "
        "Ask me for the sentence on 1 line, then add it with "
        "`python3 {outil} ajoute \"<short title>\" \"<exact sentence>\"`. "
        "Keep my sentence exactly as I write it."),
    "bench_task_mod": (
        "[Bench menu] I want to edit question {n} of the bench: \"{q}\". "
        "Ask me for the new sentence on 1 line, then replace it with "
        "`python3 {outil} remplace {n} \"<exact sentence>\"`. Keep my sentence exactly as I write it."),
    # /supp
    "age_now": "just now",
    "age_min": "{n} min",
    "age_h": "{n} h",
    "age_d": "{n} d",
    "untitled": "(untitled)",
    "supp_none": "No Telegram session to delete.",
    "supp_list": "Your Telegram sessions (most recent first).\nTap the one to delete.",
    "supp_none_button": "(none)",
    "supp_delete": "Delete",
    "supp_cancel": "Cancel",
    "supp_cancelled": "Cancelled.",
    "supp_stale": "List out of date. Run /supp again.",
    "supp_confirm": "Delete this session?\n« {titre} »",
    "supp_deleting": "Deleting...",
    "supp_done": "Session deleted: « {titre} ».\nRun /supp again for the updated list.",
    "supp_failed": "Failed: {erreur}",
    "supp_timeout": "timed out ({s} s)",
    "supp_still_there": "session is still there",
    "supp_text_howto": "To delete: /supp N, then /supp N ok",
    "supp_usage": "Usage: /supp, /supp N, /supp N ok",
    "supp_text_confirm": "Delete « {titre} »? Confirm with /supp {n} ok",
    "supp_text_done": "Session deleted: « {titre} ».",
    "supp_text_failed": "Failed: {erreur}",
    # commandes et repli texte
    "cmd_menu_desc": "Button menu for all commands",
    "cmd_supp_desc": "Delete a session",
    "text_menu_title": "Commands by category:",
}

FR: Dict[str, str] = {
    "menu_root_title": "Menu Hermes, touche une categorie :",
    "menu_root_body": "{total} commandes, toutes au doigt. Aucune n'est a taper.",
    "menu_category_title": "{titre}, touche une commande :",
    "menu_back": "< Retour",
    "menu_pin": "epingler",
    "menu_lang_button": "Language / Langue",
    "menu_lang_done": "Langue : francais",
    "cat_Session": "Session",
    "cat_Configuration": "Reglages",
    "cat_Tools & Skills": "Outils et skills",
    "cat_Info": "Infos",
    "btn_pyrit": "PyRIT · modeles",
    "btn_effort": "Effort · reflexion",
    "btn_banc": "Banc · comparer les modeles",
    "pyrit_title": "PyRIT, touche une attaque (change le modele en 1 tap) :",
    "pyrit_auto_hermes_deepseek": "auto · Hermes -> DeepSeek (recommande)",
    "pyrit_auto_hermes_claude": "auto · Hermes -> Claude",
    "pyrit_auto_dolphin_claude": "auto · Dolphin -> Claude",
    "pyrit_auto_hermes_grok": "auto · Hermes -> Grok",
    "pyrit_crescendo_hermes_deepseek": "crescendo · Hermes -> DeepSeek",
    "pyrit_tap_hermes_deepseek": "tap · Hermes -> DeepSeek",
    "effort_title": (
        "Effort, touche un niveau de reflexion (1 tap) :\n\n"
        "Colonne gauche : ce topic seulement.\n"
        "Colonne droite (epingle) : nouveau defaut partout."),
    "effort_low": "Leger · low",
    "effort_medium": "Equilibre · medium",
    "effort_high": "Pousse · high",
    "effort_xhigh": "Tres pousse · xhigh",
    "effort_max": "Maximum · max (Astra)",
    "not_for_you": "Pas pour toi.",
    "not_authorized": "Non autorise.",
    "unknown_action": "Action inconnue.",
    "unknown_category": "Categorie inconnue.",
    "unknown_command": "Commande inconnue.",
    "unknown_model": "Modele inconnu.",
    "unknown_level": "Niveau inconnu.",
    "context_unavailable": "Contexte indisponible.",
    "error": "Erreur.",
    "not_found": "Element introuvable.",
    "bench_unavailable": "Banc indisponible.",
    "bench_summary": "Banc de modeles : {nq} questions, {nm} modeles actifs.",
    "bench_no_question": "Aucune question.",
    "bench_last": "Dernier banc ({date}) :",
    "bench_row": "· {modele} : {c2}, {c3}, note {c5}",
    "bench_chosen": "Modele retenu : {modele}",
    "bench_run": "Lancer le banc",
    "bench_add": "Ajouter",
    "bench_edit": "Modifier",
    "bench_delete": "Supprimer",
    "bench_models": "Modeles a comparer",
    "bench_pick_edit": "Modifier quelle question ?",
    "bench_pick_delete": "Supprimer quelle question ?",
    "bench_models_title": "Modeles compares ([x] = actif). Touche pour activer ou retirer :",
    "bench_deleted": "Question supprimee : {titre}.",
    "bench_model_on": "{modele} active",
    "bench_model_off": "{modele} retire",
    "bench_toast_run": "Banc lance",
    "bench_toast_add": "Ajout",
    "bench_toast_mod": "Modification",
    "bench_task_run": (
        "[Menu Banc] Lance le banc de modeles : `cd {dossier} && python3 banc.py --juge z-ai/glm-5.3-flashx`. "
        "Donne le tableau (modele, cout, temps, note), puis ton avis en 3 lignes."),
    "bench_task_add": (
        "[Menu Banc] Je veux ajouter une question au banc. "
        "Demande-moi la phrase en 1 ligne, puis ajoute-la avec "
        "`python3 {outil} ajoute \"<titre court>\" \"<phrase exacte>\"`. "
        "Garde ma phrase telle quelle."),
    "bench_task_mod": (
        "[Menu Banc] Je veux modifier la question {n} du banc : \"{q}\". "
        "Demande-moi la nouvelle phrase en 1 ligne, puis remplace-la avec "
        "`python3 {outil} remplace {n} \"<phrase exacte>\"`. Garde ma phrase telle quelle."),
    "age_now": "à l'instant",
    "age_min": "{n} min",
    "age_h": "{n} h",
    "age_d": "{n} j",
    "untitled": "(sans titre)",
    "supp_none": "Aucune session Telegram à supprimer.",
    "supp_list": "Tes sessions Telegram (la plus récente en haut).\nTouche celle à supprimer.",
    "supp_none_button": "(aucune)",
    "supp_delete": "Supprimer",
    "supp_cancel": "Annuler",
    "supp_cancelled": "Annule.",
    "supp_stale": "Liste perimee. Refais /supp.",
    "supp_confirm": "Supprimer cette session ?\n« {titre} »",
    "supp_deleting": "Suppression...",
    "supp_done": "Session supprimee : « {titre} ».\nRefais /supp pour la liste a jour.",
    "supp_failed": "Echec : {erreur}",
    "supp_timeout": "delai depasse ({s} s)",
    "supp_still_there": "session toujours présente",
    "supp_text_howto": "Suppression : /supp N, puis /supp N ok",
    "supp_usage": "Usage : /supp, /supp N, /supp N ok",
    "supp_text_confirm": "Supprimer « {titre} » ? Confirme avec /supp {n} ok",
    "supp_text_done": "Session supprimee : « {titre} ».",
    "supp_text_failed": "Echec : {erreur}",
    "cmd_menu_desc": "Menu des commandes a boutons",
    "cmd_supp_desc": "Supprimer une session",
    "text_menu_title": "Commandes par categorie :",
}

TEXTES = {"en": EN, "fr": FR}


def ajouter_textes(en: Dict[str, str], fr: Dict[str, str]) -> None:
    """Ajoute les textes d'un autre plugin (memes cles dans les 2 langues)."""
    EN.update(en)
    FR.update(fr)


def t(cle: str, **kw) -> str:
    texte = TEXTES[langue()].get(cle)
    if texte is None:
        texte = EN.get(cle, cle)
    return texte.format(**kw) if kw else texte
