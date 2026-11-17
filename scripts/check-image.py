#!/usr/bin/env python3
"""Check complete Omarchy userland and the preserved Aurora boot contract."""
import json
from pathlib import Path
import sys


def check(root):
    for name in ['usr/bin/Hyprland', 'usr/bin/quickshell', 'usr/bin/foot',
                 'usr/bin/omarchy', 'usr/bin/omarchy-provision-user',
                 'usr/share/pacman/keyrings/omarchy.gpg',
                 'usr/share/omarchy-aurora/sources.lock.json',
                 'usr/lib/omarchy/aurora-boot/setup-boot']:
        if not (root / name).exists():
            raise ValueError('incomplete Omarchy image: ' + name)
    for name in ['usr/lib/systemd/system/omarchy-firstboot.service',
                 'usr/lib/initcpio/hooks/omarchy-mac-encrypt',
                 'etc/mkinitcpio.conf.d/omarchy_hooks.conf',
                 'etc/mkinitcpio.conf.d/00-omarchy-hooks.conf']:
        if (root / name).exists():
            raise ValueError('competing upstream boot stack: ' + name)
    config = (root / 'etc/pacman.conf').read_text()
    if config.index('[aurora]') > config.index('[omarchy]'):
        raise ValueError('Aurora hardware repository must have priority')
    if 'TrustAll' in config or 'file://' in config:
        raise ValueError('image retains unsafe or build-local package trust')
    if not any((root / 'etc/skel/.config/hypr' / name).exists()
               for name in ['hyprland.conf', 'hyprland.lua']):
        raise ValueError('Omarchy desktop defaults missing from skel')
    for name in ['omarchy-aurora-keyring.service', 'omarchy-aurora-hardware.service', 'omarchy-aurora-owners.service']:
        if not (root / 'etc/systemd/system/multi-user.target.wants' / name).is_symlink():
            raise ValueError('first-boot desktop integration not enabled: ' + name)
    for name in ['etc/systemd/system/multi-user.target.wants/omarchy-provision-hardware.service',
                 'var/lib/omarchy/image/pacman-keyring']:
        path = root / name
        if path.exists() or path.is_symlink():
            raise ValueError('competing first-boot hardware/keyring executor: ' + name)
    queue = root / 'var/lib/omarchy/image/deferred-steps'
    if not queue.is_file() or not queue.read_text().strip():
        raise ValueError('Apple hardware setup queue was not preserved for Aurora first boot')
    lock = json.loads((root / 'usr/share/omarchy-aurora/sources.lock.json').read_text())
    if lock['profile'] != 'omarchy-hyprland':
        raise ValueError('wrong distribution source contract')
    print('Omarchy desktop, Aurora boot ownership and signed repository policy verified')


if __name__ == '__main__':
    check(Path(sys.argv[1]))
