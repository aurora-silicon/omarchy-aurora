import importlib.util
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('key_agents', Path(__file__).resolve().parents[1] / 'scripts/stop-image-key-agents.py')
agents = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agents)


class KeyAgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.root = self.path / 'image'
        self.root.mkdir()
        self.proc = self.path / 'proc'
        self.proc.mkdir()

    def process(self, pid, root, comm='gpg-agent', state='S'):
        path = self.proc / str(pid)
        path.mkdir()
        (path / 'comm').write_text(comm)
        (path / 'stat').write_text(f'{pid} ({comm}) {state} 1 2 3')
        (path / 'root').symlink_to(root)
        return path

    def test_only_live_key_agents_in_the_exact_image_are_selected(self):
        self.process(101, self.root)
        self.process(102, '/')
        self.process(103, str(self.root) + '-other')
        self.process(104, self.root, comm='bash')
        self.process(105, self.root, state='Z')
        self.assertEqual(agents.remaining(self.root, self.proc), [101])

    def test_signals_use_stable_handles_and_ignore_every_other_process(self):
        self.process(101, self.root)
        self.process(102, '/')
        with patch.object(os, 'pidfd_open', return_value=901) as opened, \
             patch.object(signal, 'pidfd_send_signal') as sent, patch.object(os, 'close') as closed:
            agents.signal_owned(self.root, signal.SIGTERM, self.proc)
        opened.assert_called_once_with(101)
        sent.assert_called_once_with(901, signal.SIGTERM)
        closed.assert_called_once_with(901)

    def test_ownership_is_rechecked_before_signalling(self):
        process = self.process(101, self.root)
        def open_reused(pid):
            (process / 'root').unlink()
            (process / 'root').symlink_to('/')
            return 901
        with patch.object(os, 'pidfd_open', side_effect=open_reused), \
             patch.object(signal, 'pidfd_send_signal') as sent, patch.object(os, 'close') as closed:
            agents.signal_owned(self.root, signal.SIGKILL, self.proc)
        sent.assert_not_called()
        closed.assert_called_once_with(901)

    def test_host_root_is_rejected_before_any_operation(self):
        with patch.object(agents.subprocess, 'run') as run, self.assertRaises(ValueError):
            agents.stop(Path('/'))
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
