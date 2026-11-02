---
name: android-device-control
description: >-
  Root, OS custom, banques : config Pixel pour liberté max.
version: 1.0.0
disable-model-invocation: true
---

# Android Device Control : liberté max + compatibilité bancaire

## Le conflit central (à expliquer d'emblée à Vin)

**Contrôle total (root/agent) et apps bancaires 100% fonctionnelles sont mutuellement
exclusifs.** Les banques vérifient « Play Integrity », qui détecte bootloader
déverrouillé et root. Il faut arbitrer, pas promettre les deux à 100%.

## Les 3 options, du plus simple au plus libre

| Option | Root | Banques | Usage agent | Verdict |
|---|---|---|---|---|
| **GrapheneOS + sandboxed Play** | Non | ~95% (DEVICE_INTEGRITY) | Termux + SSH + ADB | Privé, stable, sans root |
| **Stock + KernelSU + LSPosed** | Oui (discret) | ~80% | Root complet | Meilleur compromis pour agent |
| **Stock + Magisk** | Oui (détecté) | Faible | Root complet | À éviter pour banques |

## Décision recommandée (donnée à Vin le 2026-08-13)

- Besoin **agent de coding + banques** → **KernelSU + LSPosed sur stock**.
  KernelSU vit dans le kernel (pas `/system`), donc les apps bancaires qui scannent
  `/system` ne le voient pas. LSPosed + Shamiko + Play Integrity Fix cachent le reste.
- Besoin **banques 100% garanties** → GrapheneOS sans root.

## Points techniques clés

- **Bootloader déverrouillé = attestation hardware** (clé dans le TEE Google). Cette
  attestation dit « unlocked » et est **incontournable**. Play Integrity Fix simule
  `DEVICE_INTEGRITY` mais jamais `STRONG_INTEGRITY`.
- **Banques FR/EU** : la plupart se contentent de `DEVICE_INTEGRITY` → passent.
  Revolut/N26/Bunq/BoursoBank : OK en général. Les apps exigeant `STRONG` (Google
  Wallet NFC, certaines banques US, Netflix 4K) refuseront.
- **Verizon/AT&T = OEM grisé définitivement** = pas de bootloader = rien ne marche.
  Vérifier « Déverrouillage OEM » non grisé AVANT tout (Réglages → À propos →
  build ×7 → Options développeur).
- **KernelSU** exige un kernel compatible. Pixel = kernel source public → faisable
  mais nécessite flasher un kernel patché après déverrouillage.

## Accès agent sans root (GrapheneOS)

- **Termux** = terminal Linux complet (git, Python, Node, SSH, rsync, cron).
- Depuis Termux, active serveur SSH → l'agent se connecte au téléphone.
- **ADB en local sans root** couvre ~95% : installer APK, lancer des activités,
  lire les logs, interagir avec l'UI via `adb shell input tap/swipe/text`.

## Ce que l'agent NE PEUT PAS faire sans root

- Modifier `/system`
- Hooker des appels système
- Accéder aux données d'autres apps (sandbox Android)

## Workflow flash Pixel (ordre)

1. Vérifier « Déverrouillage OEM » non grisé (le sésame)
2. Activer le bootloader (fastboot)
3. GrapheneOS via WebUSB (`grapheneos.org/install`), ou flasher kernel KernelSU
4. App stores : F-Droid + Aurora Store (sans compte Google)
5. Isolation : Shelter / Work Profile pour les apps fermées