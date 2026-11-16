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


if __name__ == '__main__':
    unittest.main()
