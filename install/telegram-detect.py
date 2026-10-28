#!/usr/bin/env python3
"""Detect the Telegram user id from the /start the user sends to the bot.

Reads the bot token from the HK_TOKEN environment variable (never as an argument:
an argument stays in the shell history). Waits at most N seconds (argument 1,
default 180) for a private message to the bot.

Prints a shell assignment, to be passed to `eval`:
    HK_TELEGRAM_USER=5678
Exit code 1 if no private message was received.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

TOKEN = os.environ.get("HK_TOKEN", "").strip()
DELAI = int(sys.argv[1]) if len(sys.argv) > 1 else 180
if not TOKEN:
    print("HK_TOKEN missing", file=sys.stderr)
    sys.exit(2)
API = f"https://api.telegram.org/bot{TOKEN}/"


def appel(methode, **params):
    data = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in params.items()}
    ).encode()
    with urllib.request.urlopen(API + methode, data=data, timeout=40) as r:  # noqa: S310  fixed https
        rep = json.load(r)
    if not rep.get("ok"):
        raise RuntimeError(rep.get("description", methode))
    return rep["result"]


try:
    appel("deleteWebhook")
except Exception as e:  # an active webhook blocks getUpdates
    print(f"deleteWebhook: {e}", file=sys.stderr)

offset = None
fin = time.time() + DELAI
print(f"waiting for /start ({DELAI} s)...", file=sys.stderr)
while time.time() < fin:
    try:
        maj = appel(
            "getUpdates",
            timeout=20,
            allowed_updates=["message"],
            **({"offset": offset} if offset is not None else {}),
        )
    except Exception as e:
        print(f"getUpdates: {e}", file=sys.stderr)
        time.sleep(3)
        continue
    for u in maj:
        offset = u["update_id"] + 1
        m = u.get("message") or {}
        de = m.get("from") or {}
        if (m.get("chat") or {}).get("type") == "private" and not de.get("is_bot") and de.get("id"):
            print(f"HK_TELEGRAM_USER={de['id']}")
            sys.exit(0)
sys.exit(1)
