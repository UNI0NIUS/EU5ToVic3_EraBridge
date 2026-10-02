"""Explicit resident identity mapping and auditable V3 population-group preview."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from build_m2_prototype import objects, strings
from build_m3_world import block, load_localization
from m3_world import digest, fields, load_json
from pdx_text import root
from m4_religions import write_custom_religions
from m4_cultures import checked_source, write_custom_cultures
from m4_migrant_cultures import build_migrants
from m4_culture_budget import check_and_catalog


def read_definitions(directory):
    result = {}
    for p in sorted(directory.glob('*.txt')):
        for key, obj in objects(root(p.read_text(encoding='utf-8-sig'))):
            if key in result:
                raise ValueError('Duplicate game definition: '+key)
            result[key] = fields(obj)
    return result


def culture_resolution(source, definition, existing, profile, valid):
    if existing:
        target, method = existing
        if target not in valid:
            raise ValueError('Undefined existing culture: '+target)
        return target, method, 'Previously resolved in the political population staging.'
    if source in profile.get('culture_compaction',{}):
        config=profile['culture_compaction'][source]
        checked_source(source,definition,config)
        if config['target'] not in valid:raise ValueError('Undefined compact culture: '+source)
        return config['target'],'explicit_v3_granularity_compaction',config['reason']
    if source in profile.get('custom_resident_cultures',{}):
        config = profile['custom_resident_cultures'][source]
        checked_source(source,definition,config)
        target = 'eu5_resident_'+source
        if target not in valid:raise ValueError('Custom resident definition missing: '+source)
        return target, 'preserved_resident_custom_identity', config['reason']
    if source in profile['culture_aliases']:
        target = profile['culture_aliases'][source]
        if target not in valid:
            raise ValueError('Undefined explicit culture: '+target)
        check = profile.get('culture_alias_checks',{}).get(source)
        if check:
            groups = strings(definition['culture_groups']) if 'culture_groups' in definition else []
            if target != check['target'] or definition.get('language') != check['source_language'] or set(groups) != set(check['source_groups']):
                raise ValueError('Reviewed source culture definition changed: '+source)
        return target, 'resident_explicit_alias', check['reason'] if check else profile['culture_alias_basis']
    if source in profile['culture_rule_exclusions']:
        return '', 'review_pending', 'Protected identity; excluded from broad language/group merges.'
    groups = strings(definition['culture_groups']) if 'culture_groups' in definition else []
    matches = [r for r in profile['culture_rules'] if r['group'] in groups and definition.get('language') in r['languages']]
    if len({r['target'] for r in matches}) > 1:
        raise ValueError('Conflicting culture rules: '+source)
    if matches:
        rule = matches[0]
        if rule['target'] not in valid:
            raise ValueError('Undefined rule target: '+rule['target'])
        return rule['target'], rule['id'], rule['reason']
    return '', 'review_pending', 'No explicit resident identity resolution.'


def religion_resolution(source, definition, old_profile, profile, valid):
    if source in profile.get('custom_religions',{}):
        target, method, reason = 'eu5_religion_'+source, 'preserved_custom_religion', profile['custom_religions'][source]['reason']
    elif source in profile['religion_aliases']:
        target, method, reason = profile['religion_aliases'][source], 'resident_explicit_alias', 'Explicit source/target religion identity alias.'
    elif source in old_profile['religion_aliases']:
        target, method, reason = old_profile['religion_aliases'][source], 'political_explicit_alias', 'Previously explicit religion correspondence.'
    elif source in valid:
        target, method, reason = source, 'same_key', 'Same installed religion key.'
    elif definition.get('group') in profile['religion_group_aliases']:
        target, method, reason = profile['religion_group_aliases'][definition['group']], 'explicit_group_granularity', profile['religion_group_basis']
    else:
        return '', 'review_pending', 'No explicit correspondence; source identity retained.'
    if target not in valid:
        raise ValueError('Undefined target religion: '+target)
    return target, method, reason


def round_groups(groups):
    """Single largest-remainder conversion of centipersons to whole people."""
    if any(type(n) is not int or n < 0 for n in groups.values()):
        raise ValueError('Invalid centiperson count')
    result = {k: n//100 for k, n in groups.items()}
    target = (sum(groups.values())+50)//100
    order = sorted(groups, key=lambda k: (-(groups[k] % 100), k))
    for key in order[:target-sum(result.values())]:
        result[key] += 1
    return result


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def write_csv(path, header, records):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(header); writer.writerows(records)


def build(stage, source, out, game, eu5, profile_path, political_profile_path):
    if out.exists():
        raise ValueError('Refusing to overwrite demographic output')
    out.mkdir(parents=True)
    sr = load_json(stage/'staging_report.json'); summary = load_json(source/'source_summary.json')
    profile = load_json(profile_path); old = load_json(political_profile_path)
    if profile.get('schema') != 1 or profile['target_version'] != old['target_version']:
        raise ValueError('Demographic configuration version mismatch')
    if sr['profile_sha256'] != digest(political_profile_path) or sr['source_sha256'] != summary['source_sha256']:
        raise ValueError('Demographic input provenance mismatch')
    for name, sha in sr['files_sha256'].items():
        if digest(stage/name) != sha:
            raise ValueError('Population stage changed: '+name)
    source_cultures = read_definitions(eu5/'in_game/common/cultures')
    source_religions = read_definitions(eu5/'in_game/common/religions')
    target_culture_defs = read_definitions(game/'common/cultures')
    target_cultures = set(target_culture_defs)
    political = load_json(Path(sr['political_run'])/'conversion_report.json')
    target_cultures.update(c['target'] for c in political['custom_cultures'])
    target_religions = set(read_definitions(game/'common/religions'))
    custom_religions = write_custom_religions(out/'identity_assets',game,eu5,source_religions,profile)
    custom_cultures = write_custom_cultures(out/'identity_assets',game,eu5,source_cultures,profile,target_cultures)
    generated_candidates=[c for c in custom_cultures['cultures'] if c.get('review_status')=='generated_preservation_candidate_not_historically_reviewed']
    write_csv(out/'culture_asset_review_queue.csv',['source_culture','name','centipersons','target_culture','template','heritage_group','language','language_group','review_status','limitation'],
              ((c['source'],c['labels']['simp_chinese'],sum(summary['culture_centipersons'].get(member,0) for member in (c.get('aggregate_members') or [c['source']])),c['target'],c['template'],c['heritage_group'],c['language'],c['language_group'],c['review_status'],c['limitation']) for c in sorted(generated_candidates,key=lambda c:-sum(summary['culture_centipersons'].get(member,0) for member in (c.get('aggregate_members') or [c['source']])))))
    target_cultures.update(c['target'] for c in custom_cultures['cultures'])
    effective_cultures={**target_culture_defs,**read_definitions(out/'identity_assets/common/cultures')}
    for c,rule in profile.get('culture_compaction',{}).items():
        checked_source(c,source_cultures[c],rule)
        native=effective_cultures[rule['target']]
        if native['heritage']!=rule['target_heritage'] or native['language']!=rule['target_language']:
            raise ValueError('Compaction target definition changed: '+c)
    # Count custom identities only after their concrete asset definitions exist.
    target_religions.update(r['target'] for r in custom_religions['religions'])
    for c, t in profile['culture_aliases'].items():
        if c not in source_cultures or t not in target_cultures:
            raise ValueError('Invalid explicit culture pair: '+c+' -> '+t)
    for c, check in profile.get('culture_alias_checks',{}).items():
        target = target_culture_defs[check['target']]
        if target['heritage'] != check['target_heritage'] or target['language'] != check['target_language']:
            raise ValueError('Reviewed target culture definition changed: '+c)
    for lang in ('english','simp_chinese'):
        source_labels = load_localization(eu5/'main_menu/localization'/lang)
        target_labels = load_localization(game/'localization'/lang)
        for c, check in profile.get('culture_alias_checks',{}).items():
            if source_labels.get(c) != check['labels']['source'][lang] or target_labels.get(check['target']) != check['labels']['target'][lang]:
                raise ValueError('Reviewed culture label changed: '+c+'/'+lang)
    localization = load_localization(eu5/'main_menu/localization/simp_chinese')
    existing = {r['source_culture']: r for r in rows(stage/'culture_review_queue.csv')}
    cultures, religions = {}, {}
    for c, n in summary['culture_centipersons'].items():
        if not n: continue
        if c not in source_cultures:
            raise ValueError('Source culture definition missing: '+c)
        previous = existing[c]
        resolved = (previous['approved_target'], previous['method']) if previous['approved_target'] else None
        cultures[c] = culture_resolution(c, source_cultures[c], resolved, profile, target_cultures)
    for r, n in summary['religion_centipersons'].items():
        if not n: continue
        if r not in source_religions:
            raise ValueError('Source religion definition missing: '+r)
        religions[r] = religion_resolution(r, source_religions[r], old, profile, target_religions)
    write_csv(out/'resident_culture_crosswalk.csv', ['source_culture','name','centipersons','target_culture','method','reason'],
              ((c,localization.get(c,c),summary['culture_centipersons'][c],*cultures[c]) for c in sorted(cultures,key=lambda c:-summary['culture_centipersons'][c])))
    write_csv(out/'resident_religion_crosswalk.csv', ['source_religion','name','centipersons','source_group','target_religion','method','reason'],
              ((r,localization.get(r,r),summary['religion_centipersons'][r],source_religions[r].get('group',''),*religions[r]) for r in sorted(religions,key=lambda r:-summary['religion_centipersons'][r])))
    migrant_lookup,migrant_report=build_migrants(out/'migrant_assets',stage,game,eu5,profile,source_cultures,cultures,target_cultures)
    ready, pending = Counter(), Counter()
    for row in rows(stage/'province_population_draft.csv'):
        n = int(row['centipersons']); c = cultures[row['source_culture']][0]; r = religions[row['source_religion']][0]
        c=migrant_lookup.get((row['source_culture'],row['target_state']),c)
        if c and r:
            ready[row['target_state'],row['target_owner'],c,r] += n
        else:
            pending[row['target_state'],row['target_owner'],row['source_culture'],row['source_religion'],c,r] += n
    assert sum(ready.values())+sum(pending.values()) == sr['allocated_centipersons']
    budget=check_and_catalog(out,game,political,profile,ready,cultures,migrant_report,write_csv)
    rounded = round_groups(ready)
    write_csv(out/'resident_population_groups.csv', ['state','owner','culture','religion','centipersons','preview_integer_persons'],
              ((*k,n,rounded[k]) for k,n in sorted(ready.items())))
    write_csv(out/'identity_pending_groups.csv', ['state','owner','source_culture','source_religion','target_culture','target_religion','centipersons'],
              ((*k,n) for k,n in sorted(pending.items())))
    by_state = defaultdict(lambda: defaultdict(list))
    for (state,owner,c,r),n in sorted(rounded.items()):
        if n:
            by_state[state][owner].append(block('create_pop',f'culture = {c}\nreligion = {r}\nsize = {n}'))
    text = '# PARTIAL REVIEW PREVIEW. Do not install: pending identities and geometry are excluded and recorded separately.\n'
    text += block('POPS',''.join(block('s:'+s,''.join(block('region_state:'+t,''.join(pops)) for t,pops in sorted(owners.items()))) for s,owners in sorted(by_state.items())))
    (out/'population_history_preview.txt').write_text(text, encoding='utf-8')
    result = {'schema':1, 'status':'resident_identity_and_population_preview_not_installed',
              'source_sha256':sr['source_sha256'], 'stage':str(stage.resolve()), 'stage_report_sha256':digest(stage/'staging_report.json'),
              'profile_sha256':digest(profile_path), 'profile_path':str(profile_path.resolve()), 'political_profile_sha256':digest(political_profile_path),
              'active_cultures':len(cultures), 'resolved_cultures':sum(bool(v[0]) for v in cultures.values()),
              'culture_alias_checks':profile.get('culture_alias_checks',{}),
              'culture_compaction':profile.get('culture_compaction',{}),
              'culture_budget':budget,
              'global_culture_policy':profile.get('global_culture_policy'),
              'pending_culture_centipersons':sum(summary['culture_centipersons'][c] for c,v in cultures.items() if not v[0]),
              'active_religions':len(religions), 'resolved_religions':sum(bool(v[0]) for v in religions.values()),
              'custom_religions':custom_religions,
              'custom_resident_cultures':custom_cultures,
              'generated_provisional_cultures':len(generated_candidates),
              'generated_provisional_culture_centipersons':sum(sum(summary['culture_centipersons'].get(member,0) for member in (c.get('aggregate_members') or [c['source']])) for c in generated_candidates),
              'cultural_policy_review_complete':False,
              'migrant_cultures':migrant_report,
              'pending_religion_centipersons':sum(summary['religion_centipersons'][r] for r,v in religions.items() if not v[0]),
              'world_centipersons':sr['world_centipersons'], 'geometry_pending_centipersons':sr['unmapped_centipersons'],
              'identity_pending_located_centipersons':sum(pending.values()), 'ready_located_centipersons':sum(ready.values()),
              'population_groups':len(ready), 'preview_integer_persons':sum(rounded.values()),
              'preview_rounding_delta_centipersons':sum(rounded.values())*100-sum(ready.values()),
              'deployment_ready':False,
              'limitations':['Preview covers resolved, located residents only; excludes neither by silent loss nor by replacing them with the owner identity.',
                             'Unresolved source identities remain in crosswalks; missing geography remains in stage ledger.',
                             'Homelands, vanilla fallback population policy, economic capacity and custom minority definitions still require work.'],
              'game_definition_sha256':{str(p):digest(p) for directory in (eu5/'in_game/common/cultures',eu5/'in_game/common/religions',game/'common/cultures',game/'common/religions') for p in sorted(directory.glob('*.txt'))}}
    result['files_sha256']={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()}
    (out/'demographics_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
