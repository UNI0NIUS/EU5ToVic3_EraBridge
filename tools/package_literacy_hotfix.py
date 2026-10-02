"""Carry a verified literacy-only fix into the already installed economy package."""
import json, shutil
from datetime import datetime
from pathlib import Path
from m3_world import digest,load_json
from verify_m4_literacy import parse_effects

ROOT=Path(__file__).resolve().parents[1]

def build():
    install=load_json(ROOT/'.local/economy/installation-latest.json')
    base=Path(install['package']); prior=load_json(base/'package_report.json')
    fixed=Path(load_json(ROOT/'.local/m4/test-package-latest.json')['package'])
    checked=load_json(fixed/'independent_verification.json')
    assert checked['status']==checked['literacy']['status']=='passed'
    source=Path(prior['mod_directory'])
    for rel,sha in prior['output_sha256'].items():assert digest(source/rel)==sha
    out=ROOT/'.local/economy/packages'/('m5-integrated-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(source,mod)
    rel='common/scripted_effects/zz_eu5_m4_literacy.txt'
    shutil.copy2(fixed/'eu5_m4_population_test'/rel,mod/rel)
    assert len(parse_effects(mod/rel))==checked['literacy']['state_owner_culture_religion_selectors_verified']
    # The economy layer must still have exactly the same population and hooks.
    for path in ('common/history/pops/00_eu5_world.txt','common/history/population/00_eu5_world.txt','common/on_actions/zz_eu5_m4_literacy.txt','common/on_actions/00_code_on_actions.txt'):
        assert digest(mod/path)==digest(fixed/'eu5_m4_population_test'/path)
    meta=load_json(mod/'.metadata/metadata.json');meta['version']='0.5.1-m5-test1'
    meta['name']='EU5 M5 - World 1780 - Integrated TEST'
    meta['short_description']='Integrated politics, cultures, population, literacy and population-aware economy. New campaign required; runtime balance and homelands pending.'
    (mod/'.metadata/metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    allowed={rel,'.metadata/metadata.json'}
    assert all(digest(mod/p)==sha for p,sha in prior['output_sha256'].items() if p not in allowed)
    r=dict(prior);r.update(version=meta['version'],mod_name=meta['name'],mod_directory=str(mod),
        status='literacy_hotfix_static_verified_runtime_pending',prior_package=str(base),
        literacy_package=str(fixed),changed_files=sorted(allowed),
        output_sha256={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()})
    (out/'package_report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    evidence={'status':'passed_static_runtime_pending','literacy':checked['literacy'],
              'all_other_economy_files_unchanged':True,'package_report_sha256':digest(out/'package_report.json')}
    (out/'verification.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    logs=out/'failure-evidence';logs.mkdir()
    logdir=(Path.home()/'Documents/Paradox Interactive/Victoria 3/logs')
    count=0
    for p in logdir.glob('error*.log'):
        shutil.copy2(p,logs/p.name)
        count+=sum('Badly read script value' in line and 'zz_eu5_m4_literacy.txt' in line for line in p.read_text(encoding='utf-8-sig').splitlines())
    (logs/'summary.json').write_text(json.dumps({'literacy_script_value_errors':count,'user_report':'All countries show 0 literacy in a new campaign','old_version':'0.4.1-test2 / 0.5.0-economy-test2'},indent=2),encoding='utf-8')
    print(json.dumps({'package':str(out),'version':meta['version'],'prior_engine_errors':count}))

if __name__=='__main__':build()
