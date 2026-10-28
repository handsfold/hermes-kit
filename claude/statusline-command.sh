#!/usr/bin/env bash
input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd')
model=$(echo "$input" | jq -r '.model.display_name // .model.id // "?"')
sid=$(echo "$input" | jq -r '.session_id // empty')
eff=$(echo "$input" | jq -r '.effort.level // empty')
proj=$(basename "$cwd")

if [ -n "${TMUX:-}" ]; then
  # Titre de fenêtre (Wave) : imposé par set-titles-string, que le titre auto
  # de Claude Code ne peut pas écraser (il ne référence pas #T).
  sess=$(tmux display-message -p -t "${TMUX_PANE:-}" '#S' 2>/dev/null)
  [ -n "$sess" ] && tmux set-option -t "$sess" set-titles-string "$sess · $model · Claude Code" 2>/dev/null

  # ── Renommage AUTO côté claude.ai/mobile quand le modèle change ──────────
  # Ciblage par FILIATION DE PROCESSUS uniquement (jamais l'env TMUX_PANE,
  # héritée par les sessions bg d'un autre pane → tirs croisés vécus le
  # 2026-07-24). Une session sans pane à elle ne tape nulle part.
  if [ -n "$sid" ]; then
    # 1. chaîne d'ancêtres, du plus proche au plus lointain
    chain=""; p=$PPID
    for _ in 1 2 3 4 5 6 7 8; do
      { [ -z "$p" ] || [ "$p" -le 1 ]; } && break
      chain="$chain $p"
      p=$(ps -o ppid= -p "$p" 2>/dev/null | xargs)
    done

    # 2. NOTRE process claude : le store ~/.claude/sessions/<pid>.json quand il
    #    existe, sinon comm=claude. Claude Code purge ce store et ne le réécrit
    #    qu'au démarrage / changement de statut : une session idle depuis
    #    longtemps n'en a plus (constaté le 2026-07-28, panes dj-* muets) → on
    #    ne peut plus s'en servir comme unique point d'ancrage.
    cpid=""; sfile=""; nested=""
    for q in $chain; do
      f="$HOME/.claude/sessions/$q.json"
      is_claude=""
      [ -f "$f" ] && is_claude=1
      [ "$(ps -o comm= -p "$q" 2>/dev/null | xargs)" = "claude" ] && is_claude=1
      [ -z "$is_claude" ] && continue
      if [ -z "$cpid" ]; then
        cpid=$q; [ -f "$f" ] && sfile=$f
      else
        nested=1   # un claude AU-DESSUS du nôtre = session bg imbriquée :
        break      # jamais taper dans le pane de la session mère
      fi
    done

    # 3. ceinture : un store trouvé doit être celui de NOTRE session
    if [ -n "$sfile" ] && [ "$(jq -r '.sessionId // empty' "$sfile" 2>/dev/null)" != "$sid" ]; then
      sfile=""
    fi

    CONF="$HOME/.claude/cc-sessions.conf"
    cc_managed=""
    [ -n "$sess" ] && grep -qE "^${sess}\|" "$CONF" 2>/dev/null && cc_managed=1

    # Session gérée par cc : la conf doit toujours pointer la conversation
    # réellement affichée (un /clear ou /resume change le session-id).
    if [ -n "$cc_managed" ]; then
      old_id=$(grep -E "^${sess}\|" "$CONF" | head -1 | grep -oE '\-\-resume +[a-f0-9-]{36}' | grep -oE '[a-f0-9-]{36}')
      [ -n "$old_id" ] && [ "$old_id" != "$sid" ] && sed -i "s/$old_id/$sid/" "$CONF" 2>/dev/null
    fi

    # ── Rafraîchit le SEUL suffixe « modèle-effort » ─────────────────────────
    # La statusline imposait autrefois « <session tmux> · <modèle> » à chaque
    # rendu, en ancrant le nom sur la session tmux : tout nom ne commençant pas
    # par « dj-3 » était ramené de force à « dj-3 · Opus 5 ». Elle écrasait donc
    # le sujet posé par cc-session-label.sh et se battait avec lui, d'où les
    # renommages en double constatés jusqu'au 2026-07-31.
    # Elle ne décide plus du nom : elle ne fait que suivre un /model ou un
    # /effort, en remplaçant le dernier segment du nom que le hook a posé.
    # Trace indexée sur le PID du process claude, comme le drapeau du hook : le
    # session_id change à chaque compaction et emportait le nom avec lui.
    key="$sid"; [ -n "$cpid" ] && key="pid-$cpid"
    namef="$HOME/.claude/.cc-labeled/$key.name"
    stamp="/tmp/cc-suffix-$sid"; now=$(date +%s)
    last=$(cat "$stamp" 2>/dev/null || echo 0)
    # 2 s, pas 30 : le calcul ne coûte qu'une capture de pane, et un verrou long
    # ratait le seul rendu qui suivait un /effort, laissant le nom faux pour de
    # bon (une fenêtre au repos ne se redessine plus).
    if [ -n "$cpid" ] && [ -z "$nested" ] && [ -r "$namef" ] \
       && [ $((now - last)) -ge 2 ]; then
      echo "$now" > "$stamp"
      cur=$(cat "$namef")
      source "$HOME/.claude/lib/cc-label.sh"
      panes=$(tmux list-panes -a -F '#{pane_pid} #{pane_id}' 2>/dev/null)
      mypane=""
      for q in $chain; do
        mypane=$(echo "$panes" | awk -v p="$q" '$1==p{print $2; exit}')
        [ -n "$mypane" ] && break
      done
      # Claude Code nous donne le modèle ET l'effort courants à chaque rendu :
      # deux sources instantanées, alors que le transcript ne les porte qu'au
      # tour suivant et que le pane les affiche après coup (un cran de retard).
      target="${cur% · *} · $(cc_tag_from_display "$model" "$eff")"
      if [ "$target" != "$cur" ] && [ -n "$mypane" ]; then
        pane_txt=$(tmux capture-pane -t "$mypane" -p 2>/dev/null | tail -12 | sed 's/\xc2\xa0/ /g')
        # Seule condition : le prompt est vide, donc rien n'est en cours de
        # frappe. On ne vérifie PAS que le pane affiche encore notre nom : ce
        # qu'il affiche vient du fichier de session, qui garde souvent le nom de
        # lancement, et ce contrôle effaçait la trace des sessions à jour.
        if printf '%s' "$pane_txt" | grep -qE '^\s*❯\s*$'; then
          # détaché : la statusline ne doit jamais bloquer une seconde sur la
          # pause qui sépare le texte de la touche Entrée
          setsid bash -c "tmux send-keys -t '$mypane' '/rename $target'; sleep 1
                          tmux send-keys -t '$mypane' Enter" >/dev/null 2>&1 </dev/null &
          printf '%s' "$target" > "$namef"
        fi
      fi
    fi
  fi
else
  # Hors tmux : on pousse le titre nous-mêmes (peut brièvement alterner avec
  # le titre auto de Claude Code, la statusline reprend la main à chaque refresh).
  printf '\033]0;%s · %s\007' "$proj" "$model" > /dev/tty 2>/dev/null
fi

# ── Rendu : délégué à claude-hud (barre de contexte, outils, agents, todos) ──
# Le nommage automatique ci-dessus reste maison : /claude-hud:setup remplacerait
# statusLine par un appel direct au plugin et l'emporterait avec lui.
# Si le plugin manque, est désactivé ou échoue, on retombe sur l'ancien rendu.
hud="$HOME/.claude/plugins/marketplaces/claude-hud/dist/index.js"
hud_out=""
if [ -f "$hud" ] && command -v node >/dev/null 2>&1; then
  hud_out=$(printf '%s' "$input" | COLUMNS="${COLUMNS:-120}" node "$hud" 2>/dev/null)
fi

if [ -n "$hud_out" ]; then
  printf '%s' "$hud_out"
else
  # couleur par modèle : Fable=magenta, Opus=orange, Sonnet=cyan, Haiku=vert
  case "$model" in
    Fable*)  mcol='01;35' ;;
    Opus*)   mcol='01;38;5;208' ;;
    Sonnet*) mcol='01;36' ;;
    Haiku*)  mcol='01;32' ;;
    *)       mcol='01;37' ;;
  esac
  printf '\033[01;32m%s@%s\033[00m:\033[01;34m%s\033[00m \033[%sm[%s]\033[00m' "$(whoami)" "$(hostname -s)" "$cwd" "$mcol" "$model"
fi
