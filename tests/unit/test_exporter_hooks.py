"""L'exporteur de config : un hook n'est exporte que si le kit livre son script."""

import importlib.util
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("exporter", RACINE / "outils" / "exporter-config.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

CONFIG = """\
hooks:
  pre_llm_call:
  - command: ~/.hermes/agent-hooks/perso.py
    timeout: 5
  - command: ~/.hermes/agent-hooks/livre.py
    timeout: 5
  post_llm_call:
  - command: ~/.hermes/agent-hooks/perso2.py
    timeout: 5
hooks_auto_accept: true
""".splitlines()


def test_hook_absent_retire(tmp_path, monkeypatch):
    (tmp_path / "livre.py").write_text("")
    monkeypatch.setattr(exporter, "KIT_HOOKS", tmp_path)
    assert exporter.filtrer_hooks(CONFIG) == [
        "hooks:",
        "  pre_llm_call:",
        "  - command: ~/.hermes/agent-hooks/livre.py",
        "    timeout: 5",
        "hooks_auto_accept: true",
    ]


def test_aucun_hook_livre(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "KIT_HOOKS", tmp_path)
    assert exporter.filtrer_hooks(CONFIG) == ["hooks: {}", "hooks_auto_accept: true"]


def test_modele_du_kit_sans_hook_orphelin():
    texte = (RACINE / "hermes" / "config.exemple.yaml").read_text(encoding="utf-8")
    for ligne in texte.splitlines():
        m = exporter.HOOK_CMD.match(ligne)
        assert m is None or (RACINE / "hermes" / "agent-hooks" / m.group(1)).exists(), ligne
