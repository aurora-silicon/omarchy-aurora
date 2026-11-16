#!/usr/bin/env python3
"""Extend the immutable ALARM producer without forking its hardware recipes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def extend(text):
    if text.count('size=6G\n') != 1:
        raise ValueError('ALARM image capacity boundary changed')
    text = text.replace('size=6G\n', 'size=32G\n', 1)
    anchor = 'chroot "$mountroot" userdel -r alarm\n'
    if text.count(anchor) != 1:
        raise ValueError('ALARM package/owner boundary changed')
    text = text.replace(anchor,
                        'bash /src/scripts/prepare-root "$mountroot"\n' + anchor, 1)
    anchor = 'if [[ $profile == arch-kde ]]; then\n'
    if text.count(anchor) != 2:
        raise ValueError('ALARM desktop boundary changed')
    text = text.replace(anchor,
                        'bash /src/scripts/configure-root "$mountroot"\n' + anchor, 1)
    anchor = 'tar --sparse -C "$root/out/$profile-installer" -cf - . | zstd'
    if text.count(anchor) != 1:
        raise ValueError('ALARM finalized archive boundary changed')
    text = text.replace(anchor,
        'python3 /src/scripts/finalize-bundle.py "$root/out/$profile-installer"\n' + anchor, 1)
    return text


def prepare(base):
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    revision = subprocess.check_output(['git', '-c', 'safe.directory=' + str(base.resolve()), '-C', str(base), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != lock['alarm']['commit']:
        raise ValueError('ALARM builder source is not the pinned revision')
    path = base / 'scripts/build-image'
    original = path.read_bytes()
    path.write_text(extend(original.decode()))
    (base / 'omarchy-extension.json').write_text(json.dumps({
        'alarm_source': revision, 'producer_sha256': hashlib.sha256(original).hexdigest(),
        'profile': lock['profile'], 'snapshot': lock['alarm']['snapshot']}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    prepare(parser.parse_args().base)
