#!/usr/bin/env python3
"""Adapte hermes-verif.sh importe pour une installation neuve.

- /mwbot n'existe pas dans le kit : il n'est plus attendu parmi les commandes Telegram.
- Le registre des retouches est un fichier personnel : sans lui, le point 5 est ignore
  (au lieu de compter un KO). On peut en indiquer un autre par la variable REGISTRE.
Chaque ancre est exigee. Rejouable.
"""

import pathlib
import re
import sys

p = pathlib.Path("hermes/scripts/hermes-verif.sh")
if not p.exists():
    sys.exit("adapter-scripts : hermes-verif.sh absent")
t = p.read_text()

defaut = "REGISTRE=${REGISTRE:-$HOME_H/maj/retouches.md}"
t, n = re.subn(r"^REGISTRE=.*$", defaut, t, count=1, flags=re.M)
if n != 1 and "REGISTRE:-" not in t:
    sys.exit("adapter-scripts : ligne REGISTRE introuvable")

for ancien, nouveau in (
    ("for c in menu supp mwbot; do", "for c in menu supp; do"),
    ("/menu /supp /mwbot visibles", "/menu /supp visibles"),
    (
        'ko "registre des retouches introuvable : $REGISTRE"',
        'note "pas de registre des retouches ($REGISTRE) : point ignore"',
    ),
):
    if ancien not in t and nouveau not in t:
        sys.exit(f"adapter-scripts : ancre absente : {ancien[:50]!r}")
    t = t.replace(ancien, nouveau)

p.write_text(t)
print("hermes-verif.sh adapte")
