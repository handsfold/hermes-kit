#!/usr/bin/env python3
"""hk verifier: check a skill folder against the 5 HandsFold rules.

Usage:
    hk verifier <skill-folder> [...]

Rules:
    1. hook (first sentence of `description`) of 57 characters at most:
       Hermes shows the first 57 characters in its skill index.
    2. body of 200 lines targeted, 500 at most.
    3. deterministic code lives in scripts/, not in long inline blocks.
    4. one real example of input and output.
    5. tests/taches.jsonl holds 3 real tasks, each with a checker,
       and the folder holds no secret (gitleaks when installed).

Output: E = error (blocks), W = warning. Exit code 1 when an error exists.
Stdlib only.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOOK_MAX = 57
BODY_TARGET = 200
BODY_MAX = 500
INLINE_CODE_MAX = 15
TASKS_MIN = 3
DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")
SECRET_PATTERNS = [
    re.compile(r"sk-(ant|or|proj)-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"\b\d{9,10}:AA[A-Za-z0-9_-]{30,}"),  # Telegram bot token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def frontmatter(text):
    """Return (fields, body). Top-level keys only, enough for name/description."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None, text
    fields, key, raw = {}, None, []
    for line in lines[1:end]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(\s.*|)$", line)
        if m and not line.startswith((" ", "\t")):
            if key:
                fields[key] = clean(raw)
            key, raw = m.group(1), [m.group(2).strip()]
        elif key:
            raw.append(line.strip())
    if key:
        fields[key] = clean(raw)
    return fields, "\n".join(lines[end + 1 :])


def clean(raw):
    head = raw[0]
    if head in (">", ">-", "|", "|-"):
        return " ".join(x for x in raw[1:] if x)
    txt = " ".join(x for x in raw if x).strip()
    if len(txt) >= 2 and txt[0] in "\"'" and txt[-1] == txt[0]:
        txt = txt[1:-1]
    return txt


def hook_of(description):
    m = re.match(r"(.+?[.!?])(\s|$)", description)
    return (m.group(1) if m else description).strip()


def check_tasks(folder, errs, avert):
    path = folder / "tests" / "taches.jsonl"
    if not path.exists():
        errs.append(f"rule 5: {path.relative_to(folder)} missing ({TASKS_MIN} real tasks expected)")
        return
    tasks = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError as exc:
            errs.append(f"rule 5: taches.jsonl line {n} is not JSON ({exc.msg})")
            continue
        tasks.append(t)
        tid = t.get("id", f"line {n}")
        if not t.get("consigne"):
            errs.append(f"rule 5: task {tid} has no 'consigne'")
        checks = t.get("verifs") or []
        if not checks:
            errs.append(f"rule 5: task {tid} has no checker ('verifs')")
        for c in checks:
            try:
                re.compile(c.get("motif", ""))
            except re.error as exc:
                errs.append(f"rule 5: task {tid}, check {c.get('nom')}: bad regex ({exc})")
        fx = t.get("fixtures")
        if fx and not (folder / "tests" / fx).is_dir():
            errs.append(f"rule 5: task {tid}: fixtures folder tests/{fx} missing")
    if len(tasks) < TASKS_MIN:
        errs.append(f"rule 5: {len(tasks)} task(s), {TASKS_MIN} expected")


def check_secrets(folder, errs):
    if shutil.which("gitleaks"):
        r = subprocess.run(  # noqa: S603 (gitleaks trouve par shutil.which juste avant)
            ["gitleaks", "dir", str(folder), "--no-banner", "--redact", "-l", "error"],  # noqa: S607
            capture_output=True,
            text=True,
        )
        if r.returncode == 1:
            errs.append("rule 5: gitleaks found a secret (run: gitleaks dir <folder> --redact)")
        return
    for f in folder.rglob("*"):
        if f.is_file() and f.stat().st_size < 1_000_000:
            try:
                txt = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(p.search(txt) for p in SECRET_PATTERNS):
                errs.append(f"rule 5: possible secret in {f.relative_to(folder)}")


def verify(arg):
    folder = Path(arg).expanduser().resolve()
    if folder.name == "SKILL.md":
        folder = folder.parent
    skill = folder / "SKILL.md"
    errs, avert = [], []
    if not skill.exists():
        return folder, [f"{skill} not found"], []
    fields, body = frontmatter(skill.read_text(encoding="utf-8"))
    if fields is None:
        return folder, ["SKILL.md must start with a '---' frontmatter"], []
    if fields.get("name") != folder.name:
        errs.append(f"name '{fields.get('name')}' differs from folder '{folder.name}'")
    desc = fields.get("description", "")
    if not desc:
        errs.append("rule 1: description missing")
    else:
        hook = hook_of(desc)
        if len(hook) > HOOK_MAX:
            errs.append(
                f"rule 1: hook of {len(hook)} characters, {HOOK_MAX} at most: « {hook[:70]}... »"
            )

    n = len(body.strip("\n").splitlines())
    if n > BODY_MAX:
        errs.append(f"rule 2: body of {n} lines, {BODY_MAX} at most")
    elif n > BODY_TARGET:
        avert.append(f"rule 2: body of {n} lines, {BODY_TARGET} targeted")

    for block in re.findall(r"```[a-z]*\n(.*?)```", body, re.S):
        if len(block.splitlines()) > INLINE_CODE_MAX:
            avert.append(
                f"rule 3: inline code block of {len(block.splitlines())} lines: move it to scripts/"
            )
            break
    for ref in set(re.findall(r"scripts/[\w./-]+\.(?:py|sh|js|mjs)", body)):
        if not (folder / ref).exists():
            errs.append(f"rule 3: {ref} cited but missing")

    if not re.search(
        r"(?im)^#+ .*(exemple|example)|\b(entr[ée]e|input)\b.*\n(.*\n){0,15}.*\b(sortie|output)\b",
        body,
    ):
        avert.append(
            "rule 4: no real input/output example found (a '## Example' section is enough)"
        )

    check_tasks(folder, errs, avert)
    check_secrets(folder, errs)

    for f in folder.rglob("*.md"):
        if DASHES.search(f.read_text(encoding="utf-8", errors="ignore")):
            avert.append(f"long dash (U+2013/U+2014) in {f.relative_to(folder)}")
    return folder, errs, avert


def main(args):
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    worst = 0
    for a in args:
        folder, errs, avert = verify(a)
        state = "ERROR" if errs else ("review" if avert else "ok")
        print(f"{folder.name}: {state}")
        for e in errs:
            print(f"  E {e}")
        for w in avert:
            print(f"  W {w}")
        worst = max(worst, 1 if errs else 0)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
