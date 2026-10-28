"""Le bouton Mode objectif apparait dans le clavier racine de telegram-menus."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
USER = RACINE.parent / "telegram-menus"


def _charger(nom, dossier):
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(
        nom, dossier / "__init__.py", submodule_search_locations=[str(dossier)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    spec.loader.exec_module(mod)
    return mod


poste = _charger("telegram_vj_essai", USER)
mo = _charger("mode_objectif_essai", RACINE)


def _donnees(markup):
    return [b.callback_data for r in markup.inline_keyboard for b in r]


def test_bouton_present_avec_telegram_vj():
    tm = sys.modules["telegram_vj_essai.menu"]
    assert "mo:v" not in _donnees(tm.clavier_racine())
    assert mo._brancher_telegram_vj() is True
    assert _donnees(tm.clavier_racine()).count("mo:v") == 1
    assert mo._brancher_telegram_vj() is True  # idempotent, pas de doublon
    assert _donnees(tm.clavier_racine()).count("mo:v") == 1


def test_fabrique_en_panne_ne_casse_pas_le_menu():
    tm = sys.modules["telegram_vj_essai.menu"]
    poste.ajouter_rangee_racine("casse", lambda: 1 / 0)
    assert "menu:banc" in _donnees(tm.clavier_racine())


def test_callback_repond(monkeypatch, tmp_path):
    monkeypatch.setattr(mo, "TABLE", tmp_path / "t.json")
    monkeypatch.setattr(mo, "JOURNAL", tmp_path / "j.log")
    rep = []

    class Q:
        data = "mo:on"
        from_user = SimpleNamespace(id=1, full_name="USER")
        message = SimpleNamespace(message_thread_id=42, chat=SimpleNamespace(id=9, type="supergroup"))

        async def answer(self, text=None):
            rep.append(text)

        async def edit_message_text(self, *a, **k):
            rep.append("edit")

    ad = SimpleNamespace(_is_callback_user_authorized=lambda *a, **k: True)
    asyncio.run(mo._toucher(ad, SimpleNamespace(callback_query=Q()), None))
    assert rep[0] == "Mode objectif active." and mo.lire() == ["42"]


def test_repli_sans_telegram_vj(monkeypatch):
    monkeypatch.delitem(sys.modules, "telegram_vj_essai")
    assert mo._brancher_telegram_vj() is False
    sys.modules["telegram_vj_essai"] = poste
