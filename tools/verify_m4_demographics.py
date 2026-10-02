"""Read back identity ledgers, resolved groups and the partial history preview."""
from collections import Counter
import csv
import json
from pathlib import Path

from build_m2_prototype import objects, strings
from build_m3_world import load_localization
from m3_world import digest, fields, load_json
from pdx_text import root
from verify_m4_culture_assets import verify_culture_assets
from m4_migrant_cultures import verify_migrants


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        yield from csv.DictReader(f)


def verify_religion_assets(out, report):
    """Read the actual generated definitions and references, not just the mapping report."""
    game = Path('D:/Steam/steamapps/common/Victoria 3/game')
    def defs(directory):
        return {k:fields(o) for p in sorted(directory.glob('*.txt')) for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    installed_religions = defs(game/'common/religions')
    traits = defs(game/'common/discrimination_traits'); groups = defs(game/'common/discrimination_trait_groups')
    goods = defs(game/'common/goods')
    asset = out/'identity_assets'
    added = defs(asset/'common/religions'); added_traits = defs(asset/'common/discrimination_traits'); added_groups = defs(asset/'common/discrimination_trait_groups')
    assert not (set(added)&set(installed_religions))
    assert not (set(added_traits)&set(traits)) and not (set(added_groups)&set(groups))
    traits.update(added_traits);groups.update(added_groups)
    custom = report.get('custom_religions',{'religions':[], 'inputs_sha256':{}})
    assert set(added) == {r['target'] for r in custom['religions']}
    for p,sha in custom['inputs_sha256'].items():
        assert digest(Path(p)) == sha
    locs = {lang:load_localization(asset/'localization'/lang) for lang in ('simp_chinese','english')}
    for entry in custom['religions']:
        religion = added[entry['target']];heritage = religion['heritage']
        assert heritage == entry['heritage'] and traits[heritage]['type'] == 'heritage'
        group = traits[heritage]['trait_group']
        assert group == entry['heritage_group'] and groups[group]['type'] == 'heritage'
        colors = [float(v) for v in strings(religion['color'])]
        assert colors == entry['color'] and len(colors) == 3 and all(0 <= v <= 1 for v in colors)
        assert religion['icon'] == entry['icon']
        icon = (asset/religion['icon']).resolve()
        assert icon.is_relative_to(asset.resolve()) and digest(icon) == entry['icon_sha256']
        from PIL import Image
        with Image.open(icon) as image:
            image.load();assert list(image.size) == entry['icon_dimensions']
        taboos = strings(religion['taboos']) if 'taboos' in religion else []
        assert taboos == entry['taboos'] and all(g in goods for g in taboos)
        for lang,loc in locs.items():
            assert loc.get(entry['target'])
            if entry['isolated_heritage']:
                assert loc.get(heritage) and loc.get(group)
    return set(installed_religions)|set(added)


def verify(source, out):
    r = load_json(out/'demographics_report.json'); summary = load_json(source/'source_summary.json')
    stage = Path(r['stage']); sr = load_json(stage/'staging_report.json')
    profile_path=Path(r['profile_path']);assert digest(profile_path)==r['profile_sha256']
    profile=load_json(profile_path)
    assert r.get('culture_compaction',{})==profile.get('culture_compaction',{})
    assert digest(stage/'staging_report.json') == r['stage_report_sha256']
    assert summary['source_sha256'] == r['source_sha256'] == sr['source_sha256']
    for name, sha in r['files_sha256'].items():
        assert digest(out/name) == sha
    for name, sha in sr['files_sha256'].items():
        assert digest(stage/name) == sha
    valid_religions = verify_religion_assets(out,r)
    cultures = {x['source_culture']:x for x in rows(out/'resident_culture_crosswalk.csv')}
    religions = {x['source_religion']:x for x in rows(out/'resident_religion_crosswalk.csv')}
    culture_assets = verify_culture_assets(Path('D:/Steam/steamapps/common/Victoria 3/game'),Path(sr['political_run']),cultures,valid_religions,out/'identity_assets',r.get('custom_resident_cultures'))
    migrant_lookup={}
    if r.get('migrant_cultures',{}).get('config'):
        profile_path=Path(r['profile_path']);assert digest(profile_path)==r['profile_sha256']
        migrant_lookup=verify_migrants(out/'migrant_assets',Path('D:/Steam/steamapps/common/Victoria 3/game'),r,load_json(profile_path),cultures,valid_religions)
    migrant_totals=Counter()
    provisional={c['source']:c for c in r.get('custom_resident_cultures',{}).get('cultures',[]) if c.get('review_status')=='generated_preservation_candidate_not_historically_reviewed'}
    if 'generated_provisional_cultures' in r:
        queue={x['source_culture']:x for x in rows(out/'culture_asset_review_queue.csv')}
        assert queue.keys()==provisional.keys()
        assert len(queue)==r['generated_provisional_cultures']
        for c,entry in queue.items():
            assert int(entry['centipersons'])==sum(summary['culture_centipersons'][member] for member in (provisional[c].get('aggregate_members') or [c]))
            assert entry['target_culture']==provisional[c]['target']
            assert entry['review_status']=='generated_preservation_candidate_not_historically_reviewed'
        assert sum(int(x['centipersons']) for x in queue.values())==r['generated_provisional_culture_centipersons']
        assert r['cultural_policy_review_complete'] is False
    # Re-read pinned definitions independently of the alias resolver.
    definitions = {}
    for path, sha in r['game_definition_sha256'].items():
        p = Path(path)
        assert digest(p) == sha
        if p.parent.name == 'cultures':
            side = 'source' if 'Europa Universalis V' in path else 'target'
            definitions.setdefault(side,{}).update({k:fields(o) for k,o in objects(root(p.read_text(encoding='utf-8-sig')))})
    for c,check in r.get('culture_alias_checks',{}).items():
        source_definition = definitions['source'][c]; target_definition = definitions['target'][check['target']]
        assert source_definition['language'] == check['source_language']
        source_groups = strings(source_definition['culture_groups']) if 'culture_groups' in source_definition else []
        assert set(source_groups) == set(check['source_groups'])
        assert target_definition['heritage'] == check['target_heritage'] and target_definition['language'] == check['target_language']
        if c in cultures:
            assert cultures[c]['target_culture'] == check['target'] and cultures[c]['method'] == 'resident_explicit_alias'
    effective_targets=dict(definitions['target'])
    for path in (out/'identity_assets/common/cultures').glob('*.txt'):
        effective_targets.update({k:fields(o) for k,o in objects(root(path.read_text(encoding='utf-8-sig')))})
    for c,rule in r.get('culture_compaction',{}).items():
        source_definition=definitions['source'][c];target_definition=effective_targets[rule['target']]
        assert source_definition['language']==rule['source_language']
        assert set(strings(source_definition['culture_groups']) if 'culture_groups' in source_definition else [])==set(rule['source_groups'])
        assert target_definition['heritage']==rule['target_heritage'] and target_definition['language']==rule['target_language']
        assert cultures[c]['target_culture']==rule['target'] and cultures[c]['method']=='explicit_v3_granularity_compaction'
        assert c not in {entry['source'] for entry in r['custom_resident_cultures']['cultures']}
    for check in r.get('custom_resident_cultures',{}).get('cultures',[]):
        c = check['source']; definition = definitions['source'][c]
        assert definition['language'] == check['source_language']
        source_groups = strings(definition['culture_groups']) if 'culture_groups' in definition else []
        assert set(source_groups) == set(check['source_groups'])
        if c in cultures:
            assert cultures[c]['target_culture'] == check['target'] and cultures[c]['method'] == 'preserved_resident_custom_identity'
    assert all(not x['target_religion'] or x['target_religion'] in valid_religions for x in religions.values())
    assert {k:int(x['centipersons']) for k,x in cultures.items()} == {k:n for k,n in summary['culture_centipersons'].items() if n}
    assert {k:int(x['centipersons']) for k,x in religions.items()} == {k:n for k,n in summary['religion_centipersons'].items() if n}
    expected_ready, expected_pending = Counter(), Counter()
    for x in rows(stage/'province_population_draft.csv'):
        c = cultures[x['source_culture']]['target_culture']; religion = religions[x['source_religion']]['target_religion']; n = int(x['centipersons'])
        migrant=migrant_lookup.get((x['source_culture'],x['target_state']))
        if migrant:c=migrant;migrant_totals[c]+=n
        if c and religion:
            expected_ready[x['target_state'],x['target_owner'],c,religion] += n
        else:
            expected_pending[x['target_state'],x['target_owner'],x['source_culture'],x['source_religion'],c,religion] += n
    assert dict(migrant_totals)=={entry['target']:entry['centipersons'] for entry in r.get('migrant_cultures',{}).get('cultures',[])}
    actual_ready, integer = {}, {}
    for x in rows(out/'resident_population_groups.csv'):
        key = x['state'],x['owner'],x['culture'],x['religion']
        assert key not in actual_ready
        actual_ready[key] = int(x['centipersons']); integer[key] = int(x['preview_integer_persons'])
        assert integer[key] in (actual_ready[key]//100, (actual_ready[key]+99)//100)
    actual_pending = {}
    for x in rows(out/'identity_pending_groups.csv'):
        key = tuple(x[k] for k in ('state','owner','source_culture','source_religion','target_culture','target_religion'))
        assert key not in actual_pending
        actual_pending[key] = int(x['centipersons'])
    assert dict(expected_ready) == actual_ready
    assert dict(expected_pending) == actual_pending
    budget_result=None
    if profile.get('culture_budget'):
        limits=profile['culture_budget']
        def read_assets(base,directory):
            return {k:fields(o) for p in (base/directory).glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
        game=Path('D:/Steam/steamapps/common/Victoria 3/game')
        resident=read_assets(out/'identity_assets','common/cultures')
        migrants=read_assets(out/'migrant_assets','common/cultures')
        native=read_assets(game,'common/cultures')
        political={c['target'] for c in load_json(Path(sr['political_run'])/'conversion_report.json')['custom_cultures']}
        resident_groups={k:v for k,v in read_assets(out/'identity_assets','common/discrimination_trait_groups').items() if k.startswith(('eu5_resident_','eu5_aggregate_','eu5_reviewed_'))}
        counts={'used_cultures':len({k[2] for k in actual_ready}),'resident_assets':len(resident),'migrant_assets':len(migrants),'political_assets':len(political),
            'resident_heritage_groups':sum(v['type']=='heritage' for v in resident_groups.values()),
            'resident_language_groups':sum(v['type']=='language' for v in resident_groups.values()),'population_groups':len(actual_ready),
            'effective_culture_definitions':len(native.keys()|resident.keys()|migrants.keys()|political)}
        assert set(limits)-{'policy'}=={'max_'+k for k in counts}
        for key,value in counts.items():
            assert type(limits['max_'+key]) is int and 0<=value<=limits['max_'+key], ('Culture budget exceeded',key,value)
        assert r['culture_budget']['counts']==counts and r['culture_budget']['limits']==limits
        manifest={x['source']:x for x in r['custom_resident_cultures']['cultures']}
        policy=profile['global_culture_policy'];assert r['global_culture_policy']==policy
        seen=set()
        for aggregate in policy['aggregates']:
            rep=aggregate['representative'];members=aggregate['members']
            assert not seen.intersection(members);seen.update(members)
            assert rep in members and rep in manifest
            config=profile['custom_resident_cultures'][rep]
            assert manifest[rep]['heritage_group']==config['heritage_group']
            assert manifest[rep]['aggregate_members']==config.get('aggregate_members',[])
            if len(members)>1:
                assert config['aggregate_members']==members
                if config.get('reviewed_language'):
                    assert not manifest[rep]['aggregate_language']
                    assert manifest[rep]['reviewed_language']==config['reviewed_language']
                    assert config['reviewed_language']['sources'] and config['reviewed_language']['basis']
                else:
                    assert manifest[rep]['aggregate_language'] is True
                assert manifest[rep]['labels']==config['display_labels']==aggregate['labels']
            for c in members:assert cultures[c]['target_culture']==manifest[rep]['target']
        assert seen|set(profile['culture_compaction'])==set(profile['custom_resident_cultures'])
        assert len(manifest)==len(policy['aggregates'])
        catalogue=list(rows(out/'active_culture_catalog.csv'))
        assert len(catalogue)==counts['used_cultures']==len({x['culture'] for x in catalogue})
        population=Counter();group_counts=Counter()
        for k,n in actual_ready.items():population[k[2]]+=n;group_counts[k[2]]+=1
        expected_sources={c:{s for s,x in cultures.items() if x['target_culture']==c} for c in population}
        for x in r['migrant_cultures']['cultures']:expected_sources[x['target']]={x['source']}
        for x in catalogue:
            c=x['culture'];assert int(x['centipersons'])==population[c] and int(x['population_groups'])==group_counts[c]
            assert set(x['source_identities'].split('|'))==expected_sources[c] and int(x['source_identity_count'])==len(expected_sources[c])
        budget_result={'status':'passed','counts':counts,'aggregate_membership_and_catalog_verified':True}
    parsed = {}
    for state, obj in objects(fields(root((out/'population_history_preview.txt').read_text(encoding='utf-8')))['POPS']):
        for owner, sub in objects(obj):
            for operation, pop in objects(sub):
                assert operation == 'create_pop'
                f = fields(pop); key = state.removeprefix('s:'),owner.removeprefix('region_state:'),f['culture'],f['religion']
                assert key not in parsed and int(f['size']) > 0
                parsed[key] = int(f['size'])
    assert parsed == {k:n for k,n in integer.items() if n}
    assert sum(integer.values()) == (sum(actual_ready.values())+50)//100 == r['preview_integer_persons']
    assert sum(actual_ready.values()) == r['ready_located_centipersons']
    assert sum(actual_pending.values()) == r['identity_pending_located_centipersons']
    assert sum(actual_ready.values())+sum(actual_pending.values())+sr['unmapped_centipersons'] == summary['world_centipersons']
    result = {'status':'passed','culture_and_religion_totals_preserved':True,'all_located_residents_ready_or_pending':True,
              'preview_matches_group_ledger':True,'global_rounding_error_at_most_half_person':True,
              'religion_definitions_icons_heritages_localization_validated':True,
              'reviewed_culture_alias_definitions_validated':True,
              'all_resolved_culture_assets_validated':True,
              'used_target_cultures':len({key[2] for key in actual_ready}),
              'culture_budget':budget_result,
              'base_target_cultures_checked':culture_assets['used_target_cultures'],
              'migrant_cultures_checked':len(migrant_totals),'migrant_centipersons':sum(migrant_totals.values()),
              'world_centipersons':summary['world_centipersons'],'deployment_ready':False}
    (out/'culture_asset_verification.json').write_text(json.dumps(culture_assets,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();print(json.dumps(verify(a.source,a.out)))
