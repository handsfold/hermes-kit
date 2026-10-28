#!/usr/bin/env bash
# forget-mem.sh : recherche et suppression dans les deux mémoires de Claude Code.
#   - Mémoire fichier : ~/.claude/projects/-home-poste/memory/  (MEMORY.md + fichiers .md)
#   - claude-mem      : ~/.claude-mem/claude-mem.db  (tables observations + session_summaries)
#
# Sous-commandes :
#   search   "<terme>"                 -> liste les correspondances des deux mémoires
#   show-obs <id> [<id>...]            -> affiche le détail d'observations claude-mem
#   del-obs  <id> [<id>...]            -> supprime des observations (backup auto)
#   del-sum  <id> [<id>...]            -> supprime des session_summaries (backup auto)
#
# La suppression des fichiers de mémoire fichier est faite par Claude (Edit/rm), pas ici.
set -euo pipefail

MEM_DIR="${CLAUDE_MEM_FILE_DIR:-$HOME/.claude/projects/-home-poste/memory}"
DB="${CLAUDE_MEM_DB:-$HOME/.claude-mem/claude-mem.db}"

# Échappe les apostrophes pour insertion sûre dans une chaîne SQL.
sql_escape() { printf '%s' "$1" | sed "s/'/''/g"; }

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

cmd_search() {
  local term="${1:-}"
  [ -z "$term" ] && { echo "Erreur: terme de recherche manquant." >&2; exit 2; }
  local esc; esc=$(sql_escape "$term")

  echo "############################################################"
  echo "# 1. MÉMOIRE FICHIER  ($MEM_DIR)"
  echo "############################################################"
  if [ -d "$MEM_DIR" ]; then
    echo "--- Fichiers dont le contenu correspond ---"
    grep -il -- "$term" "$MEM_DIR"/*.md 2>/dev/null | grep -v '/MEMORY.md$' || echo "(aucun)"
    echo "--- Lignes correspondantes dans MEMORY.md (index) ---"
    grep -in -- "$term" "$MEM_DIR/MEMORY.md" 2>/dev/null || echo "(aucune)"
  else
    echo "(dossier introuvable)"
  fi

  echo
  echo "############################################################"
  echo "# 2. CLAUDE-MEM : observations"
  echo "############################################################"
  sqlite3 -readonly "$DB" <<SQL || true
.mode table
.headers on
SELECT id, project, type, substr(COALESCE(title,''),1,60) AS title, date(created_at) AS jour
FROM observations
WHERE title LIKE '%$esc%' OR subtitle LIKE '%$esc%' OR narrative LIKE '%$esc%'
   OR facts LIKE '%$esc%' OR text LIKE '%$esc%' OR concepts LIKE '%$esc%'
ORDER BY created_at_epoch DESC
LIMIT 60;
SQL

  echo
  echo "############################################################"
  echo "# 3. CLAUDE-MEM : session_summaries"
  echo "############################################################"
  sqlite3 -readonly "$DB" <<SQL || true
.mode table
.headers on
SELECT id, project, substr(COALESCE(request,''),1,70) AS request, date(created_at) AS jour
FROM session_summaries
WHERE request LIKE '%$esc%' OR learned LIKE '%$esc%' OR completed LIKE '%$esc%'
   OR investigated LIKE '%$esc%' OR next_steps LIKE '%$esc%' OR notes LIKE '%$esc%'
ORDER BY created_at_epoch DESC
LIMIT 60;
SQL
}

cmd_show_obs() {
  [ "$#" -eq 0 ] && { echo "Erreur: id(s) manquant(s)." >&2; exit 2; }
  local ids; ids=$(printf '%s,' "$@"); ids=${ids%,}
  sqlite3 -readonly "$DB" <<SQL || true
.mode line
SELECT id, project, type, title, subtitle, narrative, facts, date(created_at) AS jour
FROM observations WHERE id IN ($ids);
SQL
}

_backup() {
  local bak="$DB.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$DB" "$bak"
  echo "Sauvegarde: $bak"
}

cmd_del_obs() {
  [ "$#" -eq 0 ] && { echo "Erreur: id(s) manquant(s)." >&2; exit 2; }
  local ids; ids=$(printf '%d,' "$@"); ids=${ids%,}
  _backup
  local before after
  before=$(sqlite3 "$DB" "SELECT COUNT(*) FROM observations WHERE id IN ($ids);")
  sqlite3 "$DB" "DELETE FROM observations WHERE id IN ($ids);"
  after=$(sqlite3 "$DB" "SELECT COUNT(*) FROM observations WHERE id IN ($ids);")
  echo "observations supprimées: $before (restantes correspondant aux ids: $after)"
}

cmd_del_sum() {
  [ "$#" -eq 0 ] && { echo "Erreur: id(s) manquant(s)." >&2; exit 2; }
  local ids; ids=$(printf '%d,' "$@"); ids=${ids%,}
  _backup
  local before
  before=$(sqlite3 "$DB" "SELECT COUNT(*) FROM session_summaries WHERE id IN ($ids);")
  sqlite3 "$DB" "DELETE FROM session_summaries WHERE id IN ($ids);"
  echo "session_summaries supprimées: $before"
}

case "${1:-}" in
  search)   shift; cmd_search "$@";;
  show-obs) shift; cmd_show_obs "$@";;
  del-obs)  shift; cmd_del_obs "$@";;
  del-sum)  shift; cmd_del_sum "$@";;
  *) usage;;
esac
