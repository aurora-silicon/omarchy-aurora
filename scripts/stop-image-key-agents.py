#!/usr/bin/env python3
"""Retire only key agents inside one disposable build root."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

AGENTS = {'gpg-agent', 'dirmngr', 'scdaemon', 'keyboxd'}


def remaining(root, proc=Path('/proc')):
    result = []
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            if ((process / 'comm').read_text().strip() in AGENTS
                    and os.readlink(process / 'root') == str(root)
                    and (process / 'stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'):
                result.append(int(process.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return result


def signal_owned(root, sig, proc=Path('/proc')):
    for pid in remaining(root, proc):
        descriptor = None
        try:
            descriptor = os.pidfd_open(pid)
            # Recheck ownership after opening the stable process handle.
            if pid in remaining(root, proc):
                signal.pidfd_send_signal(descriptor, sig)
        except ProcessLookupError:
            pass
        finally:
            if descriptor is not None:
                os.close(descriptor)


def wait(root, seconds):
    deadline = time.monotonic() + seconds
    while remaining(root):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def stop(root):
    root = root.resolve()
    if root == Path('/') or not root.is_dir():
        raise ValueError('expected a disposable image root, never the host root')
    for home in ('/etc/pacman.d/gnupg', '/root/.gnupg'):
        if (root / home.lstrip('/')).is_dir() and (root / 'usr/bin/gpgconf').exists():
            try:
                subprocess.run(['chroot', str(root), 'gpgconf', '--homedir', home, '--kill', 'all'],
                               check=False, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                pass
    if not wait(root, 1):
        signal_owned(root, signal.SIGTERM)
    if not wait(root, 5):
        signal_owned(root, signal.SIGKILL)
    if not wait(root, 5):
        raise RuntimeError('image key agents still hold the root: ' + str(remaining(root)))
    print('Disposable image key agents have exited', flush=True)


if __name__ == '__main__':
    stop(Path(sys.argv[1]))
