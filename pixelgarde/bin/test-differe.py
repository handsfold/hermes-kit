#!/usr/bin/env python3
"""Les neuf situations de la lecture differee, sans toucher au telephone.

Un rapport ne doit jamais parler par-dessus ce que USER ecoute. Ce test remplace
la detection audio et l'appel adb par des doublures, et verifie que le jeton
d'attente est consomme au bon moment et conserve dans tous les autres cas.

Le jeton reel est mis a l'abri le temps du test, puis remis en place : le
garde tourne pendant ce temps et un rapport peut vraiment etre en attente.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import sys
import time
import types

RACINE = os.path.dirname(os.path.abspath(__file__))


def charger():
    loader = importlib.machinery.SourceFileLoader(
        "garde", os.path.join(RACINE, "pixel-garde"))
    spec = importlib.util.spec_from_loader("garde", loader)
    m = importlib.util.module_from_spec(spec)
    sys.argv = ["pixel-garde"]
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass
    return m


def main():
    m = charger()
    abri = m.QG_DIFFERE + ".test-en-cours"
    if os.path.exists(m.QG_DIFFERE):
        shutil.move(m.QG_DIFFERE, abri)

    appels = []
    m.sh = lambda addr, cmd, timeout=15: (
        appels.append(cmd), types.SimpleNamespace(stdout=""))[1]

    def pose(age=0):
        with open(m.QG_DIFFERE, "w") as f:
            f.write("qg-test.mp3 {}\n".format(int(time.time()) - age))

    try:
        # Par defaut le telephone est disponible : les cas historiques ne
        # portent que sur l'audio, et la garde ajoutee le 2026-08-30 ne doit
        # pas les changer.
        m.indisponible = lambda a: False

        pose()
        m.audio_occupe = lambda a: False
        m.jouer_differe("x")
        assert appels and "VOIXDIRE" in appels[0] and "qg-test.mp3" in appels[0]
        assert not os.path.exists(m.QG_DIFFERE), "le jeton devait etre consomme"
        print("1. voie libre : lecture lancee, jeton consomme")

        appels.clear()
        pose()
        m.audio_occupe = lambda a: True
        m.jouer_differe("x")
        assert not appels and os.path.exists(m.QG_DIFFERE)
        print("2. occupe : rien joue, jeton conserve")

        m.audio_occupe = lambda a: None
        m.jouer_differe("x")
        assert not appels and os.path.exists(m.QG_DIFFERE)
        print("3. injoignable : rien joue, jeton conserve")

        pose(3 * 3600)
        m.audio_occupe = lambda a: False
        m.jouer_differe("x")
        assert not appels
        assert not os.path.exists(m.QG_DIFFERE)
        print("4. perime : abandonne, rien joue")

        pose()
        open("/tmp/pixel-stop", "w").close()
        try:
            m.jouer_differe("x")
        finally:
            os.unlink("/tmp/pixel-stop")
        assert not appels and os.path.exists(m.QG_DIFFERE)
        print("5. arret d'urgence : rien joue, jeton conserve")

        # Les trois cas du telephone indisponible. Signale par USER le
        # 2026-08-30 : un rapport lu tout haut quand le telephone dort parle a
        # une poche, et un ecran de verrouillage n'ecoute pas davantage.
        appels.clear()
        pose()
        m.audio_occupe = lambda a: False
        m.indisponible = lambda a: True
        m.jouer_differe("x")
        assert not appels and os.path.exists(m.QG_DIFFERE)
        print("6. ecran eteint : rien joue, jeton conserve")

        m.indisponible = lambda a: None
        m.jouer_differe("x")
        assert not appels and os.path.exists(m.QG_DIFFERE)
        print("7. telephone injoignable : rien joue, jeton conserve")

        # Le cas que USER a demande en second : ecran bien allume, mais verrouille.
        # indisponible() rend True dans les deux situations, le differe ne doit
        # pas savoir laquelle.
        m.indisponible = lambda a: True
        m.jouer_differe("x")
        assert not appels and os.path.exists(m.QG_DIFFERE)
        print("8. ecran allume mais verrouille : rien joue, jeton conserve")

        # Et il repart au reveil : sans ce dernier cas, une garde qui ne leve
        # jamais passerait le test tout en avalant les rapports pour de bon.
        m.indisponible = lambda a: False
        m.jouer_differe("x")
        assert appels and "qg-test.mp3" in appels[0]
        assert not os.path.exists(m.QG_DIFFERE), "le jeton devait etre consomme"
        print("9. retour de USER : lecture reprise, jeton consomme")
    finally:
        if os.path.exists(m.QG_DIFFERE):
            os.unlink(m.QG_DIFFERE)
        if os.path.exists(abri):
            shutil.move(abri, m.QG_DIFFERE)
    print("les 9 cas passent")


if __name__ == "__main__":
    main()
