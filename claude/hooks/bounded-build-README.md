# Hook bounded-build-output — limites, enregistrement, fixture

## Ce que fait le couple
- `bounded-build-output.py` (hook PreToolUse/Bash) : NE execute JAMAIS la
  commande. Reconnait une commande tests/build et repond en JSON avec
  `updatedInput` qui enveloppe la commande ENTIERE dans le runner.
- `bounded-build-run.py` (runner) : execute la commande entiere via
  `/bin/bash -c "set -o pipefail; <commande>"`, ecrit un journal brut complet
  (cwd, code de sortie, stdout, stderr) mode 600 sous
  `$HOME/.hermes/cache/scratch/bounded-build/`, puis affiche au plus
  100 lignes TOTALES : lignes d'erreur d'abord, fin de stderr, debut/fin de
  stdout, une ligne `[code de sortie : N] Journal complet : <chemin>`.
  Sortie <= 100 lignes : passee strictement inchangee.

## Commandes reconnues (liste statique, aucun LLM)
pytest, py.test, tox, nox, make, cmake, ninja, cargo, jest, vitest, mocha,
tsc, vite, gradle, mvn, bazel ; npm/pnpm/yarn/bun avec test|run|build ;
npx + jest|vitest|mocha|tsc|playwright ; go test ; python/python3 -m pytest ;
uv (run) pytest. Assignments d'env en tete acceptes (`FOO=1 pytest`).
Chaines via && ou || ou ; : chaque segment doit etre `cd ...` ou reconnu,
sinon la commande entiere reste intacte. Les pipes | internes sont enveloppes
entiers (pipefail ajoute, ordre preserve, jamais coupes).

## Ce qui n'est PAS modifie (limites documentees)
- Commandes ordinaires (echo, git, curl, ls...), scripts shell, heredocs
  (`<<`), retour a la ligne dans la commande, lancement en fond (`&`),
  chaines contenant un segment non reconnu (`cd x && pytest && echo fait`).
- Commandes deja enveloppees (`bounded-build-run.py` dans la ligne) :
  jamais de rewrap.
- Commandes deja reecrites par RTK (prefixe `rtk `) : le hook sort sans
  rien faire, RTK reste maitre de sa reecriture.

## Enregistrement dans ~/.claude/settings.json (apres RTK)
Inserer un groupe DANS le tableau PreToolUse, juste APRES le groupe
`"command -v rtk >/dev/null 2>&1 && rtk hook claude || true"` (et avant
`outil-existant.py`) :

```json
{
  "matcher": "Bash",
  "hooks": [
    { "type": "command", "command": "python3 $HOME/.claude/hooks/bounded-build-output.py", "timeout": 10 }
  ]
}
```

Placement apres RTK : le hook voit la commande telle que Claude l'a envoyee ;
s'il est reecrit par RTK il commence par `rtk ` et le hook ne rejoue pas.
Attention au bug Claude Code #15897 / rtk#506 : un hook PreToolUse qui sort
rien (exit 0) peut effacer un `updatedInput` d'un hook precedent ; la
convention locale (outil-existant.py) est deja ainsi, ce hook n'ajoute pas de
regression nouvelle, mais si une session montre un rewrite RTK perdu,
deplacer le groupe AVANT celui de RTK.

## Fixture qui declenche un VRAI PreToolUse (manuel, hors tests auto)
```
cd <projet avec pytest>
claude -p "Execute exactement cette commande Bash, rien d'autre : pytest --version"
```
Effet attendu : la session indique (ou le journal apparait sous
`scratch/bounded-build/`) que la commande a ete enveloppee — preuve que le
hook a repondu `updatedInput`. Les 12 tests automatiques, eux, simulent le
hook par sous-processus avec le meme JSON d'entree que Claude Code :
entierement deterministes, aucun modele.
