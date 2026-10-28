#!/usr/bin/env bash
# UserPromptSubmit : au PREMIER prompt d'un cycle (démarrage, resume ou /clear),
# renomme la session « <dossier> · <sujet du prompt> · <modèle>-<effort> ».
#
# Pourquoi ici et pas au /clear : le nom doit décrire ce sur quoi USER travaille,
# et c'est sa demande qui le dit, pas le moment où il vide l'écran.
#
# Ce hook doit rendre la main tout de suite : il se contente de repérer le pane,
# de poser le drapeau et de déléguer au worker détaché, qui lui prendra son temps
# (résumé Haiku, attente d'une fenêtre de repos dans la TUI).
input=$(cat)

# Sous-claude lancé pour résumer le prompt : ne surtout pas se renommer soi-même.
[ -z "${CC_LABEL_CHILD:-}" ] || exit 0
# /rename se tape dans la TUI : sans tmux, aucun moyen de l'envoyer.
[ -n "${TMUX:-}" ] || exit 0

sid=$(printf '%s' "$input" | jq -r '.session_id // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
tp=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
prompt=$(printf '%s' "$input" | jq -r '.prompt // empty')
[ -n "$sid" ] && [ -n "$cwd" ] && [ -n "$prompt" ] || exit 0

# Une commande slash n'est pas une demande : elle ne dit rien du sujet et donnait
# des noms creux (« dj · commande-inconnue »). On laisse la main au vrai prompt
# suivant, sans consommer le drapeau.
case "$prompt" in /*) exit 0 ;; esac

# Coller une capture émet DEUX prompts : le vrai texte, puis un pseudo-prompt
# « [Image: original 968x2376, displayed at …] » quatre secondes plus tard. Ce
# second ne décrit aucun sujet (Haiku en tire « je-ne »), il était donc refusé et
# consommait un des trois essais. USER travaillant beaucoup par captures, trois
# d'affilée suffisaient à faire abandonner le nommage. Constaté le 2026-08-05.
case "$prompt" in "[Image:"*) exit 0 ;; esac

# Ciblage par FILIATION uniquement (jamais l'env TMUX_PANE, cf tirs croisés du
# 2026-07-24) : on remonte jusqu'au process Claude, puis jusqu'au pane qui le
# contient. Session imbriquée (sous-agent, bg) → abandon.
source "$HOME/.claude/lib/cc-label.sh"

panes=$(tmux list-panes -a -F '#{pane_pid} #{pane_id}' 2>/dev/null)
anc=$PPID; mypane=""; sfile=""
for _ in 1 2 3 4 5 6 7 8; do
  # le store, quand il existe, donne au worker l'état busy/idle de la session ;
  # certaines sessions n'en ont pas (lancées avant qu'il existe) et doivent
  # quand même être nommées, donc il ne conditionne plus le ciblage
  [ -z "$sfile" ] && [ -f "$HOME/.claude/sessions/$anc.json" ] \
    && sfile="$HOME/.claude/sessions/$anc.json"
  mypane=$(printf '%s' "$panes" | awk -v p="$anc" '$1==p{print $2; exit}')
  [ -n "$mypane" ] && break
  anc=$(ps -o ppid= -p "$anc" 2>/dev/null | xargs)
  [ -z "$anc" ] || [ "$anc" -le 1 ] && exit 0
done
[ -n "$mypane" ] || exit 0
# Un claude non interactif lancé dans un pane (SDK, observer, script) ne doit
# pas renommer la fenêtre de son hôte. Sans store, on ne peut pas trancher :
# on accepte, c'est le cas des vieilles sessions légitimes.
if [ -n "$sfile" ]; then
  kind=$(jq -r '"\(.kind // "")/\(.entrypoint // "")"' "$sfile" 2>/dev/null)
  [ "$kind" = "interactive/cli" ] || exit 0
else
  sfile="-"
fi

# Drapeau atomique : un seul renommage par cycle, même si le hook part deux fois
# (le double /rename observé jusqu'au 2026-07-31 venait de là).
# Indexé sur le PID du process claude, PAS sur le session_id : celui-ci change à
# chaque compaction, et le drapeau perdu faisait re-renommer la session en plein
# milieu d'une conversation (cf cc_session_key).
dir="$HOME/.claude/.cc-labeled"; mkdir -p "$dir"
key=$(cc_session_key "$sid")
flag="$dir/$key"

# ── Adoption : une conversation reprise garde le nom qu'elle porte déjà ───────
# Ces drapeaux sont indexés sur le PID, donc ils NE SURVIVENT PAS au redémarrage
# du PC. Sans ce bloc, une session rouverte paraissait n'avoir jamais été nommée
# et se faisait renommer une fois de plus à chaque reboot, sur le sujet du
# premier prompt venu. On lit donc le nom RÉELLEMENT porté : s'il est déjà des
# nôtres et posé sur un vrai sujet, on se contente de le reprendre à notre
# compte. Un nom d'origine (« hote-08 ») ou provisoire (« dj · fix · o5-xh »)
# n'est pas conforme et laisse le renommage se faire, comme avant.
# Le marqueur .suite est posé par cc-session-rearm.sh sur resume/compact ; son
# absence signale un /clear ou un vrai démarrage, où le sujet doit être refait.
if [ -e "$flag.suite" ] && [ ! -e "$flag.name" ]; then
  porte=$(cc_live_title "$sfile" "$tp")
  if cc_title_conforme "$porte" "$cwd"; then
    printf '%s' "$porte" > "$flag.name"
    : > "$flag"
    rm -f "$flag.suite" "$flag.tries"
    exit 0
  fi
fi

# Auto-réparation : un worker mort AVANT d'écrire le nom laissait ce drapeau en
# place, et le hook ressortait à chaque prompt suivant → session condamnée à
# rester anonyme pour toujours (4 sessions dans cet état le 2026-08-04, la plus
# ancienne bloquée depuis deux jours). On ne ressort donc que si le nom a bien
# été posé, ou si le drapeau est trop récent pour qu'un worker ait pu échouer.
# Un double départ du hook se joue en millisecondes, très loin des 2 minutes
# ci-dessous : la protection anti-double-renommage du 2026-07-31 reste entière.
if ! (set -o noclobber; : > "$flag") 2>/dev/null; then
  [ -e "$flag.name" ] && exit 0
  find "$flag" -maxdepth 0 -mmin +2 2>/dev/null | grep -q . || exit 0
  : > "$flag"   # relance le compteur : au pire une tentative toutes les 2 min
fi

# Le worker rend la main sans renommer quand le prompt ne décrit aucun sujet
# (« continue »), en effaçant le drapeau pour retenter au prompt suivant. Au
# 3ᵉ essai on renonce : le nom en place vaut mieux qu'un nom au hasard.
if [ "$(cat "$flag.tries" 2>/dev/null || echo 0)" -ge 3 ] 2>/dev/null; then
  exit 0
fi

# Le prompt passe par fichier : ni échappement ni limite de longueur d'argument.
pf="$dir/$key.prompt"
printf '%s' "$prompt" > "$pf"

setsid bash "$HOME/.claude/hooks/cc-session-label-worker.sh" \
  "$mypane" "$cwd" "$tp" "$pf" "$sfile" "$key" >/dev/null 2>&1 < /dev/null &
exit 0
