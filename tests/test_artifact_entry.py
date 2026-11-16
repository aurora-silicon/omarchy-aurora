import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('artifact_entry', Path(__file__).resolve().parents[1] / 'scripts/artifact-entry.py')
entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entry)


class ArtifactReaderTests(unittest.TestCase):
    def test_small_logs_can_be_read_without_fetching_the_image_member(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('image', b'x' * (8 << 20))
            archive.writestr('out/vm/serial.log', b'boot evidence\n')
        data, fetched = output.getvalue(), []
        def fetch(start, end):
            fetched.append(end - start + 1)
            return data[start:end + 1]
        with zipfile.ZipFile(entry.RangeReader(len(data), fetch)) as archive:
            self.assertEqual(archive.read('out/vm/serial.log'), b'boot evidence\n')
        self.assertLess(sum(fetched), 128 << 10)

    def test_large_or_truncated_ranges_are_refused(self):
        reader = entry.RangeReader(8 << 20, lambda start, end: b'')
        with self.assertRaisesRegex(ValueError, 'large artifact'):
            reader.read()
        with self.assertRaisesRegex(ValueError, 'truncated'):
            reader.read(20)


if __name__ == '__main__':
    unittest.main()
