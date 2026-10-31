---
name: video-transcription
description: "Lien vidéo, transcris, résume-moi ça : lire sans voir. Lit une vidéo en ligne à partir de son lien, sans la regarder : titre, auteur, durée, description et transcription intégrale de la parole (Instagram Reel, TikTok, YouTube, Shorts, X, Facebook, Reddit, Twitch)."
when_to_use: "Se déclenche dès qu'un lien vidéo est collé, ou que USER dit « transcris cette vidéo », « c'est quoi cette vidéo », « résume-moi ça », « qu'est-ce qu'il dit ». Pas pour analyser les images ni le montage (voir analyse-video)."
disable-model-invocation: true
---

# Transcrire une video depuis son lien

Quand USER colle un lien video, meme sans consigne, **lance le script**. Un lien
seul est une demande implicite : il veut pouvoir poser une question dessus.

## La commande

```bash
~/.hermes/skills/media/video-transcription/transcrire.sh "<url>"
```

Options :

- `--lang fr` : force la langue et evite la passe de detection (facultatif)
- `--json` : sortie horodatee (`verbose_json`), utile pour citer un passage
- `--garder` : conserve l'audio source dans `/tmp/transcriptions/<id>/`

## Ce que fait le script

1. **Metadonnees** ciblees via `yt-dlp --print`. Jamais `--print-json` : 37 Ko de bruit.
2. **YouTube** : essaie d'abord les sous-titres. Gratuit, instantane, pas d'API.
3. **Sinon** : telecharge l'audio seul, le reduit en mono 16 kHz 32 kbit/s.
4. **Groq** `whisper-large-v3-turbo`. Au-dela de 24 Mo, decoupe en tranches de 20 min.
5. **Cache** par empreinte d'URL : relancer le meme lien ne recoute rien.

## Points a connaitre

- **Instagram marche sans cookies.** Teste le 2026-09-19 sur un Reel public.
- **TikTok ne passe PAS par yt-dlp** : bloque depuis 2026 ("Unexpected response
  from webpage request"). Le script bascule tout seul sur l'API publique
  `tikwm.com`, qui rend le mp4 sans filigrane plus les metadonnees. Teste le
  2026-09-20 sur un lien court `vt.tiktok.com`.
- **La langue se detecte toute seule.** Le script transcrit 30 s d'extrait en
  `verbose_json`, lit le champ `language`, puis force ce code sur toute la
  transcription. Sans ce verrou Whisper change de langue en cours de route.
  Verifie le 2026-09-20 : `th` sur un TikTok thai de 124 s, `en` sur un Reel de 39 s.
  Le pied de sortie affiche `langue th detectee` ou `langue fr imposee`.
- `--lang xx` reste prioritaire et saute la passe de detection.
- Un compte prive ou une video supprimee sort en code 4 avec le detail dans le log.
- La cle vient de `GROQ_API_KEY` (env, puis `~/.bashrc`). Sans cle, secours
  `whisper` local en modele `small` : lent, mais hors ligne.
- Instagram sert un `.m4a`, pas un `.mp4`. Le script detecte l'extension reelle.
- A 32 kbit/s, la limite Groq de 25 Mo represente environ 100 minutes d'audio.

## Codes de sortie

| Code | Cause |
|---|---|
| 2 | URL manquante |
| 3 | `yt-dlp` ou `ffmpeg` absent |
| 4 | URL illisible (prive, supprime, site non gere, TikTok refuse par tikwm) |
| 5 | Telechargement audio echoue |
| 7 | Ni cle Groq ni `whisper` local |
| 8 | Transcription vide ou refusee par l'API |

## Apres la transcription

Reponds a la question de USER, pas au script. S'il n'a pose aucune question :
donne l'auteur, la duree, et le contenu en 3 puces maximum. Ne recrache jamais
la transcription brute entiere dans le chat, sauf demande explicite.
