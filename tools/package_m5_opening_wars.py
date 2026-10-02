"""Build an auditable M5 opening-war overlay; keep runtime probes separate."""
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import argparse
import re
import shutil
from military_technology_design import read, write, ROOT, GAME
from economy_model import definitions
from extract_m3_politics import fields
from pdx_text import root,Object
from m3_world import digest
from build_m2_prototype import state_owners
from package_m5_economic_modules import files
from package_m5_uncolonized import inherited_report
from extract_war_source import extract
from opening_wars import plan,render,HISTORY,PLAYS,DEPLOY,TESTS,PREFIX
from border_war_goals import load_candidates,price_scripts,VALUES


def build(output):
    installed=read(ROOT/'.local/economy/installation-latest.json');prior=Path(installed['package'])
    old=inherited_report(prior);base=Path(old['mod_directory'])
    if files(base)!=old['output_sha256'] or files(Path(installed['target']))!=old['output_sha256']:
        raise ValueError('Installed baseline or package modified')
    if output.exists():raise ValueError('Output already exists')
    output.mkdir(parents=True)
    config_path=ROOT/'config/personal/opening_wars.json';policy=read(config_path)
    audit_path=ROOT/'.local/m1/main-report/import_report.json';audit=read(audit_path)
    save=Path(audit['source']);source=extract(save,output/'source_wars.json',policy['source_sha256'])
    mapping_path=Path(old['political_run'])/'conversion_report.json';mapping=read(mapping_path)
    if mapping['source_sha256']!=source['source_sha256']:raise ValueError('Political/war source mismatch')
    if {w['id'] for w in source['wars']}!=set(policy['war_overrides']):raise ValueError('Policy does not cover all wars')
    states=fields(root((base/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['STATES']
    owners={};state_provinces={};claims={}
    for key,obj in states.entries():
        owned=state_owners(obj);owners.update(owned);state_provinces[key[2:]]=set(owned)
        claims[key[2:]]={v.removeprefix('c:') for k,v in obj.entries() if k=='add_claim'}
    parents={}
    for path in (base/'common/history/diplomacy').glob('*.txt'):
        for k,country in fields(root(path.read_text(encoding='utf-8-sig')))['DIPLOMACY'].entries():
            for op,pact in country.entries():
                if op!='create_diplomatic_pact':continue
                f=fields(pact)
                if f.get('type') in ('puppet','vassal','dominion','protectorate','colony','personal_union','tributary','chartered_company'):
                    parents[f['country'].removeprefix('c:')]=k.removeprefix('c:')
    staging=Path(old['demographic_run'])/'staging/province_population_draft.csv'
    rows=plan(source,policy,mapping,{str(l['id']):l['name'] for l in audit['locations']},staging,owners,state_provinces,claims,parents)
    if policy.get('territorial_budget'):
        load_candidates(rows,base,GAME,ROOT/'.local/m3/cache/tribal_land_edges.json',claims,policy['territorial_budget']['per_side'])
    native_path=GAME/'common/diplomatic_plays/00_diplomatic_plays.txt'
    native=fields(root(native_path.read_text(encoding='utf-8-sig')))
    recognition=fields(root((GAME/'common/war_goal_types/22_revoke_all_claims.txt').read_text(encoding='utf-8-sig')))['revoke_all_claims']
    scripts=render(rows,native,recognition)
    if scripts!=render(rows,native,recognition):raise ValueError('Non-deterministic render')
    if policy.get('territorial_budget'):scripts[VALUES]=price_scripts(GAME)
    for rel,text in scripts.items():
        if rel.endswith('.txt'):list(root(text).entries())
    plays=fields(root(scripts[PLAYS]));history=fields(root(scripts[HISTORY]))['DIPLOMATIC_PLAYS']
    actual=[]
    for tag,obj in history.entries():
        for op,effect in obj.entries():
            if op=='create_diplomatic_play':actual.append((tag[2:],fields(effect)))
    if len(actual)!=len(rows):raise ValueError('Not all wars rendered exactly once')
    definitions_country={key for path in (base/'common/country_definitions').glob('*.txt') for key,_ in root(path.read_text(encoding='utf-8-sig')).entries()}
    for row,(tag,create) in zip(rows,actual):
        if tag!=row['attacker'] or create['type']!=row['play_type'] or create['war']!='no':raise ValueError('War setup mismatch')
        if not set(row['attackers']+row['defenders'])<=definitions_country:raise ValueError('Unknown target country')
        if fields(plays[row['play_type']])['war_goal']!=row['goal']:raise ValueError('Wrong main war goal')
        for side,leader,key in [('attackers',row['attacker'],'add_initiator_backers'),('defenders',row['leader_target'],'add_target_backers')]:
            if {v.removeprefix('c:') for _,v in create[key].entries()}!=set(row[side])-{leader}:raise ValueError('Wrong supporters')
    # Unmodified formations, ships, populations, governments and land remain byte-identical.
    mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    for rel,text in scripts.items():
        path=mod/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8-sig')
    meta=read(mod/'.metadata/metadata.json');version=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',installed['version'])
    if not version:raise ValueError('Unexpected version')
    meta['version']=f'0.5.{int(version[1])+1}-m5-test{int(version[2])+1}';write(mod/'.metadata/metadata.json',meta)
    output_hashes=files(mod);changed=[rel for rel,sha in output_hashes.items() if old['output_sha256'].get(rel)!=sha]
    if not set(changed)<=set(scripts)|{'.metadata/metadata.json'}:raise ValueError('Unexpected output delta')
    write(output/'war_mapping.json',rows);write(output/'policy.snapshot.json',policy)
    warnings=['Native runtime membership and independence/secession peace outcomes require engine validation.',
              'Source occupation, warscore, historic losses, battles and siege ticks are recorded but not applied.',
              'All six wars start active on 1836.1.1 with reset V3 war progress; source dates are audit-only.',
              'Initialization validates participants before escalating; unsupported cases are logged and aborted, never expanded to extra countries.']
    evidence={'status':'passed','source_wars':len(source['wars']),'generated_wars':len(rows),
              'source_active_memberships':source['active_memberships'],'mapped_active_memberships':sum(len(r['attackers'])+len(r['defenders']) for r in rows),
              'omitted_active_memberships':sum(len(r['omitted_participants']) for r in rows),
              'one_state_goals':sum('state' in r for r in rows),'source_hash_and_references_verified':True,
              'only_active_source_members_rendered':True,'one_state_targets_verified':True,
              'military_counts_population_borders_unchanged':True,'membership_fail_closed':True,
              'native_goal_definitions_preserved':True,'deterministic_generation':True,'runtime_verified':False,
              'occupation_restored':False,'warnings':warnings}
    if policy.get('territorial_budget'):
        evidence.update(border_goal_rules_verified=True,budget_per_side=policy['territorial_budget']['per_side'],
                        ordinary_wars=sum('candidates' in r for r in rows),
                        candidate_goals=sum(len(r.get('candidates',[])) for r in rows),
                        budget_runtime_verified=False,single_primary_runtime_verified=False)
    write(output/'opening_wars_verification.json',evidence)
    # Keep provenance for later overlay tools; population artifact belongs to its original ancestor.
    inputs=[save,audit_path,config_path,mapping_path,staging,prior/'package_report.json',native_path,
            ROOT/'tools/extract_war_source.py',ROOT/'tools/opening_wars.py',Path(__file__),ROOT/'tools/update_m5_integrated_test.ps1',
            ROOT/'tools/prepare_opening_war_probe.py',ROOT/'tools/verify_opening_war_runtime.py',ROOT/'tools/certify_opening_wars.py']
    if policy.get('territorial_budget'):
        inputs += [ROOT/'tools/border_war_goals.py',GAME/'map_data/provinces.png',GAME/'map_data/adjacencies.csv',GAME/'map_data/default.map',
                   GAME/'common/defines/00_defines.txt',GAME/'common/script_values/00_diplomacy_values.txt']
        inputs += list((GAME/'common/country_ranks').glob('*.txt'))
    inputs+=list((GAME/'common/war_goal_types').glob('*.txt'))
    report={k:old[k] for k in ('political_run','demographic_run','population_mode','population_calibrated','source_population_conserved') if k in old}
    report.update(status='m5_opening_wars_static_verified_runtime_pending',update_scope='m5_opening_wars',version=meta['version'],
                  mod_name=meta['name'],mod_directory=str(mod),prior_package=str(prior),new_campaign_required=True,
                  changed_files=changed,input_sha256={str(p.resolve()):digest(p) for p in inputs},output_sha256=output_hashes)
    write(output/'package_report.json',report)
    write(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
          'opening_wars':evidence,'package_report_sha256':digest(output/'package_report.json'),
          'audit_sha256':{name:digest(output/name) for name in ('source_wars.json','war_mapping.json','policy.snapshot.json','opening_wars_verification.json')}})
    print({'package':str(output),'version':meta['version'],'wars':len(rows),'changed_files':changed})
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'.local/economy/packages'/('m5-opening-wars-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    build(p.parse_args().output.resolve())
