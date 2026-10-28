import json, os, subprocess
H = os.path.expanduser("~/.claude/hooks/")
B = "$HOME/Bureau/Projets/perso/agent/claude-proxy/.claude/hooks/bash_guard.py"
PK = "p" + "kill"
P = os.path.expanduser("~/Bureau/Projets")


def run(hook, cmd=None, tool="Bash", inp=None, env=None):
    data = {"tool_name": tool, "tool_input": inp or {"command": cmd}}
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(["python3", hook], input=json.dumps(data), capture_output=True, text=True, env=e)
    if r.returncode == 2 or '"deny"' in r.stdout:
        return "REFUS"
    if "updatedInput" in r.stdout:
        return "BASCULE:" + str(json.loads(r.stdout)["hookSpecificOutput"]["updatedInput"].get("run_in_background"))
    return "PASSE"


cas = [
    # (hook, commande, attendu)
    (B, f"grep -n '{PK}' notes.md", "PASSE"),
    (B, f"echo 'ne jamais faire {PK}'", "PASSE"),
    (B, f"{PK} -f '[h]ermes-test'", "PASSE"),
    (B, f"{PK} -f chrome", "REFUS"),
    (B, f"ls && {PK} node", "REFUS"),
    (B, 'D=$HOME/.hermes/cache/scratch/x; rm -rf "$D"', "PASSE"),
    (B, 'rm -rf "$D"/', "REFUS"),
    (B, 'D=; rm -rf "$D"/', "REFUS"),
    (B, "systemctl --user stop foo; journalctl -u claude-proxy", "PASSE"),
    (B, "systemctl --user restart claude-proxy", "REFUS"),
    (B, "sudo systemctl restart hermes-gateway.service", "REFUS"),
    (H + "projet-sans-famille.py", f"ls {P}/* > $HOME/.hermes/cache/scratch/l.txt", "PASSE"),
    (H + "projet-sans-famille.py", f"cat {P}/*/LISEZMOI.md", "PASSE"),
    (H + "projet-sans-famille.py", f"mkdir {P}/truc-neuf-zz", "REFUS"),
    (H + "portail-sonnet.py", "opencli browser tabs", "PASSE"),
    (H + "portail-sonnet.py", "opencli browser --help", "PASSE"),
    (H + "portail-sonnet.py", "opencli browser open https://x.com", "REFUS"),
    (H + "portail-sonnet.py", "opencli browser tabs; opencli browser click 3", "REFUS"),
]
ko = 0
for hook, cmd, att in cas:
    got = run(hook, cmd)
    ok = got == att
    ko += not ok
    print("ok " if ok else "KO ", att.ljust(6), got.ljust(6), os.path.basename(hook), cmd[:60])
env = {"CLAUDE_TIMEOUT_MS": "1"}
for inp, att in [({"prompt": "x", "description": "d"}, "BASCULE:False"),
                 ({"prompt": "x", "description": "d", "run_in_background": False}, "PASSE")]:
    got = run(H + "agent-fond-guard.py", tool="Agent", inp=inp, env=env)
    ko += got != att
    print("ok " if got == att else "KO ", att, got, "agent-fond", inp.get("run_in_background"))
print(ko, "echec(s)")
