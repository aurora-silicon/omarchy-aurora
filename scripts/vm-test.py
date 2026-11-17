#!/usr/bin/env python3
"""Qualify real Aurora encryption and Omarchy userland on a disposable QEMU disk.

QEMU virt needs a generic kernel. The release image and its Apple boot/kernel
files remain unchanged; only a qcow2 test overlay gets VM modules and test I/O.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import struct
import subprocess
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False):
    return subprocess.run([str(a) for a in args], check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def completion_pattern(nonce):
    # A guest UART and its host PTY can both translate LF to CRLF.
    return re.compile(r'VM_' + re.escape(nonce) + r':([0-9]+)\r*\n')


def unlock_prompt_pattern():
    return re.compile(r'(?i)(?:Unlock Aurora root:|(?:passphrase|password)[^\r\n]*:)')


def compositor_exec(command):
    # Current Hyprland's Lua provider wraps dispatch arguments in hl.dispatch().
    expression = 'hl.dsp.exec_cmd(' + json.dumps(command) + ')'
    return shlex.join(['command', 'hyprctl', '-i', '0', 'dispatch', expression])


def frame_has_content(data):
    kind, dimensions, maximum, pixels = data.split(b'\n', 3)
    width, height = map(int, dimensions.split())
    if (kind != b'P6' or maximum != b'255' or width <= 0 or height <= 0
            or width * height > 16_777_216):
        raise ValueError('unexpected QEMU screenshot format')
    if len(pixels) != width * height * 3:
        raise ValueError('truncated QEMU screenshot')
    first = pixels[:3]
    return any(pixels[offset:offset + 3] != first for offset in range(3, len(pixels), 3))


def desktop_screenshot(qmp_path, work):
    deadline = time.monotonic() + 180
    ppm = work / 'desktop.ppm'
    while True:
        qmp(qmp_path, 'screendump', {'filename': str(ppm)})
        if ppm.stat().st_size > 50_331_700:
            raise ValueError('QEMU screenshot exceeds its bounded frame size')
        if frame_has_content(ppm.read_bytes()):
            subprocess.run(['convert', str(ppm), str(work / 'desktop.png')], check=True, timeout=20)
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('The terminal mapped, but the VM display remained a blank frame')
        time.sleep(2)


def partitions(image):
    with image.open('rb') as stream:
        stream.seek(4096)
        header = bytearray(stream.read(4096))
        if header[:8] != b'EFI PART':
            raise ValueError('VM source must have the production 4096-byte GPT')
        length, recorded = struct.unpack_from('<II', header, 12)
        struct.pack_into('<I', header, 16, 0)
        if zlib.crc32(header[:length]) != recorded:
            raise ValueError('GPT header checksum differs')
        table, count, size, checksum = struct.unpack_from('<QIII', header, 72)
        if not 3 <= count <= 256 or size != 128:
            raise ValueError('unexpected GPT table bounds')
        stream.seek(table * 4096)
        data = stream.read(count * size)
        if zlib.crc32(data) != checksum:
            raise ValueError('GPT partition table checksum differs')
        result = []
        for index in range(3):
            entry = data[index * size:(index + 1) * size]
            first, last = struct.unpack_from('<QQ', entry, 32)
            if last < first or (last + 1) * 4096 > image.stat().st_size:
                raise ValueError('invalid GPT extent')
            result.append({'offset': first * 4096, 'bytes': (last - first + 1) * 4096,
                           'uuid': str(uuid.UUID(bytes_le=entry[16:32]))})
        return result


def qmp(path, command, arguments=None):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(20)
        connection.connect(str(path))
        stream = connection.makefile('rwb', buffering=0)
        json.loads(stream.readline())
        for name, params in [('qmp_capabilities', {}), (command, arguments or {})]:
            stream.write(json.dumps({'execute': name, 'arguments': params}).encode() + b'\n')
            while True:
                answer = json.loads(stream.readline())
                if 'error' in answer:
                    raise RuntimeError(answer['error'])
                if 'return' in answer:
                    break
        return answer['return']


def write(root, name, text, executable=False):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755 if executable else 0o644)


def linear_table(device, row):
    if (not re.fullmatch(r'/dev/nbd[0-9]+', str(device)) or row['offset'] < 0
            or row['bytes'] <= 0 or row['offset'] % 512 or row['bytes'] % 512):
        raise ValueError('invalid disposable NBD partition mapping')
    # Device-mapper tables always count 512-byte sectors, even for a 4K GPT.
    return f"0 {row['bytes'] // 512} linear {device} {row['offset'] // 512}"


def wait_size(device, expected):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        answer = subprocess.run(['blockdev', '--getsize64', str(device)], capture_output=True, text=True)
        if answer.returncode == 0 and answer.stdout.strip() == str(expected):
            return
        time.sleep(0.1)
    raise RuntimeError('block device did not expose the expected byte extent: ' + str(device))


def prepare(image, work):
    rows = partitions(image)
    required = rows[2]['bytes'] + (10 << 30)
    if shutil.disk_usage(work).free < required:
        raise RuntimeError('VM encryption would cross the 8 GiB free floor; more off-host space is required')
    overlay = work / 'vm.qcow2'
    run('qemu-img', 'create', '-f', 'qcow2', '-F', 'raw', '-b', image, overlay)
    run('modprobe', 'nbd', 'max_part=0')
    candidates = sorted(Path('/sys/block').glob('nbd*'))
    device = next((Path('/dev') / p.name for p in candidates if not (p / 'pid').exists()), None)
    if device is None:
        raise RuntimeError('no unused VM NBD device')
    root = work / 'root'
    root.mkdir()
    mappings, mounts = [], []
    run('qemu-nbd', '--connect=' + str(device), '--format=qcow2', overlay)
    try:
        wait_size(device, image.stat().st_size)
        run('modprobe', 'dm_mod')
        prefix = 'omarchy-vm-' + secrets.token_hex(6)
        for index, row in enumerate(rows):
            name = prefix + '-' + str(index)
            run('dmsetup', '--noudevsync', 'create', name, '--table', linear_table(device, row))
            mappings.append(name)
            run('dmsetup', 'mknodes', name)
            block = Path('/dev/mapper') / name
            wait_size(block, row['bytes'])
            kind = run('blkid', '-p', '-s', 'TYPE', '-o', 'value', block, capture=True).strip()
            if kind != ['vfat', 'ext4', 'btrfs'][index]:
                raise ValueError(f'VM partition {index} has {kind!r}, not its exported filesystem')
            print('VM partition:', name, kind, row, flush=True)
        blocks = [Path('/dev/mapper') / name for name in mappings]
        for block, target, options in [(blocks[2], root, 'subvol=root'),
                                        (blocks[1], root / 'boot', None),
                                        (blocks[0], root / 'boot/efi', None)]:
            target.mkdir(parents=True, exist_ok=True)
            run('mount', *(['-o', options] if options else []), block, target)
            mounts.append(target)
        layout = dict(line.split('=', 1) for line in (root / 'etc/aurora/image-layout').read_text().splitlines())
        for name in ['dev', 'proc', 'sys', 'run']:
            path = root / name
            path.mkdir(exist_ok=True)
            if name in ('dev', 'sys'):
                run('mount', '--rbind', '/' + name, path)
                run('mount', '--make-rslave', path)
            else:
                run('mount', '-t', 'proc' if name == 'proc' else 'tmpfs', name, path)
            mounts.append(path)
        resolver = root / 'etc/resolv.conf'
        original_resolver = ('link', os.readlink(resolver)) if resolver.is_symlink() else ('file', resolver.read_bytes())
        resolver.unlink(missing_ok=True)
        shutil.copyfile('/etc/resolv.conf', resolver)
        run('chroot', root, 'pacman-key', '--init')
        run('chroot', root, 'pacman-key', '--populate')
        run('chroot', root, 'pacman', '-Swdd', '--noconfirm', 'core/linux-aarch64')
        archives = [p for p in (root / 'var/cache/pacman/pkg').glob('linux-aarch64-*.pkg.tar.*')
                    if not p.name.endswith('.sig')]
        if len(archives) != 1:
            raise ValueError('expected one authenticated generic VM kernel')
        generic = work / 'generic-kernel'
        generic.mkdir()
        run('bsdtar', '-xpf', archives[0], '-C', generic)
        modules = list((generic / 'usr/lib/modules').iterdir())
        if len(modules) != 1:
            raise ValueError('ambiguous VM kernel modules')
        version = modules[0].name
        shutil.copytree(modules[0], root / 'usr/lib/modules' / version, symlinks=True)
        # Extraction deliberately avoids package scriptlets; perform the
        # kernel's depmod hook before mkinitcpio resolves module dependencies.
        run('chroot', root, 'depmod', '-a', version)
        run('chroot', root, 'modinfo', '-k', version, 'virtio_net')
        kernels = [generic / p for p in ['boot/Image', 'boot/vmlinuz-linux-aarch64',
                                         'usr/lib/modules/' + version + '/vmlinuz']]
        kernel = next((p for p in kernels if p.is_file()), None)
        if kernel is None:
            raise ValueError('generic VM kernel image is absent')
        shutil.copyfile(kernel, work / 'Image')
        shutil.copyfile(kernel, root / 'boot/vmlinuz-aurora-vm')
        saved = root / 'var/lib/aurora-vm'
        saved.mkdir(parents=True, exist_ok=True)
        for name in ['mkinitcpio.conf.d', 'mkinitcpio.d']:
            original = root / 'etc' / name
            if original.exists():
                shutil.move(original, saved / name)
            original.mkdir()
        write(root, 'etc/mkinitcpio.conf',
              'MODULES=(virtio_pci virtio_blk virtio_net virtio_gpu)\n'
              'BINARIES=()\nFILES=()\nHOOKS=(base systemd modconf block sd-encrypt aurora-root filesystems fsck)\n')
        write(root, 'etc/mkinitcpio.d/aurora-vm.preset',
              'ALL_config="/etc/mkinitcpio.conf"\nALL_kver="/boot/vmlinuz-aurora-vm"\n'
              'PRESETS=(default)\ndefault_image="/boot/initramfs-aurora-vm.img"\n')
        run('chroot', root, 'mkinitcpio', '-P')
        shutil.copyfile(root / 'boot/initramfs-aurora-vm.img', work / 'initrd')
        write(root, 'etc/systemd/system/aurora-firstboot.service.d/99-vm.conf',
              '[Unit]\nBefore=serial-getty@ttyAMA0.service\n[Service]\n'
              'Environment=AURORA_FIRSTBOOT_TTY=/dev/ttyAMA0\nStandardInput=tty-force\n'
              'StandardOutput=tty\nStandardError=tty\nTTYPath=/dev/ttyAMA0\nTTYReset=yes\n')
        write(root, 'etc/systemd/system/serial-getty@ttyAMA0.service.d/99-vm.conf',
              '[Unit]\nAfter=aurora-firstboot.service omarchy-aurora-owners.service\n')
        run('chroot', root, 'systemctl', 'enable', 'serial-getty@ttyAMA0.service')
        write(root, 'usr/lib/aurora-vm-save-key',
              '#!/bin/bash\nset -euo pipefail\n'
              'if [[ -f /boot/omarchy/luks-key ]]; then install -m600 /boot/omarchy/luks-key /run/aurora-vm-temporary.key; fi\n', True)
        write(root, 'etc/systemd/system/aurora-vm-save-key.service',
              '[Unit]\nAfter=local-fs.target\nBefore=aurora-firstboot.service\n'
              '[Service]\nType=oneshot\nExecStart=/usr/lib/aurora-vm-save-key\n[Install]\nWantedBy=multi-user.target\n')
        run('chroot', root, 'systemctl', 'enable', 'aurora-vm-save-key.service')
        sessions = root / 'usr/share/wayland-sessions'
        session = next((n for n in ['omarchy.desktop', 'hyprland-uwsm.desktop', 'hyprland.desktop']
                        if (sessions / n).is_file()), None)
        if session is None:
            raise ValueError('Omarchy has no installed Hyprland login session')
        # TCG software-rendered startup can exceed UWSM's native 30-second
        # deadline. Set its documented timeout on the VM-only session entry;
        # UWSM then generates matching compositor and waitenv unit deadlines.
        session_text = (sessions / session).read_text()
        if len(re.findall(r'^Exec=', session_text, re.MULTILINE)) != 1:
            raise ValueError('VM login session must have exactly one Exec command')
        write(root, 'usr/share/wayland-sessions/aurora-vm.desktop',
              re.sub(r'^Exec=', 'Exec=env UWSM_WAIT_VARNAMES_TIMEOUT=300 ',
                     session_text, count=1, flags=re.MULTILINE))
        write(root, 'etc/sddm.conf.d/99-vm-autologin.conf',
              '[Autologin]\nUser=auroravm\nSession=aurora-vm.desktop\nRelogin=false\n')
        write(root, 'boot/efi/omarchy/install.conf', 'format=1\nencrypt=1\n')
        shutil.copyfile(ROOT / 'scripts/vm-desktop-ready.py', root / 'usr/lib/aurora-vm-desktop-ready')
        resolver.unlink(missing_ok=True)
        if original_resolver[0] == 'link':
            resolver.symlink_to(original_resolver[1])
        else:
            resolver.write_bytes(original_resolver[1])
        # Kernel authentication needs a temporary builder keyring. The real
        # guest must recreate trust on first boot just like the release image.
        run('python3', ROOT / 'scripts/stop-image-key-agents.py', root)
        shutil.rmtree(root / 'etc/pacman.d/gnupg')
    finally:
        if mounts:
            run('python3', ROOT / 'scripts/stop-image-key-agents.py', root)
        failed = False
        for path in reversed(mounts):
            if subprocess.run(['umount', '-R', str(path)]).returncode:
                failed = True
        if failed:
            raise RuntimeError('preserving mounted VM preparation root for recovery')
        for name in reversed(mappings):
            run('dmsetup', '--noudevsync', 'remove', name)
        run('qemu-nbd', '--disconnect', device)
    return overlay, rows, layout, version


def validate(image, work, report_path):
    import pexpect
    work.mkdir(parents=True, exist_ok=True)
    before = digest(image)
    overlay, rows, layout, version = prepare(image, work)
    result = {'schema': 1, 'generic_vm_kernel': version, 'kernel_override': True,
              'vm_session_startup_timeout_seconds': 300,
              'physical_qualification': 'not tested', 'source_sha256': before}
    report_path.write_text(json.dumps(result, indent=2) + '\n')
    kvm = os.access('/dev/kvm', os.R_OK | os.W_OK)
    result['acceleration'] = 'kvm' if kvm else 'tcg'
    command = ['qemu-system-aarch64', '-machine', 'virt,gic-version=3', '-cpu', 'host' if kvm else 'max',
               '-accel', 'kvm' if kvm else 'tcg', '-m', '4096', '-smp', '2',
               '-drive', 'if=none,id=os,format=qcow2,file=' + str(overlay),
               '-device', 'virtio-blk-pci,drive=os,logical_block_size=4096,physical_block_size=4096',
               '-device', 'virtio-net-pci,netdev=net', '-netdev', 'user,id=net',
               '-device', 'virtio-gpu-pci,xres=1280,yres=800', '-display', 'none',
               '-chardev', 'stdio,id=console,signal=off', '-serial', 'chardev:console',
               '-monitor', 'none', '-no-reboot']
    dtb = work / 'machine.dtb'
    dump = command.copy()
    dump[dump.index('virt,gic-version=3')] += ',dumpdtb=' + str(dtb)
    run(*dump)
    run('fdtput', '-t', 's', dtb, '/chosen', 'asahi,efi-system-partition', rows[0]['uuid'])
    qmp_path = work / 'qmp.sock'
    command += ['-dtb', str(dtb), '-kernel', str(work / 'Image'), '-initrd', str(work / 'initrd'),
                '-append', 'root=UUID=' + layout['root_uuid'] +
                ' rootflags=subvol=root rootfstype=btrfs rw console=ttyAMA0,115200 '
                'aurora.firstboot=text plymouth.enable=0 systemd.unit=multi-user.target '
                'systemd.show_status=false quiet loglevel=3',
                '-qmp', 'unix:' + str(qmp_path) + ',server=on,wait=off']
    password = 'Vm-' + secrets.token_hex(12)
    child = None
    guest_ready = False
    log = (work / 'serial.log').open('w')

    def start():
        qmp_path.unlink(missing_ok=True)
        process = pexpect.spawn(command[0], command[1:], encoding='utf-8', codec_errors='replace', timeout=900, maxread=65536)
        process.logfile_read = log
        return process

    def guest(code, sudo=False, timeout=120):
        print('VM guest: ' + code.splitlines()[0][:160], flush=True)
        nonce = secrets.token_hex(10)
        command_text = code
        if sudo:
            child.sendline('sudo -k')
            command_text = "sudo -S -p 'VM_AUTH> ' sh -c " + shlex.quote(code)
        child.sendline(command_text + "; printf '\\nVM_%s:%s\\n' '" + nonce + "' \"$?\"")
        if sudo:
            child.expect('VM_AUTH> ', timeout=min(timeout, 45))
            child.sendline(password)
        child.expect(completion_pattern(nonce), timeout=timeout)
        if child.match.group(1) != '0':
            raise RuntimeError('guest assertion failed: ' + code.splitlines()[0])

    def login():
        child.expect(r'login:')
        child.sendline('auroravm')
        child.expect(r'[Pp]assword:')
        child.sendline(password)
        if child.expect([r'❯', r'\$ ', r'# ', 'Login incorrect'], timeout=120) == 3:
            raise RuntimeError('VM owner login was rejected')
        nonce = secrets.token_hex(10)
        child.sendline("stty -echo; printf '\\nVM_%s\\n' '" + nonce + "'")
        child.expect('VM_' + nonce)

    try:
        print('VM: first boot and real encryption/owner wizard', flush=True)
        child = start()
        child.expect('Linux username:', timeout=1800)
        result['boot'] = True
        child.sendline('auroravm')
        child.expect(r'Computer name.*:')
        child.sendline('omarchy-vm')
        child.expect('Linux password')
        child.sendline(password)
        child.expect('Retype password:')
        child.sendline(password)
        child.expect('Aurora setup is complete', timeout=1800)
        login()
        guest_ready = True
        root_device = '/dev/disk/by-partuuid/' + rows[2]['uuid']
        guest("test \"$(id -u)\" -ge 1000 && id -nG | tr ' ' '\\n' | grep -qx wheel")
        result['owner'] = True
        guest('test "$(id -u)" = 0 && visudo -cf /etc/sudoers.d/10-aurora-owner', sudo=True)
        result['sudo'] = True
        guest('test -f /var/lib/aurora/omarchy-keyring-ready && '
              'pacman-key --list-keys 40DFB630FF42BCFFB047046CF0134EE680CAC571 >/dev/null', sudo=True)
        result['package_trust'] = True
        guest("grep -qx 'phase=finished' /boot/omarchy/encrypt.state && "
              "test -f /var/lib/aurora/firstboot/disk-rekeyed && "
              "test ! -e /var/lib/aurora/firstboot/pending && "
              "test ! -e /boot/omarchy/luks-key && "
              "test ! -e /var/lib/aurora/firstboot/luks-key && "
              "test ! -e /boot/omarchy/luks-header-before-recovery.bin && "
              "cryptsetup luksDump --dump-json-metadata " + root_device +
              " | python3 -c 'import sys,json;assert sorted(json.load(sys.stdin)[\"keyslots\"])==[\"1\"]'", sudo=True)
        result['encryption'] = True
        guest('set -e; test -s /run/aurora-vm-temporary.key; '
              'trap \'rm -f /run/aurora-vm-temporary.key\' EXIT; set +e; cryptsetup open --test-passphrase --key-file /run/aurora-vm-temporary.key ' + root_device +
              ' >/dev/null 2>&1; status=$?; set -e; test \"$status\" -eq 2', sudo=True)
        result['temporary_key_rejected'] = True
        guest_ready = False
        child.sendline("sudo -k; sudo -S -p 'VM_AUTH> ' systemctl reboot")
        child.expect('VM_AUTH> ')
        child.sendline(password)
        child.expect(pexpect.EOF, timeout=120)
        child.close()
        print('VM: second boot, incorrect disk password rejection, owner unlock/login', flush=True)
        child = start()
        child.expect(unlock_prompt_pattern(), timeout=900)
        child.sendline('definitely-not-the-owner-password')
        child.expect(unlock_prompt_pattern(), timeout=120)
        child.sendline(password)
        login()
        guest_ready = True
        result['second_boot'] = True
        guest('systemctl is-active --quiet NetworkManager && ip -4 route show default | grep -q default && ping -c1 -W3 10.0.2.2')
        result['network'] = True
        print('VM: actual Hyprland, Omarchy shell and terminal', flush=True)
        # Wait on compositor readiness below, rather than holding the serial
        # sudo session open for the complete graphical target transaction.
        guest('systemctl --no-block start graphical.target', sudo=True, timeout=60)
        guest("for n in $(seq 1 60); do pgrep -u $(id -u) -x Hyprland >/dev/null && break; sleep 2; done; pgrep -u $(id -u) -x Hyprland", timeout=180)
        guest('python3 /usr/lib/aurora-vm-desktop-ready && '
              'command hyprctl -i 0 -j monitors | python3 -c \'import json,sys;assert any(m["width"]>0 and m["height"]>0 for m in json.load(sys.stdin))\'',
              timeout=360)
        guest('systemctl is-active --quiet graphical.target && '
              'systemctl is-active --quiet display-manager.service')
        result['desktop'] = True
        guest('for n in $(seq 1 60); do (pgrep -u $(id -u) -x quickshell || pgrep -u $(id -u) -x qs) && break; sleep 2; done; pgrep -u $(id -u) -x quickshell || pgrep -u $(id -u) -x qs', timeout=180)
        result['shell'] = True
        guest(compositor_exec('uwsm-app -- foot --app-id=aurora-ci-terminal sh -c "echo Omarchy Aurora; sleep 300"'))
        guest("for n in $(seq 1 30); do command hyprctl -i 0 -j clients | grep -q aurora-ci-terminal && break; sleep 1; done; command hyprctl -i 0 -j clients | grep -q aurora-ci-terminal", timeout=60)
        desktop_screenshot(qmp_path, work)
        result['terminal'] = True
        result['original_unchanged'] = digest(image) == before
        if not result['original_unchanged']:
            raise RuntimeError('VM mutated the release image')
    except Exception as error:
        result['failure'] = str(error)
        if child is not None and child.isalive():
            try:
                (work / 'failure-qmp.json').write_text(json.dumps(qmp(qmp_path, 'query-status'), indent=2) + '\n')
                qmp(qmp_path, 'screendump', {'filename': str(work / 'failure.ppm')})
                subprocess.run(['convert', str(work / 'failure.ppm'), str(work / 'failure.png')],
                               check=True, timeout=20)
            except Exception as diagnostic_error:
                print('VM failure screenshot unavailable: ' + str(diagnostic_error), flush=True)
        if guest_ready and child is not None and child.isalive():
            try:
                child.sendcontrol('c')
                guest('systemctl list-jobs --no-pager; '
                      'systemctl status graphical.target display-manager.service '
                      'aurora-firstboot.service omarchy-aurora-keyring.service '
                      'omarchy-aurora-hardware.service omarchy-aurora-owners.service '
                      'omarchy-provision-hardware.service --no-pager -l; '
                      'tail -n 120 /var/log/omarchy-install.log; '
                      'cat /var/lib/omarchy/image/deferred-steps; '
                      'journalctl -b --no-pager -n 200; '
                      'journalctl -b --no-pager _UID=$(id -u auroravm) -n 150; '
                      'for log in /run/user/1000/hypr/*/hyprland.log '
                      '/home/auroravm/.cache/hyprland/*.txt; do '
                      'if test -f "$log"; then tail -n 100 "$log"; fi; done; true',
                      sudo=True, timeout=45)
            except Exception:
                print('VM guest diagnostics unavailable; retaining serial output and failure report', flush=True)
        raise
    finally:
        if child is not None and child.isalive():
            child.terminate(force=True)
        log.close()
        report_path.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    validate(args.image.resolve(), args.work.resolve(), args.report)
