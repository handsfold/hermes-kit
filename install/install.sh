#!/usr/bin/env bash
# hermes-kit: one-command install, drivable by Claude Code.
#
#   Club member: the prompt from https://club.farangvin.com/kit/install provides
#   HK_ARCHIVE_URL (personal-token link) and HK_PRENOM.
#   Developer: bash install/install.sh from a clone (the clone becomes HK_HOME).
#
# Rerunnable: each step does nothing if it was already done.
# Machine-readable output: one line "HK_ETAPE=<name> ok|ko" per step.
# Full log: /tmp/hermes-kit-install.log (HK_JOURNAL to change it).
# In the background: bash install.sh --fond (result in ~/.config/hermes-kit/dernier-resultat).
# Language: HK_LANG=en (default) or fr; only the final message exists in French.
#
# Exit codes (a piece of data is missing, rerun with the variable named):
#   0 ok | 1 error | 10 HK_PRENOM | 11 HK_TELEGRAM_TOKEN (missing or refused)
#   12 Telegram topics not seen | 13 sudo asks for a password
#   14 Claude Code not logged in | 15 kit archive unreachable (link expired?)
#
# Mailbox (the closing "wow"): HK_BOITE=oui only if the member said yes
# (read-only, local database). HK_BOITE_U = index of the Gmail account in Chrome.
#
# Variables: see install/README.md and install/env.exemple. Never as an argument.
set -euo pipefail

HK_REPO=${HK_REPO:-https://github.com/handsfold/hermes-kit.git}
HK_BRANCH=${HK_BRANCH:-master}
HK_CLUB_URL=${HK_CLUB_URL:-https://club.farangvin.com}
HK_HOME=${HK_HOME:-$HOME/.hermes-kit}
HERMES_HOME=${HERMES_HOME:-$HOME/.hermes}
# Full SHA: the upstream installer rejects an abbreviated SHA.
HERMES_COMMIT=345cd2b057a452236de401d3534b8502a7465e8d  # tag v2026.9.14
JOURNAL=${HK_JOURNAL:-/tmp/hermes-kit-install.log}
ETAT_DIR="$HOME/.config/hermes-kit"
export DEBIAN_FRONTEND=noninteractive
ETAPE=demarrage

dire()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m ok \033[0m %s\n' "$*"; }
avert() { printf '\033[1;33m !! \033[0m %s\n' "$*"; }
a()     { command -v "$1" >/dev/null 2>&1; }
# fatal "message" [code]: the HK_ETAPE=... ko line, then exit with the given code.
fatal() {
  printf '\033[1;31m XX \033[0m %s\n' "$1" >&2
  echo "HK_ETAPE=$ETAPE ko"
  echo "    log: $JOURNAL" >&2
  evenement etape "$ETAPE.ko"
  exit "${2:-1}"
}
# manque VAR code "explanation": a piece of data is missing and nobody can type it.
manque() {
  printf '\033[1;31m XX \033[0m %s\n' "$3" >&2
  echo "HK_MANQUE=$1"
  echo "    rerun with: $1=... in the environment (never as an argument)" >&2
  echo "HK_ETAPE=$ETAPE ko"
  exit "$2"
}
etape()    { ETAPE=$1; }
etape_ok() { echo "HK_ETAPE=$ETAPE ok"; evenement etape "$ETAPE"; }

# ------------------------------------------------------------- background mode
# Claude Code cuts a command off after 2 min: --fond returns immediately, the
# installation continues detached, the log and the result remain.
if [ "${1:-}" = "--fond" ]; then
  shift
  if [ -z "${BASH_SOURCE[0]:-}" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
    echo "--fond needs a file: curl -fsSL <url> -o /tmp/hk-install.sh then bash /tmp/hk-install.sh --fond" >&2
    exit 1
  fi
  mkdir -p "$ETAT_DIR"
  rm -f "$ETAT_DIR/dernier-resultat"
  : > "$JOURNAL"
  if a setsid; then
    setsid nohup bash "${BASH_SOURCE[0]}" "$@" >/dev/null 2>&1 < /dev/null &
  else
    nohup bash "${BASH_SOURCE[0]}" "$@" >/dev/null 2>&1 < /dev/null &
  fi
  echo "installation started in the background (pid $!)"
  echo "follow : tail -f $JOURNAL"
  echo "result : cat $ETAT_DIR/dernier-resultat   (appears at the end: code=... etape=...)"
  exit 0
fi

# Everything displayed also goes to the log.
mkdir -p "$(dirname "$JOURNAL")" "$ETAT_DIR" "$HOME/.local/bin"
[ "${HK_JOURNAL_GARDER:-0}" = 1 ] || : > "$JOURNAL"
exec > >(tee -a "$JOURNAL") 2>&1
trap 'rc=$?; printf "code=%s etape=%s date=%s\n" "$rc" "$ETAPE" "$(date +%FT%T)" > "$ETAT_DIR/dernier-resultat"' EXIT

# Questions go through the terminal, even under "curl | bash".
# File permissions are not enough: without a controlling terminal (docker
# exec, cron, ssh without -t, Claude Code), /dev/tty exists but opening it fails.
TTY=/dev/tty
( exec 3<>"$TTY" ) 2>/dev/null || TTY=""
[ "${HK_SANS_TERMINAL:-0}" = 1 ] && TTY=""
# Test d'installation (CI) : jamais de question. Sous WSL /dev/tty repond et la
# question de la skill auto-jailbreak figeait l'installation (CI du 2026-10-13).
[ "${HK_CI:-}" = 1 ] && TTY=""
# demander VAR "question" [default]: asks nothing if VAR is already set.
# Without a terminal: takes the default, otherwise returns 1 (the caller picks the code).
demander() {
  local var=$1 q=$2 def=${3:-} val=""
  [ -n "${!var:-}" ] && return 0
  if [ -z "$TTY" ]; then
    [ -n "$def" ] && { printf -v "$var" '%s' "$def"; return 0; }
    return 1
  fi
  while [ -z "$val" ]; do
    printf '%s%s : ' "$q" "${def:+ [$def]}" > "$TTY"
    IFS= read -r val < "$TTY" || true
    val=${val:-$def}
  done
  printf -v "$var" '%s' "$val"
}

# ------------------------------------------------------------- statistics
# Install statistics: on by default (HK_TELEMETRIE=1), switched off with one
# command, `hk telemetrie off`. Closed list of events, never the content of
# a message nor a Telegram identifier.
TELEM="$ETAT_DIR/telemetrie"
ENVOYES="$ETAT_DIR/evenements-envoyes"
propre() { printf '%s' "$1" | tr -cd 'A-Za-z0-9._:/-' | cut -c1-80; }
envoyer() { # envoyer name [step]: returns curl's exit code
  [ "${HK_TELEMETRIE:-0}" = 1 ] || return 0
  [ -n "${HK_MEMBER_TOKEN:-}" ] && [ -n "${HK_EVENT_URL:-}" ] && a curl || return 0
  case "$1" in installe|etape|telegram_ok|premier_resultat|boite_ok|actif_j7) ;; *) return 0 ;; esac
  # Body via standard input: the token does not show up in the process list.
  printf '{"jeton":"%s","install_id":"%s","event":"%s","step":"%s","version":"%s","os":"%s"}' \
    "$(propre "$HK_MEMBER_TOKEN")" "$(propre "${HK_INSTALL_ID:-}")" "$1" "$(propre "${2:-}")" \
    "$(propre "${HK_VERSION:-inconnue}")" "$(propre "${HK_OS:-}")" \
    | curl -fsS --max-time 5 -H 'Content-Type: application/json' --data-binary @- "$HK_EVENT_URL" >/dev/null 2>&1
}
evenement() { envoyer "$@" || true; }
evenement_unique() { # sends only once per machine
  [ "${HK_TELEMETRIE:-0}" = 1 ] || return 0
  grep -qx "$1" "$ENVOYES" 2>/dev/null && return 0
  if envoyer "$1"; then echo "$1" >> "$ENVOYES"; fi
}
ecrire_telemetrie() {
  umask 077
  {
    echo "HK_TELEMETRIE=${HK_TELEMETRIE:-0}"
    echo "HK_INSTALL_ID=$HK_INSTALL_ID"
    echo "HK_INSTALLE_LE=$HK_INSTALLE_LE"
    echo "HK_MEMBER_TOKEN=$(propre "${HK_MEMBER_TOKEN:-}")"
    echo "HK_EVENT_URL=$(propre "${HK_EVENT_URL:-}")"
    echo "HK_VERSION=$(propre "${HK_VERSION:-inconnue}")"
    echo "HK_OS=$(propre "${HK_OS:-}")"
  } > "$TELEM"
  umask 022
}

# ------------------------------------------------------------------ 1. system
etape systeme
OS=$(uname -s)
case "$OS" in
  Linux)  if grep -qi microsoft /proc/version 2>/dev/null; then PLATEFORME=wsl; else PLATEFORME=linux; fi ;;
  Darwin) PLATEFORME=mac ;;
  MINGW*|MSYS*|CYGWIN*)
    fatal "Native Windows: in PowerShell run 'wsl --install', restart, then rerun this command in Ubuntu (WSL2)." ;;
  *) fatal "unsupported system: $OS" ;;
esac
HK_OS="$PLATEFORME/$(uname -m)"
# Under WSL, PATH mixes in Windows tools (/mnt/c/...): a Windows npm launched
# from Linux fails or hangs. Only the Linux tools are kept.
if [ "$PLATEFORME" = wsl ]; then
  PATH=$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '^/mnt/' | paste -sd: -)
  export PATH
fi
dire "hermes-kit on $PLATEFORME ($(uname -m)). Log: $JOURNAL"
[ -n "$TTY" ] || dire "no terminal: answers come from the environment (HK_PRENOM, HK_TELEGRAM_TOKEN...)"

# Answers from previous installs (never a secret in there)
# The environment wins: a value passed to correct something is not overwritten.
if [ -f "$ETAT_DIR/reponses" ]; then
  while IFS='=' read -r k v; do
    case "$k" in HK_[A-Z_]*) ;; *) continue ;; esac
    [ -n "${!k:-}" ] && continue
    v=${v#\'}; v=${v%\'}
    printf -v "$k" '%s' "$v"
  done < "$ETAT_DIR/reponses"
fi
# Statistics: setting already chosen, stable install identifier
if [ -f "$TELEM" ]; then
  _t=${HK_TELEMETRIE:-}; _m=${HK_MEMBER_TOKEN:-}; _e=${HK_EVENT_URL:-}
  . "$TELEM"
  HK_TELEMETRIE=${_t:-$HK_TELEMETRIE}; HK_MEMBER_TOKEN=${_m:-$HK_MEMBER_TOKEN}; HK_EVENT_URL=${_e:-$HK_EVENT_URL}
fi
[ -n "${HK_INSTALL_ID:-}" ] || HK_INSTALL_ID=$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')
HK_INSTALLE_LE=${HK_INSTALLE_LE:-$(date +%s)}

# First name early: without a terminal, no point working 4 minutes only to fail later.
demander HK_PRENOM "Your first name (the agent will call you by it)" \
  || manque HK_PRENOM 10 "first name missing and no terminal to ask for it"
etape_ok

# --------------------------------------------------------------- 2. sudo
# Claude Code cannot type a password: we say so before starting.
etape sudo
manquants=()
for c in git curl python3 jq; do a "$c" || manquants+=("$c"); done
node_ok=0
if a node; then v=$(node -v | sed 's/^v//' | cut -d. -f1); [ "${v:-0}" -ge 18 ] && node_ok=1; fi
[ "$node_ok" = 1 ] || manquants+=(node)
a npm || manquants+=(npm)
SUDO=""
if [ "$(id -u)" -ne 0 ] && [ "$PLATEFORME" != mac ]; then
  a sudo && SUDO=sudo
  if [ "${#manquants[@]}" -gt 0 ]; then
    [ -n "$SUDO" ] || fatal "${manquants[*]} must be installed and sudo is missing: install them as root, then rerun" 13
    if ! sudo -n true 2>/dev/null; then
      if [ -n "$TTY" ]; then
        dire "sudo will ask for your password once (installing ${manquants[*]})"
        sudo -v < "$TTY" > "$TTY" 2>&1 || fatal "sudo refused" 13
      else
        fatal "sudo asks for a password and there is no terminal to type it. In your own terminal, type: sudo -v (then your password), and rerun within 5 minutes." 13
      fi
    fi
    ok "sudo: available"
  else
    ok "sudo: not needed, the prerequisites are there"
  fi
fi
etape_ok

# -------------------------------------------------------------- 3. prerequisites
etape prerequis
if [ "${#manquants[@]}" -gt 0 ]; then
  dire "prerequisites to install: ${manquants[*]}"
  if [ "$PLATEFORME" = mac ]; then
    a brew || fatal "Homebrew missing: install it from https://brew.sh then rerun"
    brew install git curl python jq node >>"$JOURNAL" 2>&1
  elif a apt-get; then
    APT="${SUDO:+$SUDO }env DEBIAN_FRONTEND=noninteractive apt-get"
    $APT update -qq >>"$JOURNAL" 2>&1 || fatal "apt-get update failed"
    $APT install -y -qq -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
      git curl python3 python3-venv jq ca-certificates tzdata >>"$JOURNAL" 2>&1 || fatal "apt-get install failed"
    if [ "$node_ok" = 0 ]; then
      curl -fsSL https://deb.nodesource.com/setup_22.x | ${SUDO:+$SUDO -E} bash - >>"$JOURNAL" 2>&1
      $APT install -y -qq nodejs >>"$JOURNAL" 2>&1 || fatal "nodejs installation failed"
    fi
  elif a dnf; then
    $SUDO dnf install -y git curl python3 jq nodejs npm >>"$JOURNAL" 2>&1
  elif a pacman; then
    $SUDO pacman -Sy --noconfirm git curl python jq nodejs npm >>"$JOURNAL" 2>&1
  else
    fatal "unknown package manager: install ${manquants[*]} then rerun"
  fi
  hash -r
fi
for c in git curl python3 jq node npm; do a "$c" || fatal "$c still missing after installation"; done
ok "prerequisites: git $(git --version | awk '{print $3}'), node $(node -v), python $(python3 -V | awk '{print $2}')"
etape_ok

# ---------------------------------------------------------------- 4. the kit
# Sources, in order: club token link (HK_ARCHIVE_URL or HK_MEMBER_TOKEN),
# local clone the script is run from, existing git clone, saved link, git clone.
etape kit
if [ -z "${HK_ARCHIVE_URL:-}" ] && [ -n "${HK_MEMBER_TOKEN:-}" ] && [ ! -f "$(dirname "${BASH_SOURCE[0]:-/x}")/../MANIFESTE.txt" ]; then
  HK_ARCHIVE_URL="$HK_CLUB_URL/kit/dl/$HK_MEMBER_TOKEN/hermes-kit.tar.gz"
fi
if [ -n "${HK_ARCHIVE_URL:-}" ]; then
  # The member token is in the path: /kit/dl/<token>/hermes-kit.tar.gz
  if [ -z "${HK_MEMBER_TOKEN:-}" ]; then
    HK_MEMBER_TOKEN=$(printf '%s' "$HK_ARCHIVE_URL" | sed -n 's|.*/kit/dl/\([^/]*\)/.*|\1|p')
  fi
  if [ -z "${HK_EVENT_URL:-}" ]; then
    HK_EVENT_URL="$(printf '%s' "$HK_ARCHIVE_URL" | sed -n 's|^\(https\{0,1\}://[^/]*\)/.*|\1|p')/api/kit/event"
  fi
fi
HK_EVENT_URL=${HK_EVENT_URL:-$HK_CLUB_URL/api/kit/event}

# Statistics: a single question, default yes (can be switched off later: hk telemetrie off).
if [ -z "${HK_TELEMETRIE:-}" ]; then
  if [ -n "${HK_MEMBER_TOKEN:-}" ] && [ -n "$TTY" ]; then
    rep=""
    demander rep "Send anonymous install statistics to the club (steps succeeded, never your messages)? Y/n" "y"
    case "$rep" in o|O|oui|Oui|OUI|y|Y|yes|1) HK_TELEMETRIE=1 ;; *) HK_TELEMETRIE=0 ;; esac
  else
    # No terminal, no question: always on. Inert if no member token is set.
    HK_TELEMETRIE=1
  fi
fi
case "$HK_TELEMETRIE" in 1) ;; *) HK_TELEMETRIE=0 ;; esac
ecrire_telemetrie
ok "install statistics: $([ "$HK_TELEMETRIE" = 1 ] && echo yes || echo no) (hk telemetrie on|off|voir)"

KIT_SCRIPT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/../MANIFESTE.txt" ]; then
  KIT_SCRIPT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fi
if [ -n "${HK_ARCHIVE_URL:-}" ]; then
  dire "downloading the kit (personal club link)"
  ARCH=$(mktemp "${TMPDIR:-/tmp}/hermes-kit.XXXXXX")
  code=$(printf 'url = "%s"\n' "$HK_ARCHIVE_URL" | curl -sSL --retry 3 -o "$ARCH" -w '%{http_code}' -K - 2>>"$JOURNAL" || true)
  case "$code" in
    200) ;;
    401|403|404|410) rm -f "$ARCH"; fatal "kit link refused (HTTP $code): expired or revoked. Get the prompt again at $HK_CLUB_URL/kit/install" 15 ;;
    *) rm -f "$ARCH"; fatal "kit download impossible (HTTP ${code:-no response}): network?" 15 ;;
  esac
  mkdir -p "$HK_HOME"
  tar -xzf "$ARCH" -C "$HK_HOME" >>"$JOURNAL" 2>&1 || { rm -f "$ARCH"; fatal "kit archive unreadable" 15; }
  # git archive stores the commit in the header: that is the kit version.
  HK_VERSION=$(gzip -dc "$ARCH" 2>/dev/null | git get-tar-commit-id 2>/dev/null | cut -c1-12 || true)
  rm -f "$ARCH"
  HK_VERSION=${HK_VERSION:-inconnue}
  echo "$HK_VERSION" > "$HK_HOME/.hk-version"
  # The link is used by 'hk update': it opens the kit, so it stays readable by you alone.
  ( umask 077; printf 'HK_ARCHIVE_URL=%s\n' "$HK_ARCHIVE_URL" > "$ETAT_DIR/source" )
elif [ -n "$KIT_SCRIPT" ]; then
  HK_HOME=$KIT_SCRIPT
  dire "kit read from $HK_HOME"
elif [ -d "$HK_HOME/.git" ]; then
  dire "updating the kit in $HK_HOME"
  git -C "$HK_HOME" pull -q --ff-only origin "$HK_BRANCH" >>"$JOURNAL" 2>&1 || avert "pull impossible, local version kept"
else
  dire "cloning the kit into $HK_HOME"
  git clone -q --branch "$HK_BRANCH" "$HK_REPO" "$HK_HOME" >>"$JOURNAL" 2>&1 \
    || fatal "cannot clone $HK_REPO. The kit can be downloaded from $HK_CLUB_URL/kit (free account)" 15
fi
[ -f "$HK_HOME/MANIFESTE.txt" ] || fatal "incomplete kit in $HK_HOME (MANIFESTE.txt missing)"
if [ -d "$HK_HOME/.git" ]; then
  git -C "$HK_HOME" submodule update --init --quiet proxy >>"$JOURNAL" 2>&1 || avert "proxy submodule not fetched"
  HK_VERSION=$(git -C "$HK_HOME" rev-parse --short=12 HEAD 2>/dev/null || echo inconnue)
fi
HK_VERSION=${HK_VERSION:-$(cat "$HK_HOME/.hk-version" 2>/dev/null || echo inconnue)}
# A git archive does not contain the proxy submodule (public repo, MIT):
# we fetch it at the commit pinned in install/proxy.commit.
if [ ! -f "$HK_HOME/proxy/server.js" ] && [ -f "$HK_HOME/install/proxy.commit" ]; then
  PC=$(tr -cd '0-9a-f' < "$HK_HOME/install/proxy.commit")
  dire "proxy: downloading hermes-kit/claude-proxy ${PC:0:10}"
  mkdir -p "$HK_HOME/proxy"
  curl -fsSL --retry 3 "https://codeload.github.com/hermes-kit/claude-proxy/tar.gz/$PC" 2>>"$JOURNAL" \
    | tar -xz --strip-components=1 -C "$HK_HOME/proxy" >>"$JOURNAL" 2>&1 || avert "proxy not downloaded"
fi
[ -f "$HK_HOME/proxy/server.js" ] || fatal "proxy missing: $HK_HOME/proxy/server.js"
echo "$HK_HOME" > "$ETAT_DIR/home"
ecrire_telemetrie
HK_CONTEXTE=${HK_CONTEXTE:-$HK_HOME/contexte}
HK_PROJETS=${HK_PROJETS:-$HOME/Projets}
ok "kit: version $HK_VERSION"
etape_ok

# ------------------------------------------------------------ 5. Claude Code
etape claude
export PATH="$HOME/.local/bin:$PATH"
if ! a claude; then
  dire "installing Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash >>"$JOURNAL" 2>&1 \
    || npm install -g @anthropic-ai/claude-code >>"$JOURNAL" 2>&1 \
    || fatal "Claude Code installation failed"
  hash -r
fi
a claude || fatal "claude not found after installation"
CLAUDE_BIN=$(command -v claude)
if [ "${HK_SANS_CLAUDE_LOGIN:-0}" != 1 ]; then
  if claude auth status 2>/dev/null | grep -q '"loggedIn": *true'; then
    ok "Claude Code: logged in"
  else
    # In CI (or without a terminal), nobody will answer: fail immediately, no waiting.
    [ -z "${CI:-}${GITHUB_ACTIONS:-}" ] || fatal "Claude Code not logged in and running in CI: set HK_SANS_CLAUDE_LOGIN=1" 14
    [ -n "$TTY" ] || fatal "Claude Code not logged in: run 'claude auth login' in your terminal, then rerun" 14
    dire "Claude Code login: follow the instructions (the browser opens, 10 min at most)"
    rc=0; timeout 600 claude auth login < "$TTY" > "$TTY" 2>&1 || rc=$?
    [ "$rc" -eq 124 ] && fatal "Claude Code login: no answer in 10 min, rerun when the browser is within reach" 14
    [ "$rc" -eq 0 ] || fatal "Claude Code login failed" 14
    ok "Claude Code: logged in"
  fi
fi
etape_ok

# ------------------------------------------ 5b. audit of the existing setup
etape audit
# Before the kit touches anything: a photo of the existing setup (skills of Claude Code,
# Hermes and other agents, 30 days of cost, tracking) and a full backup. Reads only;
# writes only in ~/.config/hermes-kit/audit. Never fatal: a failed audit blocks nothing.
audit_lancer() {
  HK_HOME="$HK_HOME" HERMES_HOME="$HERMES_HOME" HK_LANG="${HK_LANG:-en}" \
    python3 "$HK_HOME/install/hk-audit.py" "$@" 2>>"$JOURNAL"
}
if [ "${HK_SANS_AUDIT:-0}" != 1 ]; then
  audit_lancer --avant || avert "audit of the existing setup failed (details in $JOURNAL)"
fi
etape_ok

# ------------------------------------------------------- 6. Hermes Agent
etape hermes
HA="$HERMES_HOME/hermes-agent"
if [ ! -d "$HA/.git" ]; then
  dire "installing Hermes Agent (several minutes)"
  # The published installer follows the main branch: it expects files absent
  # from the pinned commit (pm/, failure "No module named pm"). So we take the
  # one from the pinned commit. Git fallback if raw.githubusercontent answers 429.
  HA_INSTALL="${TMPDIR:-/tmp}/hermes-install-$HERMES_COMMIT.sh"
  if ! curl -fsSL --retry 3 --retry-delay 5 -o "$HA_INSTALL" \
       "https://raw.githubusercontent.com/NousResearch/hermes-agent/$HERMES_COMMIT/scripts/install.sh" >>"$JOURNAL" 2>&1; then
    HA_TMP=$(mktemp -d)
    { git -C "$HA_TMP" init -q \
      && git -C "$HA_TMP" fetch -q --depth 1 --filter=blob:none https://github.com/NousResearch/hermes-agent.git "$HERMES_COMMIT" \
      && git -C "$HA_TMP" show "$HERMES_COMMIT:scripts/install.sh" >"$HA_INSTALL"; } >>"$JOURNAL" 2>&1 \
      || fatal "Hermes installer $HERMES_COMMIT not found"
    rm -rf "${HA_TMP:?}"
  fi
  # The Node dependencies (browser tools, TUI) are not needed by the kit: an
  # 'npm install' that fails or exceeds 10 min (seen under WSL) must not bring
  # everything down. We lighten it in the upstream installer (pinned commit, so
  # stable anchors) and 'hk doctor' reports their absence. Without --silent, the
  # npm output stays readable in the log on failure.
  # In python rather than sed: macOS (BSD) sed reads '-i -e' differently.
  python3 - "$HA_INSTALL" <<'PYEOF' || fatal "Hermes installer $HERMES_COMMIT: install_node_deps anchor not found"
import re, sys
p = sys.argv[1]
s = open(p).read()
s, n = re.subn(r'^( *)install_node_deps \|\| return$',
               r'\1install_node_deps || log_warn "Node.js dependencies skipped (browser tools unavailable)"', s, flags=re.M)
s = re.sub(r'( npm install .*)--silent \\$', r'\1\\', s, flags=re.M)
open(p, 'w').write(s)
sys.exit(0 if n else 1)
PYEOF
  export NODE_DEPS_TIMEOUT="${HK_NODE_DEPS_TIMEOUT:-600}"
  # --skip-setup: under WSL, /dev/tty answers and the upstream wizard opened
  # and waited for input. The kit places the configuration itself (poser.py).
  # --dir: as root, upstream would put the code in /usr/local/lib/hermes-agent.
  bash "$HA_INSTALL" --commit "$HERMES_COMMIT" --hermes-home "$HERMES_HOME" --dir "$HA" \
    --non-interactive --skip-setup --skip-browser --skip-computer-use >>"$JOURNAL" 2>&1 \
    || fatal "Hermes installation failed"
  hash -r
  [ -d "$HA/node_modules" ] || avert "Hermes browser tools not installed (npm): optional, 'hk reparer' will retry"
fi
HERMES_BIN="$HA/venv/bin/hermes"
[ -x "$HERMES_BIN" ] || HERMES_BIN=$(command -v hermes || true)
[ -n "$HERMES_BIN" ] || fatal "hermes not found in $HA/venv/bin nor in PATH"
if [ "${HK_PATCHES:-0}" = 1 ]; then
dire "optional kit patches on Hermes (git am)"
(
  cd "$HA"
  # Fingerprint of the series: already applied means nothing to do.
  empreinte=$(cat "$HK_HOME"/hermes/patches/*.patch 2>/dev/null | git hash-object --stdin)
  marque="$(git rev-parse --git-dir)/hermes-kit-patches"
  if [ "$(cat "$marque" 2>/dev/null)" = "$empreinte" ] && [ "$(git rev-parse --abbrev-ref HEAD)" = hermes-kit ]; then
    echo "  patches already applied"
  else
    git stash -q >>"$JOURNAL" 2>&1 || true
    git checkout -q -B hermes-kit "$HERMES_COMMIT" >>"$JOURNAL" 2>&1 || fatal "cannot check out Hermes $HERMES_COMMIT"
    # git am needs an identity: local to the clone, never the user's.
    git config user.name  "hermes-kit"
    git config user.email "noreply@hermes-kit.invalid"
    if git am -q "$HK_HOME"/hermes/patches/*.patch >>"$JOURNAL" 2>&1; then
      echo "$empreinte" > "$marque"
      echo "  $(git rev-list --count "$HERMES_COMMIT..HEAD") patches applied"
    else
      git am --abort >>"$JOURNAL" 2>&1 || true
      avert "patches not applied (Hermes stays on the official base): see the log"
    fi
  fi
)
else
  # Default: official Hermes at the tested tag, plugins only.
  git -C "$HA" checkout -q "$HERMES_COMMIT" >>"$JOURNAL" 2>&1 || avert "could not pin Hermes to $HERMES_COMMIT"
fi
ok "Hermes: $(git -C "$HA" rev-parse --short HEAD) (tag v2026.9.14$([ "${HK_PATCHES:-0}" = 1 ] && echo ' + kit patches'))"
etape_ok

# --------------------------------------------- 7. Telegram bot
etape telegram
dire "Telegram setup"
if [ -z "${HK_TELEGRAM_TOKEN:-}" ] && [ -f "$HERMES_HOME/.env" ]; then
  HK_TELEGRAM_TOKEN=$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$HERMES_HOME/.env" | tr -d '"'"'" | head -1)
fi
demander HK_TELEGRAM_TOKEN "Telegram bot token (from @BotFather)" \
  || manque HK_TELEGRAM_TOKEN 11 "Telegram bot token missing. Everything else is installed: rerun with the token, the rest takes 1 minute"
# Checked before waiting for a message that would never come. The token goes through
# curl's standard input, never its command line.
# HK_CI=1 is the explicit test mode (GitHub Actions has no real bot): it skips getMe only.
if [ "${HK_CI:-}" = 1 ]; then
  avert "HK_CI=1: getMe check skipped (installation test, fake token)"
elif ! printf 'url = "https://api.telegram.org/bot%s/getMe"\n' "$HK_TELEGRAM_TOKEN" | curl -fs --max-time 10 -K - | grep -q '"ok":true'; then
  manque HK_TELEGRAM_TOKEN 11 "Telegram refuses this token (getMe). Copy it again from @BotFather, in full"
else
  ok "Telegram bot: token accepted"
fi
if [ -z "${HK_TELEGRAM_USER:-}" ]; then
  ATTENTE=${HK_TELEGRAM_ATTENTE:-180}
  cat <<EOF > "${TTY:-/dev/stdout}"

In Telegram, while I wait (up to $ATTENTE seconds):
  1. in @BotFather, open your bot: Bot Settings, enable "Topics in private chats" (threaded mode);
  2. open your bot and press Start.

EOF
  echo "HK_ATTENTE=telegram $ATTENTE"
  if ! det=$(HK_TOKEN="$HK_TELEGRAM_TOKEN" python3 "$HK_HOME/install/telegram-detect.py" "$ATTENTE"); then
    fatal "no private message seen. Open your bot in Telegram and press Start, then rerun. Or pass HK_TELEGRAM_USER (your numeric Telegram id)" 12
  fi
  eval "$det"
fi
[[ "$HK_TELEGRAM_USER" =~ ^[0-9]+$ ]] || fatal "HK_TELEGRAM_USER must be a number: $HK_TELEGRAM_USER" 12
{
  echo "HK_PRENOM='${HK_PRENOM//\'/}'"
  echo "HK_TELEGRAM_USER=$HK_TELEGRAM_USER"
  echo "HK_LANG=${HK_LANG:-en}"
  echo "HK_CONTEXTE='$HK_CONTEXTE'"
  echo "HK_PROJETS='$HK_PROJETS'"
  [ -n "${HK_PIXEL_IP:-}" ] && echo "HK_PIXEL_IP=$HK_PIXEL_IP"
} > "$ETAT_DIR/reponses"
ok "Telegram user $HK_TELEGRAM_USER"
etape_ok
evenement_unique telegram_ok

# ------------------------------------- 7 bis. auto-jailbreak skill (yes/no)
# Yes: the skill is placed AND its engine is downloaded (venv + PyRIT, large,
# a few minutes) in step 10 bis. No: nothing is placed, nothing is downloaded.
# Without a terminal the answer is no, unless HK_AUTOJB=oui is set.
if [ -z "${HK_AUTOJB:-}" ]; then
  rep=""
  demander rep "Install the auto-jailbreak skill (LLM red-teaming, downloads PyRIT, about 1.3 GB)? y/N" "n" || rep=n
  case "$rep" in o|O|oui|Oui|OUI|y|Y|yes|1) HK_AUTOJB=oui ;; *) HK_AUTOJB=non ;; esac
fi
[ "$HK_AUTOJB" = oui ] || HK_AUTOJB=non
ok "auto-jailbreak skill: $([ "$HK_AUTOJB" = oui ] && echo yes || echo no)"

# ----------------------------------------------------------- 8. files
etape fichiers
dire "placing files (Hermes config, skills, scripts, crons, Claude Code)"
# Phase 1 runs before the first start: the QG topics have no id yet. Phase 2 (step topics)
# replays this call once Hermes has created the topics and written their ids in config.yaml.
poser_lancer() {
  HK_HOME="$HK_HOME" HK_CONTEXTE="$HK_CONTEXTE" HK_PROJETS="$HK_PROJETS" HERMES_HOME="$HERMES_HOME" \
  HK_PRENOM="$HK_PRENOM" HK_TELEGRAM_TOKEN="$HK_TELEGRAM_TOKEN" HK_TELEGRAM_USER="$HK_TELEGRAM_USER" \
  HK_LANG="${HK_LANG:-en}" HK_PIXEL_IP="${HK_PIXEL_IP:-}" HK_PLATEFORME="$PLATEFORME" HERMES_BIN="$HERMES_BIN" \
  HK_AUTOJB="$HK_AUTOJB" \
    python3 "$HK_HOME/install/poser.py" "$@"
}
poser_lancer || fatal "placing files failed"
etape_ok

# ------------------------------------------ 8b. migration of the existing setup
etape migration
# Scattered skills (Hermes, ~/.agents, ~/.codex...) join ~/.claude/skills, a link takes
# their place, duplicates keep the newest version. Nothing is deleted: copies go to
# ~/.config/hermes-kit/audit/archive and "hk annuler" undoes it. After photo at the end.
if [ "${HK_SANS_AUDIT:-0}" != 1 ] && [ -f "$HOME/.config/hermes-kit/audit/avant.json" ]; then
  rep=""
  demander rep "Also archive your skills never loaded in 30 days (undo: hk annuler)? y/N" "n" || rep=n
  opt=""; case "$rep" in o|O|oui|Oui|OUI|y|Y|yes|1) opt=--archiver-dormantes ;; esac
  audit_lancer --migrer $opt || avert "migration of the existing setup failed (details in $JOURNAL)"
fi
etape_ok

# -------------------------------------- 9. rtk, Claude Code plugins
etape outils
if [ "${HK_SANS_RTK:-0}" != 1 ] && ! a rtk; then
  dire "installing rtk (compact command output for Claude Code)"
  if [ "$PLATEFORME" = mac ] && a brew; then
    brew install rtk >>"$JOURNAL" 2>&1 || avert "rtk not installed"
  else
    curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh >>"$JOURNAL" 2>&1 || avert "rtk not installed"
  fi
  hash -r
fi
if [ "${HK_SANS_PLUGINS:-0}" != 1 ]; then
  dire "Claude Code plugins"
  while read -r depot plugin; do
    [ -n "$plugin" ] || continue
    claude plugin marketplace add "$depot" >>"$JOURNAL" 2>&1 || true
    if claude plugin install "$plugin" >>"$JOURNAL" 2>&1; then echo "  $plugin"; else avert "plugin not installed: $plugin"; fi
  done <<'EOF'
anthropics/claude-plugins-official frontend-design@claude-plugins-official
thedotmack/claude-mem claude-mem@thedotmack
jarrodwatts/claude-hud claude-hud@claude-hud
alexgreensh/token-optimizer token-optimizer@alexgreensh-token-optimizer
EOF
fi
etape_ok

# ------------------------------------- 9 bis. browser: opencli + extension
# opencli lets the agent read a page in the member's already logged-in Chrome.
# No sudo: npm package placed in ~/.local. The Chrome extension is added by hand,
# we only open the right page; the "boite" step waits until it is connected.
etape navigateur
OPENCLI_EXT=https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk
if [ "${HK_SANS_NAVIGATEUR:-0}" != 1 ]; then
  if ! a opencli; then
    dire "installing opencli (reading pages in your Chrome)"
    npm install -g --prefix "$HOME/.local" @jackwener/opencli >>"$JOURNAL" 2>&1 || avert "opencli not installed (npm)"
    hash -r
  fi
  if a opencli; then
    ok "opencli $(opencli --version 2>/dev/null | head -1)"
    if opencli doctor 2>/dev/null | grep -q 'Extension: connected'; then
      ok "OpenCLI Chrome extension already connected"
    else
      dire "add the OpenCLI extension to Chrome: $OPENCLI_EXT"
      echo "HK_ATTENTE=extension $OPENCLI_EXT"
      for ouvrir in wslview xdg-open open; do
        a "$ouvrir" && { "$ouvrir" "$OPENCLI_EXT" >/dev/null 2>&1 & break; }
      done
    fi
    etape_ok
  else
    echo "HK_ETAPE=navigateur ko"; evenement etape navigateur.ko
  fi
fi

# --------------------------------------------------------------- 10. proxy
etape proxy
dire "proxy dependencies"
(cd "$HK_HOME/proxy" && npm ci --omit=dev --no-audit --no-fund >>"$JOURNAL" 2>&1) || fatal "proxy npm ci failed"
ok "proxy ready"
etape_ok

# ------------------------------------------ 10 bis. auto-jailbreak engine
# Only if the member said yes in 7 bis: the whole engine is downloaded now
# (venv + PyRIT + LiteLLM). Models are auto-detected (OpenRouter key in
# ~/.hermes/.env, or a local Ollama); if none, the engine is still installed
# and the skill's install.sh is re-run later to choose the models.
if [ "$HK_AUTOJB" = oui ]; then
  etape autojb
  AJB="$HERMES_HOME/skills/productivity/auto-jailbreak/scripts/install.sh"
  dire "auto-jailbreak: downloading the engine (PyRIT, a few minutes)"
  if [ -f "$AJB" ] && bash "$AJB" --yes >>"$JOURNAL" 2>&1; then
    ok "auto-jailbreak engine ready"
    etape_ok
  else
    avert "auto-jailbreak engine not installed (see $JOURNAL), re-run: bash $AJB"
    echo "HK_ETAPE=autojb ko"; evenement etape autojb.ko
  fi
fi

# ---------------------------------------------------------------- 11. services
etape services
# Settings that Hermes' config migration must never change: placed once, never overwritten.
mkdir -p "$HERMES_HOME/maj"
[ -f "$HERMES_HOME/maj/reglages-proteges.yaml" ] \
  || cp "$HK_HOME/hermes/maj/reglages-proteges.exemple.yaml" "$HERMES_HOME/maj/reglages-proteges.yaml"
chmod +x "$HERMES_HOME"/scripts/hermes-*.sh "$HERMES_HOME"/scripts/redem-sur.sh 2>/dev/null || true
NODE_BIN=$(command -v node)
CHEMIN="$HOME/.local/bin:/opt/homebrew/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin"
rendre() {
  sed -e "s|__NODE__|$NODE_BIN|g" -e "s|__PROXY_DIR__|$HK_HOME/proxy|g" \
      -e "s|__CLAUDE_BIN__|$CLAUDE_BIN|g" -e "s|__HOME__|$HOME|g" -e "s|__PATH__|$CHEMIN|g" "$1"
}
if [ "${HK_SANS_SERVICES:-0}" != 1 ]; then
  dire "services: proxy (port 8000) and Hermes gateway"
  case "$PLATEFORME" in
    linux|wsl)
      if [ -d /run/systemd/system ] && systemctl --user show-environment >/dev/null 2>&1; then
        mkdir -p "$HOME/.config/systemd/user"
        rendre "$HK_HOME/install/services/claude-proxy.service.tpl" > "$HOME/.config/systemd/user/claude-proxy.service"
        systemctl --user daemon-reload
        systemctl --user enable claude-proxy.service >>"$JOURNAL" 2>&1
        systemctl --user restart claude-proxy.service
        # sudo -n: never a password prompt here, a refusal is only a warning
        ${SUDO:+$SUDO -n} loginctl enable-linger "$USER" >>"$JOURNAL" 2>&1 || avert "enable-linger refused: services will stop at logout (sudo loginctl enable-linger $USER)"
        "$HERMES_BIN" gateway install --force --start-now --start-on-login >>"$JOURNAL" 2>&1 || avert "hermes gateway install failed"
        "$HERMES_BIN" gateway restart >>"$JOURNAL" 2>&1 || true
        # Hermes update attempt every Monday: it never changes the service.
        for u in hermes-maj-hebdo.service hermes-maj-hebdo.timer; do
          sed -e "s|\$HOME|$HOME|g" "$HK_HOME/install/services/$u" > "$HOME/.config/systemd/user/$u"
        done
        systemctl --user daemon-reload
        systemctl --user enable --now hermes-maj-hebdo.timer >>"$JOURNAL" 2>&1 || avert "timer hermes-maj-hebdo not enabled"
        # Daily check: every routine that calls a model must name itself to the proxy (skill mesure-partout).
        if [ -f "$HK_HOME/install/services/controle-mesure.timer" ]; then
          cp "$HK_HOME/install/services/controle-mesure.service" "$HK_HOME/install/services/controle-mesure.timer" "$HOME/.config/systemd/user/"
          systemctl --user daemon-reload
          systemctl --user enable --now controle-mesure.timer >>"$JOURNAL" 2>&1 || avert "timer controle-mesure not enabled"
        fi
      else
        if [ "$PLATEFORME" = wsl ] && ! grep -q '^systemd=true' /etc/wsl.conf 2>/dev/null; then
          if printf '[boot]\nsystemd=true\n' | ${SUDO:+$SUDO -n} tee -a /etc/wsl.conf >/dev/null 2>&1; then
            avert "systemd enabled in /etc/wsl.conf: run 'wsl --shutdown' in PowerShell, reopen Ubuntu, rerun this command"
          else
            avert "systemd missing under WSL: add [boot] systemd=true to /etc/wsl.conf (sudo), then 'wsl --shutdown'"
          fi
        fi
        dire "no systemd: direct launch (nohup), rerun with 'hk start' after a reboot"
        bash "$HOME/.local/bin/hk" start >>"$JOURNAL" 2>&1 || true
      fi ;;
    mac)
      mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
      PL="$HOME/Library/LaunchAgents/com.hermeskit.claude-proxy.plist"
      rendre "$HK_HOME/install/services/com.hermeskit.claude-proxy.plist.tpl" > "$PL"
      launchctl bootout "gui/$(id -u)" "$PL" >/dev/null 2>&1 || true
      launchctl bootstrap "gui/$(id -u)" "$PL" >>"$JOURNAL" 2>&1 || avert "launchctl bootstrap failed"
      "$HERMES_BIN" gateway install --force --start-now --start-on-login >>"$JOURNAL" 2>&1 || avert "hermes gateway install failed"
      "$HERMES_BIN" gateway restart >>"$JOURNAL" 2>&1 || true
      ;;
  esac
fi
etape_ok

# ------------------------------------------------ 11 bis. QG topics (phase 2)
# The Hermes core creates the topics (QG, Coach, Ideas) in the private chat with the bot,
# then writes their ids in config.yaml. We wait for them, then place what depends on them.
etape topics
HK_QG_THREAD=""
if [ "${HK_SANS_SERVICES:-0}" != 1 ] && [ "${HK_CI:-}" != 1 ]; then
  dire "waiting for Hermes to create the QG topics (60 s at most)"
  t=0
  until HK_HOME="$HK_HOME" HERMES_HOME="$HERMES_HOME" HK_TELEGRAM_USER="$HK_TELEGRAM_USER" python3 "$HK_HOME/install/poser.py" --topics >/dev/null 2>&1; do
    [ "$t" -ge "${HK_TOPICS_ATTENTE:-60}" ] && break
    sleep 5; t=$((t + 5))
  done
  if HK_HOME="$HK_HOME" HERMES_HOME="$HERMES_HOME" HK_TELEGRAM_USER="$HK_TELEGRAM_USER" python3 "$HK_HOME/install/poser.py" --topics >/dev/null 2>&1; then
    poser_lancer || fatal "placing files failed (phase 2)"
    "$HERMES_BIN" gateway restart >>"$JOURNAL" 2>&1 || true
    HK_QG_THREAD=$(HK_HOME="$HK_HOME" HERMES_HOME="$HERMES_HOME" HK_TELEGRAM_USER="$HK_TELEGRAM_USER" python3 "$HK_HOME/install/poser.py" --topics | tr ' ' '\n' | sed -n 's/^QG=//p')
    ok "QG topics created (QG thread $HK_QG_THREAD)"
    etape_ok
  else
    avert "topics not created yet: in @BotFather enable topics for the bot and press Start, then run 'hk reparer'"
    echo "HK_ETAPE=topics ko"; evenement etape topics.ko
  fi
else
  avert "topics step skipped (no services started)"
  etape_ok
fi

# ------------------------------------------------------------ 12. verification
etape verification
dire "verification"
sleep 3
KO=0
if curl -fs --max-time 5 http://localhost:8000/health >/dev/null; then ok "proxy: answers on port 8000"; else avert "proxy: no answer on port 8000 (hk logs)"; KO=1; fi
# "Gateway is not running" contains "running": negations are ruled out first.
gw=$("$HERMES_BIN" gateway status 2>/dev/null || true)
if ! printf '%s' "$gw" | grep -qiE "not running|inactive|stopped" && printf '%s' "$gw" | grep -qiE "running|active"; then ok "Hermes gateway: running"; else avert "Hermes gateway: state to check (hk status)"; KO=1; fi
if [ "$KO" = 0 ]; then etape_ok; else echo "HK_ETAPE=verification ko"; evenement etape verification.ko; fi

# ------------------------------------------- 13. test message in the QG
# The first visible result: the bot writes in the QG topic and says what to reply.
etape message_test
if [ "${HK_LANG:-en}" = fr ]; then
  MSG="Bonjour $HK_PRENOM, je suis pret. Ecris-moi ici, dans le sujet QG, par exemple : resume ma journee"
else
  MSG="Hello $HK_PRENOM, I am ready. Write to me here, in the QG topic, for example: summarize my day"
fi
if [ -z "$HK_QG_THREAD" ]; then
  avert "no QG topic yet: test message skipped"
  echo "HK_ETAPE=message_test ko"; evenement etape message_test.ko
elif printf 'url = "https://api.telegram.org/bot%s/sendMessage"\n' "$HK_TELEGRAM_TOKEN" \
   | curl -fs --max-time 10 -K - --data-urlencode "chat_id=$HK_TELEGRAM_USER" \
       --data-urlencode "message_thread_id=$HK_QG_THREAD" --data-urlencode "text=$MSG" \
   | grep -q '"ok":true'; then
  ok "test message sent in the QG topic"
  etape_ok
else
  avert "Telegram refused the test message"
  echo "HK_ETAPE=message_test ko"; evenement etape message_test.ko
fi

# ------------------------------------------ 13 bis. mailbox: the review
# Only with the member's consent (HK_BOITE=oui). Read-only: nothing is sent,
# deleted, archived nor marked read. The database stays on the machine.
etape boite
if [ "${HK_BOITE:-non}" = oui ] && a opencli; then
  ATTENTE=${HK_NAVIGATEUR_ATTENTE:-420}
  t=0
  until opencli doctor 2>/dev/null | grep -q 'Extension: connected'; do
    [ "$t" = 0 ] && { dire "waiting for the OpenCLI Chrome extension ($OPENCLI_EXT)"; echo "HK_ATTENTE=extension $OPENCLI_EXT"; }
    [ "$t" -ge "$ATTENTE" ] && break
    sleep 10; t=$((t + 10))
  done
  if opencli doctor 2>/dev/null | grep -q 'Extension: connected'; then
    dire "reading the mailbox (90 days, 1000 mails at most, read-only)"
    HK_QG_CHAT="$HK_TELEGRAM_USER"
    export TELEGRAM_BOT_TOKEN="$HK_TELEGRAM_TOKEN" HK_QG_CHAT HK_QG_THREAD HK_PRENOM
    if hk-boite indexer --jours 90 --max 1000 && hk-boite bilan; then
      ok "mailbox review sent to the QG topic"
      hk-boite indexer --jours 365 --max 5000 --corps 300 --fond || true
      evenement_unique boite_ok
      etape_ok
    else
      avert "mailbox reading failed: rerun later with 'hk-boite indexer && hk-boite bilan'"
      echo "HK_ETAPE=boite ko"; evenement etape boite.ko
    fi
  else
    avert "Chrome extension not connected: rerun later with 'hk-boite indexer && hk-boite bilan'"
    echo "HK_ETAPE=boite ko"; evenement etape boite.ko
  fi
else
  dire "mailbox: not read (HK_BOITE=oui to enable it, with the member's consent)"
  etape_ok
fi

# ----------------------------------------------------------------- 14. fin
# The after photo, once proxy and services run: score and tracking before -> after.
if [ "${HK_SANS_AUDIT:-0}" != 1 ] && [ -f "$HOME/.config/hermes-kit/audit/avant.json" ]; then
  audit_lancer || avert "after photo failed (details in $JOURNAL)"
fi
etape fin
ecrire_telemetrie
evenement_unique installe
echo
if [ "${HK_LANG:-en}" = fr ]; then
  ok "termine. Dans Telegram, sujet QG : ecrivez \"resume ma journee\". La reponse arrive en moins d'une minute."
else
  ok "done. In Telegram, QG topic: write \"summarize my day\". The answer arrives in under a minute."
fi
echo "    hk status | hk logs | hk restart | hk doctor | hk update | hk reparer | hk telemetrie"
if [ -f "$HOME/.config/hermes-kit/audit/avant.json" ]; then
  if [ "${HK_LANG:-en}" = fr ]; then
    echo "    hk audit : ta config avant / apres. Relance-le dans 7 jours pour voir le gain en tokens."
  else
    echo "    hk audit: your setup before / after. Rerun it in 7 days to see the token gain."
  fi
fi
if bash "$HOME/.local/bin/hk" doctor 2>&1 | grep -q ' KO '; then
  if [ "${HK_LANG:-en}" = fr ]; then
    echo "Pour que Claude Code verifie et aligne la configuration : hk reparer"
  else
    echo "To have Claude Code check and align the configuration: hk reparer"
  fi
fi
etape_ok
