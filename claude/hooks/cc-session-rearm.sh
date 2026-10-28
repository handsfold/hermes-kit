#!/usr/bin/env bash
# SessionStart : RÉARME le renommage automatique, sans renommer lui-même.
# Le prochain prompt redonnera son nom à la session (cf cc-session-label.sh).
#
# Réarmé sur startup / clear UNIQUEMENT : les deux seuls cas où le sujet de la
# conversation repart vraiment de zéro.
#
# `resume` en était jusqu'au 2026-08-05, à tort : rouvrir une conversation ne
# change pas ce dont elle parle, exactement comme `compact`. Or un redémarrage
# du PC relance tout par `cc up --continue`, donc `resume` : chaque reboot
# réarmait les neuf sessions, et le prompt suivant les renommait toutes sur un
# sujet pris au hasard du moment (« attente-de », « tokens-restants »,
# « selection-morceaux » posés en neuf secondes le 05/08 à 00:52). USER voyait sa
# session se renommer une fois de plus à chaque redémarrage.
#
# Note : un /clear change PARFOIS le session_id, parfois non (les deux cas
# observés le 2026-07-31). Quand il change, le nouvel id n'a de toute façon pas
# de drapeau ; quand il ne change pas, c'est ce réarmement qui débloque.
input=$(cat)
src=$(printf '%s' "$input" | jq -r '.source // empty')

source "$HOME/.claude/lib/cc-label.sh"

sid=$(printf '%s' "$input" | jq -r '.session_id // empty')
dir="$HOME/.claude/.cc-labeled"
# Le drapeau porte la clé du PROCESS (stable d'une compaction à l'autre), pas
# celle de la conversation ; l'ancien format part avec, le temps de la bascule.
key=$(cc_session_key "$sid")

case "$src" in
  startup|clear)
    rm -f "$dir/$key" "$dir/$key.name" "$dir/$key.prompt" "$dir/$key.tries" "$dir/$key.suite"
    [ -n "$sid" ] && [ "$key" != "$sid" ] && rm -f "$dir/$sid" "$dir/$sid.prompt"
    ;;
  resume|compact)
    # Reprise d'une conversation en cours. On ne réarme pas, et on laisse une
    # trace pour que le hook de nommage ADOPTE le nom déjà porté au lieu d'en
    # inventer un : le transcript n'est pas encore stable à cet instant, la
    # lecture du nom se fait donc plus tard, au premier prompt.
    : > "$dir/$key.suite"
    ;;
  *) exit 0 ;;
esac

# hygiène : les drapeaux des sessions oubliées depuis une semaine
find "$dir" -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null
exit 0
