"""Build the approved broad-heritage design on the latest installed M5 baseline."""
import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil

from build_m2_prototype import objects
from m3_world import digest
from package_m5_culture_refinement import read, write, files
from package_m5_historical_homelands import population_metadata
from pdx_text import root
from verify_m5_heritage_reuse import verify, require, CULTURES, TRAITS, LOC, POPS

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT/'config/personal/m5_heritage_reuse_proposal.json'


def build(output):
    installed = read(ROOT/'.local/m5/installation-latest.json')
    require(installed == read(ROOT/'.local/economy/installation-latest.json'), 'Installation pointers differ')
    prior = Path(installed['package'])
    previous = read(prior/'package_report.json')
    base = Path(previous['mod_directory'])
    baseline = files(base)
    require(baseline == previous['output_sha256'] == files(Path(installed['target'])), 'Baseline differs from installed mod')
    approved_dir = Path(read(ROOT/'.local/m5/heritage-reuse-latest.json')['report'])
    approved, policy = read(approved_dir/'audit.json'), read(POLICY)
    require(policy == approved['policy'], 'Policy changed since reviewed table')
    require(read(approved_dir/'validation.json')['passed'], 'Approved audit did not pass')
    mapping = {r['culture']: r for r in approved['rows'] if r['status'] == 'recommended'}
    output.mkdir(parents=True, exist_ok=False)
    mod = output/'eu5_economy_test'
    shutil.copytree(base, mod)
    replacements = []
    for rel in sorted(CULTURES):
        raw = (base/rel).read_bytes()
        text = raw.decode('utf-8-sig')
        edits = []
        for culture, node in objects(root(text)):
            if culture not in mapping:
                continue
            row = mapping[culture]
            matches = list(re.finditer(r'(?m)^[ \t]*heritage[ \t]*=[ \t]*([a-z0-9_]+)', node.text()))
            require(len(matches) == 1 and matches[0][1] == row['current'], 'Heritage baseline mismatch: '+culture)
            m = matches[0]
            edits.append((node.start+m.start(1), node.start+m.end(1), row['target']))
            replacements.append({'culture': culture, 'from': row['current'], 'to': row['target'], 'file': rel})
        for start, end, value in sorted(edits, reverse=True):
            text = text[:start] + value + text[end:]
        (mod/rel).write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + text.encode('utf-8'))
    require(len(replacements) == len(mapping), 'Missing or duplicate culture edit')
    shared = policy['new_shared_heritages']
    (mod/TRAITS).write_text(''.join(f'{key} = {{\n\ttype = heritage\n\ttrait_group = {v["group"]}\n}}\n\n' for key, v in shared.items()), encoding='utf-8-sig')
    for lang, rel in LOC.items():
        text = 'l_'+lang+':\n'
        for key, value in shared.items():
            label = value['english' if lang == 'english' else 'name']
            require('"' not in label and '\n' not in label, 'Invalid localization string')
            text += f' {key}:0 "{label}"\n'
        (mod/rel).write_text(text, encoding='utf-8-sig')
    meta = read(mod/'.metadata/metadata.json')
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)', installed['version'])
    require(match, 'Unknown version pattern')
    a,b,c,d = map(int, match.groups())
    meta['version'] = f'{a}.{b}.{c+1}-m5-test{d+1}'
    write(mod/'.metadata/metadata.json', meta)
    shutil.copy2(POLICY, output/'policy.snapshot.json')
    shutil.copy2(approved_dir/'audit.json', output/'approved_audit.json')
    write(output/'heritage_changes.json', replacements)
    check = verify(base, mod, policy, approved)
    write(output/'heritage_verification.json', check)
    inputs = [POLICY, approved_dir/'audit.json', prior/'package_report.json',
              Path(__file__), ROOT/'tools/verify_m5_heritage_reuse.py', ROOT/'tools/update_m5_integrated_test.ps1']
    hashes = files(mod)
    report = {'status': 'heritage_reuse_static_verified_runtime_pending', 'update_scope': 'm5_heritage_reuse',
        'version': meta['version'], 'mod_name': meta['name'], 'mod_directory': str(mod), 'prior_package': str(prior),
        'new_campaign_required': True, 'approved_audit_directory': str(approved_dir),
        'changed_files': check['changed_files'], 'added_files': check['added_files'],
        'input_sha256': {str(p.resolve()): digest(p) for p in inputs}, 'output_sha256': hashes,
        **population_metadata(prior, baseline[POPS])}
    for key in ('political_run', 'demographic_run'):
        if key in previous:
            report[key] = previous[key]
    write(output/'package_report.json', report)
    write(output/'verification.json', {'status': 'passed_static_runtime_pending',
        'literacy': read(prior/'verification.json')['literacy'], 'heritage_reuse': check,
        'package_report_sha256': digest(output/'package_report.json'),
        'audit_sha256': {p.name:digest(p) for p in output.iterdir() if p.is_file() and p.name not in ('package_report.json','verification.json')}})
    require(read(ROOT/'.local/m5/installation-latest.json') == installed, 'Installation changed during build')
    require(files(Path(installed['target'])) == baseline, 'Live installation changed during build')
    write(ROOT/'.local/m5/heritage-package-latest.json', {'package': str(output), 'version': meta['version']})
    return {'package': str(output), 'version': meta['version'], **check}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT/'.local/economy/packages'/('m5-heritage-reuse-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    import json
    print(json.dumps(build(output.resolve()), ensure_ascii=True, indent=2))
