import importlib.util
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

HOOK = Path.home() / ".claude/hooks/verif-avant-annonce.py"
spec = importlib.util.spec_from_file_location("verif_avant_annonce", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
ANNONCE = "C'est corrigé, vérifié par test."


def test_python_edit_without_verification_is_refused():
    assert hook.decision(ANNONCE, [("Edit", {"file_path": "app.py"})])[-1] == "rien"


def test_config_edit_without_verification_is_refused():
    assert hook.decision(ANNONCE, [("Edit", {"file_path": "config.json"})])[-1] == "rien"


def test_http_200_login_page_does_not_prove_business_delivery():
    tools = [("Edit", {"file_path": "app.py"}), ("Bash", {"command": "curl https://exemple.tld"})]
    results = {1: (False, "HTTP 200 <title>Connexion</title>")}
    assert hook.decision(ANNONCE, tools, results)[-1] == "preuve_insuffisante"


def test_successful_pytest_is_accepted():
    tools = [("Edit", {"file_path": "app.py"}), ("Bash", {"command": "pytest -q"})]
    assert hook.decision(ANNONCE, tools, {1: (False, "1 passed")}) is None


def test_expected_auth_login_test_is_accepted():
    tools = [("Edit", {"file_path": "auth.py"}), ("Bash", {"command": "pytest -q tests/test_login.py"})]
    assert hook.decision(ANNONCE, tools, {1: (False, "1 passed: test_login_redirects_to_login")}) is None


def test_main_returns_expected_codes_with_mocked_transcript_and_journal():
    scenarios = [
        ([('Edit', {'file_path': 'app.py'})], {}, 2),
        ([('Edit', {'file_path': 'config.yaml'})], {}, 2),
        ([('Edit', {'file_path': 'app.py'}), ('Bash', {'command': 'curl https://exemple.tld'})],
         {1: (False, 'HTTP 200 <title>Connexion</title>')}, 2),
        ([('Edit', {'file_path': 'app.py'}), ('Bash', {'command': 'pytest -q'})],
         {1: (False, '1 passed')}, 0),
    ]
    import _tour
    for tools, results, expected in scenarios:
        with patch.object(hook.sys, 'stdin', io_string_input()), \
             patch.object(_tour, 'lire_tour', return_value=(ANNONCE, tools, ''), side_effect=None), \
             patch.object(hook, 'open', create=True) as mocked_open, \
             patch.dict(os.environ, {'VERIF_ANNONCE_OFF': ''}):
            mocked_open.return_value.__enter__.return_value = io_string_input()
            # Patch the local import's result map through the supplied reader.
            original = _tour.lire_tour
            def read_turn(_path, result_map):
                result_map.update(results)
                return ANNONCE, tools, ''
            with patch.object(_tour, 'lire_tour', side_effect=read_turn):
                assert hook.main() == expected


def io_string_input():
    from io import StringIO
    return StringIO(json.dumps({'last_assistant_message': ANNONCE, 'transcript_path': 'mock'}))


if __name__ == '__main__':
    tests = [(name, test) for name, test in list(globals().items()) if name.startswith('test_')]
    for name, test in tests:
        test()
        print('PASS', name)
    print('TOTAL', len(tests))
