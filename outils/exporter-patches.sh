#!/usr/bin/env bash
# Retouches apportees a Hermes, en patches numerotes (git format-patch, un par commit).
# Hermes = un tag amont + une serie de commits sur une branche locale (voir BASE.txt).
# Lecture seule sur le clone source. Rejouable : le dossier hermes/patches est refait.
#
# Exclus, car propres a l'installation d'origine (trailer "Retouche: Rnn") :
#   R03 : selecteur de modeles lie a un routeur LLM local (plugin llm, hors kit)
#   R21 : fil en direct des missions, lie au systeme de missions d'origine
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
HA="$HOME/.hermes/hermes-agent"
BASE=v2026.9.14
# la serie locale : l'unique branche locale nommee */local
SERIE=$(git -C "$HA" for-each-ref --format='%(refname:short)' 'refs/heads/*/local')
[ "$(echo "$SERIE" | wc -l)" = 1 ] && [ -n "$SERIE" ] || { echo "branche */local introuvable ou multiple dans $HA" >&2; exit 1; }
EXCLUS=" R03 R21 "
DEST=$PWD/hermes/patches
mkdir -p "$DEST"
rm -f "$DEST"/*.patch

n=0
exclus=""
for sha in $(git -C "$HA" rev-list --reverse "$BASE..$SERIE"); do
  r=$(git -C "$HA" log -1 --format=%B "$sha" | sed -n 's/^Retouche: *\(R[0-9]*\).*/\1/p' | tail -1)
  case "$EXCLUS" in *" $r "*) exclus="$exclus $r"; continue;; esac
  n=$((n + 1))
  f=$(git -C "$HA" format-patch -1 "$sha" --start-number "$n" --no-signature -o "$DEST")
  # En-tete anonyme (auteur, date) ; l'identifiant de salon du test du bus devient generique
  sed -i -e '0,/^From: /s//From: hermes-kit <noreply@hermes-kit.invalid>\nX-Orig: /' \
         -e '0,/^Date: .*/s//Date: Mon, 1 Jan 2024 00:00:00 +0000/' \
         -e 's/CHAT = "-100[0-9]*"/CHAT = "-1001"/' "$f"
  sed -i '/^X-Orig: /d' "$f"
done

{
  echo "base amont : $BASE (tag Hermes, commit $(git -C "$HA" rev-parse --short=10 "$BASE^{commit}"))"
  echo "patches : $n, un fichier par retouche, dans l'ordre"
  echo "exclus (propres a l'installation d'origine) :${exclus:- aucun}"
  echo "application : cd ~/.hermes/hermes-agent && git checkout -B hermes-kit $BASE && git am hermes/patches/*.patch"
} > "$DEST/BASE.txt"
echo "patches : $n fichiers (exclus :${exclus:- aucun})"
