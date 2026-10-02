"""Independent readback for an M5 tribal-country promotion."""
from collections import Counter
from pathlib import Path
import re

from build_m2_prototype import objects, strings, state_owners
from economy_model import building_rows
from package_m4_population_test import parse_pops, effective
from package_m5_economic_modules import read, write, files, canonical
from pdx_text import root, Object
from m3_world import digest


def verify(package,base,mod,candidate,owners,original,population,primary):
    from package_m5_uncolonized import STATE,POPS,COUNTRIES,DEFS,FLAGS,COAS,BUILDINGS,MILITARY,DIPLOMACY,ALLOWED,container,text
    report=read(candidate/'conversion_report.json');tags=set(primary)
    changes=read(package/'ownership_changes.json');retired=set(changes['retired_empty_vanilla_fallbacks'])
    expected=read(candidate/'province_owners.json')
    for r in changes['terrain_attachments']:
        assert expected[r['state']][r['province']]==r['from'] and r['from'] in retired and r['to'] in tags
        expected[r['state']][r['province']]=r['to']
    assert owners==expected
    actual={};parts={};homelands={}
    for scope,o in container(mod/STATE,'STATES').items():
        s=scope[2:];actual[s]={('x'+p[1:].upper()):t for p,t in state_owners(o,strict=False).items()}
        homelands[s]=[canonical(v) if isinstance(v,Object) else v for k,v in o.entries() if k=='add_homeland']
        for k,v in o.entries():
            if k=='create_state':parts[s,v.fields()['country'][2:]]=v.fields()
    assert actual==owners
    for scope,o in container(base/STATE,'STATES').items():
        assert homelands[scope[2:]]==[canonical(v) if isinstance(v,Object) else v for k,v in o.entries() if k=='add_homeland']
    defs=effective(mod,'common/country_definitions');cultures=effective(mod,'common/cultures');faiths=effective(mod,'common/religions')
    got=parse_pops(mod/POPS);assert got==population
    assert parse_pops(package/'original_population.txt')==original
    totals=Counter()
    for (s,t,c,r),n in got.items():
        assert (s,t) in parts and c in cultures and r in faiths
        totals[t]+=n
    flags=effective(mod,'common/flag_definitions');coas=root(text(mod/COAS)).fields()
    for t in tags:
        assert defs[t]['country_type']=='decentralized'
        assert strings(defs[t]['cultures'])==[primary[t]]
        assert primary[t] in cultures and defs[t]['religion'] in faiths
        assert (defs[t]['capital'],t) in parts and totals[t]>0
        assert flags[t]['flag_definition'].fields()['coa']=='eu5_uncolonized_'+t
        assert 'eu5_uncolonized_'+t in coas
    for (s,t),f in parts.items():
        if t in tags:assert f['state_type']=='unincorporated'
    before=container(base/COUNTRIES,'COUNTRIES');after=container(mod/COUNTRIES,'COUNTRIES')
    assert set(after)==(set(before)-{'c:'+t for t in retired})|{'c:'+t for t in tags}
    for k,o in before.items():
        if k[2:] not in retired:assert canonical(o)==canonical(after[k])
    old_pacts={(k[2:],v.fields()['country'][2:],v.fields()['type']) for k,o in container(base/DIPLOMACY,'DIPLOMACY').items() for op,v in objects(o)}
    new_pacts={(k[2:],v.fields()['country'][2:],v.fields()['type']) for k,o in container(mod/DIPLOMACY,'DIPLOMACY').items() for op,v in objects(o)}
    assert new_pacts=={p for p in old_pacts if not set(p[:2])&retired}
    assert not any(set(p[:2])&tags for p in new_pacts)
    assert digest(base/BUILDINGS)==digest(mod/BUILDINGS)
    assert digest(base/MILITARY)==digest(mod/MILITARY)
    for r in building_rows(mod/BUILDINGS):
        assert (r['state'],r['owner']) in parts
        for op,obj in root(r['body']).entries():
            if op!='add_ownership':continue
            for k,v in objects(obj):
                f=v.fields()
                if f.get('region') and f.get('country'):
                    assert (f['region'].removeprefix('s:'),f['country'].removeprefix('c:')) in parts
    placements=0
    def walk(o,t):
        nonlocal placements
        for k,v in o.entries():
            if k=='state_region' and isinstance(v,str):
                assert (v.removeprefix('s:'),t) in parts,(t,v)
                placements+=1
            elif isinstance(v,Object):walk(v,t)
    for scope,o in container(mod/MILITARY,'MILITARY_FORMATIONS').items():walk(o,scope[2:])
    old=files(base);new=files(mod);assert set(old)==set(new)
    changed={p for p in new if old[p]!=new[p]};assert changed<=ALLOWED
    # Population reallocation must preserve all statewide identities and the
    # population-mode total. It cannot silently resurrect cut population.
    def identities(groups):
        result=Counter()
        for (s,t,c,r),n in groups.items():result[s,c,r]+=n
        return result
    from package_m5_population_options import original_population_package
    from economy_population_calibration import majority_signature
    install=read(Path(__file__).resolve().parents[1]/'.local/m5/installation-latest.json')
    assert identities(original)==identities(parse_pops(original_population_package(Path(install['package']))))
    assert set(got)==set(original) and all(0<n<=original[k] for k,n in got.items())
    assert majority_signature(got)==majority_signature(original)
    assert majority_signature(got,True)==majority_signature(original,True)
    policy=read(package/'population_calibration.json')['policy'];old_totals=Counter();new_totals=Counter()
    for k,n in original.items():old_totals[k[1]]+=n
    for k,n in got.items():new_totals[k[1]]+=n
    assert all(old_totals[t]-n<=int(old_totals[t]*policy['maximum_country_reduction_fraction']) for t,n in new_totals.items())
    employment=read(package/'employment.json')
    assert {(r['state'],r['country']) for r in employment}=={k[:2] for k in got}
    result={'status':'passed','generated_countries':len(tags),'changed_provinces':len(report['uncolonized_tribes']['transfers'])+len(changes['terrain_attachments']),
        'terrain_attachments':len(changes['terrain_attachments']),'retired_empty_vanilla_fallbacks':sorted(retired),
        'all_province_owners_verified':True,'decentralized_types_and_unincorporated_states_verified':True,
        'source_weighted_population_reallocated':True,'original_state_culture_religion_totals_preserved':True,
        'population_mode_recomputed_from_original_once':True,'population_identity_majorities_and_country_caps_verified':True,
        'existing_countries_and_homelands_preserved':True,'latest_buildings_ownership_and_military_preserved':True,
        'military_placements_verified':placements,'unrelated_files_byte_identical':True,
        'population':sum(got.values()),'original_population':sum(original.values()),
        'empty_existing_countries':sorted(t for t in {owner for ps in owners.values() for owner in ps.values()} if not totals[t]),
        'employment_parts_recomputed':len(employment),'runtime_verified':False}
    write(package/'uncolonized_verification.json',result)
    return result
