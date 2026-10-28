"""Mode objectif : textes en/fr, anglais par defaut, langue de telegram-menus."""
import json
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_mode_objectif import mo, poste  # noqa: F401

L = sys.modules["telegram_vj_essai.langue"]
tm = sys.modules["telegram_vj_essai.menu"]


def _bouton_mo():
    return next(b for r in tm.clavier_racine().inline_keyboard for b in r if b.callback_data == "mo:v")


def test_cles_dans_les_deux_langues():
    assert set(mo.EN) == set(mo.FR)
    assert all(mo.EN[k].strip() and mo.FR[k].strip() for k in mo.EN)


def test_defaut_anglais(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_VJ_ETAT", str(tmp_path / "absent.json"))
    assert mo._langue() == "en"
    assert mo.texte("1", True).startswith("Goal mode in this topic: ON.")
    assert mo.clavier(False).inline_keyboard[0][0].text == "Turn on goal mode"
    assert mo.clavier(True).inline_keyboard[0][0].text == "Turn off goal mode"


def test_francais_et_bascule_par_le_menu(langue_fr_isolee, monkeypatch):
    monkeypatch.setattr(tm, "_RANGEES_EXTERNES", dict(tm._RANGEES_EXTERNES))
    monkeypatch.setattr(L, "EN", dict(L.EN))
    monkeypatch.setattr(L, "FR", dict(L.FR))
    monkeypatch.setitem(L.TEXTES, "en", L.EN)
    monkeypatch.setitem(L.TEXTES, "fr", L.FR)
    assert mo.texte("1", False).startswith("Mode objectif dans ce topic : coupe.")
    mo._brancher_telegram_vj()
    assert _bouton_mo().text == "Mode objectif · relais d'outils"
    langue_fr_isolee.write_text(json.dumps({"langue": "en"}))
    assert _bouton_mo().text == "Goal mode · tool relay"
    assert "mo_body" in L.EN and "mo_body" in L.FR  # textes ajoutes au module partage


def test_langue_lue_sans_telegram_vj(langue_fr_isolee, monkeypatch):
    monkeypatch.setattr(mo, "_point_extension", lambda: None)
    assert mo._langue() == "fr"
    langue_fr_isolee.write_text("pas du json")
    assert mo._langue() == "en"
