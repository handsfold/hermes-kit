#!/usr/bin/env bash
# Eprouve les hooks Stop tiret-interdit.py et verif-avant-annonce.py (2026-10-07).
# Chaque cas fabrique un transcript et une entree Stop, lance le hook, lit le code
# de sortie (2 = REFUS, 0 = PASSE). Les tirets longs sont construits par chr() :
# ce fichier n'en contient aucun.
# Usage : ~/.claude/hooks/tests/stop-hooks.sh   (sortie 1 si un cas echoue)
cd "$(dirname "$0")/.." || exit 2
ECHECS=0
export HOME_HOOKS="$PWD"
SCRIPT=$(cat <<'PY'
import json, os, subprocess, sys, tempfile
hook, attendu, scenario = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
CAD, DEMI = chr(0x2014), chr(0x2013)
sub = lambda s: s.replace("<CAD>", CAD).replace("<DEMI>", DEMI)
texte = sub(scenario.get("texte", ""))
lignes = [{"type": "user", "message": {"role": "user", "content": scenario.get("demande", "demande de USER")}}]
for k, o in enumerate(scenario.get("outils", [])):
    nom, entree = o[0], o[1]
    sortie, erreur = (o[2] if len(o) > 2 else "ok"), (o[3] if len(o) > 3 else False)
    lignes.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": f"t{k}", "name": nom, "input": entree}]}})
    lignes.append({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"t{k}", "content": sortie, "is_error": erreur}]}})
lignes.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": texte}]}})
with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
    f.write("\n".join(json.dumps(l) for l in lignes) + "\n")
entree = {"transcript_path": scenario.get("transcript", f.name),
          "stop_hook_active": scenario.get("actif", False)}
if scenario.get("brut") is not None:
    stdin = scenario["brut"]
else:
    stdin = json.dumps(entree)
faux_home = tempfile.mkdtemp()
os.makedirs(faux_home + "/.claude/hooks")
env = dict(os.environ, HOME=faux_home, **scenario.get("env", {}))
r = subprocess.run(["python3", hook], input=stdin, capture_output=True, text=True, env=env)
os.unlink(f.name)
obtenu = "REFUS" if r.returncode == 2 else "PASSE"
resume = scenario.get("nom", "")
if obtenu == attendu and (obtenu == "PASSE" or r.stderr.strip()):
    print(f"ok    {attendu}  {resume}")
else:
    print(f"ECHEC attendu {attendu}, obtenu {obtenu} (code {r.returncode}) : {resume} {r.stderr[:120]}")
    sys.exit(1)
PY
)
cas() { # cas <hook> <REFUS|PASSE> <json du scenario>
  python3 -c "$SCRIPT" "$1" "$2" "$3" || ECHECS=$((ECHECS+1))
}

T=tiret-interdit.py
cas $T REFUS '{"nom":"cadratin dans une reponse","texte":"Voici le resultat <CAD> termine."}'
cas $T REFUS '{"nom":"demi-cadratin entre deux nombres","texte":"Entre 1<DEMI>2 jours."}'
cas $T PASSE '{"nom":"tiret dans un bloc de code","texte":"Voici :\n```\na <CAD> b\n```\nFin."}'
cas $T PASSE '{"nom":"tiret dans une citation guillemets","texte":"Le document dit « 1er<DEMI>2 mars » tel quel."}'
cas $T PASSE '{"nom":"trait d union ordinaire","texte":"Un peu-etre 1-2 jours, c-a-d ok."}'
cas $T PASSE '{"nom":"deja refuse une fois (stop_hook_active)","texte":"a <CAD> b","actif":true}'
cas $T PASSE '{"nom":"echappatoire TIRET_OK=1","texte":"a <CAD> b","env":{"TIRET_OK":"1"}}'
cas $T PASSE '{"nom":"fail-open : entree illisible","brut":"pas du json"}'
cas $T PASSE '{"nom":"fail-open : transcript absent","transcript":"/tmp/inexistant.jsonl"}'

V=verif-avant-annonce.py
EDIT='["Edit",{"file_path":"/srv/projet/app.py","old_string":"a","new_string":"b"}]'
cas $V REFUS "{\"nom\":\"code modifie, rien execute, annonce 'c'est corrige'\",\"texte\":\"C'est corrigé : le bug est réglé.\",\"outils\":[$EDIT]}"
cas $V REFUS "{\"nom\":\"code modifie, seulement git diff apres\",\"texte\":\"J'ai corrigé le bug.\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"git diff app.py\"}]]}"
cas $V REFUS '{"nom":"sed -i sur un .py puis annonce","texte":"Le bug est corrigé.","outils":[["Bash",{"command":"sed -i s/a/b/ /srv/projet/app.py"}]]}'
cas $V PASSE "{\"nom\":\"code modifie puis execute\",\"texte\":\"C'est corrigé : testé, la sortie est bonne.\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 /srv/projet/app.py\"}]]}"
cas $V PASSE "{\"nom\":\"code modifie puis curl\",\"texte\":\"Ça marche maintenant, vérifié par curl.\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"curl -s localhost:8000/health\"}]]}"
cas $V REFUS "{\"nom\":\"annonce ET aveu non verifie (cas SILENT 19:07)\",\"texte\":\"C'est réglé.\\n- Pas encore vérifié sur un vrai passage.\",\"outils\":[$EDIT]}"
cas $V PASSE "{\"nom\":\"en ligne, aveu sur une donnee\",\"texte\":\"C'est en ligne : la page Routes est servie.\\n- **Prix d'achat** non vérifié.\",\"outils\":[$EDIT]}"
cas $V PASSE "{\"nom\":\"aveu sans annonce de reussite\",\"texte\":\"Correctif posé, non vérifié : pas de serveur ici.\",\"outils\":[$EDIT]}"
cas $V PASSE '{"nom":"seul un .md modifie","texte":"C est corrigé.","outils":[["Edit",{"file_path":"/tmp/notes.md","old_string":"a","new_string":"b"}]]}'
cas $V PASSE "{\"nom\":\"code modifie, aucune annonce\",\"texte\":\"J'ai modifié app.py, à toi de lancer.\",\"outils\":[$EDIT]}"
cas $V PASSE '{"nom":"annonce sans aucune modification","texte":"C est corrigé depuis hier.","outils":[]}'
cas $V PASSE "{\"nom\":\"deja refuse une fois\",\"texte\":\"C'est corrigé.\",\"outils\":[$EDIT],\"actif\":true}"
cas $V PASSE "{\"nom\":\"echappatoire VERIF_ANNONCE_OFF\",\"texte\":\"C'est corrigé.\",\"outils\":[$EDIT],\"env\":{\"VERIF_ANNONCE_OFF\":\"1\"}}"
cas $V PASSE '{"nom":"fail-open : entree illisible","brut":"{"}'

# durcissement du 2026-10-13
OK="C'est corrigé : vérifié, la sortie est bonne."
cas $V REFUS "{\"nom\":\"seulement un redemarrage apres\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"systemctl --user restart app.service\"}]]}"
cas $V REFUS "{\"nom\":\"seulement py_compile apres\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 -m py_compile /srv/projet/app.py\"}]]}"
cas $V PASSE "{\"nom\":\"redemarrage puis curl\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"systemctl --user restart app && curl -s localhost:8000\"}]]}"
cas $V REFUS "{\"nom\":\"verification en erreur (code de sortie)\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 verif.py\"},\"Exit code 1\",true]]}"
cas $V REFUS "{\"nom\":\"cas SILENT : Parse error dans la sortie\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"bash verif.sh\"},\"Parse error: no such column\"]]}"
cas $V PASSE "{\"nom\":\"echec puis verification reussie\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 verif.py\"},\"Traceback (most recent call last)\"],[\"Bash\",{\"command\":\"python3 verif.py\"},\"3 ok\"]]}"
cas $V REFUS "{\"nom\":\"USER cite un site, preuve en local\",\"demande\":\"pilotage.entreprise-a.co.th ne marche pas\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"curl -s localhost:8800\"}]]}"
cas $V PASSE "{\"nom\":\"USER cite un site, preuve sur ce site\",\"demande\":\"https://pilotage.entreprise-a.co.th/x ne marche pas\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"bin/verif-ui.sh https://pilotage.entreprise-a.co.th/x\"}]]}"
cas $V PASSE "{\"nom\":\"site dans la memoire injectee seulement\",\"demande\":\"corrige le bug <memory-context>voir exemple.tld</memory-context>\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 app.py\"}]]}"
cas $V REFUS "{\"nom\":\"annonce qui ne dit pas comment c'est verifie\",\"texte\":\"C'est corrigé.\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 app.py\"}]]}"
cas $V PASSE "{\"nom\":\"site vise par un script de test ecrit avant\",\"demande\":\"exemple.tld/tout deborde\",\"texte\":\"$OK\",\"outils\":[[\"Bash\",{\"command\":\"cat > /tmp/t.py <<EOF\\npage.goto('https://exemple.tld/tout')\\nEOF\"}],$EDIT,[\"Bash\",{\"command\":\"python3 /tmp/t.py\"}]]}"
cas $V PASSE "{\"nom\":\"resume de compaction plein d'adresses\",\"demande\":\"This session is being continued. exemple.tld\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 app.py\"}]]}"
cas $V PASSE "{\"nom\":\"lien YouTube partage par USER\",\"demande\":\"regarde https://youtu.be/abc et corrige\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"python3 app.py\"}]]}"
cas $V REFUS "{\"nom\":\"rejeu SILENT : modif par heredoc python, verif en echec, puis lecture sqlite\",\"texte\":\"C'est réglé, testé sur de vrais cas.\",\"outils\":[[\"Bash\",{\"command\":\"python3 - <<'P'\\nf='qg-collecter.py'\\nopen(f,'w').write(s)\\nP\"}],[\"Bash\",{\"command\":\"python3 - <<'P'\\nimport sqlite3\\nP\"},\"Exit code 1\",true],[\"Bash\",{\"command\":\"date +%T; sqlite3 ~/.hermes/qg.db \\\"select id from attente\\\"\"}]]}"
cas $V REFUS "{\"nom\":\"modif par cat > fichier.py, rien lance\",\"texte\":\"$OK\",\"outils\":[[\"Bash\",{\"command\":\"cat > /srv/app.py <<EOF\\nprint(1)\\nEOF\"}]]}"
cas $V PASSE "{\"nom\":\"modif par cat > fichier.py puis lance\",\"texte\":\"$OK\",\"outils\":[[\"Bash\",{\"command\":\"cat > /srv/app.py <<EOF\\nprint(1)\\nEOF\"}],[\"Bash\",{\"command\":\"python3 /srv/app.py\"}]]}"
cas $V PASSE "{\"nom\":\"2>&1 n'est pas une modification\",\"texte\":\"C'est corrigé depuis hier.\",\"outils\":[[\"Bash\",{\"command\":\"python3 x.py 2>&1 | tail\"}]]}"
cas $V REFUS "{\"nom\":\"verification lancee en arriere-plan (nohup), non lue\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"nohup bash verif.sh > v.log 2>&1 &\"}]]}"
cas $V PASSE "{\"nom\":\"script de test ecrit dans /tmp, code livre non touche\",\"texte\":\"C'est en ligne.\",\"outils\":[[\"Bash\",{\"command\":\"cat > /tmp/cap.mjs <<EOF\\nx\\nEOF\\nnode /tmp/cap.mjs\"}]]}"
cas $V REFUS "{\"nom\":\"texte d'un heredoc vers un .md n'est pas une verification\",\"texte\":\"$OK\",\"outils\":[$EDIT,[\"Bash\",{\"command\":\"cat >> notes.md <<'E'\\nmake deploy\\nlancer le test\\nE\"}]]}"

echo "$ECHECS echec(s)"
[ "$ECHECS" -eq 0 ]
