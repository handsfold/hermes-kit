#!/usr/bin/env python3
"""Un seul producteur updatedInput : plafond tests/build, RTK sinon.

Les tests/build gardent leurs logs bruts complets. Les autres commandes
compatibles utilisent RTK. Aucun changement de permission ou de commande
n'est execute par ce hook, seul l'input Bash peut etre remplace.
"""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return
    if event.get('tool_name') != 'Bash':
        return
    try:
        tool_input = event.get('tool_input') or {}
        command = tool_input.get('command', '')
        if command and 'bounded-build-run.py' not in command:
            source = Path(__file__).with_name('bounded-build-output.py')
            spec = importlib.util.spec_from_file_location(
                'bounded_build_output_local', source)
            bounded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bounded)
            if bounded.reconnue(command):
                cwd = event.get('cwd') or os.getcwd()
                runner = source.with_name('bounded-build-run.py')
                updated = dict(tool_input)
                updated['command'] = 'python3 %s --cwd %s %s' % (
                    runner, shlex.quote(cwd), shlex.quote(command))
                sys.stdout.write(json.dumps({'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse', 'updatedInput': updated}}))
                return
        rtk = shutil.which('rtk')
        if rtk:
            result = subprocess.run([rtk, 'hook', 'claude'], input=raw,
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                json.loads(result.stdout)
                sys.stdout.write(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return  # Echec ouvert : commande originale, jamais auto-autorisee.


if __name__ == '__main__':
    main()
