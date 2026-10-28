#!/usr/bin/env bash
# Eprouve les hooks commit-sans-attribution.py et envoi-sans-accord.py.
# Les cas vivent dans ce fichier : passes en ligne de commande, ils seraient
# eux-memes refuses par le hook qu'ils testent.
# Usage : ~/.claude/hooks/tests/regles-fermes.sh   (sortie 1 si un cas echoue)
cd "$(dirname "$0")/.." || exit 2
ECHECS=0
printf 'fix\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' > /tmp/msg-test-attrib.txt

cas() { # cas <hook> <REFUS|PASSE> <commande>
  local obtenu=PASSE
  printf '%s' "$3" | python3 -c 'import json,sys;print(json.dumps({"tool_input":{"command":sys.stdin.read()}}))' \
    | python3 "$1" | grep -q '"deny"' && obtenu=REFUS
  if [ "$obtenu" = "$2" ]; then echo "ok    $2  ${3//$'\n'/ }"
  else echo "ECHEC attendu $2, obtenu $obtenu : ${3//$'\n'/ }"; ECHECS=$((ECHECS+1)); fi
}

C=commit-sans-attribution.py
cas $C REFUS 'git commit -m "fix: x" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"'
cas $C REFUS 'git add a && git commit -F /tmp/msg-test-attrib.txt'
cas $C REFUS 'cd x; GIT_AUTHOR_NAME=v git -C /tmp/r commit -m "a

Claude-Session: https://claude.ai/x"'
cas $C REFUS 'gh pr create --title t --body "corps

Generated with [Claude Code](https://claude.com/claude-code)"'
cas $C PASSE 'git commit -m "fix: propre"'
cas $C PASSE 'grep -r "Co-Authored-By: Claude" .'
cas $C PASSE 'echo verif git commit Claude-Session: x'
cas $C PASSE 'claude -p "ne mets jamais Co-Authored-By: Claude dans un git commit"'

E=envoi-sans-accord.py
cas $E REFUS '~/Bureau/Projets/business/entreprise-a/gmail/.venv/bin/python gmail.py envoyer a@b.c "Objet" "texte"'
cas $E REFUS 'himalaya message send < /tmp/m.eml'
cas $E REFUS 'curl -X POST https://api.resend.com/emails -d @m.json'
cas $E REFUS 'curl https://api.line.me/v2/bot/message/push -d x'
cas $E REFUS 'python3 -c "import smtplib; s=smtplib.SMTP_SSL(\"smtp.resend.com\")"'
cas $E PASSE 'ENVOI_AUTORISE_PAR_VJ=1 gmail.py envoyer_brouillon r-123'
cas $E PASSE 'gmail.py brouillon a@b.c "Objet" "texte"'
cas $E PASSE 'grep -n "gmail.py envoyer" fiche.md'
cas $E PASSE 'himalaya envelope list'

A=attente-sans-fin.py
cas $A REFUS 'cd logs; until ! pgrep -f 15_cross_marche.py >/dev/null; do sleep 15; done; tail x.log'
cas $A REFUS 'while pgrep -f "scan.py" > /dev/null; do sleep 5; done'
cas $A REFUS 'while pgrep -af scan.py; do sleep 5; done'
cas $A PASSE "until ! pgrep -f '[1]5_cross_marche.py' >/dev/null; do sleep 15; done"
cas $A PASSE 'while kill -0 1234 2>/dev/null; do sleep 15; done'
cas $A PASSE 'pgrep -af 15_cross_marche.py'
cas $A PASSE 'ATTENTE_ASSUMEE=1 until ! pgrep -f x.py; do sleep 1; done'

rm -f /tmp/msg-test-attrib.txt
echo "$ECHECS echec(s)"
[ "$ECHECS" -eq 0 ]
