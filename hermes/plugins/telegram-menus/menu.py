"""Menu /menu a boutons (plugin telegram-menus, ex-retouches R14 et R19 du coeur).

Tout se fait au doigt : aucune commande a taper. Les categories sont
construites depuis COMMAND_REGISTRY (source unique du gateway), donc une
commande ajoutee au registre apparait ici sans toucher a ce fichier.

Contrat des callback_data (Telegram limite a 64 octets) :
  menu:root        -> racine (categories)
  menu:pyrit       -> sous-menu PyRIT (modeles red-team)
  menu:effort      -> sous-menu Effort (niveaux de reflexion)
  menu:c:<ci>      -> ouvre la categorie ci (boutons de commandes)
  menu:x:<ci>:<i>  -> lance la commande i de la categorie ci (1 tap)
  menu:m:<i>       -> applique MODELES_PYRIT[i] via /model
  menu:e:<i>       -> applique EFFORTS[i] via /reasoning (session)
  menu:eg:<i>      -> applique EFFORTS[i] via /reasoning --global (defaut)
  menu:lang        -> bascule la langue (en <-> fr), redessine la racine
  menu:banc        -> sous-menu Banc (questions et modeles du banc de modeles)
  menu:b:run|add   -> confie a l'agent : lancer le banc, ajouter une question
  menu:b:mod|del|mdl -> listes : modifier, supprimer, activer un modele
  menu:b:m:<i>     -> confie a l'agent la reecriture de la question i
  menu:b:d:<i>     -> supprime la question i (direct, sans agent)
  menu:b:t:<i>     -> active ou desactive le modele i (direct)
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import langue as _langue
from .langue import t

logger = logging.getLogger(__name__)

# Commandes ecartees du menu : sans argument elles ne font rien d'utile.
SANS_ARGUMENT_INUTILE = {"background", "queue", "steer", "approve", "deny"}

# Ordre d'affichage des categories du registre.
ORDRE_CATEGORIES = ["Session", "Configuration", "Tools & Skills", "Info"]

_cache: List[Tuple[str, List[Tuple[str, str]]]] | None = None


def categories() -> List[Tuple[str, List[Tuple[str, str]]]]:
    """(categorie du registre, [(commande, description), ...]), en cache.

    Le titre affiche vient de ``titre_categorie`` (traduit a chaque affichage).
    """
    global _cache
    if _cache is not None:
        return _cache
    try:
        from hermes_cli.commands import (
            COMMAND_REGISTRY, _is_gateway_available, _resolve_config_gates,
        )
        gates = _resolve_config_gates()
        groupes: dict[str, List[Tuple[str, str]]] = {}
        for cmd in COMMAND_REGISTRY:
            if not _is_gateway_available(cmd, gates):
                continue
            if cmd.name in SANS_ARGUMENT_INUTILE:
                continue
            groupes.setdefault(cmd.category or "Info", []).append(
                (cmd.name, cmd.description))
        ordre = ORDRE_CATEGORIES + [c for c in groupes if c not in ORDRE_CATEGORIES]
        _cache = [(c, groupes[c]) for c in ordre if groupes.get(c)]
    except Exception:  # registre indisponible : menu reduit mais fonctionnel
        _cache = []
    return _cache


# Retro-compat : l'ancien nom etait une constante.
CATEGORIES = categories()

# Un tap = /model <valeur>. Editer suffit (aucun code a toucher).
MODELES_PYRIT: List[Tuple[str, str]] = [
    ("pyrit_auto_hermes_deepseek", "pyrit-auto-hermes-vs-deepseek"),
    ("pyrit_auto_hermes_claude", "pyrit-auto-hermes-vs-claude"),
    ("pyrit_auto_dolphin_claude", "pyrit-auto-dolphin-vs-claude"),
    ("pyrit_auto_hermes_grok", "pyrit-auto-hermes-vs-grok"),
    ("pyrit_crescendo_hermes_deepseek", "pyrit-crescendo-hermes-vs-deepseek"),
    ("pyrit_tap_hermes_deepseek", "pyrit-tap-hermes-vs-deepseek"),
]

# Un tap = /reasoning <valeur>. Astra accepte ces cinq niveaux via Codex.
# ultra appartient au client Codex et n'est pas accepte par l'API (2026-09-13).
# Garder les indices existants pour les boutons deja envoyes sur Telegram.
EFFORTS: List[Tuple[str, str]] = [
    ("effort_low", "low"),
    ("effort_medium", "medium"),
    ("effort_high", "high"),
    ("effort_xhigh", "xhigh"),
    ("effort_max", "max"),
]


def titre_categorie(cat: str) -> str:
    """Titre traduit d'une categorie du registre (inconnue : nom du registre)."""
    cle = f"cat_{cat}"
    return t(cle) if cle in _langue.EN else cat


# --- Textes -----------------------------------------------------------------

def texte_racine() -> str:
    cats = categories()
    total = sum(len(c) for _t, c in cats)
    return f"{t('menu_root_title')}\n\n{t('menu_root_body', total=total)}"


def texte_pyrit() -> str:
    return t("pyrit_title")


def texte_effort() -> str:
    return t("effort_title")


def texte_categorie(index: int) -> str:
    cat, cmds = categories()[index]
    lignes = [t("menu_category_title", titre=titre_categorie(cat)), ""]
    for cmd, desc in cmds:
        lignes.append(f"/{cmd} : {desc}")
    return "\n".join(lignes)


# --- Claviers ---------------------------------------------------------------

def clavier_racine() -> InlineKeyboardMarkup:
    cats = categories()
    boutons = [
        InlineKeyboardButton(f"{titre_categorie(cat)} ({len(cmds)})", callback_data=f"menu:c:{i}")
        for i, (cat, cmds) in enumerate(cats)
    ]
    rows = [boutons[i:i + 2] for i in range(0, len(boutons), 2)]
    rows.append([
        InlineKeyboardButton(t("btn_pyrit"), callback_data="menu:pyrit"),
        InlineKeyboardButton(t("btn_effort"), callback_data="menu:effort"),
    ])
    rows.append([InlineKeyboardButton(t("btn_banc"), callback_data="menu:banc")])
    rows.append([InlineKeyboardButton(t("menu_lang_button"), callback_data="menu:lang")])
    for fabrique in tuple(_RANGEES_EXTERNES.values()):
        try:
            rangee = fabrique()
        except Exception as e:  # noqa: BLE001
            logger.warning("rangee externe du menu ignoree : %s", e)
            continue
        if rangee:
            rows.append(list(rangee))
    return InlineKeyboardMarkup(rows)


# Point d'extension : rangees ajoutees a la racine par d'autres plugins.
_RANGEES_EXTERNES: dict = {}


def ajouter_rangee_racine(nom, fabrique) -> None:
    """Ajoute (ou remplace, par ``nom``) une rangee de boutons au menu racine.

    ``fabrique()`` est appelee a chaque affichage et rend une liste de
    ``InlineKeyboardButton`` (ou ``None`` pour ne rien afficher).
    """
    _RANGEES_EXTERNES[nom] = fabrique


def clavier_retour() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("menu_back"), callback_data="menu:root")]])


def clavier_categorie(index: int) -> InlineKeyboardMarkup:
    _titre, cmds = categories()[index]
    boutons = [
        InlineKeyboardButton(f"/{cmd}", callback_data=f"menu:x:{index}:{i}")
        for i, (cmd, _d) in enumerate(cmds)
    ]
    rows = [boutons[i:i + 3] for i in range(0, len(boutons), 3)]
    rows.append([InlineKeyboardButton(t("menu_back"), callback_data="menu:root")])
    return InlineKeyboardMarkup(rows)


def clavier_pyrit() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t(label), callback_data=f"menu:m:{i}")]
        for i, (label, _m) in enumerate(MODELES_PYRIT)
    ]
    rows.append([InlineKeyboardButton(t("menu_back"), callback_data="menu:root")])
    return InlineKeyboardMarkup(rows)


def clavier_effort(
    courant: str | None = None,
    prefixe: str = "menu:e",
    prefixe_global: str = "menu:eg",
    retour: bool = True,
) -> InlineKeyboardMarkup:
    # Deux colonnes : a gauche pour la session, a droite pour figer le defaut
    # global (equivalent de `/reasoning <n> --global`), sans rien taper.
    # Le niveau courant est coche, comme le fournisseur courant dans /model.
    rows = []
    for i, (label, niveau) in enumerate(EFFORTS):
        label = t(label)
        if courant and niveau == courant:
            label = f"✓ {label}"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"{prefixe}:{i}"),
            InlineKeyboardButton(t("menu_pin"), callback_data=f"{prefixe_global}:{i}"),
        ])
    if retour:
        rows.append([InlineKeyboardButton(t("menu_back"), callback_data="menu:root")])
    return InlineKeyboardMarkup(rows)


# --- Banc de modeles --------------------------------------------------------
# Les fichiers vivent dans le projet banc-modeles, lus a chaque affichage :
# une question modifiee a la main ou par l'agent apparait au tap suivant.

import importlib.util as _ilu
import os as _os

DOSSIER_BANC = _os.path.expanduser("~/Bureau/Projets/banc-modeles")


def banc():
    """Module fichier_questions du projet (recharge a chaque appel)."""
    spec = _ilu.spec_from_file_location(
        "_banc_fq", _os.path.join(DOSSIER_BANC, "fichier_questions.py"))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _court(texte: str, n: int = 70) -> str:
    texte = " ".join(texte.split())
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def texte_banc(note: str = "") -> str:
    fq = banc()
    qs, mods = fq.lire_questions(), fq.lire_modeles()
    actifs = [m for m, a in mods if a]
    l = [t("bench_summary", nq=len(qs), nm=len(actifs)), ""]
    l += [f"{i}. {_court(q)}" for i, (_t, q) in enumerate(qs, 1)] or [t("bench_no_question")]
    dernier = fq.dernier_tableau()
    if dernier:
        date, lignes = dernier
        l += ["", t("bench_last", date=date)]
        for ligne in lignes:
            c = [x.strip() for x in ligne.strip("|").split("|")]
            if len(c) >= 6 and not set(c[0]) <= set("-"):
                l.append(t("bench_row", modele=c[0].split("/")[-1], c2=c[2], c3=c[3], c5=c[5]))
    choix = fq.dernier_choix() if hasattr(fq, "dernier_choix") else None
    if choix:
        l += ["", t("bench_chosen", modele=choix["modele"].split("/")[-1]),
              f"({choix['raison']})"]
    if note:
        l = [note, ""] + l
    return "\n".join(l)


def clavier_banc() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("bench_run"), callback_data="menu:b:run")],
        [InlineKeyboardButton(t("bench_add"), callback_data="menu:b:add"),
         InlineKeyboardButton(t("bench_edit"), callback_data="menu:b:mod"),
         InlineKeyboardButton(t("bench_delete"), callback_data="menu:b:del")],
        [InlineKeyboardButton(t("bench_models"), callback_data="menu:b:mdl")],
        [InlineKeyboardButton(t("menu_back"), callback_data="menu:root")],
    ])


def clavier_banc_liste(prefixe: str) -> InlineKeyboardMarkup:
    qs = banc().lire_questions()
    rows = [[InlineKeyboardButton(f"{i}. {_court(q, 40)}", callback_data=f"{prefixe}:{i}")]
            for i, (_t, q) in enumerate(qs, 1)]
    rows.append([InlineKeyboardButton(t("menu_back"), callback_data="menu:banc")])
    return InlineKeyboardMarkup(rows)


def clavier_banc_modeles() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(("[x] " if a else "[ ] ") + m, callback_data=f"menu:b:t:{i}")]
            for i, (m, a) in enumerate(banc().lire_modeles(), 1)]
    rows.append([InlineKeyboardButton(t("menu_back"), callback_data="menu:banc")])
    return InlineKeyboardMarkup(rows)


def consigne_banc(action: str, n: int = 0) -> str:
    """Message confie a l'agent pour les actions qui demandent une phrase ou du temps."""
    outil = f"{DOSSIER_BANC}/fichier_questions.py"
    if action == "run":
        return t("bench_task_run", dossier=DOSSIER_BANC)
    if action == "add":
        return t("bench_task_add", outil=outil)
    q = banc().lire_questions()[n - 1][1]
    return t("bench_task_mod", n=n, q=_court(q, 200), outil=outil)
