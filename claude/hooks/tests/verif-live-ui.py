import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("vl", Path.home() / ".claude/hooks/verif-live-ui.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
OK = "C'est en ligne, vérifié par capture."
CSS = ("Edit", {"file_path": "/p/web/os.css"})


def test_ui_sans_live_refuse():
    assert h.decision(OK, [CSS, ("Bash", {"command": "curl http://127.0.0.1:8745/"})])


def test_ui_avec_verif_ui_live_accepte():
    assert not h.decision(OK, [CSS, ("Bash", {"command": "verif-ui.sh https://exemple.tld/usage"})])


def test_ui_avec_portail_accepte():
    assert not h.decision(OK, [CSS, ("Agent", {"subagent_type": "portail", "prompt": "capture https://exemple.tld"})])


def test_code_non_ui_ignore():
    assert not h.decision(OK, [("Edit", {"file_path": "/p/serveur.py"})])


def test_aveu_sans_annonce_accepte():
    assert not h.decision("Correctif posé, non vérifié sur le live.", [CSS])


def test_preuve_avant_modification_ne_compte_pas():
    assert h.decision(OK, [("Bash", {"command": "verif-ui.sh https://x.com/a"}), CSS])
