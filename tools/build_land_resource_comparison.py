"""Read-only before/after audit of installed economic carrying-capacity changes."""
import csv
import hashlib
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
from economy_model import Target,apportioned,building_rows,definitions
from economy_source_structure import RESOURCES
from extract_m3_politics import fields,sequence
from build_m3_world import load_localization
from pdx_text import root

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'.local/economy/capacity-019'
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
INSTALLED=(Path.home()/'Documents/Paradox Interactive/Victoria 3/mod/eu5_economy_test')
OUT=ROOT/'outputs/economy-land-resource-20261002'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    report=load(RUN/'report.json');manifest=load(RUN/'manifest.json')
    base=load(Path(report['base_package'])/'package_report.json')
    politics=Path(base['political_run']);demographic=Path(base['demographic_run'])
    owners=load(politics/'province_owners.json');countries=load(politics/'conversion_report.json')['countries']
    target=Target(GAME);modified=definitions(RUN/'overlay/map_data/state_regions')
    employment=load(RUN/'employment.json');changed_resources=load(RUN/'source_resource_capacity.json')
    for rel,expected in manifest['outputs'].items():
        if rel.startswith('overlay/map_data/state_regions/') and sha(RUN/rel)!=expected:raise ValueError('Run map changed: '+rel)
    for path in (RUN/'overlay/map_data/state_regions').glob('*.txt'):
        if sha(path)!=sha(INSTALLED/'map_data/state_regions'/path.name):raise ValueError('Installed map differs from run: '+path.name)
    loc=load_localization(GAME/'localization/simp_chinese');loc.update(load_localization(INSTALLED/'localization/simp_chinese'))
    names=lambda s:loc.get(s,s)
    # Preserve the exact stage links used by the run and reconstruct source evidence.
    stage=demographic/'staging/province_population_draft.csv'
    if sha(stage)!=manifest['inputs'][str(stage.resolve())]:raise ValueError('Population geography changed')
    links=defaultdict(Counter)
    with stage.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):links[r['source_location']][r['target_state'],r['target_owner']]+=int(r['centipersons'])
    links={k:{pair:v/sum(weights.values()) for pair,v in weights.items()} for k,weights in links.items()}
    source_path=ROOT/'.local/economy/source-1780-v2.json'
    if sha(source_path)!=manifest['inputs'][str(source_path.resolve())]:raise ValueError('Source changed')
    source=load(source_path);catalogue=load(RUN/'source_industry_structure.json')['all_building_types']
    evidence=defaultdict(lambda:Counter(rgo=0,buildings=0))
    for b in source['buildings']:
        place=source['locations'][b['location']];goods=catalogue[b['type']]['produced_goods']
        for g in goods:
            if g not in RESOURCES:continue
            for (s,t),fraction in links.get(place['name'],{}).items():
                evidence[s,t,RESOURCES[g],place['name']]['buildings']+=float(b.get('employed',0))*1000*fraction/len(goods)
    for place in source['locations'].values():
        if place['raw_material'] not in RESOURCES:continue
        for (s,t),fraction in links.get(place['name'],{}).items():
            evidence[s,t,RESOURCES[place['raw_material']],place['name']]['rgo']+=place['rgo_workers']*fraction
    by_resource=defaultdict(list);weights=Counter()
    for (s,t,k,l),e in evidence.items():
        n=e['rgo']+e['buildings']
        if not n:continue
        weights[s,t,k]+=n
        by_resource[s,k].append({'country':t,'location':l,'rgo':e['rgo'],'buildings':e['buildings'],'total':n})
    # PMs at resource seeding: the run's UK reference, technology and effective laws.
    history=fields(root((RUN/'overlay/common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES']
    techs={k[2:]:{v for op,v in o.entries() if op=='add_technology_researched'} for k,o in history.entries()}
    target.global_technologies=set().union(*techs.values());laws=load(RUN/'effective_laws.json')
    british=defaultdict(set)
    for r in load(ROOT/'.local/economy/run-006/british_baseline.json')['buildings']:british[r['building']].update(r['pms'])
    built=Counter()
    for r in building_rows(INSTALLED/'common/history/buildings/00_eu5_world.txt'):built[r['state'],r['owner'],r['building']]+=r['levels']
    managed={t for t,c in countries.items() if c['source_id'] is not None}
    land=[];parts=[];by_state=defaultdict(list)
    for r in employment:
        s,t=r['state'],r['country'];shares=Counter(owners[s].values());q=dict(r)
        q.update(name=names(s),country_name=names(t),province_count=shares[t],province_total=sum(shares.values()),province_share=shares[t]/sum(shares.values()),
                 delta=r['new_arable_share']-r['old_arable_share'],fallback_workers=r['population']*.25-r['formal_job_capacity']*r['formal_staffing_credit'])
        q['rural_workers_remaining']=max(0,r['source_rural_workforce']-r['commercial_agricultural_jobs'])
        q['constraint']='就业退路' if math.ceil(max(0,q['fallback_workers'])/r['subsistence_jobs_per_level'])>r['source_rural_subsistence_levels'] else '源农业人口'
        by_state[s].append(q);parts.append(q)
    for s,old in target.states.items():
        new=modified.get(s,old);a=int(old.get('arable_land',0));b=int(new.get('arable_land',0))
        if a==b:continue
        ps=by_state[s]
        shares=Counter(owners[s].values())
        for q in ps:
            required=q['commercial_arable_levels']+max(q['source_rural_subsistence_levels'],math.ceil(max(0,q['fallback_workers'])/q['subsistence_jobs_per_level']))
            assert required==q['required_arable_share'],(s,q['country'],required)
        reconstructed=max([a]+[math.ceil(q['required_arable_share']*sum(shares.values())/shares[q['country']]) for q in ps])
        while any(apportioned(shares,reconstructed).get(q['country'],0)<q['required_arable_share'] for q in ps):reconstructed+=1
        assert reconstructed==b,(s,reconstructed,b)
        driver=max(ps,key=lambda q:q['required_arable_share']/q['province_share'])
        land.append({'state':s,'name':names(s),'countries':sorted(set(owners[s].values())),
                     'before':a,'after':b,'delta':b-a,'multiple':b/a if a else None,
                     'driver':driver['country'],'driver_share':driver['province_share'],'driver_required':driver['required_arable_share'],
                     'split':len(set(owners[s].values()))>1,'parts':ps})
    resources=[];groups=defaultdict(Counter)
    for s,old in target.states.items():
        a=fields(old.get('capped_resources'));b=fields(modified.get(s,old).get('capped_resources'))
        for k in set(a)|set(b):
            before=int(a.get(k,0));after=int(b.get(k,0));groups[k]['before']+=before;groups[k]['after']+=after
            if before==after:continue
            expected=changed_resources[s][k]
            assert (before,after)==(expected['before'],expected['after'])
            shares=Counter(owners[s].values());allocation=[];requests={}
            aa=apportioned(shares,before);bb=apportioned(shares,after)
            for t,count in sorted(shares.items()):
                people=weights[s,t,k];jobs=None;pms=[];requested=0
                if people and t in managed and set(sequence(target.buildings[k].get('unlocking_technologies'))) <= techs[t]:
                    pms=target.select(k,techs[t],british[k],set(laws[t]));jobs=target.coefficients(k,pms,techs[t])['jobs']
                    requested=math.floor(people*.25/jobs+.5) if jobs else 0
                    if requested:requests[t]=requested
                allocation.append({'country':t,'country_name':names(t),'province_count':count,'province_total':sum(shares.values()),
                                   'share':count/sum(shares.values()),'source_people':people,'jobs_per_level':jobs,'requested':requested,
                                   'before':aa[t],'after':bb[t],'built':built[s,t,k],'pms':pms})
            n=max([before]+[math.ceil(v*sum(shares.values())/shares[t]) for t,v in requests.items()])
            while any(apportioned(shares,n).get(t,0)<v for t,v in requests.items()):n+=1
            assert n==after,(s,k,n,after)
            es=sorted(by_resource[s,k],key=lambda e:-e['total']);total=sum(e['total'] for e in es)
            assert math.isclose(total,expected['source_employment_person_equivalents'],abs_tol=.01)
            groups[k]['changed']+=1;groups[k]['new']+=before==0
            resources.append({'state':s,'name':names(s),'resource':k,'resource_name':names(k),'countries':sorted(shares),
                              'before':before,'after':after,'delta':after-before,'multiple':after/before if before else None,
                              'source_people':total,'built':sum(x['built'] for x in allocation),'split':len(shares)>1,
                              'allocations':allocation,'evidence':es})
    assert len(land)==338 and len(resources)==687 and len({r['state'] for r in resources})==393
    summary={}
    for t in ['ITA','BOH']:
        ps=[r for r in parts if r['country']==t]
        rs=[(r,x) for r in resources for x in r['allocations'] if x['country']==t]
        summary[t]={'name':names(t),'land_before':sum(x['old_arable_share'] for x in ps),'land_after':sum(x['new_arable_share'] for x in ps),
                    'changed_parts':sum(x['delta']!=0 for x in ps),'resource_changed_entries':len(rs),
                    'resources':[{'name':names(k),'before':sum(apportioned(Counter(owners[s].values()),int(fields(f.get('capped_resources')).get(k,0))).get(t,0) for s,f in target.states.items() if s in owners),
                                  'after':sum(apportioned(Counter(owners[s].values()),int(fields(modified.get(s,f).get('capped_resources')).get(k,0))).get(t,0) for s,f in target.states.items() if s in owners),
                                  'built':sum(n for (s,owner,kind),n in built.items() if owner==t and kind==k)} for k in sorted(groups) if groups[k]['changed']]}
    data={'run':'capacity-019','installed_version':load(INSTALLED/'.metadata/metadata.json')['version'],
          'land':sorted(land,key=lambda x:-x['delta']),'parts':parts,'resources':sorted(resources,key=lambda x:-x['delta']),
          'summary':summary,'groups':[{**dict(v),'key':k,'name':names(k)} for k,v in sorted(groups.items())],
          'totals':{'changed_land_states':len(land),'land_before':sum(r['before'] for r in land),'land_after':sum(r['after'] for r in land),
                    'resource_states':len({r['state'] for r in resources}),'resource_entries':len(resources)},
          'sources':[str(p.resolve()) for p in [RUN/'report.json',RUN/'employment.json',RUN/'source_resource_capacity.json',source_path,stage,politics/'province_owners.json',Path(__file__)]],
          'verification':{'installed_map_matches_run':True,'land_caps_reconstructed':len(land),'resource_caps_reconstructed':len(resources),'source_employment_reconciled':True}}
    (OUT/'comparison.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    html=(ROOT/'tools/land_resource_comparison.html').read_text(encoding='utf-8').replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    (OUT/'资源与耕地对照.html').write_text(html,encoding='utf-8')
    print(json.dumps({'summary':summary,'totals':data['totals'],'groups':data['groups'],'verified':data['verification']},ensure_ascii=False))

if __name__=='__main__':build()
