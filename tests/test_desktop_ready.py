import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

SPEC = importlib.util.spec_from_file_location('desktop_ready', Path(__file__).resolve().parents[1] / 'scripts/vm-desktop-ready.py')
desktop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desktop)


class DesktopReadyTests(unittest.TestCase):
    def test_process_or_socket_presence_without_a_monitor_is_not_ready(self):
        for response in ('No instances found.\n', '[]', '{}'):
            self.assertIsNone(desktop.ready_session(lambda arguments: response))
        answers = iter([json.dumps([{'instance': 'session_123'}]), '[]'])
        self.assertIsNone(desktop.ready_session(lambda arguments: next(answers)))

    def test_only_a_responsive_nonzero_output_is_accepted(self):
        for dimensions, expected in [({'width': 0, 'height': 800}, None),
                                     ({'width': 1280, 'height': 800}, 'session_123')]:
            calls = []
            def query(arguments):
                calls.append(arguments)
                return json.dumps([{'instance': 'session_123'}]) if arguments[-1] == 'instances' else json.dumps([dimensions])
            self.assertEqual(desktop.ready_session(query), expected)
            self.assertEqual(calls[-1], ['hyprctl', '-i', 'session_123', '-j', 'monitors'])

    def test_an_initializing_ipc_server_can_be_retried(self):
        def unavailable(arguments):
            raise subprocess.CalledProcessError(1, arguments)
        self.assertIsNone(desktop.ready_session(unavailable))


if __name__ == '__main__':
    unittest.main()
