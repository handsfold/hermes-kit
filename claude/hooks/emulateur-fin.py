#!/usr/bin/env python3
"""Stop : ferme tout emulateur Android (emulator-NNNN) a la fin du tour.

Ne touche jamais un vrai telephone : seules les cibles `emulator-*` sont
visees. Ne dit rien et ne bloque jamais. Né le 2026-10-17 : l'emulateur
Creeper_Test restait ouvert apres la fin de la tache, USER a du le demander.
Un essai suivant relance l'emulateur en une commande (voir projets/creeper.md).
"""
import os, subprocess, sys

ADB = os.path.expanduser("~/Android/Sdk/platform-tools/adb")
if not os.path.exists(ADB):
    sys.exit(0)
for port in ("5037", "5038"):
    env = dict(os.environ, ANDROID_ADB_SERVER_PORT=port)
    try:
        out = subprocess.run([ADB, "devices"], env=env, capture_output=True,
                             text=True, timeout=8).stdout
        for ligne in out.splitlines()[1:]:
            serie = ligne.split("\t")[0].strip()
            if serie.startswith("emulator-"):
                subprocess.run([ADB, "-s", serie, "emu", "kill"], env=env,
                               capture_output=True, timeout=10)
    except Exception:
        pass
sys.exit(0)
