#!/usr/bin/env bash
# Eprouve journal-skills.py dans un HOME jetable. Sortie 1 si un cas echoue.
H=$(mktemp -d); HOOK=$HOME/.claude/hooks/journal-skills.py; ECHECS=0
envoi() { printf '%s' "$1" | HOME=$H python3 "$HOOK"; }
nb() { cat "$H"/.claude/journal-skills/*.jsonl 2>/dev/null | grep -c "$1"; }
verif() { if [ "$2" = "$3" ]; then echo "ok    $1"; else echo "ECHEC $1 : attendu $2, obtenu $3"; ECHECS=$((ECHECS+1)); fi; }
S='"session_id":"t1","cwd":"/tmp"'
envoi "{$S,\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"bonjour\"}"
verif "message sans skill : rien" 0 "$(nb '"t1"')"
envoi "{$S,\"hook_event_name\":\"PostToolUse\",\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"/a/b.md\"}}"
verif "lecture ordinaire : rien" 0 "$(nb '"t1"')"
envoi "{$S,\"hook_event_name\":\"PostToolUse\",\"tool_name\":\"Skill\",\"tool_input\":{\"skill\":\"plug:entreprise-a-index\"}}"
verif "outil Skill : chargement" 1 "$(nb '"charge".*"entreprise-a-index"')"
envoi "{$S,\"hook_event_name\":\"PostToolUse\",\"tool_name\":\"Read\",\"tool_input\":{\"file_path\":\"/x/fil/SKILL.md\"}}"
verif "lecture de SKILL.md : chargement" 1 "$(nb '"skill": "fil"')"
envoi "{$S,\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"[Vin] ça marche toujours pas\\n<memory-context>merci</memory-context>\"}"
verif "correction reperee" 1 "$(nb '"correction": true')"
verif "contexte injecte coupe" 0 "$(nb 'memory-context')"
envoi "{$S,\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"parfait merci\"}"
verif "message neutre" 1 "$(nb '"correction": false')"
envoi "{$S,\"hook_event_name\":\"PostToolUseFailure\",\"tool_name\":\"Bash\",\"error\":\"exit 1\"}"
verif "echec d'outil" 1 "$(nb '"echec"')"
envoi "{$S,\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"troisieme\"}"
envoi "{$S,\"hook_event_name\":\"UserPromptSubmit\",\"prompt\":\"quatrieme\"}"
verif "3 messages suivis au plus" 3 "$(nb '"prompt"')"
sortie=$(printf 'pas du json' | HOME=$H python3 "$HOOK"; echo "rc=$?")
verif "entree invalide : muet, exit 0" "rc=0" "$sortie"
rm -rf "${H:?}"; exit $((ECHECS>0))
