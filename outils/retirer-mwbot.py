#!/usr/bin/env python3
"""Retire /mwbot du plugin des menus Telegram importe.

/mwbot pilote un bot mail qui tourne sur un serveur precis : sans lui la
commande n'a aucun sens. Ce script coupe le cablage dans le plugin importe
(commande, bouton mw:, textes, tests) et supprime mwbot.py.
Chaque ancre est exigee : si le plugin source change, le script echoue fort
plutot que de laisser un cablage a moitie retire. Rejouable (sans effet si deja fait).
"""

import pathlib
import re
import sys

RACINE = pathlib.Path("hermes/plugins/telegram-menus")


def remplacer(chemin, paires):
    p = RACINE / chemin
    t = p.read_text()
    for ancien, nouveau in paires:
        if ancien not in t:
            sys.exit(f"retirer-mwbot : ancre absente dans {chemin} : {ancien[:60]!r}")
        t = t.replace(ancien, nouveau)
    p.write_text(t)


def couper(chemin, motif, fois=1):
    """Supprime le bloc qui correspond au motif (exige exactement `fois` occurrences)."""
    p = RACINE / chemin
    t, n = re.subn(motif, "", p.read_text(), flags=re.S | re.M)
    if n != fois:
        sys.exit(f"retirer-mwbot : {n} bloc(s) au lieu de {fois} dans {chemin} : {motif[:50]!r}")
    p.write_text(t)


if not (RACINE / "mwbot.py").exists():
    print("mwbot deja retire")
    sys.exit(0)

remplacer(
    "__init__.py",
    [
        ("/menu, /supp et /mwbot a boutons", "/menu et /supp a boutons"),
        (
            "  les 3 commandes et un CallbackQueryHandler",
            "  les 2 commandes et un CallbackQueryHandler",
        ),
        ("  les 3 commandes dans la liste native", "  les 2 commandes dans la liste native"),
        ("place menu, supp, mwbot en tete,", "place menu, supp en tete,"),
        ("Met menu, supp, mwbot en tete", "Met menu, supp en tete"),
        ("(hors ``menu:``, ``supp:``,\n``mw:``)", "(hors ``menu:`` et ``supp:``)"),
        ("from . import mwbot as tw\n", ""),
        ('("menu", "supp", "mwbot")', '("menu", "supp")'),
        (', "mwbot": h.envoyer_mwbot}', "}"),
        (
            '        elif data.startswith("mw:"):\n            await h.bouton_mwbot(adapter, query, data)\n',  # noqa: E501
            "",
        ),
    ],
)
couper("__init__.py", r"    ctx\.register_command\(\"mwbot\".*?args_hint=\"\[on\|off\|etat\]\"\)\n")
couper("__init__.py", r"async def _texte_mwbot\(.*?\n\n\n(?=def register)")

remplacer(
    "handlers.py",
    [
        ("/menu, /supp, /mwbot.", "/menu et /supp."),
        ("from . import mwbot as tw\n", ""),
        ('r"^(menu|supp|mw):"', 'r"^(menu|supp):"'),
    ],
)
couper("handlers.py", r"async def envoyer_mwbot\(.*?\n\n\n(?=async def envoyer_supp)")
couper("handlers.py", r"async def bouton_mwbot\(.*?\n\n\n(?=async def bouton_supp)")

remplacer(
    "plugin.yaml",
    [
        (", /supp with confirmation, /mwbot.", " and /supp with confirmation."),
        ("  - mwbot\n", ""),
    ],
)

# langue.py : 11 cles mw_* + cmd_mwbot_desc + le commentaire, en EN puis en FR.
couper("langue.py", r'^ *"(?:mw_[a-z_]+|cmd_mwbot_desc)":.*?\n', fois=24)
couper("langue.py", r"^ *# /mwbot\n", fois=1)

remplacer(
    "tests/test_plugin.py",
    [
        ('for ok in ("menu:root", "supp:x", "mw:etat"):', 'for ok in ("menu:root", "supp:x"):'),
        ("def test_garde_refuse_les_trois_familles", "def test_garde_refuse_les_deux_familles"),
        (
            '("supp:s:0", "Non autorise."),\n                        ("mw:on", "Pas pour toi.")):',
            '("supp:s:0", "Non autorise.")):',
        ),
        (', "mw": h.bouton_mwbot}', "}"),
        ('["tg", "menu", "supp", "mwbot"]', '["tg", "menu", "supp"]'),
        ('["personality", "mwbot", "new"]', '["personality", "new"]'),
        (
            '["menu", "supp", "mwbot", "personality", "new"]',
            '["menu", "supp", "personality", "new"]',
        ),
        ('("mwbot", "menu", "supp", "zzz")', '("menu", "supp", "zzz")'),
        ('ordre[:3] == ["menu", "supp", "mwbot"]', 'ordre[:2] == ["menu", "supp"]'),
    ],
)
couper("tests/test_plugin.py", r"def test_mwbot_bouton\(.*?\n\n\n(?=def test_effort)")

remplacer(
    "tests/test_langue.py",
    [
        ('mw = sys.modules["telegram_vj_essai.mwbot"]\n', ""),
        ('    for etat in mw.ETATS:\n        assert f"mw_{etat}" in L.EN\n', ""),
        (
            '    texte, clavier = mw.rendu("active")\n'
            '    assert "ON" in texte and clavier.inline_keyboard[0][0].text == "Turn off for the night"\n',  # noqa: E501
            "",
        ),
    ],
)

(RACINE / "mwbot.py").unlink()
print("mwbot retire du plugin des menus Telegram")
