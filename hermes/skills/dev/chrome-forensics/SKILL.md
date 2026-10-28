---
name: chrome-forensics
description: Lire bookmarks, historique, cookies Chrome sans le fermer.
version: 1.0.0
---

# Chrome Forensics: Lecture sans fermer le navigateur

Quand Chrome est ouvert, SQLite locke `History`, `Cookies`, `Login Data`. Impossible
de les lire directement. Solution : copier les fichiers dans `/tmp` d'abord.

## Profils Vin

```bash
~/.config/google-chrome/Profile 5/   # principal
~/.config/google-chrome/Profile 6/   # secondaire
~/.config/google-chrome/Default/     # fallback
```

## Bookmarks (JSON, jamais locké)

```python
import json
data = json.load(open(expanduser("~/.config/google-chrome/Profile 5/Bookmarks")))
def walk(n):
    if isinstance(n, dict):
        if 'url' in n and any(kw in n['url'].lower() for kw in keywords):
            print(n['name'], n['url'])
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for i in n: walk(i)
walk(data)
```

## Historique (copie obligatoire)

```python
import shutil, sqlite3
src = expanduser("~/.config/google-chrome/Profile 5/History")
tmp = "/tmp/hist_copy.db"
shutil.copy2(src, tmp)
db = sqlite3.connect(tmp)
rows = db.execute("SELECT url, title FROM urls WHERE url LIKE '%stackry%'").fetchall()
db.close()
# Optionnel : supprimer /tmp/hist_copy.db après
```

## Cookies (copie obligatoire)

```python
shutil.copy2("Cookies", "/tmp/cookies_copy.db")
db = sqlite3.connect("/tmp/cookies_copy.db")
rows = db.execute("SELECT host_key, name FROM cookies WHERE host_key LIKE '%myus.com%'").fetchall()
# Les valeurs sont chiffrées (AES-GCM), besoin de la clé du keychain
```

## Login Data (copie obligatoire)

```python
shutil.copy2("Login Data", "/tmp/login_copy.db")
db = sqlite3.connect("/tmp/login_copy.db")
rows = db.execute("SELECT origin_url, username_value FROM logins WHERE origin_url LIKE '%myus.com%'").fetchall()
# Les mots de passe sont chiffrés
```

## Recherche Google dans l'historique

Les URLs `google.com/search?q=...` contiennent les termes recherchés.
Extraire le paramètre `q=` pour retrouver les sujets explorés par Vin.