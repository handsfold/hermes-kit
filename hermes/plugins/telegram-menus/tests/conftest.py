"""Isole la langue des tests : fichier d'etat temporaire, en francais.

Les anciens tests verifient les textes francais. Les tests de langue
reecrivent le fichier eux-memes.
"""
import json

import pytest


@pytest.fixture(autouse=True)
def langue_fr_isolee(tmp_path, monkeypatch):
    etat = tmp_path / "telegram-menus.json"
    etat.write_text(json.dumps({"langue": "fr"}))
    monkeypatch.setenv("TELEGRAM_VJ_ETAT", str(etat))
    return etat
