---
name: cloud-cost-guard
description: >-
  Jamais scaler un job cloud sans 1-worker smoke test.
version: 1.0.0
metadata:
  hermes:
    tags: [cloud, modal, cout, batch, parallel]
---

# Cloud Cost Guard

Tu ne lances pas N workers sans en avoir testé 1. Un worker qui boucle à
l'infini sur 1000 conteneurs brûle $100 en quelques minutes.

## Avant de déployer

1. **Smoke test : 1 worker, petit range.** Vérifie sortie, temps, écritures
   volume. Pas d'exception.
2. **Mesure le temps.** Si 1 worker > 5 min sur Modal CPU, la préemption le
   tue → restart → boucle infinie. Découpe en tranches <5 min.
3. **Calcule le coût.** Modal CPU ≈ $0.00014/sec/worker (8 CPU + 16 GiB).
   Annonce le coût avant.
4. **`.map(return_exceptions=True)`.** Pour collecter les erreurs.

## Pièges Modal

| Piège | Fix |
|---|---|
| `spawn()` → workers tués au retour | `.map(params)` bloque jusqu'à la fin |
| `.starmap()` sur classe | `MyClass().method.starmap(params)` |
| Worker >5 min → préemption | Réduire charge par worker |
| Volume sans `os.makedirs` | `os.makedirs(path, exist_ok=True)` |

## Exemple : 2026-08-12

1000 workers ×2 sans smoke → $103. 50 workers préemptés 1h29 → $37.
Total $180, zéro résultat.

## Check-list

- [ ] 1 worker fumé avec succès
- [ ] Sortie vérifiée
- [ ] Temps <5 min par worker
- [ ] Coût estimé et annoncé
- [ ] `return_exceptions=True`
- [ ] `os.makedirs` pour volumes
