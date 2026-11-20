#!/usr/bin/env python3
"""Prove the overlay is desktop/platform software, never a replacement hardware stack."""
import argparse
from pathlib import Path
import subprocess

EXPECTED = {'omarchy', 'omarchy-settings', 'omarchy-mac', 'omarchy-aurora', 'aquamarine'}
FORBIDDEN = ('usr/lib/modules/', 'boot/', 'usr/share/aura/', 'usr/lib/aurora/aurora-firstboot')


def check(directory):
    names = set()
    for package in sorted(directory.glob('*.pkg.tar.*')):
        info = subprocess.check_output(['bsdtar', '-xOf', str(package), '.PKGINFO'], text=True)
        name = next(line[10:] for line in info.splitlines() if line.startswith('pkgname = '))
        if name not in EXPECTED or name in names:
            raise ValueError('unexpected or repeated desktop package: ' + name)
        names.add(name)
        files = [name.removeprefix('./') for name in subprocess.check_output(
            ['bsdtar', '-tf', str(package)], text=True).splitlines()]
        if any(path.startswith(FORBIDDEN) for path in files):
            raise ValueError('overlay attempts to replace boot/kernel files: ' + name)
        if name == 'omarchy-settings' and any(path in files for path in (
                'etc/mkinitcpio.conf.d/omarchy_hooks.conf', 'etc/mkinitcpio.conf.d/00-omarchy-hooks.conf')):
            raise ValueError('Omarchy initramfs would replace Aurora hooks')
    if names != EXPECTED:
        raise ValueError('incomplete desktop package set')
    print('Five desktop/platform packages verified; Aurora hardware/boot ownership preserved')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    check(parser.parse_args().directory)
