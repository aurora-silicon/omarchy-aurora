#!/usr/bin/env python3
"""Omarchy on Edge (aurora-distributions docs/edge-train.md).

Omarchy takes its kernel and Mesa from ALARM's [aurora-edge] overlay, which
sits ahead of [aurora] (Testing) in every pacman configuration it installs.

  pacman TEMPLATE SERVER     insert [aurora-edge] with SERVER ahead of [aurora]
  proof ALARM OUT OVERLAY    turn ALARM's arch-minimal edge-image-proof.json into
                             the omarchy-hyprland proof the Edge train stages
"""
import json
from pathlib import Path
import re
import sys

FEED = 'https://aurorasilicon.org/alarm-aurora/edge/aarch64'
RELEASES = 'https://github.com/aurora-silicon/alarm-aurora/releases/download/'
TAG = re.compile(r'edge-[0-9]{8}\.[1-9][0-9]*')
OVERLAY = re.compile(r'testing-[0-9]{8}\.[0-9]+')


def with_edge(text, server):
    if '[aurora-edge]' in text:
        raise ValueError('the configuration already has [aurora-edge]')
    at = text.index('[aurora]\n')
    return text[:at] + f'[aurora-edge]\nSigLevel = Required DatabaseRequired\nServer = {server}\n\n' + text[at:]


def build_server(tag):
    if not TAG.fullmatch(tag or ''):
        raise ValueError('invalid ALARM Edge snapshot: %r' % (tag,))
    return RELEASES + tag


def omarchy_proof(alarm, overlay):
    if not OVERLAY.fullmatch(overlay or ''):
        raise ValueError('invalid Omarchy overlay snapshot')
    if (alarm.get('schema') != 2 or alarm.get('distribution') != 'arch' or alarm.get('profile') != 'arch-minimal'
            or alarm.get('channel') != 'edge' or alarm.get('feed') != FEED or not TAG.fullmatch(alarm.get('snapshot', ''))):
        raise ValueError('expected the ALARM Edge proof of the Omarchy base image')
    return {'schema': 2, 'distribution': 'omarchy', 'profile': 'omarchy-hyprland', 'channel': 'edge',
            'snapshot': overlay, 'alarm_snapshot': alarm['snapshot'], 'feed': FEED,
            'packaged_sources': alarm['packaged_sources'], 'files': alarm['files']}


if __name__ == '__main__':
    command, *rest = sys.argv[1:]
    if command == 'pacman':
        path, server = Path(rest[0]), rest[1]
        path.write_text(with_edge(path.read_text(), server))
    elif command == 'proof':
        source, output, overlay = Path(rest[0]), Path(rest[1]), rest[2]
        output.write_text(json.dumps(omarchy_proof(json.loads(source.read_text()), overlay),
                                     indent=2, sort_keys=True) + '\n')
    else:
        raise SystemExit(__doc__)
