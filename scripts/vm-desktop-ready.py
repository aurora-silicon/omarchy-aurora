#!/usr/bin/python3
"""Wait for Hyprland output and a usable terminal in the software-rendered VM."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def probe(arguments):
    return subprocess.check_output(arguments, text=True, stderr=subprocess.DEVNULL, timeout=20)


def ready_session(query=probe):
    try:
        instances = json.loads(query(['hyprctl', '-j', 'instances']))
        if not isinstance(instances, list):
            return None
        for instance in instances:
            signature = instance.get('instance', '')
            if not isinstance(signature, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,256}', signature):
                continue
            monitors = json.loads(query(['hyprctl', '-i', signature, '-j', 'monitors']))
            if isinstance(monitors, list) and any(
                    isinstance(monitor, dict)
                    and isinstance(monitor.get('width'), (int, float)) and monitor['width'] > 0
                    and isinstance(monitor.get('height'), (int, float)) and monitor['height'] > 0
                    for monitor in monitors):
                return signature
    except (ValueError, KeyError, subprocess.SubprocessError):
        pass
    return None


def terminal_mapped(signature, query=probe):
    try:
        clients = json.loads(query(['hyprctl', '-i', signature, '-j', 'clients']))
    except (ValueError, subprocess.SubprocessError):
        return False
    return isinstance(clients, list) and any(
        isinstance(client, dict) and client.get('class') == 'aurora-ci-terminal'
        and client.get('mapped') is True and client.get('hidden') is False
        for client in clients
    )


def wait_until(check, failure):
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(2)
    raise RuntimeError(failure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal', metavar='INSTANCE')
    args = parser.parse_args()
    if args.terminal:
        marker = Path(os.environ['XDG_RUNTIME_DIR']) / 'aurora-ci-terminal-ready'
        wait_until(lambda: marker.is_file() and terminal_mapped(args.terminal),
                   'Foot did not run the test command and map a visible window within five minutes')
    else:
        signature = wait_until(ready_session, 'Hyprland did not expose a responsive monitor within five minutes')
        print(signature, flush=True)


if __name__ == '__main__':
    main()
