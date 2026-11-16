import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Contracts(unittest.TestCase):
    def test_pinned_inputs_are_complete_and_immutable(self):
        lock = json.loads((ROOT / 'sources.lock.json').read_text())
        self.assertEqual(lock['profile'], 'omarchy-hyprland')
        for name in ('alarm', 'omarchy', 'omarchy_mac', 'recipes'):
            self.assertRegex(lock[name]['commit'], r'^[0-9a-f]{40}$')
        self.assertEqual(lock['omarchy_mac']['version'], '0.2.6')
        import hashlib
        self.assertEqual(hashlib.sha256((ROOT / 'sources/omarchy.db').read_bytes()).hexdigest(),
                         lock['omarchy']['package_database_sha256'])
        self.assertEqual(hashlib.sha256((ROOT / 'sources/alarm-manifest.json').read_bytes()).hexdigest(),
                         lock['alarm']['manifest_sha256'])
        self.assertEqual(hashlib.sha256((ROOT / 'sources/alarm-package-versions.json').read_bytes()).hexdigest(),
                         lock['alarm']['package_versions_sha256'])

    def test_hardware_aliases_never_resolve_to_the_older_omarchy_stack(self):
        selected, excluded = module('select-desktop-packages').targets(
            ['m1n1-aurora', 'linux-asahi', 'vulkan-asahi', 'libva-v4l2_request-avd',
             'omarchy-mac-boot', 'limine', 'foot', 'nvim', 'dotnet-runtime',
             'omarchy-power-profiles-daemon'],
            {'aura', 'linux-aurora', 'vulkan-aurora', 'libva-v4l2-request-avd', 'power-profiles-daemon'})
        self.assertEqual(selected, ['aurora/aura', 'aurora/linux-aurora', 'aurora/vulkan-aurora',
                                    'aurora/libva-v4l2-request-avd', 'omarchy-aurora/omarchy-aurora',
                                    'foot', 'neovim', 'dotnet-runtime-bin', 'aurora/power-profiles-daemon'])
        self.assertEqual(excluded, ['limine'])

    def test_changed_or_removed_hardware_is_a_hard_failure(self):
        check = module('check-hardware-versions').check
        check({'mesa': '30', 'foot': '1'}, {'mesa': '30', 'foot': '2'}, {'mesa'})
        for after in ({'mesa': '31'}, {}):
            with self.assertRaisesRegex(ValueError, 'hardware package set changed'):
                check({'mesa': '30'}, after, {'mesa'})

    def test_hardware_must_match_the_exact_signed_snapshot_even_without_a_desktop_change(self):
        check = module('check-hardware-versions').check
        check({'mesa': '30'}, {'mesa': '30'}, {'mesa'}, {'mesa': '30'})
        with self.assertRaisesRegex(ValueError, 'differs from the signed snapshot'):
            check({'mesa': '31'}, {'mesa': '31'}, {'mesa'}, {'mesa': '30'})

    def test_compatibility_evidence_covers_the_exact_shipped_platform_and_runtime(self):
        import hashlib
        lock = (ROOT / 'sources.lock.json').read_bytes()
        data = json.loads(lock)
        evidence = {'mac_unit_suite': True, 'mac_integration_suite': True,
                    'integration_scope': 'omarchy-mac',
                    'runtime_tests': data['validation']['mac_runtime_tests'],
                    'sources_lock_sha256': hashlib.sha256(lock).hexdigest(),
                    'mac_source': data['omarchy_mac']['commit'], 'runtime_source': data['omarchy']['commit']}
        verify = module('compatibility').verify
        verify(evidence, lock)
        for key in evidence:
            with self.subTest(field=key), self.assertRaises(ValueError):
                verify(dict(evidence, **{key: None}), lock)

    def test_producer_extension_refuses_upstream_contract_drift(self):
        extend = module('prepare-base').extend
        source = ('size=6G\nchroot "$mountroot" userdel -r alarm\n'
                  'if [[ $profile == arch-kde ]]; then\nfi\n'
                  'if [[ $profile == arch-kde ]]; then\nfi\n'
                  'tar --sparse -C "$root/out/$profile-installer" -cf - . | zstd\n')
        result = extend(source)
        self.assertIn('size=32G', result)
        self.assertEqual(result.count('/src/scripts/prepare-root'), 1)
        self.assertEqual(result.count('/src/scripts/configure-root'), 1)
        with self.assertRaises(ValueError):
            extend(source.replace('size=6G', 'size=8G'))
        with self.assertRaises(ValueError):
            extend(source.replace('userdel -r alarm', 'userdel alarm'))

    def test_repository_templates_preserve_required_package_signatures_and_priority(self):
        text = (ROOT / 'overlay/usr/share/omarchy-aurora/pacman/pacman-edge.conf').read_text()
        self.assertLess(text.index('[aurora]'), text.index('[omarchy-aurora]'))
        self.assertLess(text.index('[omarchy-aurora]'), text.index('[omarchy]'))
        self.assertNotIn('TrustAll', text)
        self.assertNotIn('SigLevel = Never', text)
        self.assertEqual(text.count('Required DatabaseRequired'), 2)

    def test_only_the_aurora_boot_provider_is_packaged(self):
        base = ROOT / 'overlay/usr/lib/omarchy'
        self.assertTrue((base / 'aurora-boot/setup-boot').is_file())
        self.assertFalse((base / 'mac-boot').exists())
        self.assertIn('aurora-root', (ROOT / 'docs/boot-contract.txt').read_text())


if __name__ == '__main__':
    unittest.main()
