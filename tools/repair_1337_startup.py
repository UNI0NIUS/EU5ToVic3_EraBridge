"""Prepare a hash-checked test1 hotfix without rebuilding reviewed world data."""
from build_fresh_1337 import *
from build_m3_world import entry
from v3_startup_validation import rewrite_homelands, validate_state_history, culture_modifiers, flag_assets


def build():
 package=RUN/'complete';backup=RUN/'before-crash-test1';mod=package/'eu5_m5_1337_test'
 old=read((backup if backup.exists() else package)/'package_report.json')
 assert old['version']=='0.6.0-1337-test1'
 if backup.exists():
  assert files(backup/'eu5_m5_1337_test')==old['output_sha256']
  changed={p for p,sha in files(mod).items() if old['output_sha256'].get(p)!=sha}
  assert changed<={'common/history/states/00_eu5_world.txt','common/static_modifiers/zz_eu5_culture_runtime.txt'},changed
 else:
  assert files(mod)==old['output_sha256']
  shutil.copytree(package,backup)
  shutil.copyfile(RUN/'installation.json',backup/'installation.json')
 crash=Path.home()/'Documents/Paradox Interactive/Victoria 3/crashes/victoria3_01260902_142330'
 evidence=RUN/'crash-review-test1'
 for name in ['exception.txt','meta.yml']:
  shutil.copyfile(crash/name,evidence/name)
 home=defaultdict(set)
 for row in read(RUN/'homeland_manifest.json'):home[row['state']].add(row['culture'])
 repairs=[]
 for destination in [mod]:
  path=destination/'common/history/states/00_eu5_world.txt';before=(backup/'eu5_m5_1337_test/common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')
  cultures=defs(destination,'cultures');states=[];removed=[];actions_before=[]
  # One-time removal of precisely the test1 regex debris. Future builds reject it.
  for state,obj in objects(root(before).fields()['STATES']):
   body=[]
   for key,value in obj.entries():
    if key is None:
     assert isinstance(value,str) and value.startswith(':') and value[1:] in cultures,(state,value)
     removed.append([state,value]);continue
    body.append(entry(key,value))
    if key!='add_homeland':actions_before.append((state,key,value.text().strip() if isinstance(value,Object) else value))
   states.append(block(state,''.join(body)))
  after=rewrite_homelands(block('STATES',''.join(states)),home)
  count=validate_state_history(after,cultures)
  actions_after=[(state,key,value.text().strip() if isinstance(value,Object) else value)
                 for state,obj in objects(root(after).fields()['STATES']) for key,value in obj.entries() if key!='add_homeland']
  assert actions_before==actions_after,'Non-homeland state action changed'
  assert count==sum(map(len,home.values()))
  text(path,after)
  modifiers=culture_modifiers(GAME,destination,write=True)
  flag_repairs=flag_assets(GAME,destination,EU5)
  repairs.append(dict(mod=str(destination),removed_bare_tokens=len(removed),homelands=count,added_modifier_definitions=modifiers,flag_repairs=flag_repairs))
 changed={p for p,sha in files(mod).items() if old['output_sha256'].get(p)!=sha}
 assert changed=={'common/history/states/00_eu5_world.txt','common/static_modifiers/zz_eu5_culture_runtime.txt'},changed
 report=dict(status='fixed_static_runtime_pending',crash=str(crash),old_version=old['version'],new_version='0.6.1-1337-test2',
             confirmed_faults=['homeland regex left bare :culture tokens','new homeland effects omitted cu: scope','custom culture static modifier definitions missing'],
             crash_causality='Confirmed script defects immediately precede crash; unsymbolized access violation does not prove exclusive cause; user runtime retest required',
             memory_at_crash=dict(system_memory_available_mb=1252,swap_available_mb=278),
             repairs=repairs,reviewed_world_data_preserved=True,backup=str(backup),
             evidence_sha256={str(p):digest(p) for p in evidence.iterdir() if p.is_file()})
 write(RUN/'startup_hotfix.json',report)
 print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':build()
