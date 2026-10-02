"""Configured origin + settlement-region identities; never inferred from rulers."""
from collections import Counter
import json
import re
from pathlib import Path

from build_m2_prototype import objects, strings
from build_m3_world import block, load_localization
from m3_world import digest, fields
from m4_cultures import checked_source
from m4_religions import definitions
from pdx_text import root
from verify_m4_population import rows


def cohort_states(config, regions):
    macro={}
    for key,entry in config.get('macro_regions',{}).items():
        for region in entry['regions']:
            if region in macro:raise ValueError('Overlapping migrant macro regions: '+region)
            macro[region]=key
    scopes={}
    for kind,keys in config['regions'].items():
        scopes[kind]={}
        for region in keys:
            for state in strings(regions[region]['states']):
                if state in scopes[kind]:raise ValueError('Overlapping migrant regions: '+state)
                if macro and region not in macro:raise ValueError('Missing migrant macro region: '+region)
                scopes[kind][state]=macro.get(region,region)
    return scopes


def build_migrants(out, stage, game, eu5, profile, source_defs, base_cultures, reserved):
    config=profile.get('migrant_cultures')
    if not config:return {}, {'cultures':[], 'inputs_sha256':{}, 'config':None}
    regions=definitions(game/'common/strategic_regions');scopes=cohort_states(config,regions)
    templates={k:o for p in sorted((game/'common/cultures').glob('*.txt')) for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    traits=definitions(game/'common/discrimination_traits');groups=definitions(game/'common/discrimination_trait_groups')
    inputs={str(p):digest(p) for directory in (game/'common/strategic_regions',game/'common/cultures',game/'common/discrimination_traits',game/'common/discrimination_trait_groups',eu5/'in_game/common/cultures') for p in sorted(directory.glob('*.txt'))}
    for c,rule in config['sources'].items():
        checked_source(c,source_defs[c],rule)
        if base_cultures[c][0]!=rule['template']:raise ValueError('Migrant origin resolution changed: '+c)
        native=fields(templates[rule['template']])
        if native['heritage']!=rule['expected_heritage'] or native['language']!=rule['expected_language']:raise ValueError('Migrant origin template changed: '+c)
    counts=Counter()
    for r in rows(stage/'province_population_draft.csv'):
        rule=config['sources'].get(r['source_culture'])
        if rule:
            region=scopes[rule['kind']].get(r['target_state'])
            if region:counts[r['source_culture'],region]+=int(r['centipersons'])
    source_locs={l:load_localization(eu5/'main_menu/localization'/l) for l in ('english','simp_chinese')}
    target_locs={l:load_localization(game/'localization'/l) for l in source_locs}
    bodies={};new_traits={};labels={l:{} for l in source_locs};records=[];lookup={}
    for (source,region),amount in sorted(counts.items()):
        rule=config['sources'][source];key='eu5_migrant_'+source+'_'+region
        if key in reserved:raise ValueError('Migrant culture collision: '+key)
        heritage=('heritage_african_diaspora' if rule['kind']=='african_diaspora' else 'eu5_migrant_heritage_'+region)
        if rule['kind']=='african_diaspora':
            assert traits[heritage]['trait_group']=='heritage_group_african'
        else:
            assert heritage not in traits and groups['heritage_group_european']['type']=='heritage'
            new_traits[heritage]='type = heritage\ntrait_group = heritage_group_european'
        body,n=re.subn(r'\bheritage\s*=\s*\w+','heritage = '+heritage,templates[rule['template']].text());assert n==1
        bodies[key]=body
        for lang in labels:
            a=source_locs[lang][source]
            b=config['macro_regions'][region]['labels'][lang] if config.get('macro_regions') else target_locs[lang][region]
            labels[lang][key]=(b+'·'+a+'裔' if lang=='simp_chinese' else a+' — '+b)
            if heritage in new_traits:labels[lang][heritage]=(b+'移民传承' if lang=='simp_chinese' else b+' Settler Heritage')
        states=sorted(s for s,r in scopes[rule['kind']].items() if r==region)
        for state in states:lookup[source,state]=key
        records.append({'source':source,'region':region,'states':states,'target':key,'template':rule['template'],'kind':rule['kind'],
                        'heritage':heritage,'language':rule['expected_language'],'centipersons':amount,
                        'labels':{lang:labels[lang][key] for lang in labels},
                        'limitation':'Origin + present settlement region is a user-selected conversion policy, not a measured migration generation or assimilation history. Source languages and religions remain; no enslaved/free history, owner identity, new people or homelands are inferred. Template names, portraits and traditions are provisional.'})
    for rel,data in [('common/cultures/zz_eu5_migrant_cultures.txt',bodies),('common/discrimination_traits/zz_eu5_migrant_heritages.txt',new_traits)]:
        path=out/rel;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(block(k,v) for k,v in sorted(data.items())),encoding='utf-8-sig')
    for lang,data in labels.items():
        path=out/'localization'/lang/('eu5_migrant_cultures_l_'+lang+'.yml');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('l_'+lang+':\n'+''.join(' '+k+':0 '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in sorted(data.items())),encoding='utf-8-sig')
    return lookup, {'cultures':records,'inputs_sha256':inputs,'config':config}


def verify_migrants(out, game, report, profile, base_cultures, valid_religions):
    """Independent asset/reference checks and source/state rule reconstruction."""
    from verify_m4_culture_assets import validate_culture
    manifest=report.get('migrant_cultures',{'cultures':[],'inputs_sha256':{},'config':None})
    assert manifest['config']==profile.get('migrant_cultures')
    if not manifest['config']:return {}
    for p,sha in manifest['inputs_sha256'].items():assert digest(Path(p))==sha
    native=definitions(game/'common/cultures');traits=definitions(game/'common/discrimination_traits');groups=definitions(game/'common/discrimination_trait_groups')
    actual=definitions(out/'common/cultures');added_traits=definitions(out/'common/discrimination_traits')
    assert not actual.keys()&native.keys() and not added_traits.keys()&traits.keys()
    traits.update(added_traits)
    records={r['target']:r for r in manifest['cultures']};assert actual.keys()==records.keys()
    regions=definitions(game/'common/strategic_regions');config=manifest['config']
    source_defs={k:fields(o) for p in manifest['inputs_sha256'] if 'Europa Universalis V' in p for k,o in objects(root(Path(p).read_text(encoding='utf-8-sig')))}
    for c,rule in config['sources'].items():
        sf=source_defs[c];assert sf['language']==rule['source_language']
        assert set(strings(sf['culture_groups']) if 'culture_groups' in sf else [])==set(rule['source_groups'])
        assert base_cultures[c]['target_culture']==rule['template']
        assert native[rule['template']]['language']==rule['expected_language'] and native[rule['template']]['heritage']==rule['expected_heritage']
    locs={l:{**load_localization(game/'localization'/l),**load_localization(out/'localization'/l)} for l in ('english','simp_chinese')}
    lookup={};expected_traits=set()
    for key,entry in records.items():
        source=entry['source'];rule=config['sources'][source];region=entry['region']
        selectors=config['macro_regions'][region]['regions'] if config.get('macro_regions') else [region]
        selectors=[s for s in selectors if s in config['regions'][rule['kind']]]
        assert selectors
        assert entry['states']==sorted(s for selector in selectors for s in strings(regions[selector]['states']))
        assert key=='eu5_migrant_'+source+'_'+region
        heritage='heritage_african_diaspora' if rule['kind']=='african_diaspora' else 'eu5_migrant_heritage_'+region
        assert actual[key]['heritage']==entry['heritage']==heritage
        if rule['kind']!='african_diaspora':
            expected_traits.add(heritage);assert traits[heritage]['trait_group']=='heritage_group_european'
        else:assert traits[heritage]['trait_group']=='heritage_group_african'
        assert actual[key]['language']==entry['language']==rule['expected_language']
        for field,value in native[rule['template']].items():
            if field in (None,'heritage'):continue
            other=actual[key][field]
            assert (value.text() if hasattr(value,'text') else value)==(other.text() if hasattr(other,'text') else other)
        validate_culture(key,actual[key],traits,groups,valid_religions,locs)
        for lang,loc in locs.items():assert loc[key]==entry['labels'][lang]
        for state in entry['states']:
            assert (source,state) not in lookup;lookup[source,state]=key
    assert set(added_traits)==expected_traits
    # Reconstruct all configured selectors, including a missing emitted cohort.
    for source,rule in config['sources'].items():
        for region in config['regions'][rule['kind']]:
            macro=[k for k,v in config.get('macro_regions',{}).items() if region in v['regions']]
            assert len(macro)==(1 if config.get('macro_regions') else 0)
            target_region=macro[0] if macro else region
            for state in strings(regions[region]['states']):
                lookup[source,state]='eu5_migrant_'+source+'_'+target_region
    return lookup
