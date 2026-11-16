#!/usr/bin/env python3
"""Download the exact signed desktop snapshot, never a mutable package feed."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, path, maximum):
    with urllib.request.urlopen(url, timeout=90) as response, path.open('wb') as output:
        total = 0
        while block := response.read(1 << 20):
            total += len(block)
            if total > maximum:
                raise ValueError('snapshot asset exceeds its bound')
            output.write(block)


def download(snapshot, output):
    if not re.fullmatch(r'testing-[0-9]{8}\.[0-9]+', snapshot):
        raise ValueError('expected an immutable desktop snapshot')
    base = 'https://github.com/aurora-silicon/omarchy-aurora/releases/download/' + snapshot
    output.mkdir(parents=True, exist_ok=True)
    fetch(base + '/manifest.json', output / 'manifest.json', 1 << 20)
    fetch(base + '/manifest.json.sig', output / 'manifest.json.sig', 1 << 20)
    with tempfile.TemporaryDirectory(prefix='omarchy-snapshot-trust-') as home:
        subprocess.run(['gpg', '--homedir', home, '--batch', '--import', str(ROOT / 'keys/aurora-alarm.asc')], check=True)
        subprocess.run(['gpg', '--homedir', home, '--batch', '--verify', str(output / 'manifest.json.sig'), str(output / 'manifest.json')], check=True)
    manifest = json.loads((output / 'manifest.json').read_text())
    validation = manifest.get('validation', {})
    lock = (ROOT / 'sources.lock.json').read_bytes()
    if (validation.get('mac_unit_suite') is not True or validation.get('mac_integration_suite') is not True
            or validation.get('sources_lock_sha256') != hashlib.sha256(lock).hexdigest()):
        raise ValueError('overlay lacks matching, passing source compatibility evidence')
    if manifest['signing_key'] != (ROOT / 'keys/fingerprint.txt').read_text().strip() or manifest.get('dry_run'):
        raise ValueError('desktop signer does not match Aurora trust')
    for package in manifest['packages']:
        name = package['filename']
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+\.pkg\.tar\.(?:xz|zst|gz)', name):
            raise ValueError('unsafe snapshot filename')
        fetch(base + '/' + name, output / name, min(package['bytes'] + 1, 1 << 30))
        with (output / name).open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if (output / name).stat().st_size != package['bytes'] or digest != package['sha256']:
            raise ValueError('desktop snapshot package identity mismatch')
        fetch(base + '/' + name + '.sig', output / (name + '.sig'), 1 << 20)
    for name in ['omarchy-aurora.db', 'omarchy-aurora.db.sig']:
        fetch(base + '/' + name, output / name, 1 << 20)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    download(args.snapshot, args.output)
