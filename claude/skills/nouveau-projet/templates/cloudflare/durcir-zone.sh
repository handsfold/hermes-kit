#!/usr/bin/env bash
# Durcit une zone Cloudflare neuve, sans rien casser si on le relance.
# Usage : durcir-zone.sh <domaine> [--mail]   (--mail : le domaine envoie du mail, SPF/DMARC laisses a la main)
# Lecons de tous les sites (ProjetA, MARQUE-E, Vynn, realvoxai) : une zone neuve
# a cache navigateur 4 h, https off, TLS 1.0, ni SPF ni DMARC, www sans redirection.
set -euo pipefail
D="${1:?Usage : durcir-zone.sh <domaine> [--mail]}"; MAIL="${2:-}"
cd ~/Bureau/Projets/business/sites/projet-a   # .infisical.json
infisical run --env=prod --path=/cloudflare --silent -- env D="$D" MAIL="$MAIL" python3 - <<'PY'
import json, os, urllib.request
T, D = os.environ["API_TOKEN_SUPER"], os.environ["D"]
def api(m, p, b=None):
    r = urllib.request.Request("https://api.cloudflare.com/client/v4" + p, method=m,
        data=json.dumps(b).encode() if b is not None else None,
        headers={"Authorization": f"Bearer {T}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r))["result"]
Z = api("GET", f"/zones?name={D}")[0]["id"]
for k, v in {"browser_cache_ttl": 0, "always_use_https": "on", "min_tls_version": "1.2", "ssl": "full"}.items():
    api("PATCH", f"/zones/{Z}/settings/{k}", {"value": v}); print(f"ok  {k} = {v}")
if not os.environ["MAIL"]:
    for nom, val in ((D, "v=spf1 -all"), (f"_dmarc.{D}", "v=DMARC1; p=reject")):
        deja = [r for r in api("GET", f"/zones/{Z}/dns_records?type=TXT&name={nom}") if r["content"].strip('"').startswith(val.split(";")[0].split(" ")[0])]
        if not deja: api("POST", f"/zones/{Z}/dns_records", {"type": "TXT", "name": nom, "content": val, "ttl": 1})
        print(f"ok  TXT {nom} = {val}" + (" (deja la)" if deja else ""))
regle = {"description": "www vers apex", "action": "redirect", "enabled": True,
         "expression": f'(http.host eq "www.{D}")',
         "action_parameters": {"from_value": {"status_code": 301, "preserve_query_string": True,
             "target_url": {"expression": f'concat("https://{D}", http.request.uri.path)'}}}}
api("PUT", f"/zones/{Z}/rulesets/phases/http_request_dynamic_redirect/entrypoint", {"rules": [regle]})
print(f"ok  www.{D} -> https://{D} (301, chemin et parametres gardes)")
print("Rappel : le DNS de www doit exister (proxifie) pour que la redirection reponde.")
PY
