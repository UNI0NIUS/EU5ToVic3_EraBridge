"""Fault-injection checks against a disposable copy of the built candidate."""
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from package_m5_culture_refinement import read
from verify_m5_heritage_reuse import verify, TRAITS, LOC, POPS

ROOT = Path(__file__).resolve().parents[1]


class HeritageOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(read(ROOT/'.local/m5/heritage-package-latest.json')['package'])
        report = read(cls.package/'package_report.json')
        cls.base = Path(read(Path(report['prior_package'])/'package_report.json')['mod_directory'])
        cls.policy = read(cls.package/'policy.snapshot.json')
        cls.approved = read(cls.package/'approved_audit.json')
        cls.temp = tempfile.TemporaryDirectory(prefix='heritage-check-', dir=ROOT/'.local/m5')
        cls.mod = Path(cls.temp.name)/'mod'
        shutil.copytree(Path(report['mod_directory']), cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self):
        return verify(self.base, self.mod, self.policy, self.approved)

    def reject_mutation(self, rel, transform, message):
        path = self.mod/rel
        raw = path.read_bytes()
        try:
            altered = transform(raw)
            self.assertNotEqual(raw, altered)
            path.write_bytes(altered)
            with self.assertRaisesRegex(ValueError, message):
                self.check()
        finally:
            path.write_bytes(raw)

    def test_approved_payload(self):
        result = self.check()
        self.assertEqual(result['changed_cultures'], 300)
        self.assertEqual(result['active_custom_heritages'], 22)

    def test_language_mutation_rejected(self):
        self.reject_mutation('common/cultures/zz_eu5_resident_cultures.txt',
            lambda b: re.sub(rb'(?m)^(\s*language\s*=\s*)[a-z0-9_]+', rb'\1language_bad', b, count=1),
            'Unexpected culture field change')

    def test_trait_group_mutation_rejected(self):
        self.reject_mutation(TRAITS, lambda b: b.replace(b'heritage_group_indigenous_american', b'heritage_group_european', 1),
            'Invalid shared trait')

    def test_missing_trait_rejected(self):
        self.reject_mutation(TRAITS, lambda b: b'\xef\xbb\xbf# no shared definitions\n', 'Shared trait definitions incomplete')

    def test_population_bytes_protected(self):
        self.reject_mutation(POPS, lambda b: b+b'\n# unexpected population-file edit\n', 'Unrelated files changed')

    def test_localization_mutation_rejected(self):
        self.reject_mutation(LOC['english'], lambda b: b.replace(b'Andean Pacific Coast', b'Wrong label'), 'Wrong/missing localization')


if __name__ == '__main__':
    unittest.main()
