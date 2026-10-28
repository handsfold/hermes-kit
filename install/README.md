# One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/handsfold/hermes-kit/master/install/install.sh | bash
```

Requirements: a Claude Code subscription (claude.ai login) and a Telegram bot token from @BotFather.
Linux, macOS and Windows (through WSL2: run `wsl --install` first, then the command above inside Ubuntu).

The kit speaks English by default. For French, add `HK_LANG=fr` to the command (see Language below).

## Telegram: 3 gestures

No group to create, no topic to make by hand. The bot works in its private chat with you.

1. Create the bot in @BotFather (`/newbot`) and copy the token. The installer asks for it.
2. In @BotFather, open your bot, then Bot Settings, then "Topics in private chats". Turn it on.
3. Open your bot in Telegram and press Start.

The installer checks the token (`getMe`), then waits for your Start (180 seconds by default, `HK_TELEGRAM_ATTENTE`). It reads your numeric Telegram id from that message. It writes `platforms.telegram.extra.dm_topics` in `~/.hermes/config.yaml` with three topics: QG, Coach and Ideas. Hermes creates the topics itself at first start. The installer waits up to 60 seconds for it (`HK_TOPICS_ATTENTE`), reads the topic ids back from `config.yaml`, then places everything that depends on them. At the end, a test message arrives in the QG topic.

If the topics do not appear in time, the step `topics` ends in `ko` and the rest of the install stays done. Check step 2 and step 3, then run `hk reparer`.

## What it does

1. Installs prerequisites (git, curl, python3, jq, node 18+).
2. Clones the kit into `~/.hermes-kit` (or uses the clone you run it from).
3. Installs Claude Code and logs you in if needed.
4. Installs the official Hermes Agent, pinned at the release tag `v2026.9.14`, with no change to its code. Installs the `telegram-menus` and `mode-objectif` plugins and enables them. Drops `reglages-proteges.yaml` (never overwritten) and a weekly update-trial timer on systemd.
   Optional: with `HK_PATCHES=1`, the kit patch series is applied on top with `git am`, on a local `hermes-kit` branch. Off by default.
5. Asks your first name and the bot token, checks the token, then waits for your Start (see above).
6. Writes `~/.hermes/config.yaml`, `.env`, cron jobs, skills, scripts, Claude Code hooks, settings, global `CLAUDE.md` and the `Clair` output style (your previous files are backed up with the `.avant-hermes-kit-<timestamp>` suffix). Writes the menu language in `~/.hermes/telegram-menus.json`.
   Only 3 cron jobs start active: the outage watcher (every 3 min), the daily QG digest and the statistics job (silent without consent). The 7 others (daily coach, learning, weekly retro, monthly reviews, AI news) need a filled `focus.md` or a week of history: they are installed paused. `hermes cron list` shows them, `hermes cron resume <id>` turns one on.
7. Installs rtk and 4 Claude Code plugins, builds the local proxy.
8. Registers 2 services: `claude-proxy` (port 8000, systemd user unit or launchd agent) and `hermes-gateway`.
9. Waits for the QG topics, then checks the proxy, the bot and the gateway, sends the test message to the QG topic, and installs the `hk` command.

Re-running the command is safe: every step is skipped when already done.

## Variables

All optional, see `install/env.exemple`. Pass them in the environment, never as arguments.

- `HK_PRENOM`, `HK_TELEGRAM_TOKEN`, `HK_TELEGRAM_USER`: skip the questions. `HK_TELEGRAM_USER` is your numeric Telegram id; when set, the installer does not wait for Start.
- `HK_LANG`: `en` (default) or `fr`. See Language.
- `HK_PATCHES=1`: apply the optional Hermes patch series (default 0, official Hermes only).
- `HK_TELEGRAM_ATTENTE`: seconds to wait for Start (default 180). `HK_TOPICS_ATTENTE`: seconds to wait for Hermes to create the topics (default 60).
- `HK_CI=1`: test mode for the installation test in CI. It skips only the `getMe` check, so a fake token passes. Never use it on a real install.
- `HK_PIXEL_IP`: ADB address of an Android phone; places the PixelGarde scripts (Creeper, optional, see below).
- `HK_HOME`, `HK_CONTEXTE`, `HK_PROJETS`, `HERMES_HOME`: locations.
- `HK_SANS_CLAUDE_LOGIN=1`, `HK_SANS_PLUGINS=1`, `HK_SANS_RTK=1`, `HK_SANS_SERVICES=1`, `HK_SANS_NAVIGATEUR=1`: skip a step (useful in containers and CI).
- `HK_AUTOJB=oui`: the member said yes to the `auto-jailbreak` skill (asked during install, default no). Yes: the skill is placed and its whole engine is downloaded (venv, PyRIT, LiteLLM). No: nothing is placed, nothing is downloaded.
- `HK_BOITE=oui`: the member said yes to the mailbox report (see below). Without it, the mailbox is never read.
- `HK_BOITE_U`: index of the Gmail account in Chrome (`/mail/u/N`, default 0). `HK_NAVIGATEUR_ATTENTE`: seconds to wait for the Chrome extension (default 420).

## Language

`HK_LANG` is `en` by default and `fr` as an option. It sets the language of the test message and writes the key `langue` in `~/.hermes/telegram-menus.json`, the single setting for the Telegram menus. The button "Language / Langue" in `/menu` switches it later (`menu:lang`).

## Creeper (optional)

Creeper is the Android bubble (the `pixelgarde/` folder), driven over ADB. The installer never asks for it and the rest of the kit works without it. It needs developer mode and ADB on the phone. If you pass `HK_PIXEL_IP`, the PixelGarde scripts are placed; the APK itself is built separately.

## Mailbox report (the first result)

Step `navigateur` installs [opencli](https://github.com/jackwener/opencli) without sudo (`npm install -g --prefix ~/.local`) and opens the Chrome Web Store page of the OpenCLI extension (`HK_ATTENTE=extension <url>`). The member clicks "Add to Chrome": that is the only manual action.

Step `boite` runs only with `HK_BOITE=oui`. `hk-boite` reads the mailbox in the member's own logged-in Chrome (Gmail web; Outlook web is best-effort):

- read-only: it never clicks, opens, sends, deletes, archives or marks a mail; full text is fetched only for threads already read (Gmail print view, no state change);
- first pass: 90 days, 1000 mails at most, about 1 minute; then a background pass (365 days, 5000 mails);
- everything stays local: SQLite + full-text search in `~/.local/share/hermes-kit/boite.db` (mode 600);
- it sends one Telegram message to the QG topic: mail count, top senders, what probably waits for a reply, invoices and suppliers, and 3 questions to ask now, each with its source mail.

Commands: `hk-boite indexer`, `hk-boite bilan [--sec]`, `hk-boite cherche "question"`, `hk-boite stats`. The Hermes skill `boite-mail` answers from this base and always cites the source mail.

## Install driven by Claude Code (club members)

The page `https://club.farangvin.com/kit/install` gives a ready prompt with your first name and a personal link. Claude Code runs:

```bash
curl -fsSL <link>/install.sh -o /tmp/hk-install.sh
HK_ARCHIVE_URL=<link>/hermes-kit.tar.gz HK_PRENOM=<name> HK_SANS_TERMINAL=1 bash /tmp/hk-install.sh
```

- The kit comes from `HK_ARCHIVE_URL` (a `git archive`, no `.git`), not from `git clone`. The proxy is downloaded at the commit in `install/proxy.commit`.
- apt runs with `DEBIAN_FRONTEND=noninteractive`. `sudo -n true` is tested first.
- Right after the Claude login, step `audit` photographs the existing setup (skills of Claude Code, Hermes, ~/.agents, Codex, 30 days of cost) and backs it up in `~/.config/hermes-kit/audit`. After the files, step `migration` gathers scattered skills into `~/.claude/skills` (links elsewhere, nothing deleted) and prints the score before and after. `hk audit` reruns the report, `hk annuler` undoes the migration, `HK_SANS_AUDIT=1` skips both steps.
- Every step prints one line `HK_ETAPE=<name> ok|ko`. A missing value prints `HK_MANQUE=<VAR>` and the line to rerun with. Full log: `/tmp/hermes-kit-install.log`.
- `bash /tmp/hk-install.sh --fond` runs it detached; the result is written to `~/.config/hermes-kit/dernier-resultat`.
- At the end the bot posts a test message in the QG topic (step `message_test`).

Exit codes: 0 ok, 1 error, 10 `HK_PRENOM` missing, 11 `HK_TELEGRAM_TOKEN` missing or refused, 12 no private message seen (press Start in your bot, or pass `HK_TELEGRAM_USER`), 13 sudo needs a password (type `sudo -v` in your own terminal, rerun within 5 minutes), 14 Claude Code not logged in, 15 kit archive not reachable.

### Claude Code permissions

`install/claude-permissions.json` is merged into `~/.claude/settings.json`: reading, editing and safe commands are allowed; `rm`, `sudo`, `git push`, `curl`, `apt` and other destructive or outgoing actions are asked; secret files are denied. A `bypassPermissions` default mode is replaced by `default`. Never use `--dangerously-skip-permissions`.

### Anonymous statistics (opt-in)

Enabled by default at install time (`HK_TELEMETRIE=1`; asked once in interactive installs, default **yes**). Only these events go to `/api/kit/event`: `installe`, `etape`, `telegram_ok`, `premier_resultat`, `boite_ok`, `actif_j7`, with a random install id, the kit version and the OS. Never message content, never a Telegram id, no stored IP. `actif_j7` and `premier_resultat` come from the hourly `hk-telemetrie.py` job and are sent once. Turn it off any time: `hk telemetrie off` (`on|off|voir`).

## Afterwards

```
hk status     # proxy and gateway
hk logs       # follow both services
hk restart
hk doctor     # full checklist
hk update     # git pull (or the club link again), then re-run the installer
hk reparer    # Claude Code reads the doctor report and fixes the machine
hk telemetrie voir   # statistics: on, off, what is sent
```

`hk doctor` also runs every line of `install/attendu.md`, the checkable list of what a well configured machine owns (one line per item, with the command that verifies it).

Your own `~/.claude/CLAUDE.md` is kept: the kit text is added between `<!-- HERMES-KIT:DEBUT -->` and `<!-- HERMES-KIT:FIN -->` and replaced there on re-run. Your own `outputStyle` setting wins over the kit one.

`hk reparer` needs Claude Code installed and logged in (`claude auth status`), otherwise it explains and exits. It gathers a report (`hk doctor`, the last 60 lines of the install log, `install/attendu.md`, `.env` keys without values, service state), then runs `claude -p` in the kit folder with `acceptEdits` and the tools Bash, Read, Edit, Write. Claude compares the machine with `attendu.md` item by item and aligns the configuration (re-runs `python3 install/poser.py`, installs missing plugins, repairs services). It fixes the machine (never the kit repository), re-runs `hk doctor` after each fix, stops at green or explains what stays blocked, and answers in 10 lines. Then `hk doctor` runs once more. The installer suggests it when the final doctor shows a KO.

Log of the last run: `/tmp/hermes-kit-install.log`.
