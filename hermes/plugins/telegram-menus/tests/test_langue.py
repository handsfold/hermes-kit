"""Tests de la langue (en par defaut, fr en option) et du bouton Language / Langue."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_plugin import FauxAdapter, FauxQuery, plugin, run  # noqa: F401

RACINE = Path(__file__).resolve().parent.parent
L = sys.modules["telegram_vj_essai.langue"]
tm = sys.modules["telegram_vj_essai.menu"]
h = sys.modules["telegram_vj_essai.handlers"]
ts = sys.modules["telegram_vj_essai.supp"]


def _poser(etat, valeur):
    etat.write_text(json.dumps({"langue": valeur}))


def _boutons(markup):
    return [b for r in markup.inline_keyboard for b in r]


def test_cles_identiques_dans_les_deux_langues():
    assert set(L.EN) == set(L.FR)
    assert all(v.strip() for v in list(L.EN.values()) + list(L.FR.values()))


def test_aucun_tiret_long_ni_emoji():
    for texte in list(L.EN.values()) + list(L.FR.values()):
        assert not re.search("[" + chr(0x2013) + chr(0x2014) + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]", texte.replace(chr(0x2713), ""))


def test_cles_utilisees_dans_le_code_existent():
    utilisees = set()
    for f in RACINE.glob("*.py"):
        if f.name != "langue.py":
            utilisees |= set(re.findall(r"\bt\(\s*f?[\"']([a-z_A-Z]+)[\"']", f.read_text()))
    assert utilisees and utilisees <= set(L.EN)
    # cles composees (mw_<etat>, effort_<niveau>, pyrit_*, cat_*)
    for _l, niveau in tm.EFFORTS:
        assert _l in L.EN and _l in L.FR
    for cle, _m in tm.MODELES_PYRIT:
        assert cle in L.EN and cle in L.FR


def test_formats_identiques_entre_langues():
    champs = lambda s: set(re.findall(r"{(\w+)}", s))
    for cle in L.EN:
        assert champs(L.EN[cle]) == champs(L.FR[cle]), cle


def test_defaut_anglais_sans_fichier(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_VJ_ETAT", str(tmp_path / "absent.json"))
    assert L.langue() == "en"
    assert L.t("menu_back") == "< Back"
    assert tm.texte_racine().startswith("Hermes menu")


@pytest.mark.parametrize("contenu", ["pas du json", '{"langue": "de"}', "[]", ""])
def test_defaut_anglais_fichier_invalide(langue_fr_isolee, contenu):
    langue_fr_isolee.write_text(contenu)
    assert L.langue() == "en"


def test_francais_en_option(langue_fr_isolee):
    assert L.langue() == "fr"
    assert tm.texte_racine().startswith("Menu Hermes")
    _poser(langue_fr_isolee, "en")
    assert tm.texte_racine().startswith("Hermes menu")


def test_bouton_langue_a_la_racine():
    cles = [b.callback_data for b in _boutons(tm.clavier_racine())]
    assert cles.count("menu:lang") == 1
    assert next(b for b in _boutons(tm.clavier_racine()) if b.callback_data == "menu:lang").text == "Language / Langue"


def test_bouton_bascule_et_redessine(langue_fr_isolee):
    ad = FauxAdapter()
    q = FauxQuery("menu:lang")
    run(h.bouton_menu(ad, q, "menu:lang"))
    assert L.langue() == "en"
    texte, markup = q.editions[0]
    assert texte.startswith("Hermes menu")
    assert "Back" not in texte and any("Bench" in b.text for b in _boutons(markup))
    assert q.reponses == ["Language: English"]
    q2 = FauxQuery("menu:lang")
    run(h.bouton_menu(ad, q2, "menu:lang"))
    assert L.langue() == "fr"
    assert q2.editions[0][0].startswith("Menu Hermes")
    assert any("Banc" in b.text for b in _boutons(q2.editions[0][1]))


def test_bouton_langue_refuse_si_non_autorise(langue_fr_isolee):
    q = FauxQuery("menu:lang")
    run(h.bouton_menu(FauxAdapter(autorise=False), q, "menu:lang"))
    assert L.langue() == "fr" and q.editions == []


def test_bascule_garde_les_autres_cles(langue_fr_isolee):
    langue_fr_isolee.write_text(json.dumps({"langue": "fr", "autre": 1}))
    L.basculer()
    assert json.loads(langue_fr_isolee.read_text()) == {"langue": "en", "autre": 1}


def test_ecrans_en_anglais(langue_fr_isolee):
    _poser(langue_fr_isolee, "en")
    assert "Cancel" in [b.text for b in _boutons(ts.clavier_confirme(0))]
    assert ts.texte_liste([]).startswith("No Telegram session")
    assert "Light · low" in [b.text for b in _boutons(tm.clavier_effort())]
    assert "pin" in [b.text for b in _boutons(tm.clavier_effort())]
    assert ts._age(None) == "?"
    assert "Commands by category:" in plugin._texte_menu("")


def test_garde_en_anglais(langue_fr_isolee):
    _poser(langue_fr_isolee, "en")
    q = FauxQuery("menu:root")
    run(h.bouton_menu(FauxAdapter(autorise=False), q, "menu:root"))
    assert q.reponses == ["Not for you."]
