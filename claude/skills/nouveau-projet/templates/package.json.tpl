{
  "name": "@@PKG@@",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "packageManager": "pnpm@11.22.0",
  "scripts": {
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "check": "bash scripts/check.sh",
    "audit": "pnpm audit --audit-level high"
  },
  "_scripts_pourquoi": [
    "Pas de --passWithNoTests : il fait passer une suite vide en silence.",
    "Ces scripts sont appelés par scripts/check.sh, qui reste LE filet.",
    "packageManager épingle pnpm : corepack refuse alors un autre gestionnaire.",
    "Version choisie stable et déjà publiée depuis plus d'une semaine, jamais la dernière."
  ],
  "devDependencies": {}
}
