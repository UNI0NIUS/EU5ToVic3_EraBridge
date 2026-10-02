"""Independently re-read save literacy, population weights, and emitted effects."""
from collections import Counter
from decimal import Decimal
import csv,json,re
from pathlib import Path
from build_m2_prototype import objects,strings
from m3_world import digest,load_json
from pdx_text import root,Object

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)

def parse_effects(path):
    result={}
    for effect,country in objects(root(path.read_text(encoding='utf-8-sig'))):
        if not effect.startswith('eu5_m4_literacy_'):raise ValueError('Unexpected literacy effect')
        owner=effect[len('eu5_m4_literacy_'):]
        for operation,state in objects(country):
            if operation!='every_scope_state':raise ValueError('Unexpected literacy state operation')
            parts=list(state.entries());limit=parts.pop(0)
            if limit[0]!='limit':raise ValueError('Unbounded literacy state selector')
            region=limit[1].fields()
            if set(region)!={'state_region'} or not region['state_region'].startswith('s:'):raise ValueError('Invalid literacy state selector')
            state_key=region['state_region'][2:]
            for action,pops in parts:
                if action!='every_scope_pop':raise ValueError('Unexpected literacy population operation')
                f=pops.fields()
                if set(f)!={'limit','set_pop_literacy'}:raise ValueError('Unexpected pop mutation')
                selectors=f['limit'].fields()
                if set(selectors)!={'culture','religion'}:raise ValueError('Incomplete literacy identity selector')
                c=selectors['culture'];r=selectors['religion']
                if not c.startswith('cu:') or not r.startswith('rel:'):raise ValueError('Invalid culture/religion scope')
                setter=f['set_pop_literacy'].fields()
                if set(setter)!={'literacy_rate'}:raise ValueError('Unexpected literacy value expression')
                expression=setter['literacy_rate']
                if not isinstance(expression,Object) or set(expression.fields())!={'value'}:raise ValueError('Literacy requires an explicit script value block')
                literal=expression.fields()['value']
                rate=Decimal(literal)
                if not rate.is_finite() or not 0<=rate<=1:raise ValueError('Literacy fraction outside 0..1')
                if not re.fullmatch(r'(?:0(?:\.\d{1,5})?|1(?:\.0{1,5})?)',literal):raise ValueError('Literacy requires an engine-safe decimal fraction with at most five places')
                key=(state_key,owner,c[3:],r[4:])
                if key in result:raise ValueError('Duplicate literacy selector')
                result[key]=rate
    return result

def verify(package,mod,political_mod):
    out=package/'literacy';r=load_json(out/'literacy_report.json');d=Path(r['demographic_run'])
    for p,sha in r['input_sha256'].items():assert digest(Path(p))==sha
    for p,sha in r['output_sha256'].items():assert digest(out/p)==sha
    for p,sha in r['mod_files'].items():assert digest(mod/p)==sha
    source_dir=Path(r['source_literacy_directory']);sr=load_json(source_dir/'source_literacy_report.json')
    save=Path(sr['source_save']);assert digest(save)==sr['source_sha256']==r['source_sha256']
    # This parser does not use the extraction function or its percent converter.
    doc=root(save.read_text(encoding='utf-8')).fields();source={}
    for pid,obj in doc['population'].fields()['database'].entries():
        if not isinstance(obj,Object):continue
        f=obj.fields();percent=Decimal(f.get('literacy','0'));assert percent.is_finite() and 0<=percent<=100
        source[pid]=(int(Decimal(f.get('size','0'))*100000),percent, 'literacy' not in f)
    ledger={x['pop_id']:x for x in rows(source_dir/'source_literacy.csv')}
    for pid,x in ledger.items():
        n,p,omitted=source[pid]
        assert int(x['centipersons'])==n and Decimal(x['literacy_micro_percent'])/1000000==p
        assert bool(int(x['omitted_zero']))==omitted
    assert {pid for pid,x in ledger.items() if int(x['omitted_zero'])}==set(sr['omitted_zero_ids'])
    cultures={x['source_culture']:x['target_culture'] for x in rows(d/'demographics/resident_culture_crosswalk.csv')}
    religions={x['source_religion']:x['target_religion'] for x in rows(d/'demographics/resident_religion_crosswalk.csv')}
    report=load_json(d/'demographics/demographics_report.json')
    migration={(x['source'],state):x['target'] for x in report['migrant_cultures']['cultures'] for state in x['states']}
    amounts=Counter();weighted=Counter();by_pop=Counter()
    for x in rows(d/'staging/province_population_draft.csv'):
        n=int(x['centipersons']);pid=x['source_pop_id'];by_pop[pid]+=n
        c=migration.get((x['source_culture'],x['target_state']),cultures[x['source_culture']])
        key=x['target_state'],x['target_owner'],c,religions[x['source_religion']]
        amounts[key]+=n;weighted[key]+=Decimal(n)*source[pid][1]
    assert all(by_pop[pid]==value[0] for pid,value in source.items())
    actual=parse_effects(mod/'common/scripted_effects/zz_eu5_m4_literacy.txt')
    groups={tuple(x[k] for k in ('state','owner','culture','religion')):x for x in rows(d/'demographics/resident_population_groups.csv')}
    assert set(actual)=={k for k,x in groups.items() if int(x['preview_integer_persons'])>0}
    exported={tuple(x[k] for k in ('state','owner','culture','religion')):x for x in rows(out/'literacy_groups.csv')}
    assert exported.keys()==groups.keys()==amounts.keys()
    source_literates=Decimal(0);integer_literates=Decimal(0);rounding_bound=Decimal(0)
    for k,n in amounts.items():
        x=exported[k];exact=weighted[k]/Decimal(n*100);rate=Decimal(x['literacy_fraction'])
        assert int(x['centipersons'])==n==int(groups[k]['centipersons'])
        assert Decimal(x['weighted_micro_percent'])==weighted[k]*1000000
        assert abs(rate-exact)<=Decimal('0.000005')
        whole=int(groups[k]['preview_integer_persons']);assert int(x['integer_persons'])==whole
        if whole:assert actual[k]==rate
        source_literates+=weighted[k]/10000;integer_literates+=whole*rate
        rounding_bound+=abs(Decimal(whole)-Decimal(n)/100)*exact+Decimal(whole)*Decimal('0.000005')
    assert abs(integer_literates-source_literates)<=rounding_bound
    assert sum(weighted.values())*1000000==r['weighted_literacy_numerator']==sr['weighted_literacy_numerator']
    # Prove only the literacy operations changed inside population initialization.
    before=root((political_mod/'common/history/population/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['POPULATION'].fields()
    after=root((mod/'common/history/population/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['POPULATION'].fields()
    assert before.keys()==after.keys()
    template_owners={x['owner'] for x in rows(d/'template_fallback/template_population_groups.csv')}
    owners={k[1] for k in actual}
    def canonical(values):return [(k,v.text().strip() if isinstance(v,Object) else v) for k,v in values]
    for scope,obj in before.items():
        tag=scope[2:];new=list(after[scope].entries())
        expected=[(k,v) for k,v in obj.entries() if not (k.startswith('effect_starting_pop_literacy_') and tag not in template_owners)]
        if tag in owners:expected.append(('eu5_m4_literacy_'+tag,'yes'))
        assert canonical(new)==canonical(expected)
    old_hooks=root((political_mod/'common/on_actions/00_code_on_actions.txt').read_text(encoding='utf-8-sig')).fields()
    new_hooks=root((mod/'common/on_actions/00_code_on_actions.txt').read_text(encoding='utf-8-sig')).fields()
    assert old_hooks.keys()==new_hooks.keys()
    for name,obj in old_hooks.items():
        if name!='on_game_started':assert obj.text()==new_hooks[name].text()
    old=old_hooks['on_game_started'].fields();new=new_hooks['on_game_started'].fields()
    assert set(new)==set(old)|{'on_actions'}
    for k,v in old.items():
        if k!='on_actions':assert v.text()==new[k].text()
    assert strings(new['on_actions'])==([] if 'on_actions' not in old else strings(old['on_actions']))+['eu5_m4_literacy_after_setup']
    hook=root((mod/'common/on_actions/zz_eu5_m4_literacy.txt').read_text(encoding='utf-8-sig')).fields()
    assert set(hook)=={'eu5_m4_literacy_after_setup'}
    country_scopes=hook['eu5_m4_literacy_after_setup'].fields()['effect'].fields()
    assert set(country_scopes)=={'c:'+tag for tag in owners}
    for scope,obj in country_scopes.items():
        assert set(obj.fields())=={'if'};f=obj.fields()['if'].fields();tag=scope[2:]
        assert set(f)=={'limit','eu5_m4_literacy_'+tag,'set_variable'}
        assert f['limit'].fields()['NOT'].fields()=={'has_variable':'eu5_m4_literacy_imported'}
        assert f['set_variable']=='eu5_m4_literacy_imported' and f['eu5_m4_literacy_'+tag]=='yes'
    result={'status':'passed','source_save_pop_literacy_read_back':True,'source_populations_checked':len(ledger),
        'every_source_pop_allocated_once_in_total':True,'exact_weighted_source_numerator_preserved':True,
        'state_owner_culture_religion_selectors_verified':len(actual),'template_only_populations_excluded_from_source_rates':True,
        'wealth_and_non_literacy_initialization_unchanged':True,'one_time_hook_and_existing_hre_hooks_preserved':True,
        'world_source_literacy_percent':r['world_literacy_percent'],'target_ITA_literacy_percent':r['target_ITA_literacy_percent'],
        'source_weighted_literate_persons':str(source_literates),'integer_output_weighted_literate_persons':str(integer_literates),
        'literate_persons_rounding_delta':str(integer_literates-source_literates),'rounding_error_bound':str(rounding_bound),
        'runtime_verified':False}
    (out/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
