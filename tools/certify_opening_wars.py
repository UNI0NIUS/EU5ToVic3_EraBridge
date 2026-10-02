"""Bind independent native save readbacks to the exact package being installed."""
from pathlib import Path
import argparse,json,shutil
from m3_world import digest
from package_m5_economic_modules import files


def certify(package,probes):
    def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
    def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    actual=files(package/'eu5_economy_test');seen=set();audits={};budgets=[]
    for probe in probes:
        evidence=read(probe/'runtime_verification.json')
        if evidence['status']!='passed' or evidence['errors']:raise ValueError('Failed runtime probe')
        if evidence['tested_output_sha256']!=actual:raise ValueError('Runtime evidence tested a different package')
        side=evidence['peace_winner'];seen.add(side)
        budgets.append(evidence.get('budget_audit',[]))
        if not evidence.get('single_primary_verified'):raise ValueError('Single primary objective not verified')
        for key in ('opening','peace'):
            if digest(Path(evidence[key]['save']))!=evidence[key]['save_sha256']:raise ValueError('Runtime save changed')
        rel='runtime_'+side+'.json';shutil.copy2(probe/'runtime_verification.json',package/rel);audits[rel]=digest(package/rel)
    if seen!={'initiator','target'}:raise ValueError('Both peace outcomes required')
    check=read(package/'opening_wars_verification.json')
    check.update(runtime_verified=True,attacker_and_defender_peace_verified=True,
                 runtime_validation_scope='Six wars, exact sides and goals, three territorial settlements, independence, secession, colonial pact; first campaign week.')
    check['warnings']=[w for w in check['warnings'] if not w.startswith('Native runtime')]
    if check.get('border_goal_rules_verified'):
        if any(len(b)!=check['ordinary_wars'] for b in budgets):raise ValueError('Missing war budget evidence')
        for cases in budgets:
            for case in cases:
                if any(v>check['budget_per_side'] or v<0 for v in case['spent'].values()):raise ValueError('War budget exceeded')
        check.update(budget_runtime_verified=True,single_primary_runtime_verified=True)
        check['runtime_validation_scope']='Six active wars; exact participants; budgeted shared-border and defensive homeland objectives; one primary per war; both peace outcomes and protected third-party territory.'
    write(package/'opening_wars_verification.json',check)
    mapping=read(package/'war_mapping.json')
    for row in mapping:row['runtime_verified']=True
    write(package/'war_mapping.json',mapping)
    report=read(package/'package_report.json');report['status']='m5_opening_wars_runtime_verified';write(package/'package_report.json',report)
    verification=read(package/'verification.json');verification['opening_wars']=check
    verification['package_report_sha256']=digest(package/'package_report.json')
    verification['audit_sha256']['opening_wars_verification.json']=digest(package/'opening_wars_verification.json')
    verification['audit_sha256']['war_mapping.json']=digest(package/'war_mapping.json')
    verification['audit_sha256'].update(audits);write(package/'verification.json',verification)
    print('Certified exact package against both native peace probes:',package)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--probe',type=Path,action='append',required=True)
    a=p.parse_args();certify(a.package,a.probe)
