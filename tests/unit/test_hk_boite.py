"""hk-boite : analyse, base locale et bilan, sur des mails fictifs (sans navigateur)."""

import importlib.util
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hk_boite", RACINE / "install" / "hk-boite.py")
hkb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hkb)

MOI = "moi@example.com"
MAINTENANT = datetime(2026, 10, 4, 12, tzinfo=UTC)


def ligne(thread, gens, sujet, extrait="", non_lu=False):
    return {
        "thread": thread,
        "dernier": thread,
        "sujet": sujet,
        "extrait": extrait,
        "non_lu": non_lu,
        "libelles": [],
        "gens": [{"email": e, "nom": n} for e, n in gens],
    }


# identifiants Gmail : (ms epoch << 20) en hexadecimal
def hexid(jour):
    ms = int(datetime(2026, 10, jour, 9, tzinfo=UTC).timestamp() * 1000)
    return format(ms << 20, "x")


def jeu():
    lignes = [
        ligne(
            hexid(1),
            [("paul@client.fr", "Paul")],
            "Devis cuisine",
            "Pouvez-vous confirmer le devis ?",
        ),
        ligne(
            hexid(2), [("paul@client.fr", "Paul"), (MOI, "moi")], "Re: planning", "OK pour jeudi"
        ),
        ligne(
            hexid(3),
            [("billing@acme.io", "Acme")],
            "Your invoice #42",
            "Invoice of the month",
            non_lu=True,
        ),
        ligne(
            hexid(3)[:-1] + "1",
            [("no-reply@shop.com", "Shop")],
            "Order confirmed",
            "Receipt attached",
        ),
        ligne(
            hexid(2)[:-1] + "2",
            [("anna@ami.org", "Anna")],
            "Automatic reply: absent",
            "Je suis absente",
        ),
    ]
    return [hkb.ligne_vers_mail(x, MOI, 0, 1) for x in lignes]


def test_date_depuis_identifiant():
    assert hkb.date_gmail(hexid(4)).startswith("2026-10-04T09:00")
    assert hkb.date_gmail("zz") == ""


def test_ligne_vers_mail():
    m = jeu()[1]
    assert m["de_email"] == "paul@client.fr"
    assert m["dernier_moi"] == 1
    assert m["lien"].startswith("https://mail.google.com/mail/u/0/#all/")


def test_analyse():
    a = hkb.analyser(jeu(), MOI, MAINTENANT)
    assert a["total"] == 5
    assert a["non_lus"] == 1
    # attente : Paul (devis) seulement. Exclus : le fil ou j'ai repondu,
    # le robot et la reponse automatique
    assert [m["sujet"] for m in a["attente"]] == ["Devis cuisine"]
    assert {m["sujet"] for m in a["factures"]} == {"Your invoice #42", "Order confirmed"}
    assert a["top"][0][1] == "paul@client.fr"


def test_bilan_et_questions():
    mails = jeu()
    a = hkb.analyser(mails, MOI, MAINTENANT)
    a["_mails"] = mails
    qs = hkb.questions(a)
    assert len(qs) == 3
    assert all(m["lien"] for _, m in qs)
    texte = hkb.rediger(a, "en", "Alice")
    assert "Hi Alice" in texte and "3 questions" in texte
    assert len(texte) < 4096
    assert not any(c in texte for c in "\u2013\u2014")
    assert "Bonjour" in hkb.rediger(a, "fr", "Alice")


def test_base_et_recherche(tmp_path):
    c = hkb.ouvrir(tmp_path / "b.db")
    mails = jeu()
    mails[0]["corps"] = "Le devis de la cuisine en chene est de trois pages."
    hkb.enregistrer(c, mails)
    hkb.enregistrer(c, [dict(mails[0], corps="")])  # le corps deja lu reste
    res = hkb.cherche(c, "cuisine chêne")
    assert res and res[0]["sujet"] == "Devis cuisine"
    assert "chene" in res[0]["corps"]
    assert (tmp_path / "b.db").stat().st_mode & 0o777 == 0o600
    assert hkb.cherche(c, "the of") == []


def test_recherche_sans_fts(tmp_path, monkeypatch):
    c = hkb.ouvrir(tmp_path / "b.db")
    c.execute("INSERT OR REPLACE INTO meta VALUES ('fts', '0')")
    hkb.enregistrer(c, jeu())
    assert hkb.cherche(c, "invoice")[0]["de_nom"] == "Acme"
    assert isinstance(c, sqlite3.Connection)


def test_nettoyer_corps():
    assert hkb.nettoyer_corps("Gmail - X\n Moi <a@b>\n 2 messages \n Bob : salut") == "Bob : salut"
