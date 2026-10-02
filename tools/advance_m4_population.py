"""Snapshot user decisions and advance private demographic artifacts without deployment."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import uuid

from m3_world import digest, load_json
from stage_m4_population import stage
from verify_m4_population import verify as verify_stage
from m4_demographics import build
from verify_m4_demographics import verify as verify_demographics
from m4_template_population import build_templates, verify_templates

ROOT = Path(__file__).resolve().parents[1]


def advance(only_changed=False):
    source = ROOT/'.local/m4/source-1780-population'
    review_path = ROOT/'.local/m4/location-workstation/location_reviews.json'
    political = Path(load_json(ROOT/'.local/m3/latest.json')['run'])
    profile = ROOT/'config/personal/m4_demographics.json'
    old_profile = ROOT/'config/personal/m3_world.json'
    policy = ROOT/'config/personal/m4_population_policy.json'
    latest_path = ROOT/'.local/m4/demographics-latest.json'
    # Read the atomic live review document once. All subsequent processing uses
    # this immutable snapshot while the user continues editing in the browser.
    raw = review_path.read_bytes(); review = json.loads(raw)
    signatures = {'reviews':hashlib.sha256(raw).hexdigest(), 'demographic_profile':digest(profile),'population_policy':digest(policy),
                  'political_profile':digest(old_profile),'political_report':digest(political/'conversion_report.json'),
                  'source_ledger':digest(source/'source_summary.json'),
                  'pipeline_code':{p:digest(ROOT/'tools'/p) for p in ('advance_m4_population.py','m3_world.py','m4_demographics.py','m4_cultures.py','m4_religions.py','stage_m4_population.py','verify_m4_demographics.py','verify_m4_culture_assets.py','verify_m4_population.py','location_reviews.py')}}
    signatures['pipeline_code']['m4_location_overrides.py']=digest(ROOT/'tools/m4_location_overrides.py')
    signatures['pipeline_code']['m4_template_population.py']=digest(ROOT/'tools/m4_template_population.py')
    signatures['pipeline_code']['m4_migrant_cultures.py']=digest(ROOT/'tools/m4_migrant_cultures.py')
    signatures['pipeline_code']['m4_culture_budget.py']=digest(ROOT/'tools/m4_culture_budget.py')
    signatures['pipeline_code']['religion_icon_texture.py']=digest(ROOT/'tools/religion_icon_texture.py')
    signatures['culture_scaffold_policy']=digest(ROOT/'config/personal/m4_culture_asset_scaffolds.json')
    if only_changed and latest_path.exists() and load_json(latest_path).get('input_signatures') == signatures:
        return {'status':'unchanged','revision':review['revision']}
    run = ROOT/'.local/m4/runs'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    snapshot = run/'location_reviews.snapshot.json'; snapshot.write_bytes(raw)
    config_snapshot = run/'demographics_profile.snapshot.json'; config_snapshot.write_bytes(profile.read_bytes())
    policy_snapshot = run/'population_policy.snapshot.json'; policy_snapshot.write_bytes(policy.read_bytes())
    game = Path('D:/Steam/steamapps/common/Victoria 3/game')
    eu5 = Path('D:/Steam/steamapps/common/Europa Universalis V/game')
    staging = run/'staging'; demographics = run/'demographics'
    stage(political,source,staging,game,eu5,snapshot,policy_snapshot)
    verify_stage(source,staging)
    build(staging,source,demographics,game,eu5,config_snapshot,old_profile)
    verify_demographics(source,demographics)
    template_report=build_templates(run,game,policy_snapshot)
    verify_templates(run,game)
    s=load_json(staging/'staging_report.json'); d=load_json(demographics/'demographics_report.json')
    result={'schema':1,'status':'verified_demographic_draft_not_installed','run':str(run),
            'review_revision':review['revision'],'confirmed_locations':s['location_reviews']['applied_locations'],
            'pending_locations':s['locations_without_geometry'],'pending_geometry_persons':s['unmapped_centipersons']/100,
            'resolved_cultures':d['resolved_cultures'],'pending_cultures':d['active_cultures']-d['resolved_cultures'],
            'culture_budget':d.get('culture_budget'),
            'candidate_culture_budget':template_report.get('candidate_culture_budget'),
            'generated_provisional_cultures':d.get('generated_provisional_cultures',0),
            'generated_provisional_culture_persons':d.get('generated_provisional_culture_centipersons',0)/100,
            'cultural_policy_review_complete':False,
            'pending_culture_persons':d['pending_culture_centipersons']/100,
            'resolved_religions':d['resolved_religions'],'pending_religions':d['active_religions']-d['resolved_religions'],
            'pending_religion_persons':d['pending_religion_centipersons']/100,
            'ready_located_persons':d['ready_located_centipersons']/100,'world_persons':d['world_centipersons']/100,
            'template_supplement_persons':template_report['template_supplement_persons'],
            'migrant_cultures':len(d.get('migrant_cultures',{}).get('cultures',[])),
            'migrant_persons':sum(c['centipersons'] for c in d.get('migrant_cultures',{}).get('cultures',[]))/100,
            'candidate_world_persons':template_report['candidate_world_centipersons']/100,
            'input_signatures':signatures,'deployment_ready':False}
    (run/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temp=latest_path.with_suffix('.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(latest_path)
    return {k:v for k,v in result.items() if k!='input_signatures'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--if-changed',action='store_true');a=p.parse_args()
    print(json.dumps(advance(a.if_changed)))
