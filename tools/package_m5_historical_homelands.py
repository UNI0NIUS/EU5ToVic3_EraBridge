"""Package the reviewed homeland overlay against the current installed baseline.

This promotes a verified research artifact; it never installs or infers new claims.
An outdated research baseline is rejected so newer modules cannot be overwritten.
"""
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
import shutil

from package_m5_culture_refinement import read, write, files
from package_m4_population_test import parse_pops
from m3_world import digest
from verify_m5_historical_homelands import verify, state_structure, STATE, POPS

ROOT = Path(__file__).resolve().parents[1]


def population_metadata(package, population_sha):
    """Recover options only through ancestors with identical population bytes."""
    seen = set()
    while package is not None:
        package = package.resolve()
        if package in seen:
            raise ValueError('Cycle in population provenance')
        seen.add(package)
        report = read(package / 'package_report.json')
        if report['output_sha256'][POPS] != population_sha:
            raise ValueError('Population options missing at a population change')
        if 'population_mode' in report:
            return {k: report[k] for k in ('population_mode', 'population_calibrated',
                                           'source_population_conserved')}
        if 'population_calibrated' in report:
            return {k: report[k] for k in ('population_calibrated', 'source_population_conserved')}
        package = Path(report['prior_package']) if report.get('prior_package') else None
    return {}


def verify_payload(base, mod, candidate_hashes):
    current = files(mod)
    expected = dict(candidate_hashes)
    expected['.metadata/metadata.json'] = current['.metadata/metadata.json']
    if current != expected:
        raise ValueError('Packaged payload differs from verified research candidate')
    before, before_structure, states = state_structure(base / STATE)
    after, after_structure, final_states = state_structure(mod / STATE)
    if before_structure != after_structure or states != final_states or not before <= after:
        raise ValueError('Political state structure or existing homelands changed')
    pops = parse_pops(mod / POPS)
    if pops != parse_pops(base / POPS):
        raise ValueError('Population changed')
    totals, migrant = Counter(), Counter()
    for (s, t, c, r), n in pops.items():
        totals[s] += n
        if c.startswith('eu5_migrant_'):
            migrant[s, c] += n
    expected_migrant = {(s, c) for (s, c), n in migrant.items() if 2 * n > totals[s]}
    if {(s, c) for s, c in after if c.startswith('eu5_migrant_')} != expected_migrant:
        raise ValueError('Migrant homelands differ from current population majorities')
    return {
        'packaged_payload_verified': True,
        'migrant_strict_majority_verified': True,
        'migrant_homeland_pairs': len(expected_migrant),
        'global_integer_population': sum(pops.values()),
        'integer_population_groups': len(pops),
        'population_and_non_homeland_files_unchanged': True,
    }


def build(candidate, output):
    installed = read(ROOT / '.local/m5/installation-latest.json')
    if installed != read(ROOT / '.local/economy/installation-latest.json'):
        raise ValueError('Installation pointers disagree')
    prior = Path(installed['package'])
    previous = read(prior / 'package_report.json')
    base = Path(previous['mod_directory'])
    baseline = files(base)
    if baseline != previous['output_sha256'] or files(Path(installed['target'])) != baseline:
        raise ValueError('Installed baseline changed')
    manifest = read(candidate / 'manifest.json')
    if Path(manifest['baseline_package']).resolve() != prior.resolve() or manifest['baseline_sha256'] != baseline:
        raise ValueError('Research baseline is stale; rebuild the candidate on the latest installation')
    evidence = verify(candidate)
    if evidence['unprocessed_designs'] or evidence['removed_homeland_pairs']:
        raise ValueError('Incomplete or subtractive homeland update')
    output.mkdir(parents=True, exist_ok=False)
    mod = output / 'eu5_economy_test'
    shutil.copytree(Path(manifest['candidate_mod']), mod)
    meta = read(mod / '.metadata/metadata.json')
    version = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)', installed['version'])
    if not version:
        raise ValueError('Unrecognized M5 version')
    major, minor, patch, test = map(int, version.groups())
    meta['version'] = f'{major}.{minor}.{patch + 1}-m5-test{test + 1}'
    write(mod / '.metadata/metadata.json', meta)
    payload = verify_payload(base, mod, manifest['output_sha256'])
    final_hashes = files(mod)
    changed = sorted(p for p in final_hashes if final_hashes[p] != baseline[p])
    if set(changed) != {STATE, '.metadata/metadata.json'}:
        raise ValueError('No new homeland update or unrelated changes')
    # Preserve the research snapshot as research; deployment has its own report.
    for name in ('manifest.json', 'policy.snapshot.json', 'homeland_register.csv'):
        shutil.copy2(candidate / name, output / ('research_' + name))
    write(output / 'research_verification.json', evidence)
    summary = {k: v for k, v in evidence.items() if not k.endswith('_cultures') and k != 'installed'}
    summary.update(payload, runtime_verified=False)
    write(output / 'homeland_verification.json', summary)
    inputs = dict(manifest['input_sha256'])
    for path in (candidate / 'manifest.json', candidate / 'policy.snapshot.json',
                 candidate / 'homeland_register.csv', prior / 'package_report.json',
                 Path(__file__), ROOT / 'tools/update_m5_integrated_test.ps1'):
        inputs[str(path.resolve())] = digest(path)
    report = {
        'status': 'historical_homelands_static_verified_runtime_pending',
        'update_scope': 'm5_historical_homelands', 'version': meta['version'],
        'mod_name': meta['name'], 'mod_directory': str(mod), 'prior_package': str(prior),
        'research_candidate': str(candidate), 'new_campaign_required': True,
        'changed_files': changed, 'input_sha256': inputs, 'output_sha256': final_hashes,
    }
    for key in ('political_run', 'demographic_run'):
        if key in previous:
            report[key] = previous[key]
    report.update(population_metadata(prior, baseline[POPS]))
    write(output / 'package_report.json', report)
    audits = [p for p in output.iterdir() if p.is_file() and p.name != 'package_report.json']
    write(output / 'verification.json', {
        'status': 'passed_static_runtime_pending',
        'literacy': read(prior / 'verification.json')['literacy'],
        'historical_homelands': summary,
        'inherited_verified_package': str(prior),
        'package_report_sha256': digest(output / 'package_report.json'),
        'audit_sha256': {p.name: digest(p) for p in audits},
    })
    if read(ROOT / '.local/m5/installation-latest.json') != installed:
        raise ValueError('Installation changed during packaging; rebuild on the new baseline')
    return {'package': str(output), 'version': meta['version'], 'changed_files': changed,
            'newly_covered_cultures': evidence['newly_covered_cultures'],
            'added_homeland_pairs': evidence['added_homeland_pairs'],
            'withheld_count': evidence['withheld_count'], **payload}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    candidate = args.candidate or Path(read(ROOT / '.local/m5/historical-homelands-latest.json')['candidate'])
    output = args.output or ROOT / '.local/economy/packages' / ('m5-historical-homelands-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    import json
    print(json.dumps(build(candidate.resolve(), output.resolve()), ensure_ascii=False, indent=2))
