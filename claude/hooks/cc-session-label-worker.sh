#!/usr/bin/env bash
# Partie lente du renommage, détachée du hook : résume le prompt, compose le
# label, puis attend que la session soit VRAIMENT au repos pour taper /rename.
# Usage : worker.sh <pane> <cwd> <transcript.jsonl> <prompt.txt> <session.json>
#                   <clé> [label déjà composé]
# Le 7ᵉ argument sert au renommage d'une session déjà en cours, dont le sujet ne
# se lit pas dans un premier prompt : l'appelant compose le label, on ne fait
# plus qu'attendre le repos et taper.
set -u
source "$HOME/.claude/lib/cc-label.sh"

pane="$1"; cwd="$2"; tp="$3"; pf="$4"; store="$5"; key="$6"; label="${7:-}"
dir="$HOME/.claude/.cc-labeled"

if [ -z "$label" ]; then
  prompt=$(cat "$pf" 2>/dev/null); rm -f "$pf"
  [ -n "$prompt" ] || exit 0
  subject=$(cc_subject "$prompt")
  # « continue », « oui », « fix » : le prompt ne dit pas sur quoi on travaille.
  # On rend le drapeau pour retenter au prompt suivant, en comptant les essais,
  # plutôt que de poser un nom qui ne veut rien dire.
  if ! cc_subject_valide "$subject"; then
    printf '%s' "$(( $(cat "$dir/$key.tries" 2>/dev/null || echo 0) + 1 ))" > "$dir/$key.tries"
    rm -f "$dir/$key"
    exit 0
  fi
  # Modèle et effort lus APRÈS le résumé : à cet instant le transcript porte au
  # moins une ligne assistant du tour en cours, donc les vraies valeurs.
  label="$(cc_folder_tag "$cwd") · $subject · $(cc_model_tag "$tp")"
fi

# Repos = "status":"idle" dans le store, écrit par Claude Code lui-même.
# NE PAS se fier au texte « esc to interrupt » du pane : sous 60 colonnes il est
# tronqué, le pane paraît au repos et /rename part au milieu d'un tour (cause du
# double renommage constaté jusqu'au 2026-07-31, pane de 48 colonnes).
_idle() {
  if [ -r "$store" ]; then
    [ "$(jq -r '.status // ""' "$store" 2>/dev/null)" = "idle" ]; return
  fi
  # Sessions lancées avant l'existence du store (ex. dj-modifs) : on retombe sur
  # le pane, en guettant la ligne d'activité « (2m 11s · ↓ 7.2k tokens) », qui
  # elle survit à un pane étroit, contrairement à « esc to interrupt ».
  ! tmux capture-pane -t "$pane" -p 2>/dev/null | tail -8 | grep -qE '·.*(tokens|jetons)\)'
}

# Ligne de saisie vide : ne jamais coller /rename dans un prompt en cours de
# frappe (le nbsp de la TUI est ramené à un espace avant le test).
# La fenêtre était à 6 lignes, calée sur une statusline d'UNE ligne : `❯` tombait
# alors en position 4. Depuis la greffe de claude-hud (2026-08-04) la statusline
# en occupe TROIS, ce qui pousse `❯` en position 6, pile sur la limite, et la
# moindre ligne de plus (« new task? /clear to save 328k tokens », un rendu qui
# passe à la ligne sous 48 colonnes) le faisait sortir de la fenêtre : le worker
# tournait ses 8 minutes sans jamais voir le prompt vide, et la session gardait
# son nom provisoire. 16 lignes laissent dix lignes de marge, et le motif reste
# strict (une ligne ne contenant QUE `❯`), donc aucun faux positif possible sur
# du texte de conversation.
_prompt_vide() {
  tmux capture-pane -t "$pane" -p 2>/dev/null | tail -16 \
    | sed 's/\xc2\xa0/ /g' | grep -qE '^\s*❯\s*$'
}

# UNE seule frappe, jamais de seconde tentative : c'est la garantie de non-double
# renommage que réclamait USER. Le champ "name" du store ne fait PAS foi pour
# vérifier (il reste au nom passé par --name dans certaines sessions), donc un
# réessai « au cas où » renommerait deux fois pour rien. Si la frappe se perd,
# le prochain cycle (resume ou /clear) remettra le bon nom.
for _ in $(seq 1 240); do              # 8 min : le temps d'un tour long
  sleep 2
  tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$pane" || exit 0
  if _idle && _prompt_vide; then
    # Texte et Entrée séparés : envoyés d'un bloc, la TUI perd le dernier
    # caractère sous charge (« o5-xh » arrivé en « o5-x » le 2026-07-31).
    tmux send-keys -t "$pane" "/rename $label" 2>/dev/null
    sleep 1
    tmux send-keys -t "$pane" Enter 2>/dev/null
    # trace du nom RÉELLEMENT posé : le store ne le reflète pas, et la
    # statusline en a besoin pour rafraîchir le seul suffixe modèle-effort
    printf '%s' "$label" > "$dir/$key.name"
    rm -f "$dir/$key.tries"
    exit 0
  fi
done
exit 0
