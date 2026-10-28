#!/usr/bin/env python3
"""Rafraichit les resumes d'etat des topics qui ont bouge. Sortie silencieuse."""
import subprocess
import sys
r = subprocess.run([sys.executable, "$HOME/.hermes/scripts/qg.py", "resumer"],
                   capture_output=True, text=True, timeout=1200)
sys.stderr.write(r.stderr[-500:])
sys.exit(0)
