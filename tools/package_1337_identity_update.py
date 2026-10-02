"""Package the validated fresh 1337 conversion under the existing test mod identity."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
from converter_project import read,write,digest
from converter_source_world import files
from verify_converter_identity import verify,verify_output
from v3_startup_validation import culture_modifiers,flag_assets,validate_state_history,validate_opening_war_removals
from economy_model import definitions
from build_m3_world import load_localization


def build(root,run,rules,previous,game,eu5,out):
    root,run,rules,previous,game,eu5,out=map(lambda p:Path(p).resolve(),(root,run,rules,previous,game,eu5,out))
    if out.exists():raise ValueError('Package already exists')
    old=read(previous/'package_report.json');prior=read(run/'complete/package_report.json')
    assert prior['source_date']=='1337.4.1' and prior['source_sha256']==old['source_sha256']
    source=Path(prior['mod_directory']);assert files(source)==prior['output_sha256']
    validation=verify(rules,game,eu5);world=verify_output(run,game)
    mod=out/'eu5_m5_1337_test';shutil.copytree(source,mod)
    shutil.copytree(rules/'assets',mod,dirs_exist_ok=True)
    version='0.6.3-1337-test4';meta=read(mod/'.metadata/metadata.json')
    legacy=read(Path(old['mod_directory'])/'.metadata/metadata.json')
    meta.update(name=old['mod_name'],id=legacy['id'],version=version,short_description='1337 source; updated culture framework, historical homelands, religion icons and flags. New campaign required; runtime verification pending.')
    write(mod/'.metadata/metadata.json',meta)
    after=files(mod);changed={p for p,sha in after.items() if prior['output_sha256'].get(p)!=sha}
    assert all(p=='.metadata/metadata.json' or p.startswith(('common/cultures/','common/religions/','common/discrimination_traits/','common/discrimination_trait_groups/','localization/replace/','gfx/interface/icons/religion_icons/')) for p in changed),changed
    assert all(after[p]==sha for p,sha in prior['output_sha256'].items() if p.startswith('common/history/'))
    culture_modifiers(game,mod,write=True);flag_assets(game,mod,eu5)
    cultures=set(definitions(game/'common/cultures'))|set(definitions(mod/'common/cultures'))
    validate_state_history((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig'),cultures)
    validate_opening_war_removals(mod,read(run/'war_mapping.json'))
    for lang,value in [('english','Bedouin'),('simp_chinese','贝都因')]:
        loc=load_localization(game/'localization'/lang)
        loc.update(load_localization(mod/'localization'/lang));loc.update(load_localization(mod/'localization/replace'/lang))
        assert loc['bedouin']==value
    descriptor=f'name="{old["mod_name"]}"\nversion="{version}"\nsupported_version="1.13.11"\npath="mod/eu5_m5_1337_test"\n'
    (out/'eu5_m5_1337_test.mod').write_text(descriptor,encoding='utf-8-sig')
    write(out/'identity_verification.json',dict(rules=validation,world=world,history_identical_to_verified_rebuild=True,bedouin_labels=['Bedouin','贝都因'],prior_countries=old['summary']['countries'],countries=prior['summary']['countries']))
    report=dict(prior,version=version,mod_name=old['mod_name'],mod_directory=str(mod),previous_package=str(previous),verified_run=str(run),new_campaign_required=True,source_population_conserved=True,population_mode='preserve',rules_sha256=digest(rules/'manifest.json'),output_sha256=files(mod),input_sha256={str(run/'complete/package_report.json'):digest(run/'complete/package_report.json'),str(previous/'package_report.json'):digest(previous/'package_report.json'),str(rules/'manifest.json'):digest(rules/'manifest.json')})
    write(out/'package_report.json',report)
    (out/'README.txt').write_text('1337 test4：更新通用文化与宗教设置，文化名恢复贝都因。\n使用最新通用流程重新生成世界；国家数由1954变为1950，含原生文化归并与当前归属规则的结果。总人口保持394557661。\n保留原模组ID和名称；必须新开1836沙盒档。旧存档不会迁移。静态验证通过，游戏内测试待完成。\n',encoding='utf8')
    return dict(package=str(out),version=version,files=len(report['output_sha256']),verification=world)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('root','run','rules','previous','game','eu5','out'):p.add_argument('--'+n,type=Path,required=True)
    print(build(**vars(p.parse_args())))
