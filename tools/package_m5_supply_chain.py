"""Apply equal-job opening PM rules to the latest M5 without rebuilding its world."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
import shutil

from build_economy import expand_template_tech
from complete_economy import active_laws
from economy_capacity import Ledger
from economy_model import Target, building_rows, definitions, render_buildings
from economy_supply_chain import apply, audit
from extract_m3_politics import fields
from m3_world import digest
from package_m4_population_test import parse_pops
from package_m5_economic_modules import ROOT, GAME, BUILDINGS, read, write, files, canonical
from package_m5_historical_homelands import population_metadata
from package_m5_population_calibration import find_ancestor, POPS
from pdx_text import root, Object


def load_current():
    install = read(ROOT/'.local/m5/installation-latest.json')
    if install != read(ROOT/'.local/economy/installation-latest.json'):
        raise ValueError('Installation pointers disagree')
    prior = Path(install['package']); report = read(prior/'package_report.json')
    base = Path(report['mod_directory'])
    if files(base) != report['output_sha256'] or files(Path(install['target'])) != report['output_sha256']:
        raise ValueError('Installed baseline changed')
    target = Target(GAME); target.states.update(definitions(base/'map_data/state_regions'))
    mapping = read(Path(report['political_run'])/'conversion_report.json')
    history = {k[2:]:v for k,v in fields(root((base/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
    effects = {k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    techs = {t:expand_template_tech(o,effects,target) for t,o in history.items()}
    laws = {t:active_laws(o,target,mapping['countries'][t]) for t,o in history.items()}
    for path in (base/'common/history/countries').glob('*.txt'):
        if path.name == '00_eu5_world.txt': continue
        for k,o in fields(root(path.read_text(encoding='utf-8-sig')))['COUNTRIES'].entries():
            techs[k[2:]].update(v for op,v in o.entries() if op=='add_technology_researched')
    target.global_technologies = set().union(*techs.values())
    population = Counter()
    for k,n in parse_pops(base/POPS).items(): population[k[:2]] += n
    policy = read(ROOT/'config/personal/economy_capacity.json')
    rows = building_rows(base/BUILDINGS)
    ledger = Ledger(target,rows,population,techs,laws,read(Path(report['political_run'])/'province_owners.json'),defaultdict(set),policy['employment'])
    if len(rows) != len(ledger.rows): raise ValueError('Duplicate building histories need separate conditional evaluation')
    ownership = read(find_ancestor(prior,'ownership.json')/'ownership.json')
    ledger.ownership_jobs = {(r['state'],r['country']):r['estimated_owner_jobs'] for r in ownership['owner_hosts']}
    ledger.owner_levels = {(r['state'],r['country']):r['referenced_owned_levels'] for r in ownership['owner_hosts']}
    tags = {t for t,c in mapping['countries'].items() if c['source_id'] is not None}
    return install,prior,report,base,ledger,tags,policy


def verify_rows(ledger, before, after):
    identity = lambda r:(r['state'],r['owner'],r['building'])
    old = {identity(r):r for r in before}; new = {identity(r):r for r in after}
    if old.keys()!=new.keys() or len(after)!=len(new): raise ValueError('Building identity changed')
    def other_body(r):
        return [(k,canonical(v) if isinstance(v,Object) else v) for k,v in root(r['body']).entries() if k!='activate_production_methods']
    for key,a in old.items():
        b = new[key]
        guards = lambda r:[canonical(root(g)) for g in r.get('guards',())]
        if a['levels']!=b['levels'] or guards(a)!=guards(b) or other_body(a)!=other_body(b):
            raise ValueError('Levels/ownership/non-PM history changed: '+str(key))
        ca,cb = ledger.coefficients(a),ledger.coefficients(b)
        if ca['jobs']!=cb['jobs']: raise ValueError('Employment capacity changed: '+str(key))
        if a['pms']!=b['pms']:
            if a.get('guards'): raise ValueError('Conditional history changed')
            for pm in set(b['pms'])-set(a['pms']):
                if not ledger.target.available(pm,ledger.techs[b['owner']],ledger.laws[b['owner']]):
                    raise ValueError('Unavailable method: '+pm)
            groups = ledger.target.complete_methods(b['building'],b['pms'],b['pms'])
            if len(groups)!=len(b['pms']): raise ValueError('Incomplete methods')
    return len(new)


def totals(ledger):
    out = defaultdict(lambda: {'outputs':Counter(),'inputs':Counter(),'levels':Counter()})
    for row in ledger.rows.values():
        if row.get('guards'): continue
        c=ledger.coefficients(row);d=out[row['owner']];n=row['levels']
        d['levels'][row['building']] += n
        for g,v in c['outputs'].items():d['outputs'][g]+=v*n
        for g,v in c['inputs'].items():d['inputs'][g]+=v*n
    return dict(out)


def infrastructure(ledger):
    result = []
    for (s,t),pop in sorted(ledger.population.items()):
        rows=ledger.local(s,t)
        used=sum(ledger.target.infrastructure_usage(r['building'])*r['levels'] for r in rows)
        owner_used=sum(ledger.target.infrastructure_usage({'manor':'building_manor_house','finance':'building_financial_district'}[kind])*n
                       for kind,n in ledger.owner_levels.get((s,t),{}).items())
        available=ledger.target.infrastructure(s,pop,ledger.techs[t],rows)
        result.append({'state':s,'country':t,'productive_usage':used,'owner_usage':owner_used,'available':available,'gap':max(0,used+owner_used-available)})
    return result


def build(output):
    install,prior,report,base,ledger,tags,policy = load_current()
    before=deepcopy(list(ledger.rows.values())); old_totals=totals(ledger); old_infra=infrastructure(ledger)
    ledger.supply_chain_policy=policy['supply_chain']; old_audit=audit(ledger,tags)
    changes=apply(ledger,tags,policy['supply_chain'],policy['input_support']['goods'])
    new_audit=audit(ledger,tags)
    if infrastructure(ledger)!=old_infra: raise ValueError('Infrastructure changed in PM-only package')
    output.mkdir(parents=True,exist_ok=False);mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    (mod/BUILDINGS).write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8-sig')
    count=verify_rows(ledger,before,building_rows(mod/BUILDINGS))
    meta=read(mod/'.metadata/metadata.json')
    m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',install['version'])
    a,b,c,d=map(int,m.groups());meta['version']=f'{a}.{b}.{c+1}-m5-test{d+1}'
    write(mod/'.metadata/metadata.json',meta)
    hashes=files(mod);changed=sorted(k for k,v in hashes.items() if v!=report['output_sha256'][k])
    if set(changed)!={BUILDINGS,'.metadata/metadata.json'}:raise ValueError('Unexpected update scope')
    # Per-level jobs, land use and ownership are exactly unchanged; refresh the
    # provenance anchor so later population-mode switches accept the new history.
    for name in ('employment.json','ownership.json','ownership_provinces.json','agriculture.json'):
        shutil.copy2(find_ancestor(prior,name)/name,output/name)
    write(output/'changes.json',changes)
    write(output/'supply_chain.json',{'policy':policy['supply_chain'],'before':old_audit,'after':new_audit,
          'limits':['Static full-staffing domestic flows exclude household demand, trade, market grouping, subsistence and runtime throughput.',
                    'Supply-ship reservation is a full-capacity stress scenario, not the saved queue or an engine price prediction.',
                    'Existing source factory levels retained. Porcelain source remapping applies to fresh conversion; this patch preserves current jobs/ownership.']})
    write(output/'country_flows.json',{'before':old_totals,'after':totals(ledger)})
    write(output/'infrastructure.json',old_infra)
    check={'status':'passed','rows_verified':count,'changed_rows':len(changes),
           'levels_ownership_employment_unchanged':True,'unrelated_files_byte_identical':True,
           'infrastructure_unchanged':True,'runtime_verified':False}
    write(output/'supply_chain_verification.json',check)
    inputs=[ROOT/'config/personal/economy_capacity.json',prior/'package_report.json',
            Path(__file__),ROOT/'tools/economy_supply_chain.py',ROOT/'tools/economy_model.py',
            ROOT/'tools/complete_economy.py',ROOT/'tools/economy_consumption.py',ROOT/'tools/update_m5_integrated_test.ps1']
    for folder in ('production_methods','production_method_groups','ship_types','goods','buy_packages','technology/technologies'):
        inputs.extend(sorted((GAME/'common'/folder).glob('*.txt')))
    new={'status':'supply_chain_static_verified_runtime_pending','update_scope':'m5_supply_chain','version':meta['version'],
         'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),'new_campaign_required':True,
         'changed_files':changed,'output_sha256':hashes,'input_sha256':{str(p.resolve()):digest(p) for p in inputs},
         'political_run':report['political_run'],'demographic_run':report['demographic_run'],
         **population_metadata(prior,hashes[POPS])}
    write(output/'package_report.json',new)
    write(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
          'supply_chain':check,'package_report_sha256':digest(output/'package_report.json'),
          'audit_sha256':{p.name:digest(p) for p in output.iterdir() if p.is_file() and p.name not in ('verification.json','package_report.json')}})
    if read(ROOT/'.local/m5/installation-latest.json')!=install:raise ValueError('Baseline changed during packaging')
    return {'package':str(output),'version':meta['version'],**check,'ITA_before':old_totals.get('ITA'),'ITA_after':totals(ledger).get('ITA')}


if __name__=='__main__':
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    output=a.output or ROOT/'.local/economy/packages'/('m5-supply-chain-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    print(json.dumps(build(output.resolve()),ensure_ascii=False,indent=2))
