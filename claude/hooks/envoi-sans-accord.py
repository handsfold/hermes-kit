#!/usr/bin/env python3
"""Refuse tout envoi externe (mail, LINE) que USER n'a pas ordonne.

Regle ferme de USER (CLAUDE.md global) : montrer le brouillon, le destinataire
et l'adresse d'envoi, puis attendre son ordre. Nee le 2026-09-24 : 3 demandes
de devis parties de `adresse@example.com`, la mauvaise adresse, et une piece
partie chez WorldFirst sur un « oui » ambigu. Un envoi ne se reprend pas.

Pourquoi un hook (2026-10-05) : la regle ne vivait que dans le texte, plus un
garde-fou dans `gmail.py`. Les autres voies d'envoi (himalaya, Resend, LINE,
smtplib) n'avaient rien. Regle 10 du guide Anthropic des skills : une regle
absolue va dans un hook.

Laissez-passer : prefixer la commande de `ENVOI_AUTORISE_PAR_VJ=1 `, la
convention deja en place dans `entreprise-a-gmail/gmail.py`. A ne poser que sur un
ordre ecrit de USER pour CE message.

Limite connue : un clic « Envoyer » dans un navigateur (opencli) n'est pas vu.
"""
import json
import re
import sys

ENVOI = re.compile(
    r"""(
        gmail\.py\s+(envoyer|envoyer_brouillon)\b
      | \bhimalaya\b.*\b(message|template)\s+send\b
      | api\.resend\.com/emails
      | api\.line\.me/v2/bot/message/(push|multicast|broadcast|reply|narrowcast)
      | notify-api\.line\.me
      | \b(users\.messages|users\.drafts|drafts)\.send\b
      | \bgws\b.*\bgmail\b.*\bsend\b
      | \b(sendmail|msmtp|ssmtp)\s
      | smtplib\.SMTP
      | \bswaks\b
    )""",
    re.X | re.I,
)
# Lire ou chercher dans un fichier qui parle d'envoi n'est pas envoyer.
LECTURE = re.compile(r"^\s*(grep|rg|ugrep|cat|less|head|tail|sed\s+-n|supertool|git\s+(log|diff|show|grep))\b")

MOTIF = """Refus : cette commande envoie un message a un tiers (mail ou LINE).

Regle ferme de USER : aucun message externe sans son ordre ecrit pour CE message.
Avant l'envoi, montre-lui dans le chat :
  1. le brouillon complet (et les pieces jointes) ;
  2. le destinataire ;
  3. l'adresse d'envoi (pas adresse@example.com par defaut).
Puis attends son « envoie ». Un « oui » a une autre question ne compte pas.

Une fois l'ordre recu, relance la meme commande prefixee de :
  ENVOI_AUTORISE_PAR_VJ=1 """


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd or "ENVOI_AUTORISE_PAR_VJ=1" in cmd or LECTURE.search(cmd):
        return 0
    if not ENVOI.search(cmd):
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": MOTIF,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
