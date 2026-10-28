#!/usr/bin/env python3
"""Refuse a l'agent de se couper la parole a lui-meme.

Mesure de la retro du 2026-08-31 : 64 tours interrompus en 7 jours, repartis
sur 27 sessions, avec 73 SIGTERM dans gateway.log. La cause n'est pas un bug
du gateway : c'est l'agent qui lance `systemctl --user restart hermes-gateway`
pour appliquer un changement de config, alors qu'il tourne LUI-MEME dans ce
gateway. Il tue son propre tour, et ceux des autres topics en pleine reflexion.

La consigne existait deja, ecrite deux fois dans contexte/projets/hermes.md.
Elle n'a pas tenu : une fiche lue a la demande ne protege pas un reflexe.
Ce hook la rend structurelle. Il ne conseille pas, il refuse.

Sortie d'urgence, quand le redemarrage immediat est reellement voulu :
prefixer la commande de `REDEMARRAGE_ASSUME=1 `.
"""
import json
import re
import sys

# Ce qui decapite le gateway, sous toutes ses formes.
DANGER = re.compile(
    r"""(
        systemctl\s+(--user\s+)?(restart|stop|kill)\s+\S*hermes-gateway
      | p''kill\s+.*hermes[-_]?gateway
      | killall\s+.*hermes[-_]?gateway
      | kill\s+.*gateway\.pid
      | hermes\s+(restart|stop)\b
    )""".replace("''", ""),
    re.X | re.I,
)

# Le geste correct, et les fichiers qui ont le droit de parler du geste interdit.
EXEMPT = re.compile(
    r"(redem-sur\.sh|redemarrer-gateway-au-calme\.sh|REDEMARRAGE_ASSUME=1"
    r"|garde-gateway\.py|hermes\.md|JOURNAL\.md)",
    re.I,
)

MOTIF = """Refus : cette commande tue le gateway dans lequel tu es en train de parler.

Mesure du 2026-08-31 : 64 tours coupes en 7 jours par ce geste. Le gateway met
60 a 90 s a s'arreter, il attend le `claude` qui redige, et finit au SIGKILL :
la reponse en cours est perdue, et celles des autres topics avec elle.

Le geste correct, le SEUL script : il attend la fin de TOUS les tours en
cours, sans limite de temps, puis redemarre (alerte au QG apres 45 min) :

  setsid nohup ~/.hermes/scripts/redem-sur.sh >/dev/null 2>&1 </dev/null &

Journal : /tmp/redem-sur.log. Detail : contexte/projets/hermes.md.

Avant meme ca, verifie que le redemarrage est necessaire : `agent.reasoning_effort`,
`gateway_model_overrides.json` et les settings de `claude -p` se lisent a chaud.

Si le redemarrage immediat est vraiment voulu : prefixe de `REDEMARRAGE_ASSUME=1 `."""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd or not DANGER.search(cmd) or EXEMPT.search(cmd):
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": MOTIF,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
