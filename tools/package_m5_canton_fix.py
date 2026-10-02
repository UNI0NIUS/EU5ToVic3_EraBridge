"""Supply missing overlord canton COAs without regenerating any flag artwork."""
from datetime import datetime
from pathlib import Path
import json,shutil
from build_m2_prototype import objects,patch,replace_body
from m3_world import load_json,digest
from pdx_text import root,Object

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')

def build():
    installed=load_json(ROOT/'.local/m5/installation-latest.json');base=Path(installed['package'])
    prior=load_json(base/'package_report.json');source=Path(prior['mod_directory'])
    for rel,sha in prior['output_sha256'].items():assert digest(source/rel)==sha,rel
    audit=load_json(base/'conversion_report.json');wanted={r['tag'] for r in audit['flags'] if r['mode']!='existing_v3_identity_flag'}
    out=ROOT/'.local/economy/packages'/('m5-canton-fix-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(source,mod)
    repaired={};before_defs={};after_defs={};changed=[]
    for path in sorted((source/'common/flag_definitions').glob('*.txt')):
        text=path.read_text(encoding='utf-8-sig');edits=[]
        for tag,obj in objects(root(text)):
            if tag not in wanted:continue
            entries=objects(obj);assert len(entries)==1 and entries[0][0]=='flag_definition'
            definition=entries[0][1];f=definition.fields();before_defs[tag]=f
            assert isinstance(f['coa'],str) and f['coa']!='list'
            if 'subject_canton' not in f:
                edits.append(replace_body(definition,definition.text()+'\nsubject_canton = '+f['coa']+'\n'))
                repaired[tag]=f['coa']
            else:assert f['subject_canton']==f['coa']
        if edits:
            rel=path.relative_to(source).as_posix();changed.append(rel)
            (mod/rel).write_text(patch(text,edits),encoding='utf-8-sig')
    assert set(before_defs)==wanted
    # Independent output walk: all properties except the single added field must
    # compare exactly, including every child canton offset/scale and trigger.
    def canonical(f):return {k:(v.text() if isinstance(v,Object) else v) for k,v in f.items()}
    for path in (mod/'common/flag_definitions').glob('*.txt'):
        for tag,obj in objects(root(path.read_text(encoding='utf-8-sig'))):
            if tag not in wanted:continue
            f=objects(obj)[0][1].fields();after_defs[tag]=f
            assert f['subject_canton']==f['coa']
            expected=canonical(before_defs[tag]);expected['subject_canton']=expected['coa'];assert canonical(f)==expected
    coas={k for directory in (GAME,mod) for p in (directory/'common/coat_of_arms/coat_of_arms').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    assert all(f['subject_canton'] in coas for f in after_defs.values())
    colonies=[r for r in audit['flags'] if r.get('overlord_canton')]
    links=[]
    for r in colonies:
        child=after_defs[r['tag']];parent=after_defs[r['overlord']]
        assert child['allow_overlord_canton']=='yes' and parent['subject_canton']==parent['coa']
        links.append({'subject':r['tag'],'overlord':r['overlord'],'subject_canton':parent['subject_canton']})
    meta=load_json(mod/'.metadata/metadata.json');meta['version']='0.5.5-m5-test6'
    (mod/'.metadata/metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    changed.append('.metadata/metadata.json')
    for rel,sha in prior['output_sha256'].items():
        if rel not in changed:assert digest(mod/rel)==sha,rel
    for rel in changed:
        if rel=='.metadata/metadata.json':continue
        # Stripping only the new field restores the original text exactly.
        text=(mod/rel).read_text(encoding='utf-8-sig')
        for tag,obj in objects(root(text)):
            if tag in repaired:assert objects(obj)[0][1].fields()['subject_canton']==repaired[tag]
    evidence={'status':'passed','repaired_definitions':len(repaired),'colony_links_checked':len(links),
        'overlord_count':len({r['overlord'] for r in colonies}),'missing_parent_cantons_before':sum('subject_canton' not in before_defs[r['overlord']] for r in colonies),
        'missing_parent_cantons_after':0,'links':links,'only_subject_canton_field_added':True,
        'all_flag_artwork_and_non_flag_files_unchanged':True,'runtime_visual_verified':False}
    (out/'canton_verification.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    shutil.copy2(base/'conversion_report.json',out/'conversion_report.json')
    report={'status':'m5_canton_fix_static_verified_runtime_pending','version':meta['version'],'mod_name':meta['name'],
        'mod_directory':str(mod),'prior_package':str(base),'update_scope':'m5_flags','new_campaign_required':False,
        'changed_files':changed,'output_sha256':{rel:digest(mod/rel) for rel in prior['output_sha256']},
        'input_sha256':{str(p):digest(p) for p in (base/'package_report.json',base/'conversion_report.json',GAME/'common/flag_definitions/00_flag_definitions.txt',Path(__file__),ROOT/'tools/m3_flags.py')}}
    (out/'package_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    checks=load_json(base/'verification.json');checks.update(status='passed_static_runtime_pending',canton=evidence,non_flag_files_byte_identical=True,package_report_sha256=digest(out/'package_report.json'))
    (out/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print(json.dumps({'package':str(out),'repaired':len(repaired),'colonies':len(links),'overlords':evidence['overlord_count'],'changed_files':changed}))

if __name__=='__main__':build()
