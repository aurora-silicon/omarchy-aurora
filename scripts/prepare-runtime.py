#!/usr/bin/env python3
"""Apply the bounded Aurora integration to the pinned Omarchy runtime."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise ValueError(f'upstream contract changed: {path}: {old!r}')
    path.write_text(text.replace(old, new, 1))


def prepare(runtime):
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    revision = subprocess.check_output(['git', '-c', 'safe.directory=' + str(runtime.resolve()), '-C', str(runtime), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != lock['omarchy']['commit']:
        raise ValueError('runtime is not the pinned Omarchy source')
    replace(runtime / 'install/helpers/pacman.sh',
            'omarchy_pacman_templates() {\n',
            'omarchy_pacman_templates() {\n'
            '  if [[ ${1:-} == aarch64-apple && -d /usr/share/omarchy-aurora/pacman ]]; then\n'
            '    echo /usr/share/omarchy-aurora/pacman\n'
            '    return\n'
            '  fi\n')
    replace(runtime / 'bin/omarchy-lifecycle-dispatch',
            'implementation=/usr/lib/omarchy/mac-boot\n    package=omarchy-mac-boot',
            'implementation=/usr/lib/omarchy/aurora-boot\n    package=omarchy-aurora')
    replace(runtime / 'install/config/snapper.sh',
            'systemctl enable --now snapper-cleanup.timer limine-snapper-sync.service',
            'systemctl enable --now snapper-cleanup.timer')
    (runtime / 'version').write_text(lock['version'] + '\n')
    print('Prepared Aurora boot-provider and repository integration in the pinned runtime')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    prepare(parser.parse_args().runtime)
