"""Transforme la configuration Hermes vivante en modele a trous.

- ~/.hermes/config.yaml -> hermes/config.exemple.yaml :
    . chaque cle secrete est videe ;
    . sous platforms.telegram.channel_prompts, seuls les topics generiques restent,
      renommes en trous (__QG_THREAD__, __COACH_THREAD__) ;
    . le routeur local (port 8010) devient le proxy livre avec le kit (port 8000).
- hermes/gateway_model_overrides.exemple.json : exemple SYNTHETIQUE (2 topics), jamais
  une copie du fichier vivant. Le 2026-10-04, la copie brute a emporte 3 jetons OAuth
  dans un commit : les overrides portent des api_key par topic.
Le texte est traite ligne a ligne pour garder les commentaires et ligne'ordre.
"""

import json
import re
from pathlib import Path

H = Path.home() / ".hermes"
SECRETES = re.compile(
    r"^(\s*)(api_key|record_key|token|secret|password|bot_token|webhook_secret)(\s*:\s*)(.*)$"
)
GARDEES = {"local", "''", '""', "", "~"}
TOPICS = {"2923": "__QG_THREAD__", "635": "__COACH_THREAD__"}
PROXY = "http://localhost:8000"
REMPLACEMENTS = [
    ("http://localhost:8010/anthropic", PROXY),
    ("http://127.0.0.1:8010/anthropic", PROXY),
    ("provider: routeur", "provider: claude-proxy"),
    ("  routeur:", "  claude-proxy:"),
    ("name: Routeur local", "name: Claude proxy local"),
]
CLE_TOPIC = re.compile(r"^(\s+)'?(\d+)'?\s*:")
HOOK_CMD = re.compile(r"^\s*-\s*command:\s*~/\.hermes/agent-hooks/(\S+)")
KIT_HOOKS = Path("hermes/agent-hooks")
KIT_PLUGINS = {"telegram-menus", "mode-objectif", "aiguilleur"}
PLUGIN_TELEGRAM = re.compile(r"^telegram-\w+$")  # renomme telegram-menus par la desidentification


def filtrer_hooks(lignes):
    """Dans hooks:, jette chaque hook dont le script n'est pas livre par le kit.

    Le 2026-10-04, le test reel a montre 6 hooks perso exportes sans leur script :
    Hermes les cherchait a chaque tour (« command not found »).
    """
    sortie, i = [], 0
    while i < len(lignes):
        if lignes[i].rstrip() != "hooks:":
            sortie.append(lignes[i])
            i += 1
            continue
        i += 1
        evenements = []
        while i < len(lignes) and (not lignes[i].strip() or lignes[i].startswith(" ")):
            ligne = lignes[i]
            if (
                ligne.strip()
                and not ligne.lstrip().startswith(("-", "timeout"))
                and ligne.startswith("  ")
                and not ligne.startswith("   ")
            ):
                evenements.append([ligne, []])
                i += 1
                continue
            m = HOOK_CMD.match(ligne)
            j = i + 1
            while (
                j < len(lignes)
                and lignes[j].startswith("    ")
                and not lignes[j].lstrip().startswith("-")
            ):
                j += 1
            if evenements and (m is None or (KIT_HOOKS / m.group(1)).exists()):
                evenements[-1][1].extend(lignes[i:j])
            i = j
        gardes = [(t, c) for t, c in evenements if c]
        if gardes:
            sortie.append("hooks:")
            for tete, corps in gardes:
                sortie.append(tete)
                sortie.extend(corps)
        else:
            sortie.append("hooks: {}")
    return sortie


def est_kit(nom):
    return nom in KIT_PLUGINS or bool(PLUGIN_TELEGRAM.match(nom))


def filtrer_plugins(lignes):
    """Dans plugins:, ne garde que les plugins livres par le kit (enabled et entries).

    Les autres sont propres a l'installation d'origine et n'existent pas dans le kit.
    """
    sortie, dans, rubrique, entree_ok = [], False, None, True
    for ligne in lignes:
        if not ligne.startswith(" ") and ligne.strip():
            dans = ligne.rstrip() == "plugins:"
        if dans:
            s = ligne.strip()
            indent = len(ligne) - len(ligne.lstrip())
            if indent == 2 and s.endswith(":"):
                rubrique = s[:-1]
            elif rubrique == "enabled" and s.startswith("- ") and not est_kit(s[2:]):
                continue
            elif rubrique == "entries":
                if indent == 4 and s.endswith(":"):
                    entree_ok = est_kit(s[:-1])
                if not entree_ok:
                    continue
        sortie.append(ligne)
    return sortie


def filtrer_topics(lignes):
    """Dans channel_prompts, garde les topics de TOPICS, renommes ; jette les autres."""
    sortie, i = [], 0
    while i < len(lignes):
        ligne = lignes[i]
        sortie.append(ligne)
        i += 1
        if ligne.strip() != "channel_prompts:":
            continue
        indent_bloc = None
        while i < len(lignes):
            m = CLE_TOPIC.match(lignes[i])
            if not m or (indent_bloc is not None and len(m.group(1)) != indent_bloc):
                break
            indent_bloc = len(m.group(1))
            topic = m.group(2)
            j = i + 1
            while j < len(lignes) and (
                not lignes[j].strip() or len(lignes[j]) - len(lignes[j].lstrip()) > indent_bloc
            ):
                j += 1
            if topic in TOPICS:
                bloc = lignes[i:j]
                bloc[0] = (
                    bloc[0]
                    .replace(f"'{topic}'", f"'{TOPICS[topic]}'", 1)
                    .replace(f"{topic}:", f"'{TOPICS[topic]}':", 1)
                )
                sortie.extend(bloc)
            i = j
    return sortie


DM_TOPICS = """      dm_topics:
        - chat_id: __QG_CHAT__
          topics:
            - name: QG
              icon_color: 7322096
            - name: Coach
              icon_color: 16766590
            - name: Ideas
              icon_color: 13338331""".splitlines()


def bloc_extra(lignes, i):
    """Les lignes du bloc qui suit « extra: » (indentees d'au moins 6 espaces)."""
    bloc = []
    for suite in lignes[i + 1 :]:
        if suite.strip() and not suite.startswith("      "):
            break
        bloc.append(suite)
    return bloc


def filtrer_bot_local(lignes):
    """Retire le serveur Bot API local (127.0.0.1:8093) : absent chez les autres.

    Le 2026-10-27 a 14:22, base_url, base_file_url et local_mode sont arrives
    entre « extra: » et « command_menu: ». L'ancrage a casse la synchro, et
    publies tels quels ils coupaient Telegram a toute nouvelle installation.
    """
    sortie = []
    for ligne in lignes:
        cle = ligne.strip().split(":", 1)[0]
        if (
            ligne.startswith("      ")
            and not ligne.startswith("       ")
            and (
                (cle in ("base_url", "base_file_url") and "127.0.0.1" in ligne)
                or cle == "local_mode"
            )
        ):
            continue
        sortie.append(ligne)
    return sortie


def ajouter_dm_topics(lignes):
    """Les sujets du QG, que le coeur d'Hermes cree lui-meme dans le chat prive du bot."""
    sortie, fait = [], False
    for i, ligne in enumerate(lignes):
        sortie.append(ligne)
        if not fait and ligne == "    extra:" and "      command_menu:" in bloc_extra(lignes, i):
            sortie.extend(DM_TOPICS)
            fait = True
    if not fait:
        raise SystemExit("exporter-config : ancrage 'extra:' (command_menu) introuvable")
    return sortie


def main():
    src = H / "config.yaml"
    dst = Path("hermes/config.exemple.yaml")
    dst.parent.mkdir(parents=True, exist_ok=True)
    lignes = []
    for ligne in src.read_text().splitlines():
        m = SECRETES.match(ligne)
        if m and m.group(4).strip() not in GARDEES:
            ligne = m.group(1) + m.group(2) + m.group(3) + '""  # a renseigner'
        for a, b in REMPLACEMENTS:
            ligne = ligne.replace(a, b)
        lignes.append(ligne)
    lignes = filtrer_plugins(filtrer_hooks(filtrer_topics(lignes)))
    lignes = ajouter_dm_topics(filtrer_bot_local(lignes))
    dst.write_text("\n".join(lignes) + "\n")

    # Overrides par topic : un modele par salon Telegram. Exemple construit, pas copie.
    exemple = {
        "agent:main:telegram:dm:__QG_CHAT__:__QG_THREAD__": {
            "model": "claude-opus-5-5",
            "provider": "claude-proxy",
            "api_key": "local",
            "base_url": PROXY,
            "api_mode": "anthropic_messages",
        },
        "agent:main:telegram:dm:__QG_CHAT__:__COACH_THREAD__": {
            "model": "claude-sonnet-5",
            "provider": "claude-proxy",
            "api_key": "local",
            "base_url": PROXY,
            "api_mode": "anthropic_messages",
        },
    }
    Path("hermes/gateway_model_overrides.exemple.json").write_text(
        json.dumps(exemple, indent=2, ensure_ascii=False) + "\n"
    )
    print("config : modele ecrit")


if __name__ == "__main__":
    main()
