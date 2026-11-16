#!/usr/bin/env python3
"""The new desktop must not replace any installed ALARM snapshot package."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def versions(text):
    return dict(line.split(' ', 1) for line in text.splitlines() if line.strip())


def check(before, after, protected, expected=None):
    changes = {name: (version, after.get(name)) for name, version in before.items()
               if name in protected and after.get(name) != version}
    if changes:
        raise ValueError('Aurora hardware package set changed: ' + json.dumps(changes))
    if expected is not None:
        drift = {name: (expected[name], version) for name, version in after.items()
                 if name in protected and version != expected[name]}
        if drift:
            raise ValueError('Aurora hardware differs from the signed snapshot: ' + json.dumps(drift))


if __name__ == '__main__':
    before = versions(Path(sys.argv[1]).read_text())
    after = versions(subprocess.check_output(['chroot', sys.argv[2], 'pacman', '-Q'], text=True))
    protected = {p['name'] for p in json.loads((ROOT / 'sources/alarm-manifest.json').read_text())['packages']}
    expected = json.loads((ROOT / 'sources/alarm-package-versions.json').read_text())
    check(before, after, protected, expected)
    Path('/src/out/hardware-versions.json').write_text(json.dumps(
        {name: version for name, version in after.items() if name in protected}, indent=2) + '\n')
    print('Preserved', len(protected & before.keys()), 'installed signed ALARM package versions')
