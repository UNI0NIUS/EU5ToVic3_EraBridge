"""Independent readback of a heritage-only M5 overlay, including installed copies."""
import argparse
from collections import Counter
from pathlib import Path

from build_m2_prototype import objects
from build_m3_world import load_localization
from package_m4_population_test import effective, parse_pops
from package_m5_culture_refinement import read, write, files
from pdx_text import root, Object

CULTURES = {f'common/cultures/zz_eu5_{s}.txt' for s in ('cultures', 'resident_cultures', 'migrant_cultures')}
TRAITS = 'common/discrimination_traits/zz_eu5_shared_heritages.txt'
LOC = {lang: f'localization/{lang}/eu5_shared_heritages_l_{lang}.yml' for lang in ('english', 'simp_chinese')}
ADDED = {TRAITS, *LOC.values()}
ALLOWED = CULTURES | ADDED | {'.metadata/metadata.json'}
POPS = 'common/history/pops/00_eu5_world.txt'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(node):
    return [(k, canonical(v) if isinstance(v, Object) else v) for k, v in node.entries()]


def verify(base, mod, policy, approved):
    old_files, new_files = files(base), files(mod)
    changed = {p for p in new_files if new_files[p] != old_files.get(p)}
    require(old_files.keys() <= new_files.keys(), 'Deleted existing file')
    require(new_files.keys() - old_files.keys() == ADDED, 'Unexpected additions')
    require(changed <= ALLOWED, 'Unrelated files changed')
    mapping = {}
    for group in policy['groups']:
        require(group['status'] == 'recommended', 'Unapproved policy group')
        for culture in group['members']:
            require(culture not in mapping, 'Duplicate policy membership')
            mapping[culture] = group['target']
    reviewed = {r['culture']: r for r in approved['rows']}
    require(mapping == {k: r['target'] for k, r in reviewed.items() if r['status'] == 'recommended'}, 'Approved mapping changed')
    old, new = effective(base, 'common/cultures'), effective(mod, 'common/cultures')
    require(old.keys() == new.keys(), 'Culture identities changed')
    require(set(reviewed) == {c for c in old if c.startswith('eu5_')}, 'Custom inventory changed since approval')
    for c, definition in old.items():
        expected = {k: canonical(v) if isinstance(v, Object) else v for k, v in definition.items()}
        if c in reviewed:
            require(definition['heritage'] == reviewed[c]['current'], 'Approved baseline heritage differs: ' + c)
        if c in mapping:
            expected['heritage'] = mapping[c]
        actual = {k: canonical(v) if isinstance(v, Object) else v for k, v in new[c].items()}
        require(actual == expected, 'Unexpected culture field change: ' + c)
    # Preserve repeated/list fields as well, not only the flattened field catalog.
    seen = set()
    for rel in CULTURES:
        before = dict(objects(root((base/rel).read_text(encoding='utf-8-sig'))))
        after = dict(objects(root((mod/rel).read_text(encoding='utf-8-sig'))))
        require(before.keys() == after.keys(), 'Local culture definitions differ')
        for c, obj in before.items():
            expected = [(k, mapping[c] if k == 'heritage' and c in mapping else v) for k, v in canonical(obj)]
            require(canonical(after[c]) == expected, 'Non-heritage culture body changed: ' + c)
            if c in mapping:
                require(c not in seen, 'Duplicate written culture')
                seen.add(c)
    require(seen == set(mapping), 'Not every approved culture written')
    shared = policy['new_shared_heritages']
    entries = list(objects(root((mod/TRAITS).read_text(encoding='utf-8-sig'))))
    require(len(entries) == len(shared) and {k for k, _ in entries} == set(shared), 'Shared trait definitions incomplete')
    for key, obj in entries:
        require(obj.fields() == {'type': 'heritage', 'trait_group': shared[key]['group']}, 'Invalid shared trait: ' + key)
    all_traits = effective(mod, 'common/discrimination_traits')
    for culture, definition in new.items():
        h = definition['heritage']
        require(h in all_traits and all_traits[h]['type'] == 'heritage', 'Missing culture heritage: ' + culture)
        if culture in reviewed:
            require(all_traits[h]['trait_group'] == reviewed[culture]['target_group'], 'Approved heritage group differs: ' + culture)
    for lang, rel in LOC.items():
        raw = (mod/rel).read_bytes()
        require(raw.startswith(b'\xef\xbb\xbf'), 'Localization requires UTF-8 BOM')
        require(raw.decode('utf-8-sig').splitlines()[0] == 'l_' + lang + ':', 'Wrong localization header')
        loaded = load_localization(mod/'localization'/lang)
        for key, value in shared.items():
            require(loaded[key] == value['english' if lang == 'english' else 'name'], 'Wrong/missing localization')
    pops = parse_pops(mod/POPS)
    require(pops == parse_pops(base/POPS), 'Population changed')
    active = {d['heritage'] for c, d in new.items() if c.startswith('eu5_') and d['heritage'].startswith('eu5_')}
    require(len(active) == approved['stats']['active_custom_traits_if_recommended_applied'], 'Wrong active custom heritage count')
    require(len(active) <= policy['budget']['max_remaining_active_custom_heritages'], 'Heritage budget exceeded')
    require(len(shared) <= policy['budget']['max_new_shared_heritages'], 'New shared trait budget exceeded')
    old_meta, new_meta = read(base/'.metadata/metadata.json'), read(mod/'.metadata/metadata.json')
    require({k:v for k,v in old_meta.items() if k != 'version'} == {k:v for k,v in new_meta.items() if k != 'version'}, 'Unexpected metadata fields')
    return {'status': 'passed', 'changed_cultures': len(mapping), 'new_shared_heritages': len(shared),
        'active_custom_heritages': len(active), 'effective_cultures': len(new),
        'pop_groups': len(pops), 'global_integer_population': sum(pops.values()),
        'used_pop_cultures': len({c for (_, _, c, _) in pops}),
        'heritage_only_culture_changes': True, 'all_heritage_references_resolved': True,
        'population_homelands_literacy_borders_economy_byte_identical': True,
        'unrelated_files_byte_identical': True, 'unchanged_existing_files': len(old_files) - len(changed - ADDED),
        'shared_localization_verified': True, 'runtime_verified': False,
        'changed_files': sorted(changed), 'added_files': sorted(ADDED)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--mod', type=Path)
    args = parser.parse_args()
    report = read(args.package/'package_report.json')
    base = Path(read(Path(report['prior_package'])/'package_report.json')['mod_directory'])
    result = verify(base, args.mod or Path(report['mod_directory']), read(args.package/'policy.snapshot.json'), read(args.package/'approved_audit.json'))
    write(args.package/('installed_heritage_readback.json' if args.mod else 'independent_heritage_readback.json'), result)
    import json
    print(json.dumps(result, ensure_ascii=True, indent=2))
