# Observabilité locale

## Installation vérifiée

- Bilan : `bilan-tokens` (coûts équivalents et facture d'abonnement séparés).
- Collecteur natif : http://127.0.0.1:4318/health ; journaux, métriques, spans.
- Suivi des compteurs Hermès : timer local toutes les 10 minutes, zéro modèle.
- Sauvegarde avant installation : `$HOME/.hermes/backups/observabilite-install-20261113-134635`.
- Tests : 29 tests réussis. Sortie conservée dans `$HOME/.hermes/cache/scratch/conso-unifiee-20261113/tests-final.txt`.
- Dernier bilan lisible : `$HOME/.hermes/cache/scratch/conso-unifiee-20261113/bilan-final.txt`.

## Limites à garder visibles

- Pas de somme entre Claude, proxy, Hermès et OpenTelemetry : ces vues se recouvrent.
- Montants API équivalents, pas argent réellement prélevé sur un abonnement.
- Quota HTTP 429 : conserver la mesure ancienne datée, aucune fausse actualisation ni alerte fondée sur ce cache.
- Anciennes attributions absentes restent inconnues. Hermès : deltas à partir du premier relevé valide, pas de journée historique inventée.
- Les tables dérivées Hermès v1 contiennent des essais invalidés. Seules les tables `*_v2` sont lues. Aucune donnée source effacée.
- Identité Hermès complète : session, modèle, fournisseur, URL de facturation, mode, tâche. Identité hachée dans les tables dérivées.
- Les sources natives existantes conservent leur politique de contenu. Cette nouvelle collecte ne copie pas de prompts, réponses ou entrées/sorties d'outils.
- Les nouveaux processus Claude prennent les settings de télémétrie ; aucune coupure forcée des processus existants.

## Services

`bilan-tokens-otel.service` : collecteur local privé.
`bilan-tokens-ledger.timer` : registre et deltas, muet.
`bilan-tokens-quota.timer` : contrôle de quota préexistant ; bloque l'alerte si mesure ancienne.

Ne pas redémarrer le gateway pour ce suivi. Ne pas réactiver des dumps de requêtes brutes.
