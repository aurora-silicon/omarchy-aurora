#!/usr/bin/python3
"""Wait for an actual Hyprland output, including slow software-rendered VMs."""
import json
import re
import subprocess
import time


def probe(arguments):
    return subprocess.check_output(arguments, text=True, stderr=subprocess.DEVNULL, timeout=10)


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


def main():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        signature = ready_session()
        if signature:
            print(signature, flush=True)
            return
        time.sleep(2)
    raise RuntimeError('Hyprland did not expose a responsive monitor within five minutes')


if __name__ == '__main__':
    main()
