#!/usr/bin/env python3
"""hk banc: measure what a skill brings, with and without it, on 2 models.

Usage:
    hk banc <skill-folder> [--modeles fort,gratuit] [--taches id1,id2]
            [--conditions avec,sans] [--jobs 3] [--essai] [--garder]

Each run starts Hermes in a blank HOME (sandbox), with only its bundled skills
("sans") or the bundled skills plus the tested one ("avec", not forced: the
model has to pick it like in real life), or preloaded with -s ("forcee": what
the skill brings once read, apart from triggering), or "aiguillee": "avec" plus
the text hk-aiguilleur.py would inject through pre_llm_call (the router picks
the skill from the message, the model no longer has to). The task comes from
<skill>/tests/taches.jsonl, its files from <skill>/tests/<fixtures>/.

Two sliders per run:
    performance = share of the task checks passed (regex on the final answer)
    simplicity  = tokens read and written, from Hermes' own stream-json count

Writes <skill>/tests/mesure.json (summary, never by hand) and appends one line
per run to ~/.config/hermes-kit/banc.jsonl (the measurement journal).
"""

import argparse
import concurrent.futures as cf
import contextlib
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HOME = Path.home()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", HOME / ".hermes"))
HERMES_BIN = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "hermes"
JOURNAL = HOME / ".config" / "hermes-kit" / "banc.jsonl"
# claude-proxy logs the real usage of each call; in -toolrelay mode Hermes only
# gets estimates (2026-10-25: 5 868 announced, 13 071 real with cache).
PROXY_USAGE = HERMES_HOME / "proxy-usage.jsonl"
PROXY_LOCK = threading.Lock()  # one proxy run at a time: the time window names it
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "hermes-kit" / "banc"

# The strong model goes through the local claude-proxy (Claude subscription).
# Suffix -toolrelay: the proxy hands tool calls back to Hermes (sandboxed)
# instead of running its own tools on the host,
# the free one through OpenRouter (":free" models that call tools, checked
# 2026-10-25: nemotron-3.5-lightning and laguna-s-2.1 pass, gemma-4 returns 429).
MODELES = {
    "fort": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6-toolrelay",
        "base_url": "http://localhost:8000/anthropic",
    },
    "gratuit": {"provider": "openrouter", "model": "nvidia/nemotron-3.5-lightning:free"},
}
TOOLSETS = ["file", "skills"]  # no terminal, even jailed: keep the run read-and-answer
# Tools those toolsets give. Any other tool call = the sandbox leaked (run voided).
ALLOWED_TOOLS = {
    "read_file",
    "write_file",
    "patch",
    "search_files",
    "skills_list",
    "skill_view",
    "skill_manage",
}
MAX_TURNS = 15
TIMEOUT_S = 360
RETRIES = 3
BULLET = re.compile(r"^\s*([-*•]|\d+[.)])\s+")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+")


JAIL_HOME = "/home/banc"


def jail(run):
    """bubblewrap: the run sees its sandbox as /home/banc and nothing of /home,
    /mnt, /media or /tmp. Hermes' file tools read any path, so a plain HOME
    swap is not enough (2026-10-25: a run read the real ~/Bureau notes).
    The Hermes checkout and its Python stay read-only, the network is shared
    (claude-proxy and OpenRouter)."""
    if not shutil.which("bwrap"):
        sys.exit("bwrap (bubblewrap) missing: the bench refuses to run unjailed")
    ro = [str(HERMES_HOME / "hermes-agent")] + [d for d in ("/home/linuxbrew",) if Path(d).exists()]
    args = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/home",
        "--tmpfs",
        "/mnt",
        "--tmpfs",
        "/media",
        "--tmpfs",
        "/tmp",  # noqa: S108 (tmpfs neuf monte dans la prison bwrap)
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--bind",
        str(run),
        JAIL_HOME,
    ]
    for d in ro:
        args += ["--ro-bind", d, d]
    return args + ["--chdir", JAIL_HOME, "--die-with-parent", "--"]


def proxy_tokens(t0, t1):
    """Real tokens of the proxy calls made between t0 and t1 (epoch seconds).
    Hermes sends no metadata.user_id, so the call is found by its time window
    (relay calls are logged as source "prime"). None when nothing matches."""
    if not PROXY_USAGE.exists():
        return None
    lo = dt.datetime.fromtimestamp(t0 - 1, dt.UTC).strftime("%Y-%m-%dT%H:%M:%S")
    hi = dt.datetime.fromtimestamp(t1 + 5, dt.UTC).strftime("%Y-%m-%dT%H:%M:%S")
    tot = {"appels": 0, "entree": 0, "sortie": 0, "cache_lu": 0, "cache_ecrit": 0, "cout_usd": 0.0}
    with PROXY_USAGE.open(encoding="utf-8") as f:
        f.seek(max(0, PROXY_USAGE.stat().st_size - 2_000_000))
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (lo <= e.get("ts", "")[:19] <= hi) or e.get("source") != "prime":
                continue
            if any(not k.startswith("mcp__relay__") for k in (e.get("outils") or {})):
                continue
            tot["appels"] += 1
            for k in ("entree", "sortie", "cache_lu", "cache_ecrit", "cout_usd"):
                tot[k] += e.get(k) or 0
    return tot if tot["appels"] else None


def openrouter_key():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    env = HERMES_HOME / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    return key


def load_tasks(skill, only):
    path = skill / "tests" / "taches.jsonl"
    tasks = [json.loads(lg) for lg in path.read_text(encoding="utf-8").splitlines() if lg.strip()]
    return [t for t in tasks if not only or t["id"] in only]


ROUTER = Path(__file__).with_name("hk-aiguilleur.py")
ROUTES, ROUTES_LOCK = {}, threading.Lock()


def route(task):
    """What the skill router injects for this task (once per task, all models)."""
    with ROUTES_LOCK:
        if task["id"] not in ROUTES:
            py = os.environ.get("HK_EMBED_PYTHON") or sys.executable
            p = subprocess.run(  # noqa: S603 (python et routeur du kit, pas d'entree externe)
                [
                    py,
                    str(ROUTER),
                    "injection",
                    "--json",
                    "--racine-vue",
                    f"{JAIL_HOME}/.hermes/skills/banc",
                    task["consigne"],
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            line = next((lg for lg in reversed(p.stdout.splitlines()) if lg.startswith("{")), None)
            if not line:
                sys.exit(f"skill router failed on {task['id']}: {p.stderr[-400:]}")
            ROUTES[task["id"]] = json.loads(line)
        return ROUTES[task["id"]]


def build_sandbox(skill, task, modele, condition):
    run = Path(tempfile.mkdtemp(prefix=f"hkbanc-{task['id']}-", dir=CACHE))
    if task.get("fixtures"):
        shutil.copytree(skill / "tests" / task["fixtures"], run, dirs_exist_ok=True)
    hh = run / ".hermes"
    hh.mkdir()
    m = MODELES[modele]
    lines = ["model:", f"  default: {m['model']}", f"  provider: {m['provider']}"]
    if m.get("base_url"):
        lines.append(f"  base_url: {m['base_url']}")
    ts = task.get("toolsets", TOOLSETS)
    lines += ["toolsets:"] + [f"  - {t}" for t in ts]
    lines += ["platform_toolsets:", "  cli:"] + [f"    - {t}" for t in ts]
    (hh / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if m["provider"] == "openrouter":
        env = hh / ".env"
        env.write_text(f"OPENROUTER_API_KEY={openrouter_key()}\n", encoding="utf-8")
        env.chmod(0o600)
    if condition in ("avec", "forcee", "aiguillee"):
        dest = hh / "skills" / "banc" / skill.name
        shutil.copytree(
            skill, dest, ignore=shutil.ignore_patterns("tests", "__pycache__"), symlinks=False
        )
    if condition == "aiguillee":  # the injected skills must exist where the header says
        for name, path in route(task).get("chemins", {}).items():
            dest = hh / "skills" / "banc" / name
            if not dest.exists():
                shutil.copytree(
                    path,
                    dest,
                    ignore=shutil.ignore_patterns("tests", "__pycache__", ".git"),
                    symlinks=False,
                )
    return run


def parse(out):
    events = []
    for line in out.splitlines():
        if line.startswith("{"):
            with contextlib.suppress(json.JSONDecodeError):
                events.append(json.loads(line))
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tools = [e for e in events if e.get("type") == "tool_use"]
    return result, tools


def score(task, text):
    checks = []
    for c in task.get("verifs", []):
        found = re.search(c["motif"], text, re.M) is not None
        checks.append({"nom": c["nom"], "ok": found == c.get("doit", True)})
    lines = text.splitlines()
    if "max_puces" in task:
        n = sum(1 for lg in lines if BULLET.match(lg))
        checks.append({"nom": f"{n} puces <= {task['max_puces']}", "ok": n <= task["max_puces"]})
    if "max_numerotees" in task:
        n = sum(1 for lg in lines if NUMBERED.match(lg))
        checks.append(
            {
                "nom": f"{n} numerotees <= {task['max_numerotees']}",
                "ok": n <= task["max_numerotees"],
            }
        )
    passed = sum(c["ok"] for c in checks)
    return round(passed / len(checks), 3) if checks else 0.0, checks


def one_run(skill, task, modele, condition, keep):
    raw_dir = CACHE / "sorties" / skill.name
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw = raw_dir / f"{task['id']}_{modele}_{condition}.jsonl"
    routed = route(task) if condition == "aiguillee" else {}
    prompt = task["consigne"] + (f"\n\n{routed['injection']}" if routed.get("injection") else "")
    for attempt in range(1, RETRIES + 1):
        run = build_sandbox(skill, task, modele, condition)
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("OPENROUTER_API_KEY", "TMPDIR") and not k.startswith("XDG_")
        }
        env.update(
            HOME=JAIL_HOME,
            HERMES_HOME=f"{JAIL_HOME}/.hermes",
            TMPDIR="/tmp",  # noqa: S108 (le /tmp de la prison, un tmpfs neuf)
            ANTHROPIC_API_KEY=env.get("ANTHROPIC_API_KEY", "proxy-local"),
        )
        lock = PROXY_LOCK if MODELES[modele].get("base_url") else contextlib.nullcontext()
        lock.acquire() if lock is PROXY_LOCK else None
        t0 = time.time()
        try:
            p = subprocess.run(  # noqa: S603 (bwrap + hermes du kit, arguments construits ici)
                jail(run)
                + [
                    str(HERMES_BIN),
                    "chat",
                    "-Q",
                    "--format",
                    "stream-json",
                    "--max-turns",
                    str(MAX_TURNS),
                    "-t",
                    ",".join(task.get("toolsets", TOOLSETS)),
                    *(["-s", skill.name] if condition == "forcee" else []),
                    "-q",
                    prompt,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
            out, rc = p.stdout + p.stderr, p.returncode
        except subprocess.TimeoutExpired as exc:
            out, rc = (
                (exc.stdout or b"").decode()
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or ""),
                124,
            )
        t1 = time.time()
        real = proxy_tokens(t0, t1) if lock is PROXY_LOCK else None
        if lock is PROXY_LOCK:
            lock.release()
        dur = round(t1 - t0, 1)
        if not keep:
            shutil.rmtree(run, ignore_errors=True)
        raw.write_text(out, encoding="utf-8")
        result, tools = parse(out)
        text = result.get("text") or ""
        transient = re.search(r"HTTP (429|5\d\d)", out) and not text.strip()
        if not transient or attempt == RETRIES:
            break
        time.sleep(30 * attempt)
    tok = result.get("tokens") or {}
    if real:  # the proxy count wins over the relay estimate
        tok = {
            "input": real["entree"],
            "output": real["sortie"],
            "cache_read": real["cache_lu"],
            "total": real["entree"] + real["sortie"] + real["cache_lu"] + real["cache_ecrit"],
        }
    perf, checks = score(task, text)
    leaks = sorted({t.get("name") for t in tools} - ALLOWED_TOOLS)
    if leaks:
        perf = 0.0
    loaded = (
        condition == "forcee"
        or skill.name in routed.get("choix", [])
        or any(
            t.get("name") == "skill_view" and skill.name in json.dumps(t.get("input", {}))
            for t in tools
        )
    )
    return {
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "skill": skill.name,
        "tache": task["id"],
        "modele": modele,
        "modele_id": MODELES[modele]["model"],
        "condition": condition,
        "performance": perf,
        "verifs": checks,
        "skill_chargee": loaded,
        **(
            {"skills_injectees": routed.get("choix", []), "aiguillage": routed.get("voie")}
            if condition == "aiguillee"
            else {}
        ),
        "tokens_total": tok.get("total"),
        "tokens_entree": tok.get("input"),
        "tokens_sortie": tok.get("output"),
        "cache_lu": tok.get("cache_read"),
        "tokens_source": "proxy" if real else "hermes",
        "cout_usd": real and round(real["cout_usd"], 4),
        "outils": len(tools),
        "duree_s": dur,
        "rc": rc,
        "essais": attempt,
        "fuite": leaks,
        "erreur": f"sandbox leak: {','.join(leaks)}"
        if leaks
        else None
        if text.strip()
        else (re.findall(r'"error": "([^"]{0,120})', out) or [f"rc={rc}"])[0],
        "sortie": str(raw),
    }


def summary(rows):
    out = {}
    for r in rows:
        key = f"{r['modele']}/{r['condition']}"
        d = out.setdefault(
            key, {"n": 0, "performance": 0.0, "tokens": 0, "chargee": 0, "erreurs": 0}
        )
        d["n"] += 1
        d["performance"] += r["performance"]
        d["tokens"] += r["tokens_total"] or 0
        d["chargee"] += r["skill_chargee"]
        d["erreurs"] += r["erreur"] is not None
    for d in out.values():
        d["performance"] = round(d["performance"] / d["n"], 3)
        d["tokens"] = round(d["tokens"] / d["n"])
    return out


def main():
    ap = argparse.ArgumentParser(prog="hk banc", description=__doc__.split("\n\n")[0])
    ap.add_argument("skill")
    ap.add_argument("--modeles", default="fort,gratuit")
    ap.add_argument("--conditions", default="avec,sans")
    ap.add_argument("--taches", default="")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--essai", action="store_true", help="1 task, 1 model, 1 condition (avec)")
    ap.add_argument("--garder", action="store_true", help="keep the sandbox HOMEs")
    a = ap.parse_args()

    skill = Path(a.skill).expanduser().resolve()
    if not (skill / "tests" / "taches.jsonl").exists():
        sys.exit(f"{skill}/tests/taches.jsonl missing: write 3 tasks first (see hk verifier)")
    if not HERMES_BIN.exists():
        sys.exit(f"Hermes not found at {HERMES_BIN}")
    modeles = [m for m in a.modeles.split(",") if m]
    if "gratuit" in modeles and not openrouter_key():
        sys.exit("OPENROUTER_API_KEY missing (env or ~/.hermes/.env): free model unavailable")
    tasks = load_tasks(skill, set(filter(None, a.taches.split(","))))
    conds = a.conditions.split(",")
    if a.essai:
        tasks, modeles, conds = tasks[:1], modeles[:1], conds[:1]
    CACHE.mkdir(parents=True, exist_ok=True)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)

    plan = [(t, m, c) for t in tasks for m in modeles for c in conds]
    print(
        f"{skill.name}: {len(plan)} runs ({len(tasks)} tasks x {len(modeles)} models x "
        f"{len(conds)})",
        flush=True,
    )
    rows = []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futs = {pool.submit(one_run, skill, t, m, c, a.garder): (t, m, c) for t, m, c in plan}
        for f in cf.as_completed(futs):
            r = f.result()
            rows.append(r)
            with JOURNAL.open("a", encoding="utf-8") as j:
                j.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(
                f"  {r['tache']:<14} {r['modele']:<8} {r['condition']:<5} perf "
                f"{r['performance']:.2f}"
                f"  tokens {r['tokens_total'] or 0:>7}  skill "
                f"{'oui' if r['skill_chargee'] else 'non'}"
                f"  {r['duree_s']:>5}s" + (f"  ERREUR {r['erreur']}" if r["erreur"] else ""),
                flush=True,
            )

    res = summary(rows)
    print("\nmodele/condition   perf   tokens  skill chargee")
    for k in sorted(res):
        d = res[k]
        print(
            f"  {k:<16} {d['performance']:.2f}  {d['tokens']:>7}  {d['chargee']}/{d['n']}"
            + (f"  ({d['erreurs']} erreur)" if d["erreurs"] else "")
        )
    if not a.essai:
        # merge with the previous measure: a run on one condition keeps the others
        path = skill / "tests" / "mesure.json"
        old = {}
        if path.exists():
            with contextlib.suppress(ValueError, OSError):
                old = json.loads(path.read_text(encoding="utf-8"))
        neufs = {(x["modele"], x["condition"]) for x in rows}

        def keep(r):
            return (r["modele"], r["condition"]) not in neufs

        runs = [r for r in old.get("runs", []) if keep(r)] + [
            {
                k: r[k]
                for k in (
                    "tache",
                    "modele",
                    "condition",
                    "performance",
                    "tokens_total",
                    "skill_chargee",
                    "erreur",
                )
            }
            for r in rows
        ]
        par = {**old.get("par_condition", {}), **res}
        mods = sorted({k.split("/")[0] for k in par})

        def perf(m, c):
            return par.get(f"{m}/{c}", {}).get("performance")

        gain = {}
        for m in mods:
            for c in ("avec", "forcee", "aiguillee"):
                if perf(m, c) is not None and perf(m, "sans") is not None:
                    gain[f"{m}/{c}"] = round(perf(m, c) - perf(m, "sans"), 3)
        mesure = {
            "date": dt.date.today().isoformat(),
            "modeles": {**old.get("modeles", {}), **{m: MODELES[m]["model"] for m in modeles}},
            "toolsets": TOOLSETS,
            "par_condition": par,
            "gain_contre_sans": gain,
            "runs": runs,
        }
        path.write_text(json.dumps(mesure, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwritten: {path}")


if __name__ == "__main__":
    main()
