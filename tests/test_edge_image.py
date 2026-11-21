import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('edge_image', ROOT / 'scripts/edge-image.py')
edge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(edge)

PAIR = {'linux': {'repository': 'aurora-silicon/linux', 'branch': 'aurora-edge', 'revision': '1' * 40, 'tree': '2' * 40},
        'mesa': {'repository': 'aurora-silicon/mesa', 'branch': 'aurora-edge', 'revision': '3' * 40, 'tree': '4' * 40}}
ALARM = {'schema': 2, 'distribution': 'arch', 'profile': 'arch-minimal', 'channel': 'edge',
         'snapshot': 'edge-20261121.1', 'feed': 'https://aurorasilicon.org/alarm-aurora/edge/aarch64',
         'packaged_sources': PAIR,
         'files': {'kernelImageSHA256': 'sha256:' + '5' * 64, 'mesaDsoSHA256': 'sha256:' + '6' * 64}}


class EdgeImageTests(unittest.TestCase):
    def test_the_overlay_precedes_aurora_in_the_shipped_template(self):
        text = (ROOT / 'overlay/usr/share/omarchy-aurora/pacman/pacman-edge.conf').read_text()
        result = edge.with_edge(text, edge.FEED)
        self.assertLess(result.index('[aurora-edge]'), result.index('[aurora]\n'))
        self.assertLess(result.index('[aurora]\n'), result.index('[omarchy-aurora]'))
        self.assertEqual(result.count('Required DatabaseRequired'), 3)
        self.assertIn('[aurora-edge]\nSigLevel = Required DatabaseRequired\nServer = ' + edge.FEED + '\n', result)
        with self.assertRaises(ValueError):
            edge.with_edge(result, edge.FEED)
        self.assertEqual(edge.build_server('edge-20261121.1'),
                         'https://github.com/aurora-silicon/alarm-aurora/releases/download/edge-20261121.1')

    def test_the_omarchy_proof_names_its_overlay_and_alarm_edge_snapshot(self):
        proof = edge.omarchy_proof(ALARM, 'testing-20261121.2')
        self.assertEqual((proof['distribution'], proof['profile'], proof['snapshot'], proof['alarm_snapshot']),
                         ('omarchy', 'omarchy-hyprland', 'testing-20261121.2', 'edge-20261121.1'))
        self.assertEqual((proof['files'], proof['packaged_sources']), (ALARM['files'], PAIR))
        for key, value in (('profile', 'arch-kde'), ('channel', 'testing'), ('feed', 'https://example.invalid')):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'ALARM Edge proof'):
                edge.omarchy_proof(dict(ALARM, **{key: value}), 'testing-20261121.2')

    def test_images_workflow_takes_the_alarm_edge_overlay(self):
        text = (ROOT / '.github/workflows/images.yml').read_text()
        self.assertIn('alarm-edge-snapshot:', text)
        self.assertIn('out/omarchy-hyprland-installer/edge-image-proof.json', text)


if __name__ == '__main__':
    unittest.main()
