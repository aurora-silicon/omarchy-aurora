#!/usr/bin/env python3
"""Resolve the Omarchy desktop while keeping Aurora's hardware providers."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    'nvim': 'neovim', 'dotnet-runtime': 'dotnet-runtime-bin',
    'omarchy-power-profiles-daemon': 'power-profiles-daemon',
    'linux': 'linux-aurora', 'linux-aarch64': 'linux-aurora', 'linux-asahi': 'linux-aurora',
    'linux-headers': 'linux-aurora-headers', 'linux-asahi-headers': 'linux-aurora-headers',
    'm1n1': 'aura', 'm1n1-aurora': 'aura', 'uboot-asahi': 'uboot-aurora',
    'mesa': 'mesa-aurora', 'vulkan-asahi': 'vulkan-aurora',
    'asahi-audio': 'aurora-audio', 'alsa-ucm-conf-asahi': 'alsa-ucm-conf-aurora',
    'asahi-bless': 'aurora-bless', 'libva-v4l2_request-avd': 'libva-v4l2-request-avd',
    'upower': 'upower-aurora', 'networkmanager': 'networkmanager-aurora',
    'omarchy-mac-boot': 'omarchy-aurora',
}
EXCLUDED_BOOT = {'limine', 'limine-mkinitcpio-hook', 'limine-snapper-sync',
                 'omarchy-first-boot', 'omarchy-apple-boot'}
OVERLAY = {'omarchy', 'omarchy-settings', 'omarchy-mac', 'omarchy-aurora'}


def targets(names, hardware, providers=None):
    providers = providers or {}
    result, excluded = [], []
    for original in names:
        if original in EXCLUDED_BOOT:
            excluded.append(original)
            continue
        name = ALIASES.get(original, original if original in hardware else providers.get(original, original))
        if name in hardware:
            name = 'aurora/' + name
        elif name in OVERLAY:
            name = 'omarchy-aurora/' + name
        if name not in result:
            result.append(name)
    return result, excluded


if __name__ == '__main__':
    root, defaults, output = map(Path, sys.argv[1:])
    hardware = {p['name'] for p in json.loads((ROOT / 'sources/alarm-manifest.json').read_text())['packages']}
    provider_data = json.loads((ROOT / 'sources/alarm-providers.json').read_text())
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    if (provider_data['database_sha256'] != lock['alarm']['package_database_sha256']
            or provider_data['snapshot'] != lock['alarm']['snapshot']
            or not set(provider_data['providers'].values()) <= hardware):
        raise ValueError('hardware provider table differs from the pinned signed snapshot')
    install, excluded = targets(defaults.read_text().splitlines(), hardware, provider_data['providers'])
    missing = [name for name in install if subprocess.run(
        ['chroot', str(root), 'pacman', '-Si', name], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode]
    if missing:
        raise ValueError('Omarchy desktop packages unavailable: ' + ', '.join(missing))
    output.write_text(json.dumps({'install': install, 'replaced': ALIASES,
                                  'hardware_providers': provider_data,
                                  'excluded_boot_stack': excluded}, indent=2) + '\n')
