"""Le poseur de fichiers : substitutions, chemins cibles, bloc coach."""

import importlib.util
import os
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
ENV = {
    "HK_HOME": "/tmp/hk-test/kit",  # noqa: S108  chemin fictif, jamais ecrit
    "HK_CONTEXTE": str(Path.home() / "hk-test/contexte"),
    "HK_PROJETS": str(Path.home() / "hk-test/Projets"),
    "HERMES_HOME": str(Path.home() / "hk-test/.hermes"),
    "HK_PRENOM": "Alice",
    "HK_QG_CHAT": "-1001",
    "HK_QG_THREAD": "7",
    "HK_COACH_THREAD": "9",
    "HK_PIXEL_IP": "",
}


@pytest.fixture(scope="module")
def poser():
    os.environ.update(ENV)
    spec = importlib.util.spec_from_file_location("poser", RACINE / "install" / "poser.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.MANIFESTE = RACINE / "MANIFESTE.txt"
    return mod


def test_trous_et_prenom(poser):
    texte = (
        "chat __QG_CHAT__ fil __QG_THREAD__ coach __COACH_THREAD__ "
        "pour USER, pas $USER ni ${USER} ni USER_ID"
    )
    assert (
        poser.substituer(texte)
        == "chat -1001 fil 7 coach 9 pour Alice, pas $USER ni ${USER} ni USER_ID"
    )


def test_chemins_contexte_avant_projets(poser):
    texte = "~/Bureau/Projets/contexte/focus.md et ~/Bureau/Projets/autre et Bureau/Projets/x"
    out = poser.substituer(texte)
    assert out == "~/hk-test/contexte/focus.md et ~/hk-test/Projets/autre et hk-test/Projets/x"


def test_ip_sans_telephone(poser):
    assert (
        poser.substituer("adb connect __PIXEL_IP__:5555 __TS_IP__")
        == "adb connect 127.0.0.1:5555 127.0.0.1"
    )


def test_cible_de(poser):
    assert (
        poser.cible_de("~/Bureau/Projets/contexte/bin/x.sh")
        == Path(ENV["HK_CONTEXTE"]) / "bin/x.sh"
    )
    assert poser.cible_de("~/.hermes/scripts/a.py") == Path(ENV["HERMES_HOME"]) / "scripts/a.py"
    assert poser.cible_de("~/.claude/RTK.md") == Path.home() / ".claude/RTK.md"


def test_retirer_bloc_coach(poser):
    yaml = (
        "    channel_prompts:\n"
        "      '__QG_THREAD__': |\n"
        "        Tu es le QG.\n"
        "      '__COACH_THREAD__': |\n"
        "        Tu es le coach.\n"
        "\n"
        "        Deuxieme paragraphe.\n"
        "    autre: 1\n"
    )
    out = poser.retirer_bloc_coach(yaml)
    assert "__COACH_THREAD__" not in out
    assert "coach" not in out
    assert out.endswith("    autre: 1\n")
    assert "Tu es le QG." in out


def test_manifeste_lisible(poser):
    entrees = list(poser.lire_manifeste())
    assert len(entrees) > 20
    assert all(a.startswith("~/") for a, _ in entrees)


def test_claude_md_sans_fichier(poser):
    out = poser.fusionner_claude_md("", "regle A\n")
    assert out.startswith(poser.MARQUE_DEBUT) and out.endswith(poser.MARQUE_FIN + "\n")
    assert "regle A" in out


def test_claude_md_ajoute_apres_le_contenu_existant(poser):
    out = poser.fusionner_claude_md("# Mon fichier\nma regle\n", "regle A\n")
    assert out.startswith("# Mon fichier\nma regle\n\n" + poser.MARQUE_DEBUT)
    assert out.count(poser.MARQUE_DEBUT) == 1


def test_claude_md_remplace_le_bloc_et_garde_le_reste(poser):
    un = poser.fusionner_claude_md("avant\n", "regle A\n") + "\napres\n"
    deux = poser.fusionner_claude_md(un, "regle B\n")
    assert "regle B" in deux and "regle A" not in deux
    assert deux.startswith("avant\n") and deux.rstrip().endswith("apres")
    assert deux.count(poser.MARQUE_DEBUT) == 1 and deux.count(poser.MARQUE_FIN) == 1


def test_claude_md_idempotent(poser):
    un = poser.fusionner_claude_md("avant\n", "regle A\n")
    assert poser.fusionner_claude_md(un, "regle A\n") == un


def test_config_cree_le_dossier_de_travail(poser, tmp_path, monkeypatch):
    # Test reel du 2026-10-04 : « TERMINAL_CWD does not exist » a chaque tour.
    monkeypatch.setattr(poser, "HK_HOME", RACINE)
    monkeypatch.setattr(poser, "HA", tmp_path / ".hermes")
    monkeypatch.setattr(poser, "HOME", tmp_path)
    poser.poser_config()
    assert (tmp_path / ".hermes" / "workspace").is_dir()


def test_sujets_lus_dans_config(poser, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "platforms:\n  telegram:\n    extra:\n      dm_topics:\n"
        "      - chat_id: 42\n        topics:\n"
        "        - name: QG\n          thread_id: 11\n"
        "        - name: Coach\n          thread_id: 12\n"
        "other: 1\n"
    )
    assert poser.lire_sujets(cfg) == {"QG": "11", "Coach": "12"}


def test_sujets_absents(poser, tmp_path):
    assert poser.lire_sujets(tmp_path / "nulle-part.yaml") == {}
    vide = tmp_path / "c.yaml"
    vide.write_text("a: 1\n")
    assert poser.lire_sujets(vide) == {}


def test_langue_par_defaut_anglais(poser):
    assert poser.LANGUE == "en"


# Garde-fous nes du 2026-10-12 : un essai a reecrit le vrai ~/.claude.


def test_garde_refuse_hermes_home_hors_home(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "HOME", tmp_path / "home")
    monkeypatch.setattr(poser, "HA", tmp_path / "ailleurs" / ".hermes")
    monkeypatch.delenv("HK_FORCER_HOME", raising=False)
    with pytest.raises(SystemExit) as e:
        poser.garde_home()
    assert "HERMES_HOME" in str(e.value)


def test_garde_refuse_prenom_d_essai_hors_conteneur(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "HOME", tmp_path)
    monkeypatch.setattr(poser, "HA", tmp_path / ".hermes")
    monkeypatch.setattr(poser, "PRENOM", "Test")
    monkeypatch.setattr(poser, "en_conteneur", lambda: False)
    monkeypatch.setattr(poser, "home_reel", lambda: tmp_path)
    for v in ("HK_FORCER_HOME", "HK_CI", "CI"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(SystemExit):
        poser.garde_home()
    monkeypatch.setattr(poser, "home_reel", lambda: tmp_path / "autre")
    poser.garde_home()  # HOME jetable (HOME=$(mktemp -d)) : l'essai est permis
    monkeypatch.setattr(poser, "home_reel", lambda: tmp_path)
    monkeypatch.setenv("HK_CI", "1")
    poser.garde_home()  # en CI, le prenom d'essai est attendu


def test_garde_laisse_passer_une_vraie_installation(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "HOME", tmp_path)
    monkeypatch.setattr(poser, "HA", tmp_path / ".hermes")
    monkeypatch.setattr(poser, "PRENOM", "Alice")
    poser.garde_home()


def test_garde_forcee(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "HOME", tmp_path / "home")
    monkeypatch.setattr(poser, "HA", tmp_path / "ailleurs")
    monkeypatch.setenv("HK_FORCER_HOME", "1")
    poser.garde_home()


def test_copie_garde_l_ancien_et_saute_l_identique(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "HOME", tmp_path)
    monkeypatch.setattr(poser, "SAUVEGARDE", tmp_path / "sauv")
    src = tmp_path / "kit.md"
    src.write_text("pour USER\n", encoding="utf-8")
    dst = tmp_path / ".claude" / "a.md"
    dst.parent.mkdir()
    dst.write_text("ma version\n", encoding="utf-8")

    poser.copier_fichier(src, dst)
    assert dst.read_text(encoding="utf-8") == "pour Alice\n"
    assert (tmp_path / "sauv" / ".claude" / "a.md").read_text(encoding="utf-8") == "ma version\n"

    avant = dst.stat().st_mtime_ns
    (tmp_path / "sauv" / ".claude" / "a.md").unlink()
    poser.copier_fichier(src, dst)
    assert dst.stat().st_mtime_ns == avant  # identique : ni reecrit ni sauvegarde
    assert not (tmp_path / "sauv" / ".claude" / "a.md").exists()


def test_coauteur_par_defaut(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "SANS_COAUTEUR", tmp_path / "sans-coauteur")
    monkeypatch.delenv("HK_COAUTEUR", raising=False)
    fusion = {}
    poser.regler_coauteur(fusion, {})
    assert fusion["attribution"]["commit"] == "Co-Authored-By: HandsFold <hello@handsfold.com>"


def test_coauteur_coupe(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "SANS_COAUTEUR", tmp_path / "sans-coauteur")
    monkeypatch.setenv("HK_COAUTEUR", "0")
    mien = {"attribution": {"commit": poser.COAUTEUR, "pr": "x"}}
    fusion = dict(mien)
    poser.regler_coauteur(fusion, mien)
    assert fusion["attribution"] == {"pr": "x"}
    assert (tmp_path / "sans-coauteur").exists()


def test_coauteur_respecte_le_choix(poser, tmp_path, monkeypatch):
    monkeypatch.setattr(poser, "SANS_COAUTEUR", tmp_path / "sans-coauteur")
    monkeypatch.delenv("HK_COAUTEUR", raising=False)
    mien = {"attribution": {"commit": ""}}
    fusion = dict(mien)
    poser.regler_coauteur(fusion, mien)
    assert fusion["attribution"] == {"commit": ""}
