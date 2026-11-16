#!/usr/bin/env python3
"""Fetch only immutable public source inputs; never use a moving build ref."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / 'sources.lock.json').read_text())
for name, field in [('alarm', 'alarm'), ('runtime', 'omarchy'), ('mac', 'omarchy_mac')]:
    record = lock[field]
    if not re.fullmatch(r'(?:aurora-silicon|omacom)/[a-zA-Z0-9._-]+', record['repository']):
        raise ValueError('unexpected source owner')
    if not re.fullmatch('[0-9a-f]{40}', record['commit']):
        raise ValueError('source must be an immutable Git commit')
    target = ROOT / 'inputs' / name
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        subprocess.run(['git', 'init', str(target)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', '-C', str(target), 'remote', 'add', 'origin',
                        'https://github.com/' + record['repository'] + '.git'], check=True)
        subprocess.run(['git', '-C', str(target), 'fetch', '--depth=1', 'origin', record['commit']], check=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != record['commit']:
        raise ValueError('existing input differs from lock: ' + name)
