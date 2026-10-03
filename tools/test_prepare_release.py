import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from prepare_release import copy_tree, prepare, seal, sha256, license_inventory, copy_public_docs, PUBLIC_DOCUMENTS, stage_visual_cpp


class ReleasePreparationTests(unittest.TestCase):
    def test_private_and_build_artifacts_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / 'source', root / 'target'
            for name in ['app.py', 'icons/logo.png', '__pycache__/app.pyc', '.local/token.txt', 'logs/debug.txt', 'save.eu5', 'save.v3', 'launcher.obj', 'launcher.res']:
                p = source / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'fixture')
            copy_tree(source, target)
            self.assertEqual({'app.py', 'icons/logo.png'}, {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()})

    def test_only_public_documents_are_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (*PUBLIC_DOCUMENTS, 'M5_INTEGRATED_TEST.md', 'research/private-notes.md'):
                p = root / 'docs' / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('fixture', encoding='utf-8')
            stage = root / 'candidate'
            copy_public_docs(root, stage)
            self.assertEqual(set(PUBLIC_DOCUMENTS), {p.relative_to(stage / 'docs').as_posix() for p in (stage / 'docs').rglob('*') if p.is_file()})

    def test_archive_manifest_matches_payload_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / 'candidate'
            stage.mkdir()
            (stage / 'sample.txt').write_text('中文 sample', encoding='utf-8')
            archive = root / 'candidate.zip'
            manifest = seal(stage, archive)
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual({'candidate/sample.txt', 'candidate/build_manifest.json'}, set(zipped.namelist()))
                self.assertEqual(json.loads(zipped.read('candidate/build_manifest.json')), manifest)
            self.assertEqual(sha256(stage / 'sample.txt'), manifest['files']['sample.txt'])
            self.assertTrue(manifest['internal_candidate'])
            with self.assertRaises(FileExistsError):
                seal(stage, archive)

    def test_public_preview_seals_same_bytes_with_public_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / 'preview'
            stage.mkdir()
            (stage / 'payload.txt').write_bytes(b'public preview')
            manifest = seal(stage, root / 'preview.zip', public_preview=True, source_commit='a' * 40)
            self.assertFalse(manifest['internal_candidate'])
            self.assertEqual('community_preview', manifest['channel'])
            self.assertEqual('a' * 40, manifest['source_commit'])
            self.assertEqual(sha256(stage / 'payload.txt'), manifest['files']['payload.txt'])

    def test_official_runtime_replaces_old_copies_and_reaches_importer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'redist/x64/Microsoft.VC143.CRT/vcruntime140.dll'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'official')
            stage = root / 'stage'
            (stage / 'native').mkdir(parents=True)
            for name in ('runtime/vcruntime140.dll', 'runtime/DLLs/vcruntime140.dll'):
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'old')
            sources = {'vcruntime140.dll': source}
            stage_visual_cpp(stage, sources)
            for name in ('native/vcruntime140.dll', 'runtime/vcruntime140.dll', 'runtime/DLLs/vcruntime140.dll'):
                self.assertEqual(b'official', (stage / name).read_bytes())
            self.assertEqual([], license_inventory(stage, root / 'python', sources)['unmatched_binaries'])
            (stage / 'runtime/vcruntime140.dll').write_bytes(b'changed')
            self.assertEqual(['runtime/vcruntime140.dll'], license_inventory(stage, root / 'python', sources)['unmatched_binaries'])

    def test_metadata_cannot_certify_a_different_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, cache, stage = root / 'python', root / 'cache', root / 'stage'
            (base / 'conda-meta').mkdir(parents=True)
            (cache / 'DLLs').mkdir(parents=True)
            (cache / 'DLLs/lib.dll').write_bytes(b'original')
            (stage / 'runtime').mkdir(parents=True)
            (stage / 'runtime/lib.dll').write_bytes(b'replaced by pip')
            (base / 'conda-meta/pkg.json').write_text(json.dumps({'name':'fixture', 'version':'1', 'files':['DLLs/lib.dll'], 'link':{'source':str(cache)}}))
            result = license_inventory(stage, base)
            self.assertEqual(['runtime/lib.dll'], result['unmatched_binaries'])
            self.assertEqual([], result['packages'])

    def test_wheel_record_matches_bytes_even_for_relocated_dll(self):
        import base64
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stage = root / 'stage'
            info = stage / 'runtime/Lib/site-packages/fixture-1.dist-info'
            info.mkdir(parents=True)
            (info / 'METADATA').write_text('Name: fixture\nVersion: 1\nLicense: MIT\n')
            digest = base64.urlsafe_b64encode(hashlib.sha256(b'original').digest()).decode().rstrip('=')
            (info / 'RECORD').write_text('fixture.libs/lib.dll,sha256=' + digest + ',8\n')
            (stage / 'runtime/lib.dll').write_bytes(b'original')
            result = license_inventory(stage, root / 'python')
            self.assertEqual([], result['unmatched_binaries'])
            self.assertEqual(['fixture-1-wheel-record'], result['binaries'][0]['matched_packages'])
            (stage / 'runtime/lib.dll').write_bytes(b'changed')
            self.assertEqual(['runtime/lib.dll'], license_inventory(stage, root / 'python')['unmatched_binaries'])

    def test_rejects_output_outside_build_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                prepare(root, root / 'app', root / 'release', root / 'python')
            self.assertFalse((root / 'release').exists())


if __name__ == '__main__':
    unittest.main()
