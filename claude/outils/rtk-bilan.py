#!/usr/bin/env python3
"""Bilan RTK : gains par jour, par commande, et ce qui passe a cote.

  rtk-bilan.py [nb_jours]   (defaut : 7)
"""
import sqlite3, os, sys

J = int(sys.argv[1]) if len(sys.argv) > 1 else 7
p = os.path.expanduser('~/.local/share/rtk/history.db')
if not os.path.exists(p):
    sys.exit('base RTK absente : ' + p)
c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
f = f"datetime('now','-{J} days')"

print(f"=== PAR JOUR ({J} derniers) ===")
for d, n, sv, i in c.execute(
        f"SELECT date(timestamp),count(*),sum(saved_tokens),sum(input_tokens) "
        f"FROM commands WHERE timestamp > {f} GROUP BY 1 ORDER BY 1 DESC"):
    print(f"  {d}  {n:6d} cmd  {(sv or 0)/1000:8.1f}k economises sur {(i or 0)/1000:8.1f}k")

print("\n=== CE QUI EST OPTIMISE ===")
for cmd, n, sv, pct in c.execute(
        f"SELECT substr(rtk_cmd,1,22),count(*),sum(saved_tokens),avg(savings_pct) "
        f"FROM commands WHERE timestamp > {f} GROUP BY 1 ORDER BY 3 DESC LIMIT 8"):
    print(f"  {cmd:24s} {n:5d}x  {(sv or 0)/1000:8.1f}k  ({pct or 0:.0f} %)")

print("\n=== CE QUI PASSE A COTE ===")
for cmd, n, i in c.execute(
        f"SELECT substr(original_cmd,1,30),count(*),sum(input_tokens) FROM commands "
        f"WHERE timestamp > {f} AND coalesce(saved_tokens,0)=0 GROUP BY 1 "
        f"ORDER BY 3 DESC LIMIT 8"):
    print(f"  {cmd:32s} {n:5d}x  {(i or 0)/1000:7.1f}k non optimises")

print("\n=== COMMANDES QUE RTK NE SAIT PAS LIRE ===")
for e, n in c.execute("SELECT substr(error_message,1,45),count(*) FROM parse_failures "
                      "GROUP BY 1 ORDER BY 2 DESC LIMIT 5"):
    print(f"  {n:5d}x  {(e or '').splitlines()[0]}")
