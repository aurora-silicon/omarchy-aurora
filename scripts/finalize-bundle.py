#!/usr/bin/env python3
"""Bind the finalized ALARM filesystem contract to the Omarchy profile."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
bundle = Path(sys.argv[1])
path = bundle / 'image.json'
image = json.loads(path.read_text())
if image['installation_profile'] != 'arch-minimal' or image['layout_kind'] != 'alarm-btrfs-v1':
    raise ValueError('unexpected base filesystem contract')
image['installation_profile'] = 'omarchy-hyprland'
path.write_text(json.dumps(image, indent=2) + '\n')
for name in ['hardware-versions.json', 'desktop-package-plan.json']:
    shutil.copyfile(ROOT / 'out' / name, bundle / name)
lock = (ROOT / 'sources.lock.json').read_bytes()
(bundle / 'omarchy-provenance.json').write_text(json.dumps({
    'schema': 1, 'profile': image['installation_profile'],
    'sources_lock_sha256': hashlib.sha256(lock).hexdigest(),
    'sources': json.loads(lock), 'image_source': os.environ.get('GITHUB_SHA'),
    'overlay_snapshot': os.environ['OMARCHY_OVERLAY_SNAPSHOT']}, indent=2) + '\n')
