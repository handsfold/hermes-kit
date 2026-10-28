# Artefacts de session : jamais versionnés
artifacts/

# Secrets
.env
.env.*
!.env.example

# Réglages Claude Code personnels
.claude/settings.local.json
.claude/deploy_status.json
.claude/.deploy_reported
.claude/deploy.log

# Python
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/

# Node
node_modules/

# Le fichier lock N'EST PAS ignoré : il se commite. C'est lui qui fige les
# dépendances transitives et rend l'installation reproductible.
# Les locks d'un AUTRE gestionnaire, en revanche, n'ont rien à faire ici.
package-lock.json
yarn.lock
dist/
.vite/

# Divers
.DS_Store
