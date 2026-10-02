"""Independent source and PDX readback for the bounded colonial-law patch."""
from collections import Counter
from pathlib import Path
import json
from types import SimpleNamespace

from pdx_text import root, Object
from extract_m3_politics import fields, sequence
from deploy_political_rules import countries
from complete_economy import active_laws
from economy_model import definitions
from economy_bureaucracy import institution_levels
from package_m4_population_test import effective, parse_pops, GAME
from package_m5_culture_refinement import files
from m3_world import digest

ROOT=Path(__file__).resolve().parents[1]
HISTORY='common/history/countries/00_eu5_world.txt'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def semantic(obj):
    return [(k,semantic(v) if isinstance(v,Object) else v) for k,v in obj.entries()]
def non_colonial(obj, lawdefs):
    result=[]
    for k,v in obj.entries():
        if k=='activate_law' and lawdefs[v.split(':')[-1]]['group']=='lawgroup_colonization':continue
        if k=='set_institution_investment_level' and fields(v)['institution']=='institution_colonial_affairs':continue
        result.append((k,semantic(v) if isinstance(v,Object) else v))
    return result


def frontier_evidence(mod,political,owner_path):
    owners=read(owner_path); flat={p:(s,t) for s,ps in owners.items() for p,t in ps.items()}
    cache=read(ROOT/'.local/m3/cache/tribal_land_edges.json')
    assert cache['sha256']==[digest(GAME/'map_data'/p) for p in ['provinces.png','adjacencies.csv','default.map']]
    edges=[('x'+a[1:].upper(),'x'+b[1:].upper()) for a,b in cache['edges']]
    state_history=fields(root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['STATES']
    homelands={s[2:]:{v.removeprefix('cu:') for k,v in body.entries() if k=='add_homeland'} for s,body in state_history.entries()}
    actual=effective(mod,'common/country_definitions')
    decentralized={t for t,c in political['countries'].items() if c['country_type']=='decentralized'}
    evidence={}
    for tag in ['RUS','MCH']:
        primary=sequence(actual[tag]['cultures']);owned={s for s,ps in owners.items() if tag in ps.values()}
        homes={s for s in owned if homelands[s].intersection(primary)}
        direct=set();broad=set()
        for a,b in edges:
            if a not in flat or b not in flat:continue
            for x,y in [(a,b),(b,a)]:
                s,t=flat[x];ss,tt=flat[y]
                if t==tag and tt in decentralized:direct.add((s,ss,tt))
                # Deliberately includes all parts of the home state region and explicit straits.
                # If even this broader screen is empty, we have no native frontier witness.
                if s in homes and tt in decentralized:broad.add((s,ss,tt))
        evidence[tag]=dict(primary_cultures=primary,owned_homeland_states=sorted(homes),
            direct_decentralized_borders=sorted(direct),broad_homeland_region_neighbours=sorted(broad),
            decision='retain_existing_law_no_native_frontier_witness' if not broad else 'requires_new_review',
            runtime_engine_evaluated=False,capital_route_evaluated=False)
        assert not broad, 'Frontier evidence changed; revisit the previously deferred proposal'
    return evidence


def verify(output):
    output=Path(output);report=read(output/'package_report.json');policy=read(output/'policy.snapshot.json')
    prior=Path(report['prior_package']);old=read(prior/'package_report.json')
    base=Path(old['mod_directory']);mod=Path(report['mod_directory'])
    oldfiles,newfiles=files(base),files(mod)
    assert oldfiles==old['output_sha256']
    assert newfiles==report['output_sha256']
    assert oldfiles.keys()==newfiles.keys()
    changed={p for p,h in newfiles.items() if oldfiles[p]!=h}
    assert changed=={HISTORY,'.metadata/metadata.json'}
    for p,h in report['input_sha256'].items():assert digest(Path(p))==h,p
    assert digest(output/'original_population.txt')==digest(prior/'original_population.txt')==report['original_population_sha256']
    a=read(base/'.metadata/metadata.json');b=read(mod/'.metadata/metadata.json')
    assert {k:v for k,v in a.items() if k!='version'}=={k:v for k,v in b.items() if k!='version'}
    before=countries((base/HISTORY).read_text(encoding='utf-8-sig'));after=countries((mod/HISTORY).read_text(encoding='utf-8-sig'))
    assert before.keys()==after.keys()
    source=read(ROOT/'.local/m3/politics.json');political=read(Path(report['political_run'])/'conversion_report.json')
    assert source['source_sha256']==political['source_sha256']==policy['source_sha256']
    lawdefs=definitions(GAME/'common/laws');target=SimpleNamespace(game=GAME)
    evidence={};all_changes=[]
    for tag,body in after.items():
        info=political['countries'][tag]
        newlaws=active_laws(body,target,info);oldlaws=active_laws(before[tag],target,info)
        if tag not in policy['countries']:
            assert semantic(body)==semantic(before[tag]),tag
            continue
        spec=policy['countries'][tag]
        assert info['source_id']==spec['source_id']
        assert non_colonial(body,lawdefs)==non_colonial(before[tag],lawdefs),tag
        assert newlaws==(oldlaws-{spec['old_law']})|{spec['law']}
        oldinst=institution_levels(before[tag],oldlaws,lawdefs);newinst=institution_levels(body,newlaws,lawdefs)
        assert oldinst['institution_colonial_affairs']==2 and 'institution_colonial_affairs' not in newinst
        assert {k:v for k,v in oldinst.items() if k!='institution_colonial_affairs'}==newinst
        for law in newlaws:
            assert not newlaws.intersection(sequence(lawdefs[law].get('disallowing_laws')))
        relations=[r for r in source['subjects'] if r['overlord']==spec['source_id'] and r['type'] in ('trade_company','colonial_nation')]
        assert {r['subject'] for r in relations}==set(spec['building_companies'])
        assert all(source['countries'][r['subject']]['type']=='building' for r in relations)
        assert not [r for r in political['subjects'] if r['target_overlord']==tag and r['type'] in ('trade_company','colonial_nation')]
        assert all(r in political['omitted_subjects'] for r in relations)
        # This law removes institution cost; all production inputs and techs stay identical.
        assert fields(lawdefs[spec['law']].get('modifier'))=={'country_acceptance_homeland_add':'10'}
        evidence[tag]=dict(source_relations=relations,source_company_types={r['subject']:source['countries'][r['subject']]['type'] for r in relations},
            old_law=spec['old_law'],new_law=spec['law'],old_institutions=oldinst,new_institutions=newinst,
            institution_demand='non_increasing; colonial institution removed; exact runtime budget not simulated')
        all_changes.append(tag)
    # Detect later history commands that could overwrite the selected laws/institutions.
    for p in (mod/'common/history/countries').glob('*.txt'):
        if p.name=='00_eu5_world.txt':continue
        for tag,body in countries(p.read_text(encoding='utf-8-sig')).items():
            if tag not in policy['countries']:continue
            for k,v in body.entries():
                assert k not in ('activate_law','set_institution_investment_level'),(p,tag,k)
    pops=parse_pops(mod/'common/history/pops/00_eu5_world.txt')
    assert pops==parse_pops(base/'common/history/pops/00_eu5_world.txt')
    frontier=frontier_evidence(mod,political,Path(report['political_run'])/'province_owners.json')
    write(output/'colonial_law_evidence.json',dict(countries=evidence,frontier_review=frontier,
        limits=['Native law effects preserved, including homeland acceptance +10.',
                'No runtime eligibility/AI/fiscal simulation; unchanged literacy evidence inherited by byte identity.']))
    literacy=read(prior/'verification.json')['literacy'];assert literacy['status']=='passed'
    check=dict(status='passed',changed_countries=sorted(all_changes),countries_checked=len(after),population=sum(pops.values()),
        source_building_company_false_positives_verified=True,only_two_colonial_laws_and_institutions_changed=True,
        technology_and_other_institutions_preserved=True,institution_demand_non_increasing=True,
        population_literacy_borders_homelands_economy_byte_identical=True,unrelated_files_byte_identical=True,
        frontier_native_conditions_reviewed=True,runtime_verified=False)
    result=dict(status='passed_static_runtime_pending',colonial_laws=check,literacy=literacy,
        literacy_validation_basis='Prior passed verification plus byte-identical population, selectors, source metadata and initialization hooks.',
        package_report_sha256=digest(output/'package_report.json'),audit_sha256={p:digest(output/p) for p in ['policy.snapshot.json','colonial_law_evidence.json']})
    write(output/'verification.json',result)
    return result


if __name__=='__main__':
    import sys
    print(json.dumps(verify(Path(sys.argv[1])),ensure_ascii=False,indent=2))
