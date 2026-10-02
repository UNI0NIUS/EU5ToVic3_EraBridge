"""Read the reusable identity bundle independently of the package builder."""
import argparse
from pathlib import Path
import re
from PIL import Image
from converter_project import read,write
from converter_pipeline import validate_rules
from economy_model import definitions
from build_m3_world import load_localization
from converter_identity_policy import dated_mapping


def verify_output(run, game):
    import csv
    from collections import Counter
    from package_m4_population_test import parse_pops
    from pdx_text import root,Object
    from build_m2_prototype import objects,strings
    run,game=Path(run),Path(game)
    def rows(p):
        with p.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
    context=read(run/'fresh_context.json');mod=run/'complete/eu5_converted'
    rules=run/'rules'
    if (rules/'identity_policy.json').exists():
        source_date=read(run/'source/audit/import_report.json')['date']
        assert context['mapping']==dated_mapping(read(rules/'culture_mapping.json'),read(rules/'identity_policy.json'),source_date),'Wrong rule revision or date selection'
    if not mod.exists():mod=Path(context['mod_directory'])
    demo=run/'demographic';source=rows(run/'source/population/source_populations.csv')
    allocated=Counter()
    for r in rows(demo/'staging/province_population_draft.csv'):
        assert r['target_culture']==context['mapping'][r['source_culture']],'Resident mapping differs from selected policy'
        allocated[r['source_pop_id'],r['source_culture'],r['source_religion']]+=int(r['centipersons'])
    expected=Counter()
    for r in source:expected[r['pop_id'],r['source_culture'],r['source_religion']]+=int(r['centipersons'])
    assert +allocated==+expected,'Per-source population, culture or religion changed'
    groups=Counter()
    for filename,col in [('demographics/resident_population_groups.csv','preview_integer_persons'),('template_fallback/template_population_groups.csv','persons')]:
        for r in rows(demo/filename):groups[tuple(r[k] for k in ('state','owner','culture','religion'))]+=int(r[col])
    actual=Counter(parse_pops(mod/'common/history/pops/00_eu5_world.txt'))
    assert +actual==+groups,'Population readback differs from conversion ledger'
    owners={};homes=set()
    for s,obj in objects(root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['STATES']):
        state=s[2:];owners[state]={}
        for op,v in obj.entries():
            if op=='add_homeland':homes.add((state,v[3:]))
            if op=='create_state':
                f=v.fields()
                for p in strings(f['owned_provinces']):owners[state][p]=f['country'][2:]
    assert owners==read(Path(context['political_run'])/'province_owners.json'),'Political borders changed'
    totals=Counter();migrants=Counter()
    for (s,t,c,r),n in actual.items():
        totals[s]+=n
        if c.startswith('eu5_migrant_'):migrants[s,c]+=n
    for s,c in homes:
        if c.startswith('eu5_migrant_'):assert migrants[s,c]*2>totals[s],('Migrant homeland below majority',s,c)
    reasons=read(run/'homeland_manifest.json')
    assert all((r['state'],r['culture']) in homes for r in reasons)
    flags=0
    if (run/'dynamic_identity_manifest.json').exists():
        from m5_dynamic_identity import entries
        from verify_dynamic_identity import evaluate
        audit=read(run/'dynamic_identity_manifest.json')
        scripts={k:v for base in (game,mod) for p in (base/'common/scripted_triggers').glob('*.txt') for k,v in entries(p).items()}
        for tag,r in audit['countries'].items():
            if not r['source_coa']:continue
            ctx=dict(laws=set(r['initial_laws'].values()),ideology=r['initial_ideology'])
            for subject in (False,True):
                ctx['subject']=subject
                assert evaluate(scripts[r['opening_flag_guard']],ctx,scripts) is True,tag
            flags+=1
    return dict(status='passed',source_pop_groups=len(+expected),source_centipersons=sum(expected.values()),output_people=sum(actual.values()),political_provinces=sum(map(len,owners.values())),historical_and_migrant_evidence_pairs=len({(r['state'],r['culture']) for r in reasons}),status_independent_flag_guards=flags,runtime_verified=False)


def verify(rules,game,eu5):
    rules,game,eu5=map(Path,(rules,game,eu5))
    validate_rules(rules/'manifest.json',game,eu5)
    assets=rules/'assets';defs={}
    for kind in ('cultures','religions','discrimination_traits','discrimination_trait_groups'):
        defs[kind]=definitions(game/'common'/kind);defs[kind].update(definitions(assets/'common'/kind))
    for key,spec in defs['cultures'].items():
        for field in ('heritage','language'):
            if spec.get(field) not in defs['discrimination_traits']:raise ValueError('Missing '+field+': '+key)
        if spec.get('religion') not in defs['religions']:raise ValueError('Missing religion: '+key)
    for key,spec in defs['discrimination_traits'].items():
        if 'trait_group' in spec and spec['trait_group'] not in defs['discrimination_trait_groups']:raise ValueError('Missing trait group: '+key)
    keys=set().union(*(set(d) for d in defs.values()))
    marker=re.compile(r'审核|审查|映射|暂定|待审|reviewed mapping|provisional',re.I)
    for lang in ('english','simp_chinese'):
        loc=load_localization(game/'localization'/lang);loc.update(load_localization(assets/'localization/replace'/lang))
        missing=keys-set(loc)
        if missing:raise ValueError('Missing labels: '+str(sorted(missing)))
        if any(marker.search(loc[k]) for k in keys):raise ValueError('Workflow labels leaked into game')
        exported=load_localization(assets/'localization/replace'/lang)
        if set(exported)-keys:raise ValueError('Non-identity localization included')
    mapping=read(rules/'culture_mapping.json');policy=read(rules/'identity_policy.json')
    for date in ('1337.1.1','1780.1.1','1836.1.1'):
        if set(dated_mapping(mapping,policy,date).values())-set(defs['cultures']):raise ValueError('Missing dated mapping asset')
    icons=[]
    for p in (assets/'gfx/interface/icons/religion_icons').glob('eu5_religion_*.dds'):
        with Image.open(p) as im:
            if im.size!=(256,256):raise ValueError('Wrong icon size: '+p.name)
            box=im.convert('RGBA').getchannel('A').getbbox()
            if not box or abs((box[0]+box[2])/2-128)>1 or abs((box[1]+box[3])/2-128)>1:raise ValueError('Off-center icon: '+p.name)
        icons.append(p.name)
    if (assets/'common/history').exists():raise ValueError('Campaign history copied into reusable assets')
    return dict(status='passed',mapping_count=len(mapping),asset_definitions={k:len(v) for k,v in defs.items()},centered_icons=len(icons),labels_checked=len(keys)*2,history_free=True,runtime_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('rules','game','eu5','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=verify(a.rules,a.game,a.eu5);write(a.output,result);print(result)
