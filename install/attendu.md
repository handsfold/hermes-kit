# What a well configured machine owns

Format: `- item => \`command\``. The command returns 0 when the item is there.
`hk doctor` reads this file and runs every command (ok or KO).
`hk reparer` hands it to Claude Code, which aligns the machine on it.
The variables `$HOME`, `$HERMES_HOME` and `$HK_HOME` are known to the commands.

## Claude Code (~/.claude)

- Global CLAUDE.md, kit block between markers => `grep -q 'HERMES-KIT:DEBUT' "$HOME/.claude/CLAUDE.md" && grep -q 'HERMES-KIT:FIN' "$HOME/.claude/CLAUDE.md"`
- RTK.md (imported by CLAUDE.md) => `test -s "$HOME/.claude/RTK.md"`
- Output style clair.md => `test -s "$HOME/.claude/output-styles/clair.md"`
- settings.json: valid JSON => `jq -e . "$HOME/.claude/settings.json"`
- settings.json: key outputStyle => `jq -e '.outputStyle' "$HOME/.claude/settings.json"`
- settings.json: key hooks (PreToolUse) => `jq -e '.hooks.PreToolUse | length > 0' "$HOME/.claude/settings.json"`
- settings.json: key statusLine => `jq -e '.statusLine.command' "$HOME/.claude/settings.json"`
- settings.json: key enabledPlugins => `jq -e '.enabledPlugins | length > 0' "$HOME/.claude/settings.json"`
- Hook outil-existant => `test -f "$HOME/.claude/hooks/outil-existant.py"`
- Hook agent-fond-guard => `test -f "$HOME/.claude/hooks/agent-fond-guard.py"`
- Analysis tools (8 scripts) => `test "$(ls "$HOME"/.claude/outils/*.py | wc -l)" -ge 8`
- Claude Code agents => `test -d "$HOME/.claude/agents"`
- Statusline => `test -f "$HOME/.claude/statusline-command.sh"`
- Skill nouveau-projet => `test -f "$HOME/.claude/skills/nouveau-projet/SKILL.md"`
- Skill r => `test -f "$HOME/.claude/skills/r/SKILL.md"`
- Skill forget => `test -f "$HOME/.claude/skills/forget/SKILL.md"`
- Skill update-all-skills => `test -f "$HOME/.claude/skills/update-all-skills/SKILL.md"`

## Claude Code plugins

- Plugin frontend-design => `claude plugin list 2>&1 | grep -q frontend-design`
- Plugin claude-mem => `claude plugin list 2>&1 | grep -q claude-mem`
- Plugin claude-hud => `claude plugin list 2>&1 | grep -q claude-hud`
- Plugin token-optimizer => `claude plugin list 2>&1 | grep -q token-optimizer`

## Hermes (~/.hermes)

- Hermes installed (venv binary) => `test -x "$HERMES_HOME/hermes-agent/venv/bin/hermes"`
- config.yaml readable => `test -s "$HERMES_HOME/config.yaml"`
- .env in mode 600 => `test "$(stat -c %a "$HERMES_HOME/.env" 2>/dev/null || stat -f %Lp "$HERMES_HOME/.env")" = 600`
- .env : TELEGRAM_BOT_TOKEN set => `grep -q '^TELEGRAM_BOT_TOKEN=.' "$HERMES_HOME/.env"`
- .env : HERMES_GATEWAY_TOKEN set => `grep -q '^HERMES_GATEWAY_TOKEN=.' "$HERMES_HOME/.env"`
- gateway_model_overrides.json => `jq -e . "$HERMES_HOME/gateway_model_overrides.json"`
- QG address => `jq -e '.chat and .thread' "$HERMES_HOME/qg-adresse.json"`
- Hermes scripts (qg.py) => `test -f "$HERMES_HOME/scripts/qg.py"`
- Hermes skills => `test -d "$HERMES_HOME/skills/dev/verifier-avant-livraison"`
- Skill auto-jailbreak => `test -f "$HERMES_HOME/skills/productivity/auto-jailbreak/SKILL.md"`
- Hermes plugin telegram-menus (/menu, /supp) => `test -d "$HERMES_HOME/plugins/telegram-menus"`
- Hermes plugin mode-objectif => `test -d "$HERMES_HOME/plugins/mode-objectif"`
- Hermes plugin aiguilleur (skill chosen before the model) => `test -d "$HERMES_HOME/plugins/aiguilleur" && test -f "$HERMES_HOME/scripts/hk-aiguilleur.py"`
- Plugins enabled in the config => `grep -q 'telegram-menus' "$HERMES_HOME/config.yaml" && grep -q 'mode-objectif' "$HERMES_HOME/config.yaml"`
- Hermes on the tested tag v2026.9.14 (official, or patched on top) => `git -C "$HERMES_HOME/hermes-agent" merge-base --is-ancestor 345cd2b057a452236de401d3534b8502a7465e8d HEAD`
- Menu language set (key langue, en or fr) => `jq -e '.langue == "en" or .langue == "fr"' "$HERMES_HOME/telegram-menus.json"`
- QG topics declared (dm_topics in config.yaml) => `grep -q 'dm_topics' "$HERMES_HOME/config.yaml"`
- Safe update tool => `test -x "$HERMES_HOME/scripts/hermes-maj-sure.sh"`
- Protected settings placed => `test -s "$HERMES_HOME/maj/reglages-proteges.yaml"`
- Crons: 9 installed => `jq -e '.jobs | length == 9' "$HERMES_HOME/cron/jobs.json"`
- Crons: 3 active (watcher, QG digest, kit statistics, silent without token or consent), 7 paused => `jq -e '[.jobs[] | select(.enabled)] | length == 3' "$HERMES_HOME/cron/jobs.json"`
- Statistics script placed => `test -x "$HERMES_HOME/scripts/hk-telemetrie.py"`
- Claude Code permissions set (no bypass mode, destructive actions asked) => `jq -e '.permissions.defaultMode != "bypassPermissions" and (.permissions.ask|length>0)' ~/.claude/settings.json`

## Kit, commands and services

- Kit repository => `test -f "$HK_HOME/MANIFESTE.txt"`
- Proxy: server.js present => `test -f "$HK_HOME/proxy/server.js"`
- Proxy: npm dependencies installed => `test -d "$HK_HOME/proxy/node_modules"`
- hk command in the PATH => `test -x "$HOME/.local/bin/hk"`
- focus command => `test -e "$HOME/.local/bin/focus"`
- rtk installed => `command -v rtk`
- Proxy service (systemd or launchd) => `case "$(uname -s)" in Darwin) launchctl list | grep -q hermeskit;; *) test ! -d /run/systemd/system || systemctl --user is-active --quiet claude-proxy.service;; esac`
- Hermes gateway service (systemd) => `case "$(uname -s)" in Darwin) true;; *) test ! -d /run/systemd/system || systemctl --user is-active --quiet hermes-gateway.service;; esac`

## Browser and mailbox

- opencli installed => `command -v opencli`
- OpenCLI Chrome extension connected => `opencli doctor 2>/dev/null | grep -q 'Extension: connected'`
- hk-boite installed => `test -x "$HOME/.local/bin/hk-boite"`
- Skill boite-mail => `test -f "$HERMES_HOME/skills/productivity/boite-mail/SKILL.md"`
