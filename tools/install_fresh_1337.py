"""Install the verified 1337 test separately; preserve the 1780 installation."""
from build_fresh_1337 import *
from datetime import datetime,timezone

def install(update_from=None):
 package=RUN/'complete';report=read(package/'package_report.json');source=Path(report['mod_directory'])
 assert report['status']=='passed_static_runtime_pending'
 for name,sha in report['input_sha256'].items():
  if digest(Path(name))!=sha:raise ValueError('Input changed after verification: '+name)
 assert files(source)==report['output_sha256']
 base=Path.home()/'Documents/Paradox Interactive/Victoria 3/mod';target=(base/'eu5_m5_1337_test').resolve();descriptor=base/'eu5_m5_1337_test.mod'
 assert target.parent==base.resolve() and target.name=='eu5_m5_1337_test'
 previous=None
 if update_from:
  previous=read(Path(update_from)/'package_report.json')
  assert previous['mod_name']==report['mod_name'] and previous['version']!=report['version']
  assert files(target)==previous['output_sha256'],'Installed mod changed since prior release; refusing overwrite'
  assert digest(descriptor)==digest(Path(update_from)/descriptor.name),'Descriptor changed since prior release'
  assert set(previous['output_sha256'])<=set(report['output_sha256']),'Update requires file deletion; refusing'
 elif target.exists() or descriptor.exists():raise ValueError('Existing 1337 installation; refuse unreviewed overwrite')
 prior=base/'eu5_economy_test';before=files(prior);pointer=ROOT/'.local/m5/installation-latest.json';pointer_sha=digest(pointer)
 shutil.copytree(source,target,dirs_exist_ok=bool(update_from));shutil.copyfile(package/descriptor.name,descriptor)
 assert files(target)==report['output_sha256']
 assert files(prior)==before and digest(pointer)==pointer_sha
 write(RUN/'installation.json',dict(status='installed_static_verified_runtime_pending',version=report['version'],name=report['mod_name'],package=str(package),target=str(target),verified_files=len(report['output_sha256']),previous_1780_unchanged=True,playset_changed=False,new_campaign_required=True,previous_1337_backup=str(update_from) if update_from else None,timestamp=datetime.now(timezone.utc).isoformat()))
 print(json.dumps(read(RUN/'installation.json'),ensure_ascii=False))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--update-from',type=Path)
 install(parser.parse_args().update_from)
