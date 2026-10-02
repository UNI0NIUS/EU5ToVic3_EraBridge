import json
from pathlib import Path
import tempfile
import unittest

from release_acceptance import sha256, verify_payload


class PayloadIntegrityTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'app.txt').write_bytes(b'original')
        (root / 'build_manifest.json').write_text(json.dumps({
            'version': 'test', 'files': {'app.txt': sha256(root / 'app.txt')}}))

    def test_detects_changed_missing_and_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            self.assertEqual(1, verify_payload(root)['files_checked'])
            (root / 'app.txt').write_bytes(b'changed')
            with self.assertRaises(ValueError): verify_payload(root)
            (root / 'app.txt').unlink()
            with self.assertRaises(ValueError): verify_payload(root)
            self.fixture(root)
            (root / 'unexpected.dll').write_bytes(b'extra')
            with self.assertRaises(ValueError): verify_payload(root)

    def test_rejects_manifest_path_outside_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / 'app'; root.mkdir()
            (parent / 'outside').write_bytes(b'outside')
            (root / 'build_manifest.json').write_text(json.dumps({
                'version': 'test', 'files': {'../outside': sha256(parent / 'outside')}}))
            with self.assertRaises(ValueError): verify_payload(root)

    def test_allows_new_player_data_but_checks_packaged_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / 'data').mkdir()
            (root / 'data/player.json').write_text('{}')
            self.assertEqual(1, verify_payload(root)['files_checked'])
            (root / 'data/defaults.json').write_text('{}')
            manifest = json.loads((root / 'build_manifest.json').read_text())
            manifest['files']['data/defaults.json'] = sha256(root / 'data/defaults.json')
            (root / 'build_manifest.json').write_text(json.dumps(manifest))
            (root / 'data/defaults.json').write_text('{"changed":true}')
            with self.assertRaises(ValueError): verify_payload(root)


if __name__ == '__main__':
    unittest.main()
