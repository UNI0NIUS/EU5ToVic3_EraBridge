"""Explicit source-empty state templates, accounted separately from EU5 people."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from build_m2_prototype import objects
from build_m3_world import block
from m3_world import digest, fields, load_json
from m4_religions import definitions
from pdx_text import root
from verify_m4_population import rows


def build_templates(run, game, policy_path):
    out=run/'template_fallback';out.mkdir()
    policy=load_json(policy_path); chosen=policy['empty_state_templates']
    stage=load_json(run/'staging/staging_report.json'); political=Path(stage['political_run'])
    report=load_json(political/'conversion_report.json'); mod=Path(report['mod_directory'])
    owners=load_json(political/'province_owners.json')
    populated={(r['state'],r['owner']) for r in rows(run/'staging/state_owner_totals.csv') if int(r['centipersons'])}
    empty={(s,t) for s,ps in owners.items() for t in set(ps.values())}-populated
    assert empty==set(chosen.items()), ('Unreviewed source-empty state parts',empty)
    for s,t in chosen.items():assert set(owners[s].values())=={t}, ('Template requires whole empty state',s)
    cultures=definitions(game/'common/cultures');religions=definitions(game/'common/religions')
    inputs={str(policy_path):digest(policy_path),str(political/'conversion_report.json'):digest(political/'conversion_report.json')}
    for directory in ('common/cultures','common/religions'):
        inputs.update({str(p):digest(p) for p in sorted((game/directory).glob('*.txt'))})
    groups=Counter();bodies=defaultdict(list)
    for path in sorted((mod/'common/history/pops').glob('*.txt')):
        assert digest(path)==report['output_sha256'][str(path.relative_to(mod))]
        inputs[str(path)]=digest(path)
        for state,obj in objects(root(path.read_text(encoding='utf-8-sig')).fields()['POPS']):
            s=state.removeprefix('s:')
            if s not in chosen:continue
            for owner,body in objects(obj):
                t=owner.removeprefix('region_state:');assert t==chosen[s]
                for op,pop in objects(body):
                    assert op=='create_pop'
                    f=fields(pop);c=f['culture'];religion=f.get('religion',cultures[c]['religion'])
                    assert religion in religions
                    n=int(f['size']);assert n>0
                    groups[s,t,c,religion]+=n
                    # Keep template fields and make its effective default religion explicit.
                    bodies[s,t].append(block('create_pop',pop.text()+('\nreligion = '+religion if 'religion' not in f else '')))
    assert {s for s,t in bodies}==set(chosen)
    text='# SOURCE-EMPTY TEMPLATE SUPPLEMENT. Not EU5-origin population. Local preview only.\n'
    text+=block('POPS',''.join(block('s:'+s,block('region_state:'+t,''.join(b))) for (s,t),b in sorted(bodies.items())))
    (out/'population_history_preview.txt').write_text(text,encoding='utf-8')
    with (out/'template_population_groups.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['state','owner','culture','religion','persons'])
        writer.writerows((*k,n) for k,n in sorted(groups.items()))
    risk=[]
    for p,config in policy['deferred_target_provinces'].items():
        s=config['state'];t=owners[s][p]
        provinces=[q for ps in owners.values() for q,owner in ps.items() if owner==t]
        risk.append({'province':p,'owner':t,'owner_province_count':len(provinces),'sole_province_polity':provinces==[p],**config})
    result={'status':'template_candidate_not_installed','source_world_centipersons':stage['world_centipersons'],
            'template_supplement_persons':sum(groups.values()),'candidate_world_centipersons':stage['world_centipersons']+100*sum(groups.values()),
            'source_empty_states':chosen,'deferred_targets':risk,'input_sha256':inputs,'deployment_ready':False,
            'output_sha256':{p.name:digest(p) for p in out.iterdir() if p.is_file()}}
    demographics=load_json(run/'demographics/demographics_report.json')
    if demographics.get('culture_budget'):
        from m4_culture_budget import enforce
        from build_m3_world import load_localization
        budget=demographics['culture_budget'];counts=dict(budget['counts'])
        source_groups=list(rows(run/'demographics/resident_population_groups.csv'))
        counts['used_cultures']=len({r['culture'] for r in source_groups}|{k[2] for k in groups})
        counts['population_groups']=len(source_groups)+len(groups)
        enforce(budget['limits'],counts)
        result['candidate_culture_budget']={'status':'passed','counts':counts,'limits':budget['limits'],'includes_source_empty_templates':True}
        catalog={r['culture']:{**r,'template_centipersons':0} for r in rows(run/'demographics/active_culture_catalog.csv')}
        labels=load_localization(game/'localization/simp_chinese')
        for (_,_,culture,_),n in groups.items():
            entry=catalog.setdefault(culture,{'culture':culture,'name':labels[culture],'kind':'vanilla_template','source_identity_count':0,'source_identities':'','centipersons':0,'population_groups':0,'template_centipersons':0})
            entry['centipersons']=int(entry['centipersons'])+n*100
            entry['population_groups']=int(entry['population_groups'])+1
            entry['template_centipersons']+=n*100
        path=out/'candidate_culture_catalog.csv'
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(next(iter(catalog.values()))));writer.writeheader()
            writer.writerows(sorted(catalog.values(),key=lambda r:-int(r['centipersons'])))
        result['output_sha256'][path.name]=digest(path)
    (out/'template_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def verify_templates(run, game):
    """Reparse pinned original templates and emitted preview independently."""
    out=run/'template_fallback';report=load_json(out/'template_report.json')
    for p,sha in report['input_sha256'].items():assert digest(Path(p))==sha
    for p,sha in report['output_sha256'].items():assert digest(out/p)==sha
    chosen=report['source_empty_states'];culture_defs=definitions(game/'common/cultures')
    expected=Counter();actual=Counter()
    for p in report['input_sha256']:
        path=Path(p)
        if path.parent.name!='pops':continue
        for state,obj in objects(root(path.read_text(encoding='utf-8-sig')).fields()['POPS']):
            s=state.removeprefix('s:')
            if s not in chosen:continue
            for owner,part in objects(obj):
                t=owner.removeprefix('region_state:');assert t==chosen[s]
                for op,pop in objects(part):
                    assert op=='create_pop';f=pop.fields();c=f['culture']
                    expected[s,t,c,f.get('religion',culture_defs[c]['religion'])]+=int(f['size'])
    for state,obj in objects(root((out/'population_history_preview.txt').read_text(encoding='utf-8')).fields()['POPS']):
        for owner,part in objects(obj):
            for op,pop in objects(part):
                assert op=='create_pop';f=pop.fields()
                actual[state.removeprefix('s:'),owner.removeprefix('region_state:'),f['culture'],f['religion']]+=int(f['size'])
    ledger=Counter()
    for r in rows(out/'template_population_groups.csv'):ledger[r['state'],r['owner'],r['culture'],r['religion']]+=int(r['persons'])
    assert expected==actual==ledger and sum(actual.values())==report['template_supplement_persons']
    source_parts={(r['state'],r['owner']) for r in rows(run/'staging/state_owner_totals.csv') if int(r['centipersons'])}
    assert not source_parts & {(s,t) for s,t,c,r in actual}
    assert report['candidate_world_centipersons']==report['source_world_centipersons']+sum(actual.values())*100
    result={'status':'passed','template_groups':len(actual),'template_persons':sum(actual.values()),'no_source_population_overlap':True,'source_population_unchanged':True,'preview_matches_pinned_templates':True,'report_sha256':digest(out/'template_report.json')}
    if report.get('candidate_culture_budget'):
        budget=report['candidate_culture_budget']
        original=list(rows(run/'demographics/resident_population_groups.csv'))
        assert budget['counts']['used_cultures']==len({x['culture'] for x in original}|{k[2] for k in actual})<=budget['limits']['max_used_cultures']
        assert budget['counts']['population_groups']==len(original)+len(actual)<=budget['limits']['max_population_groups']
        d=load_json(run/'demographics/demographics_report.json')
        assert budget['limits']==d['culture_budget']['limits']
        for key,value in budget['counts'].items():
            assert 0<=value<=budget['limits']['max_'+key]
            if key not in ('used_cultures','population_groups'):assert value==d['culture_budget']['counts'][key]
        totals=Counter();group_counts=Counter();supplement=Counter()
        for r in original:totals[r['culture']]+=int(r['centipersons']);group_counts[r['culture']]+=1
        for (_,_,c,_),n in actual.items():totals[c]+=n*100;supplement[c]+=n*100;group_counts[c]+=1
        catalog=list(rows(out/'candidate_culture_catalog.csv'))
        assert len(catalog)==len({x['culture'] for x in catalog})==len(totals)
        for x in catalog:
            c=x['culture'];assert int(x['centipersons'])==totals[c] and int(x['population_groups'])==group_counts[c]
            assert int(x['template_centipersons'])==supplement[c]
        result['candidate_culture_budget']=budget
    (out/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
