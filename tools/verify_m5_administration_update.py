"""Bind an M5 administration update to its exact installed predecessor."""
import argparse
from pathlib import Path
from package_economy_candidate import load, write
from m3_world import digest
from economy_model import definitions


def verify(package,world_review=None):
    report = load(package/'package_report.json')
    base = Path(report['base_package'])
    prior = load(base/'package_report.json')
    previous_check = load(base/'verification.json')
    candidate = Path(report['economy_candidate'])
    manifest = load(candidate/'manifest.json')
    for rel, sha in manifest['outputs'].items():
        if digest(candidate/rel) != sha: raise ValueError('Candidate output changed: '+rel)
    before, after = prior['output_sha256'], report['output_sha256']
    if set(before) != set(after): raise ValueError('Unexpected mod file addition/removal')
    mod, old_mod = Path(report['mod_directory']), Path(prior['mod_directory'])
    changed = []
    for rel in sorted(before):
        if digest(mod/rel) != after[rel] or digest(old_mod/rel) != before[rel]:
            raise ValueError('Package file changed: '+rel)
        if before[rel] == after[rel]: continue
        if rel not in ('.metadata/metadata.json', 'common/history/buildings/00_eu5_world.txt') and not rel.startswith('map_data/state_regions/'):
            raise ValueError('Unrelated M5 change: '+rel)
        changed.append(rel)
    # No geographic / trait / resource changes hidden in arable capacity updates.
    old_states = definitions(old_mod/'map_data/state_regions')
    new_states = definitions(mod/'map_data/state_regions')
    def clean(value):
        return value.text().split() if hasattr(value, 'text') else value
    for state, old in old_states.items():
        a = {k: clean(v) for k, v in old.items() if k != 'arable_land'}
        b = {k: clean(v) for k, v in new_states[state].items() if k != 'arable_land'}
        if a != b: raise ValueError('Unexpected state definition change: '+state)
    budget = load(candidate/'bureaucracy.json')
    if budget['countries_below_core_demand']:
        raise ValueError('Unresolved core administration demand: '+str(budget['countries_below_core_demand']))
    if previous_check['literacy']['status'] != 'passed': raise ValueError('M5 literacy baseline not verified')
    development = None
    if world_review:
        check = load(world_review/'verification.json')
        world = load(world_review/'report.json')
        if digest(world_review/'report.json') != check['report_sha256'] or digest(world_review/'review.html') != check['review_sha256']:
            raise ValueError('World audit changed')
        if world['status'] != 'passed_source_development_static_runtime_pending' or world['coverage']['unprocessed_countries'] or world['source_development_violations'] or not world['source_armies_unchanged']:
            raise ValueError('World development verification missing')
        if Path(world['candidate']).resolve() != candidate.resolve() or world['input_sha256'][str((candidate/'manifest.json').resolve())] != digest(candidate/'manifest.json'):
            raise ValueError('World review belongs to another candidate')
        development = {'status':'passed','coverage':world['coverage'],'source_development_violations':0,
                       'source_armies_unchanged':True,'runtime_verified':False}
        report['input_sha256'][str((world_review/'report.json').resolve())] = digest(world_review/'report.json')
        report['world_review'] = str(world_review.resolve())
    scope = 'm5_world_economy' if development else 'm5_administration'
    report.update(prior_package=str(base.resolve()), update_scope=scope,
                  changed_files=changed, status=scope+'_static_verified_runtime_pending')
    write(package/'package_report.json', report)
    result = {'status': 'passed_static_runtime_pending', 'literacy': previous_check['literacy'],
              'development':development,
              'administration': {'status': 'passed', 'countries_checked': len(budget['countries']),
                                 'core_demand_gaps': 0,
                                 'reserve_shortfalls': budget['countries_with_planning_gap'],
                                 'paper_shortfalls': [r['country'] for r in budget['countries'] if r['paper_net_industrial_supply'] < -.001],
                                 'runtime_verified': False},
              'unchanged_countries_diplomacy_population_literacy_geography': True,
              'changed_files': changed, 'package_report_sha256': digest(package/'package_report.json')}
    write(package/'verification.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--package', type=Path, required=True)
    p.add_argument('--world-review',type=Path)
    a = p.parse_args(); print(verify(a.package,a.world_review))
