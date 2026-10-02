"""Reconstruct homelands from pinned setup and actual POP output, not audit decisions."""
import argparse,json,re
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
import numpy as np
from build_m2_prototype import objects
from m3_world import load_json,digest
from pdx_text import root,Object
from package_m4_population_test import parse_pops
from m5_culture_geography import rows,lab,read_color,COLOR,CULTURE_FILES,STATE_FILE,GAME,EU5

def verify(package):
    report=load_json(package/'package_report.json');audit=load_json(package/'culture_geography.json');policy=audit['policy']
    assert digest(package/'culture_geography.json')==report['culture_geography_sha256']
    for p,sha in report['input_sha256'].items():assert digest(Path(p))==sha,p
    base=Path(report['prior_package']);before=load_json(base/'package_report.json');old=Path(before['mod_directory']);mod=Path(report['mod_directory'])
    assert set(report['output_sha256'])==set(before['output_sha256'])
    for p,sha in report['output_sha256'].items():assert digest(mod/p)==sha,p
    allowed={*CULTURE_FILES,STATE_FILE,'.metadata/metadata.json'}
    for p,sha in before['output_sha256'].items():
        assert digest(old/p)==sha,p
        if p not in allowed:assert digest(mod/p)==sha,p
    keys=set();rgb={}
    for rel in CULTURE_FILES:
        a=dict(objects(root((old/rel).read_text(encoding='utf-8-sig'))));b=dict(objects(root((mod/rel).read_text(encoding='utf-8-sig'))))
        assert a.keys()==b.keys()
        for c in a:
            assert c not in keys;keys.add(c)
            assert COLOR.sub('COLOR',a[c].text())==COLOR.sub('COLOR',b[c].text())
            rgb[c]=read_color(b[c].text());assert rgb[c]==audit['colors'][c]['rgb']
    assert len(keys)==140 and keys==audit['homelands'].keys()==audit['colors'].keys()
    native={c:read_color(o.text()) for p in (GAME/'common/cultures').glob('*.txt') for c,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    allkeys=list(native)+sorted(keys);labs=lab([native.get(c,rgb.get(c)) for c in allkeys]);minimum=999
    for c in keys:
        i=allkeys.index(c);dist=np.linalg.norm(labs-labs[i],axis=1);dist[i]=999
        minimum=min(minimum,float(dist.min()));assert dist.min()>=policy['colors']['minimum_delta_e_76']-0.005
    actualpops=parse_pops(mod/'common/history/pops/00_eu5_world.txt');totals=Counter();amounts=Counter()
    for (s,owner,c,religion),n in actualpops.items():totals[s]+=n;amounts[s,c]+=n
    migrants={c for c in keys if c.startswith('eu5_migrant_')};ordinary=keys-migrants
    expected=defaultdict(set)
    for (s,c),n in amounts.items():
        if c in keys and n*2>totals[s]:expected[c].add(s)
    d=Path(audit['demographic_run']);links=defaultdict(set)
    for r in rows(d/'staging/province_population_draft.csv'):links[r['source_location']].add(r['target_state'])
    cross={r['source_culture']:r['target_culture'] for r in rows(d/'demographics/resident_culture_crosswalk.csv')}
    # Separate traversal with exact rational comparisons, including denominator
    # cultures absent from the crosswalk and locations split across target states.
    best={};evidence=set();unmapped=set()
    doc=root((EU5/'main_menu/setup/start/06_pops.txt').read_text(encoding='utf-8-sig')).fields()['locations']
    for loc,obj in objects(doc):
        population=Counter()
        for key,value in obj.entries():
            if key!='define_pop':continue
            f=value.fields();population[cross.get(f['culture'],f['culture'])]+=Decimal(f['size'])*100000
        total=sum(population.values())
        for c,n in population.items():
            if c not in ordinary or not n or not total:continue
            if links.get(loc) and (c not in best or n*best[c][2]>best[c][1]*total):best[c]=(loc,n,total)
            if n*5>=total:
                if links.get(loc):
                    expected[c].update(links[loc])
                    for state in links[loc]:evidence.add((c,state,loc,int(n),int(total)))
                else:unmapped.add((c,loc))
    for c in ordinary:
        if not expected[c]:
            assert c in policy['dispersed_exceptions'],c
            if policy['dispersed_policy']=='strongest_historical_location':expected[c].add(sorted(links[best[c][0]])[0])
    assert {c:set(audit['homelands'][c]) for c in keys}=={c:expected[c] for c in keys}
    assert {(r['culture'],r['location']) for r in audit['historical_anchors_without_mapping']}==unmapped
    actual_evidence=set()
    for r in audit['homeland_evidence']:
        for e in r['evidence']:
            if e['rule']=='1337_local_share_at_least_20_percent':actual_evidence.add((r['culture'],r['state'],e['location'],e['centipersons'],e['location_centipersons']))
    assert actual_evidence==evidence
    def states(path):return root(path.read_text(encoding='utf-8-sig')).fields()['STATES'].fields()
    oldstates=states(old/STATE_FILE);newstates=states(mod/STATE_FILE);assert oldstates.keys()==newstates.keys()
    found=defaultdict(set);preserved=0
    def canonical(entries):return [(k,v.text() if isinstance(v,Object) else v) for k,v in entries]
    for scope,obj in oldstates.items():
        prior=list(obj.entries());new=list(newstates[scope].entries())
        additions=[(k,v) for k,v in new if k=='add_homeland' and v.removeprefix('cu:') in keys]
        assert not any(k=='add_homeland' and v.removeprefix('cu:') in keys for k,v in prior)
        assert canonical(prior)==canonical([(k,v) for k,v in new if (k,v) not in additions])
        assert len(additions)==len(set(additions))
        preserved+=sum(k=='add_homeland' for k,v in prior)
        for k,v in additions:found[v[3:]].add(scope[2:])
    assert {c:found[c] for c in keys}=={c:expected[c] for c in keys}
    result={'status':'passed','custom_colors':len(keys),'minimum_delta_e_76_to_other_cultures':minimum,
            'homeland_pairs':sum(map(len,found.values())),'cultures_with_homelands':sum(bool(found[c]) for c in keys),
            'migrant_homeland_pairs':sum(len(found[c]) for c in migrants),'migrant_strict_majority_verified':True,
            'all_existing_homelands_preserved':preserved,'political_setup_and_all_other_fields_unchanged':True,
            'population_religion_literacy_economy_unchanged':True,'historical_anchor_evidence_reconstructed':len(evidence),
            'unmapped_historical_anchors':len(unmapped),'no_homeland':audit['no_homeland'],'runtime_verified':False}
    checked=load_json(base/'verification.json');checked.update(status='passed_static_runtime_pending',culture_geography=result,package_report_sha256=digest(package/'package_report.json'))
    (package/'verification.json').write_text(json.dumps(checked,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);a=p.parse_args();print(json.dumps(verify(a.package),ensure_ascii=True))
