<p align="center">
  <img src="docs/handsfold-avatar.png" width="96" alt="HandsFold">
</p>

<h1 align="center">hermes-kit</h1>

<p align="center">
  <b>Your own AI agent on Telegram, set up in one command.</b><br>
  Hermes Agent + Claude Code, tuned and wired together. Nothing to configure by hand.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/runs%20on-Linux%20%C2%B7%20macOS%20%C2%B7%20WSL2-lightgrey" alt="Linux, macOS, WSL2">
  <img src="https://img.shields.io/badge/Hermes-v2026.9.14-orange" alt="Hermes v2026.9.14">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#everyday-commands">Commands</a> ·
  <a href="#privacy">Privacy</a> ·
  <a href="README.fr.md">Français</a>
</p>

---

You talk to your agent in Telegram. It answers, works on your machine, and keeps
its tasks sorted in topics. Behind it run [Hermes Agent](https://github.com/NousResearch/hermes-agent)
and your own [Claude Code](https://claude.com/claude-code) subscription, with a set
of skills, hooks and guard rails tested every day.

**No API key to buy.** The kit uses the Claude Code subscription you already pay for.

## Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/handsfold/hermes-kit/master/install/install.sh | bash
```

Then, in Telegram:

1. Send `/newbot` to [@BotFather](https://t.me/BotFather) and paste the token when the installer asks.
2. In @BotFather: your bot, then Bot Settings, then **Topics in private chats**: on.
3. Open your bot and press **Start**.

A test message lands in your new QG topic. That's it.

Time, measured in CI: **2 min 30** on Ubuntu, **4 min 20** on macOS, **11 min** on WSL2.
Running the command again is safe: every step already done is skipped.

## What you get

- **A private QG in Telegram.** 3 topics (QG, Coach, Ideas), created by Hermes itself. No group, no manual setup.
- **The official Hermes**, pinned at the tested tag `v2026.9.14`. Its code is untouched.
- **A local proxy** that lets Hermes run on your Claude Code subscription ([claude-proxy](https://github.com/handsfold/claude-proxy)).
- **28 skills** ready to use, and a **skill router** that picks the right one before the model sees your message.
- **3 plugins**: `telegram-menus` (a `/menu` with buttons), `mode-objectif` (keep a goal across turns), `aiguilleur` (the router).
- **22 Claude Code hooks**: guard rails that block risky commands, leaked secrets and unsafe edits.
- **Measuring tools**: tokens, cost per model, which skills fire and whether they help (`hk banc`).
- **Safe updates**: a weekly trial of the next Hermes release, your settings never overwritten.

English by default. French with `HK_LANG=fr`.

## How it works

```
 You (Telegram)
      │
      ▼
 Hermes gateway  ──  skills · router · plugins · crons
      │
      ▼
 claude-proxy (local, port 8000)
      │
      ▼
 Claude Code CLI  ──  your subscription · hooks · guard rails
```

Everything runs on your machine. Your messages go from Telegram to Hermes, then to
Claude through your own login. The kit adds no server of its own in the middle.

## Requirements

- A Claude Code subscription (claude.ai login).
- A Telegram account.
- Linux, macOS, or Windows with WSL2 (`wsl --install`, then run the command inside Ubuntu).
- `sudo` access to install packages (git, curl, python3, jq, node 18+).
- About 2 GB free disk (estimate).

## Everyday commands

The installer adds `hk`:

| Command | What it does |
|---|---|
| `hk status` | Proxy and gateway state |
| `hk restart` | Restart both |
| `hk logs` | Follow the logs |
| `hk doctor` | Check the whole install |
| `hk reparer` | Repair a broken step |
| `hk update` | Update the kit |
| `hk audit` | Your config before and after the kit, in numbers |
| `hk annuler` | Undo the last skill migration |
| `hk telemetrie on\|off\|voir` | Install statistics (see Privacy) |
| `hk coauteur on\|off\|voir` | The co-author line in commits (see Privacy) |

## Options

Pass them in the environment, in front of the command. Full list: `install/env.exemple`.

| Variable | Effect |
|---|---|
| `HK_LANG=fr` | French menus and messages. Default `en`. |
| `HK_PATCHES=1` | Apply the optional Hermes patch series on a local branch. Off by default. |
| `HK_TELEGRAM_TOKEN`, `HK_TELEGRAM_USER` | Skip the Telegram questions (unattended install). |
| `HK_PIXEL_IP=<ip>` | Add Creeper, an Android bubble driven over ADB. Never required. |
| `HK_SANS_SERVICES=1` | Skip systemd services (containers, CI). |

Step by step detail: [`install/README.md`](install/README.md).

## Privacy

- **Your data stays on your machine.** The repository holds no personal data: content enters only through a whitelist (`MANIFESTE.txt`), and every commit is scanned for secrets (gitleaks) and private identities.
- **Install statistics** are sent only if you hold a HandsFold member token. A closed list of events, each sent once: install finished, each install step (ok or failed), Telegram connected, the bot answered once, the bot is still active on day 7. Never a message, a Telegram id or an IP. See them with `hk telemetrie voir`, stop them with `hk telemetrie off`.
- **Co-author line.** Commits made by Claude Code end with `Co-Authored-By: HandsFold <hello@handsfold.com>`. Turn it off with `hk coauteur off`. An `attribution` you set yourself is never touched.

## Repository layout

| Folder | What |
|---|---|
| `install/` | The one-command installer and the `hk` tools |
| `hermes/` | Hermes config template, skills, plugins, scripts, optional patches |
| `claude/` | Claude Code settings, hooks, agents, analysis tools |
| `proxy/` | The local LLM proxy (git submodule) |
| `pixelgarde/` | Creeper, the optional Android bubble |
| `docs/` | Guides, e.g. [updating Hermes safely](docs/mise-a-jour-hermes.md) |

## FAQ

**Does it change Hermes?** No. Hermes is installed from its official tag. The patch series exists, but only with `HK_PATCHES=1`.

**Can I keep my own Claude Code settings?** Yes. The kit merges into `~/.claude/settings.json`, takes a snapshot first (`hk audit`), and keeps your own choices.

**Something broke.** Run `hk doctor`, then `hk reparer`. Every step can be replayed.

## Credits

Built on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research,
[Claude Code](https://claude.com/claude-code) by Anthropic, and [RTK](https://github.com/rtk-ai/rtk).

## License

[MIT](LICENSE) · made by [HandsFold](https://handsfold.com)
