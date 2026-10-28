#!/usr/bin/env bash
# Test de ouvert-ferme.py : ferme ce que la session a ouvert, rien d'autre.
H=~/.claude/hooks/ouvert-ferme.py; S=test-$$; ok=0
python3 -m http.server 8771 >/dev/null 2>&1 & ANCIEN=$!      # nait AVANT la note : doit survivre
sleep 3.5
echo "{\"session_id\":\"$S\",\"tool_input\":{\"command\":\"python3 -m http.server 8772 &\"}}" | python3 $H note
python3 -m http.server 8772 >/dev/null 2>&1 & NOUVEAU=$!
python3 -m http.server 8773 >/dev/null 2>&1 & GARDE=$!        # autre session : doit survivre
sleep 1
echo "{\"session_id\":\"$S\"}" | python3 $H ferme; sleep 1
kill -0 $NOUVEAU 2>/dev/null && { echo "ECHEC : serveur de la session encore ouvert"; ok=1; }
kill -0 $ANCIEN 2>/dev/null || { echo "ECHEC : serveur plus ancien ferme a tort"; ok=1; }
kill $ANCIEN $GARDE $NOUVEAU 2>/dev/null
[ $ok = 0 ] && echo "OK 2 controles"; exit $ok
