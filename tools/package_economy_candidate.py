"""Assemble a fresh economic test mod; never install or mutate its verified inputs."""
import argparse
import json
from pathlib import Path
import shutil
from m3_world import digest


def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def build(base,economy,output,version='0.5.0-economy-test2',name=None):
    if output.exists(): raise ValueError('Refusing to overwrite a package')
    report=load(base/'package_report.json'); source=Path(report['mod_directory'])
    manifest=load(economy/'manifest.json')
    for rel,sha in report['output_sha256'].items():
        if digest(source/rel)!=sha: raise ValueError('Base package changed: '+rel)
    for rel,sha in manifest['outputs'].items():
        if digest(economy/rel)!=sha: raise ValueError('Economy candidate changed: '+rel)
    if load(economy/'verification.json')['status']!='passed_static_runtime_pending':
        raise ValueError('Economy verification missing')
    folder='eu5_economy_test'
    name=name or 'EU5 World 1780 - Economy TEST '+version
    mod=output/folder
    shutil.copytree(source,mod)
    shutil.copytree(economy/'overlay',mod,dirs_exist_ok=True)
    metadata=load(mod/'.metadata/metadata.json')
    metadata.update(name=name,id='eu5-personal-economy-test',version=version,
                    short_description='Population-aware economy, production technology and regular armies. New campaign required. Runtime balance pending.')
    write(mod/'.metadata/metadata.json',metadata)
    (output/(folder+'.mod')).write_text(f'name="{name}"\nversion="{version}"\nsupported_version="1.13.11"\npath="mod/{folder}"\n',encoding='utf-8-sig')
    overlay_files={p.relative_to(economy/'overlay').as_posix() for p in (economy/'overlay').rglob('*') if p.is_file()}
    unchanged=set(report['output_sha256'])-overlay_files-{'.metadata/metadata.json'}
    for rel in unchanged:
        if digest(mod/rel)!=report['output_sha256'][rel]: raise ValueError('Unrelated package change: '+rel)
    for rel in overlay_files:
        if digest(mod/rel)!=digest(economy/'overlay'/rel): raise ValueError('Overlay copy mismatch: '+rel)
    # User explicitly declined a new transit treaty. Check all diplomatic history bytes.
    for directory in ('common/history/treaties','common/history/diplomacy','common/history/power_blocs'):
        before={p.relative_to(source).as_posix():digest(p) for p in (source/directory).rglob('*') if p.is_file()}
        after={p.relative_to(mod).as_posix():digest(p) for p in (mod/directory).rglob('*') if p.is_file()}
        if before!=after: raise ValueError('Diplomacy changed despite user policy: '+directory)
    (output/'README.txt').write_text(
        '经济候选包：需新开局，尚未通过游戏内生活水平与财政验收。\n'
        '保留现有外交；波西米亚保留 406 营；不会自动新增贸易过境权。\n'
        '本工具没有安装模组。独立测试时只启用本包，不要与旧人口包同时启用。\n'
        '本包已经包含人口、识字率、文化、国界和政治基础文件。\n'
        '应记录第 1 周、3 个月、1 年和 3 年存档，检查饥荒、失业、生活水平、市场连接及财政。\n'
        '完整设计与限制见仓库 docs/ECONOMY_POPULATION_BALANCE_20261001.md。\n',encoding='utf-8-sig')
    result={'status':'standalone_candidate_static_verified_not_installed_runtime_pending','version':version,
            'mod_name':name,'mod_directory':str(mod.resolve()),'base_package':str(base.resolve()),
            'economy_candidate':str(economy.resolve()),'preserved_base_files':len(unchanged),
            'diplomacy_unchanged':True,'population_and_literacy_preserved':True,
            'input_sha256':{str((base/'package_report.json').resolve()):digest(base/'package_report.json'),
                            str((economy/'manifest.json').resolve()):digest(economy/'manifest.json'),
                            str(Path(__file__).resolve()):digest(Path(__file__))},
            'output_sha256':{p.relative_to(mod).as_posix():digest(p) for p in sorted(mod.rglob('*')) if p.is_file()}}
    write(output/'package_report.json',result)
    return {k:v for k,v in result.items() if not k.endswith('sha256')}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('base','economy','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--version',default='0.5.0-economy-test2')
    parser.add_argument('--name')
    a=parser.parse_args();print(json.dumps(build(a.base,a.economy,a.output,a.version,a.name)))
