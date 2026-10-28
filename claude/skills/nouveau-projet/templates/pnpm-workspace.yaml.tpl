# Chaîne de dépendances : les garde-fous de pnpm.
#
# Pourquoi ce fichier existe. Un `npm install` exécute les scripts
# preinstall/install/postinstall de TOUTE la fermeture transitive, sans que le
# paquet soit jamais importé dans le code. En août 2026, plusieurs paquets très
# répandus ont été compromis par cette voie, dont des dépendances profondes
# d'ESLint : le code injecté cherchait des clés AWS, des jetons GitHub et des
# portefeuilles crypto. Un projet qui n'utilise « que trois librairies » en
# installe deux cents.
#
# Les valeurs ci-dessous ne sont pas des préférences : chacune ferme une porte
# précise. Toutes les clés sont en camelCase, vérifiées sur pnpm.io le
# 2026-08-24 pour pnpm 11. Une clé mal orthographiée est ignorée EN SILENCE :
# ne rien renommer sans revérifier la doc.
# https://pnpm.io/settings/dependency-resolution

# ── 1. Délai avant d'accepter une version fraîche ────────────────────────────
# Le seul garde-fou qui protège d'un paquet compromis CE MATIN. Un audit ne
# voit que les failles déjà publiées ; ici on laisse simplement le temps à la
# communauté et aux outils de détection de repérer l'attaque avant nous.
# 10080 minutes = 7 jours. Défaut de pnpm 11 : 1440 (un seul jour).
minimumReleaseAge: 10080
# Aucune version de la plage n'a l'âge requis : on ÉCHOUE, on ne se rabat pas
# en silence sur une version trop jeune. Sans ça, la règle du dessus devient
# une suggestion.
minimumReleaseAgeStrict: true
# Un paquet dont le registre ne publie pas de date de publication ne peut pas
# être daté, donc pas jugé. Le défaut de pnpm (true) le laisse passer ; ici on
# refuse. À repasser à true seulement si un registre privé ou un miroir est en
# jeu, et en le notant.
minimumReleaseAgeIgnoreMissingTime: false
# Exemptions, une par ligne, avec la DATE et la RAISON. Toute ligne ajoutée ici
# est une porte rouverte : elle se justifie, ou elle se retire.
# minimumReleaseAgeExclude:
#   - "@monorg/*"

# ── 2. Confiance de publication ─────────────────────────────────────────────
# Un paquet publié jusqu'ici par un « trusted publisher » (CI, OIDC, provenance
# attestée) qui se met soudain à sortir sans provenance : c'est la signature
# d'un compte de mainteneur volé. no-downgrade fait échouer l'installation.
trustPolicy: no-downgrade
# Le lock n'est PAS considéré comme déjà vérifié : chaque install revérifie
# l'âge et la confiance. À laisser tel quel dès qu'un tiers peut toucher au lock.
trustLockfile: false

# ── 3. Sources exotiques dans les dépendances profondes ─────────────────────
# Une dépendance directe peut légitimement venir d'un dépôt git : c'est un
# choix conscient. Une dépendance transitive qui va chercher une archive
# arbitraire ou un dépôt git, jamais : c'est du code hors registre, sans
# somme de contrôle, modifiable après coup.
blockExoticSubdeps: true

# ── 4. Scripts d'installation ───────────────────────────────────────────────
# LE point qui compte le plus. strictDepBuilds fait échouer l'installation si
# une dépendance porte un script de build non revu, au lieu d'un avertissement
# qu'on ne lit pas.
strictDepBuilds: true
# allowBuilds remplace onlyBuiltDependencies, supprimé en pnpm 11. Tout ce qui
# n'est pas listé ici est INTERDIT. On n'approuve qu'après avoir regardé ce que
# le script fait, et jamais « pour que ça passe » :
#   pnpm approve-builds            (interactif, écrit dans ce bloc)
#   pnpm approve-builds esbuild '!core-js'
# allowBuilds:
#   esbuild: true

# ── 5. Audit ────────────────────────────────────────────────────────────────
# Section `audit`, et pas la clé auditLevel, dépréciée depuis pnpm 11.16.
# Rappel : un audit n'est pas un antivirus. Il liste les failles CONNUES et
# publiées, il ne verra jamais un paquet compromis hier. C'est le délai de
# 7 jours ci-dessus qui couvre ce trou, pas cette section.
audit:
  level: high
  # Chaque GHSA ignoré porte sa date et sa raison, sinon la liste devient une
  # façon de ne plus rien voir.
  # ignore:
  #   - GHSA-xxxx-xxxx-xxxx
