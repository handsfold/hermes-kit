#!/usr/bin/env bash
# Stop : quand le tour qui vient de finir était un `/r`, renomme la conversation
# d'après la PHRASE DE RÉSUMÉ produite.
#
# Pourquoi : le nommage ordinaire déduit le sujet du PREMIER prompt d'un cycle,
# ce qui vieillit mal sur une longue conversation qui a dérivé. `/r` produit
# justement, en une phrase, ce dont la session parle VRAIMENT maintenant : la
# meilleure source de sujet qui existe, et explicitement demandée par USER. Le
# renommage reste donc SON geste, pas une dérive automatique, ce qui préserve la
# règle « cc-reconcile ne recalcule jamais le sujet d'une session déjà nommée ».
#
# Ce hook ne fait que REPÉRER et déléguer : le résumé Haiku, l'attente du repos
# et la frappe unique restent au worker détaché. Un hook Stop peut être tué quand
# le tour se termine ; rien de lent ne doit tourner ici.
input=$(cat)

# Sous-claude lancé pour résumer un prompt : ne jamais se renommer soi-même.
[ -z "${CC_LABEL_CHILD:-}" ] || exit 0
# /rename se tape dans la TUI : sans tmux, aucun moyen de l'envoyer.
[ -n "${TMUX:-}" ] || exit 0

sid=$(printf '%s' "$input" | jq -r '.session_id // empty')
tp=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
[ -n "$sid" ] && [ -r "$tp" ] || exit 0

source "$HOME/.claude/lib/cc-label.sh"

# Le tour qui vient de finir était-il un `/r` ? Sortie non nulle (donc abandon)
# dans tous les autres cas : ce hook part à CHAQUE fin de tour.
python3 - "$tp" <<'PY' 2>/dev/null || exit 0
import json, os, sys
# Seule la fin du fichier compte, et un transcript atteint couramment 14 Mo :
# un hook Stop part à chaque tour, il n'a pas le droit de tout relire.
p = sys.argv[1]; sz = os.path.getsize(p); f = open(p, "rb")
if sz > 4_000_000:
    f.seek(sz - 4_000_000); f.readline()   # rebut de la ligne coupée
msgs = []
for raw in f:
    try: o = json.loads(raw.decode("utf-8", "replace"))
    except Exception: continue
    t = o.get("type")
    if t not in ("user", "assistant"): continue
    c = o.get("message", {}).get("content")
    if isinstance(c, list):
        c = " ".join(b.get("text", "") for b in c
                     if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(c, str) or not c.strip(): continue
    msgs.append((t, " ".join(c.split())))
# ATTENTION : quand ce hook part, la réponse finale de l'assistant n'est PAS
# encore écrite dans le transcript (vérifié le 2026-08-06 : exiger un message
# d'assistant en dernière position faisait échouer le hook à tous les coups,
# alors qu'il marchait sur les mêmes fichiers relus après coup). On ignore donc
# ce qui traîne en fin de fichier côté assistant, et on examine le DERNIER bloc
# utilisateur contigu : `/r` y arrive en deux messages, l'invocation puis le
# corps de la skill. Un tour ordinaire met un autre texte dans ce bloc, donc
# aucun risque de rejouer un vieux `/r`.
i = len(msgs) - 1
while i >= 0 and msgs[i][0] == "assistant": i -= 1
vu = False
while i >= 0 and msgs[i][0] == "user":
    if "command-name>/r<" in msgs[i][1]: vu = True
    i -= 1
sys.exit(0 if vu else 1)
PY

# La phrase vient de la charge utile, pas du transcript : Claude Code la fournit
# telle quelle dans `last_assistant_message`, sans attendre l'écriture du fichier.
phrase=$(printf '%s' "$input" | jq -r '.last_assistant_message // empty' | tr '\n' ' ')
[ -n "$phrase" ] || exit 0

# Le gabarit de `/r` colle CE QUI RESTE en fin de phrase, après « ; reste » ou
# « , reste ». Le sujet de la session est ce qui a été FAIT, pas la suite : sans
# cette coupe, « …vérifié sur cinq scénarios ; reste le hook Stop » donnait
# « dj · hook-stop », c'est-à-dire le nom du travail qu'on n'a PAS fait.
phrase=$(printf '%s' "$phrase" | sed -E 's/[;,][^;,]*\breste\b.*$//')

# Ciblage par FILIATION, comme cc-session-label.sh : jamais l'env TMUX_PANE.
panes=$(tmux list-panes -a -F '#{pane_pid} #{pane_id}' 2>/dev/null)
anc=$PPID; pane=""; sfile=""
for _ in 1 2 3 4 5 6 7 8; do
  [ -z "$sfile" ] && [ -f "$HOME/.claude/sessions/$anc.json" ] \
    && sfile="$HOME/.claude/sessions/$anc.json"
  pane=$(printf '%s' "$panes" | awk -v p="$anc" '$1==p{print $2; exit}')
  [ -n "$pane" ] && break
  anc=$(ps -o ppid= -p "$anc" 2>/dev/null | xargs)
  [ -z "$anc" ] || [ "$anc" -le 1 ] && exit 0
done
[ -n "$pane" ] || exit 0
# Un claude non interactif (SDK, observer) ne renomme pas la fenêtre de son hôte.
if [ -n "$sfile" ]; then
  [ "$(jq -r '"\(.kind // "")/\(.entrypoint // "")"' "$sfile" 2>/dev/null)" \
    = "interactive/cli" ] || exit 0
else
  sfile="-"
fi
[ -n "$cwd" ] || cwd=$(readlink "/proc/$anc/cwd" 2>/dev/null)
[ -n "$cwd" ] || exit 0

dir="$HOME/.claude/.cc-labeled"; mkdir -p "$dir"
key=$(cc_session_key "$sid")

# Une phrase déjà traitée ne relance rien : le hook Stop repart à chaque tour, et
# d'autres échanges peuvent suivre un `/r` sans que sa phrase change.
emp=$(printf '%s' "$phrase" | cksum | cut -d' ' -f1)
[ "$(cat "$dir/$key.rsum" 2>/dev/null)" = "$emp" ] && exit 0
printf '%s' "$emp" > "$dir/$key.rsum"

# Le drapeau est repris de force : c'est un ordre de USER, il prime sur le nom déjà
# posé pour ce cycle. Les essais refusés repartent de zéro pour la même raison.
# La trace `.name`, elle, reste EN PLACE : le worker ne la consulte pas, il la
# réécrit après avoir tapé. L'effacer d'avance ferait passer la session pour
# jamais nommée si le worker échouait, et cc-reconcile lui recollerait alors le
# sujet du premier prompt du cycle, c'est-à-dire l'ancien nom qu'on remplace.
printf '%s' "$phrase" > "$dir/$key.prompt"
: > "$dir/$key"
rm -f "$dir/$key.tries"

setsid bash "$HOME/.claude/hooks/cc-session-label-worker.sh" \
  "$pane" "$cwd" "$tp" "$dir/$key.prompt" "$sfile" "$key" >/dev/null 2>&1 < /dev/null &
exit 0
