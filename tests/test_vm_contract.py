import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import uuid
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vm_test', ROOT / 'scripts/vm-test.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class VMContract(unittest.TestCase):
    def test_blank_or_flat_frames_do_not_prove_a_rendered_desktop(self):
        header = b'P6\n2 1\n255\n'
        for pixel in (b'\0\0\0', b'\xff\xff\xff', b'\x20\x30\x40'):
            self.assertFalse(vm.frame_has_content(header + pixel * 2))
        self.assertTrue(vm.frame_has_content(header + b'\0\0\0\xff\xff\xff'))

    def test_a_truncated_frame_is_not_accepted_as_visual_evidence(self):
        with self.assertRaisesRegex(ValueError, 'truncated'):
            vm.frame_has_content(b'P6\n2 1\n255\n\0\0\0')

    def test_unlock_prompt_matches_the_real_aurora_prompt_after_reboot(self):
        pattern = vm.unlock_prompt_pattern()
        captured = '\x1b[0;1;39mUnlock Aurora root: (press TAB for no echo) \x1b[0m'
        self.assertEqual(pattern.search(captured).group(), 'Unlock Aurora root:')
        self.assertIsNotNone(pattern.search('Please enter passphrase for disk root:'))
        self.assertIsNotNone(pattern.search('Password for encrypted root:'))
        self.assertIsNone(pattern.search('omarchy-vm login:'))

    def test_serial_completion_accepts_uart_and_pty_line_endings(self):
        nonce = '28db08f0d3321540001b'
        pattern = vm.completion_pattern(nonce)
        for ending in ('\n', '\r\n', '\r\r\n'):
            self.assertEqual(pattern.search('VM_' + nonce + ':0' + ending).group(1), '0')
        self.assertEqual(pattern.search('VM_' + nonce + ':7\r\r\n').group(1), '7')
        self.assertIsNone(pattern.search("printf '\\nVM_%s:%s\\n' '" + nonce + "' \"$?\""))

    def image(self, path, outside=False):
        entries = bytearray(128 * 128)
        ids = []
        for number in range(3):
            entry = number * 128
            identifier = uuid.UUID(int=number + 1)
            ids.append(str(identifier))
            entries[entry + 16:entry + 32] = identifier.bytes_le
            first = (number + 1) * 128
            last = first + (2048 if outside and number == 2 else 127)
            struct.pack_into('<QQ', entries, entry + 32, first, last)
        header = bytearray(4096)
        header[:8] = b'EFI PART'
        struct.pack_into('<I', header, 12, 92)
        struct.pack_into('<QIII', header, 72, 2, 128, 128, zlib.crc32(entries))
        struct.pack_into('<I', header, 16, zlib.crc32(header[:92]))
        with path.open('wb') as output:
            output.truncate(4 << 20)
            output.seek(4096)
            output.write(header)
            output.seek(8192)
            output.write(entries)
        return ids

    def test_the_vm_uses_production_4k_gpt_geometry_and_uuid_byte_order(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'image'
            ids = self.image(path)
            rows = vm.partitions(path)
            self.assertEqual([row['uuid'] for row in rows], ids)
            self.assertEqual([row['offset'] for row in rows], [128 * 4096, 256 * 4096, 384 * 4096])
            self.assertTrue(all(row['bytes'] == 128 * 4096 for row in rows))

    def test_bad_gpt_crc_and_out_of_image_extents_are_refused_before_mounts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'image'
            self.image(path)
            with path.open('r+b') as output:
                output.seek(4096 + 20)
                output.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                vm.partitions(path)
            self.image(path, outside=True)
            with self.assertRaisesRegex(ValueError, 'extent'):
                vm.partitions(path)

    def test_4k_partition_byte_extents_become_exact_512_byte_dm_sectors(self):
        self.assertEqual(vm.linear_table(Path('/dev/nbd0'),
                         {'offset': 133120 * 4096, 'bytes': 262144 * 4096}),
                         '0 2097152 linear /dev/nbd0 1064960')
        for device, row in [('/dev/sda', {'offset': 0, 'bytes': 4096}),
                            ('/dev/nbd0', {'offset': 1, 'bytes': 4096}),
                            ('/dev/nbd0', {'offset': 0, 'bytes': 4097})]:
            with self.assertRaises(ValueError):
                vm.linear_table(Path(device), row)


if __name__ == '__main__':
    unittest.main()
