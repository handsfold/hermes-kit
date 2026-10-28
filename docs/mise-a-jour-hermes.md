# Updating Hermes without breaking anything

This guide is in English. The kit places Hermes in one of two ways.

- Default: the official Hermes at the tested tag `v2026.9.14`, with no change to its code. The kit adds only two plugins, `telegram-menus` and `mode-objectif`, through Hermes' own plugin extension point.
- Option `HK_PATCHES=1` at install time: the kit patch series is applied on top with `git am`, on a local `hermes-kit` branch. One file per patch, in `hermes/patches/`. The list and the base are in `hermes/patches/BASE.txt`.

Check where you stand: `git -C ~/.hermes/hermes-agent rev-parse --abbrev-ref HEAD`. The branch `hermes-kit` means the patch series is applied. Anything else means official Hermes.

## Default install (official Hermes)

Nothing of the kit sits inside the Hermes code, so a new Hermes version cannot conflict with it. The plugins live in `~/.hermes/plugins/`. The protected settings (below) keep your config safe after a migration. The installer pins the tag it tested, and `hk doctor` checks that Hermes still contains it.

## Patched install (HK_PATCHES=1)

The tool below is written for this case. It replays the patches, it does not apply to an unpatched checkout.

Never run `hermes update`. It can drop your patches from the branch. Always go through `~/.hermes/scripts/hermes-maj-sure.sh`.

The 4 gestures:

1. **See where you stand**: `hermes-maj-sure.sh etat`. Version, lag, number of patches, loose files.
2. **Look for the next version**: `hermes-maj-sure.sh prochain`.
3. **Try without touching anything**: `hermes-maj-sure.sh essai`. It copies Hermes into a throwaway folder, replays the patches one by one and runs the tests. The report is in `~/.hermes/maj/essai-*.md`. The service does not move.
4. **Switch**: `hermes-maj-sure.sh bascule --a-blanc`, then `bascule --oui`. It refuses on a conflict or a red test. Before switching it sets a tag `avant-maj-YYYYMMDD-HHMM`. After, it restores your protected settings, restarts without cutting a conversation, then checks.

Go back in 1 command:

```bash
~/.hermes/scripts/hermes-maj-sure.sh retour --oui
```

It returns to the last `avant-maj-*` tag. To look first: `retour --a-blanc`. It does not undo the config migration. Your protected settings already guard it.

Every Monday at 9:00, a timer (`hermes-maj-hebdo`) runs `prochain` then `essai`. It never switches. It tells you in the QG topic only when the version is ready or the result is new.

Move up in steps: go from one stable tag to the next. A big jump gives many conflicts.

## Protected settings (both installs)

The file `~/.hermes/maj/reglages-proteges.yaml` lists what a migration must never change. The kit places an example. Add your model and your settings to it. It is never overwritten.

## Check at any time

`~/.hermes/scripts/hermes-verif.sh` gives OK or KO per point in under 2 minutes.
