"""Build a local desktop distribution using the installed Python runtime and MSVC.

No installer, registry changes or global package installation. Dependency DLL closure
is copied from the same Python distribution. Local generated rules can contain
game-derived assets and absolute paths; this output is not a public release.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from converter_project import read,write,digest


def copy_language_docs(root,out):
    from prepare_release import copy_public_docs
    copy_public_docs(root,out)
    with (out/'README.txt').open('a',encoding='utf-8') as guide:
        guide.write('\nEnglish: run EU5Converter.exe and choose English under 语言 / Language.\n'
                    'Choose Game display language on import/export and set the same language in Victoria 3.\n'
                    'See docs/CONVERTER_WORKBENCH.en.md and docs/LOCALIZATION.en.md.\n')


def refresh_rules(root,out):
    """Refresh the default rules too; code-only refresh used to leave identities stale."""
    from datetime import datetime
    root,out=Path(root).resolve(),Path(out).resolve()
    source=root/'.local/converter/rules';target=out/'data/rules'
    manifest=read(source/'manifest.json')
    for rel,sha in manifest['files'].items():
        p=(source/rel).resolve()
        if not p.is_relative_to(source.resolve()) or digest(p)!=sha:raise ValueError('Invalid default rules: '+rel)
    if target.exists() and digest(source/'manifest.json')==digest(target/'manifest.json'):return
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    staged=out/'data'/('rules-staged-'+stamp)
    shutil.copytree(source,staged)
    if target.exists():target.rename(out/'data'/('rules-backup-'+stamp))
    staged.rename(target)

def seal(out,archive=None):
    out=Path(out).resolve()
    payload=[]
    for path in out.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(out)
        if '__pycache__' in rel.parts or path.suffix in ('.pyc','.obj','.pdb'):continue
        if rel.parts[0]=='data' and not (rel.parts[1]=='rules' or rel.as_posix()=='data/defaults.json'):continue
        if rel.as_posix()=='build_manifest.json':continue
        payload.append(path)
    write(out/'build_manifest.json',dict(version='0.12.2',python=sys.version,files={p.relative_to(out).as_posix():digest(p) for p in sorted(payload)}))
    if archive:
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(payload)+[out/'build_manifest.json']:z.write(p,out.name+'/'+p.relative_to(out).as_posix())
        print(str(Path(archive).resolve()),flush=True)

def refresh(root,out,include_local_rules=False):
    root,out=Path(root).resolve(),Path(out).resolve()
    if not (out/'runtime/python.exe').exists():raise ValueError('No existing packaged runtime')
    if include_local_rules:refresh_rules(root,out)
    for path in (root/'tools').glob('*.py'):
        if not path.name.startswith('test_'):shutil.copy2(path,out/'tools'/path.name)
    shutil.copytree(root/'tools/converter_ui',out/'tools/converter_ui',dirs_exist_ok=True)
    shutil.copytree(root/'tools/converter_locales',out/'tools/converter_locales',dirs_exist_ok=True)
    shutil.copytree(root/'config',out/'config',dirs_exist_ok=True)
    for name in ('EU5ToVic3Converter.exe','rakaly.dll'):shutil.copy2(root/'build/Release-Windows/EU5ToVic3'/name,out/'native'/name)
    (out/'docs').mkdir(exist_ok=True)
    shutil.copy2(root/'docs/CONVERTER_WORKBENCH.md',out/'docs/CONVERTER_WORKBENCH.md')
    shutil.copy2(root/'docs/CONVERTER_SOURCE_CORES.md',out/'docs/CONVERTER_SOURCE_CORES.md')
    write(out/'data/defaults.json',dict(candidate_paths=[],game='',eu5=''))
    (out/'README.txt').write_text('EU5 → Victoria 3 桌面转换器 0.12.2\n\n双击 EU5Converter.exe 打开独立桌面窗口。无需浏览器，无需另装 Python。\n完整保留软件目录，不要单独复制 EXE。\n首次使用点击“准备转换规则”，选择自己的游戏安装和 V3 原版 1836.1.1 开局存档。\n支持原始存档转换、地图选择、参数调试、合并、撤销和导出。\n耕地 ≤ 3、严重失业和食物不足分别提醒。\n操作失败弹出具体原因并保存日志。详细说明见 docs/CONVERTER_WORKBENCH.md。\n',encoding='utf-8')
    copy_language_docs(root,out)

def package(root,out,include_local_rules=False):
    root,out=Path(root).resolve(),Path(out).resolve();base=Path(sys.base_prefix)
    if out.exists():raise ValueError('Distribution already exists')
    runtime=out/'runtime';runtime.mkdir(parents=True)
    for name in ('python.exe','pythonw.exe'):
        if (base/name).exists():shutil.copy2(base/name,runtime/name)
    for path in base.glob('*.dll'):shutil.copy2(path,runtime/path.name)
    shutil.copytree(base/'DLLs',runtime/'DLLs',ignore=shutil.ignore_patterns('*.pdb','*.lib'))
    version=f'{sys.version_info.major}{sys.version_info.minor}'
    with zipfile.ZipFile(runtime/f'python{version}.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in (base/'Lib').rglob('*.py'):
            rel=path.relative_to(base/'Lib')
            if any(p in ('site-packages','test','tests','__pycache__','idlelib','ensurepip','venv') for p in rel.parts):continue
            z.write(path,rel.as_posix())
    for name in ('numpy','numpy.libs','PIL'):
        source=base/'Lib/site-packages'/name
        shutil.copytree(source,runtime/'Lib/site-packages'/name,ignore=shutil.ignore_patterns('__pycache__','tests','*.pyc','*.pdb','*.lib'))
    # Include distribution metadata/license files for the bundled third-party libraries.
    for pattern in ('numpy-*.dist-info','pillow-*.dist-info'):
        for source in (base/'Lib/site-packages').glob(pattern):shutil.copytree(source,runtime/'Lib/site-packages'/source.name)
    for name in ('tcl8.6','tk8.6','tcl8'):
        source=base/'Library/lib'/name
        if source.exists():shutil.copytree(source,runtime/'tcl'/name)
    if (base/'LICENSE_PYTHON.txt').exists():shutil.copy2(base/'LICENSE_PYTHON.txt',runtime/'LICENSE_PYTHON.txt')
    (runtime/f'python{version}._pth').write_text(f'python{version}.zip\nDLLs\nLib/site-packages\n../tools\nimport site\n',encoding='ascii')
    (runtime/'Lib/site-packages/sitecustomize.py').write_text('import os, sys\nfrom pathlib import Path\n_runtime=Path(sys.executable).parent\n_dll_handle=os.add_dll_directory(str(_runtime/"DLLs"))\nos.environ["TCL_LIBRARY"]=str(_runtime/"tcl/tcl8.6")\nos.environ["TK_LIBRARY"]=str(_runtime/"tcl/tk8.6")\n',encoding='utf-8')
    dumpbin=next((root/'.tools/msvc/VC/Tools/MSVC').glob('*/bin/Hostx64/x64/dumpbin.exe'))
    search=[base,base/'DLLs',base/'Library/bin',*[(runtime/'Lib/site-packages'/n) for n in ('numpy.libs','PIL')]]
    lookup={p.name.lower():p for folder in search for p in folder.glob('*.dll')}
    todo=list(runtime.rglob('*.pyd'))+list(runtime.glob('*.dll'));seen=set()
    while todo:
        binary=todo.pop();key=binary.name.lower()
        if key in seen:continue
        seen.add(key)
        r=subprocess.run([str(dumpbin),'/DEPENDENTS',str(binary)],capture_output=True,text=True,errors='replace',check=True)
        for name in re.findall(r'^\s+([\w.+-]+\.dll)\s*$',r.stdout,re.M|re.I):
            source=lookup.get(name.lower())
            if source and name.lower() not in seen:
                target=runtime/'DLLs'/source.name
                if source.resolve()!=target.resolve() and not target.exists():shutil.copy2(source,target)
                todo.append(target)
    shutil.copytree(root/'tools',out/'tools',ignore=shutil.ignore_patterns('__pycache__','test_*.py','*.html','*.ps1','*.cpp'))
    # HTML is application data, excluded only at tools root above.
    shutil.copytree(root/'tools/converter_ui',out/'tools/converter_ui',dirs_exist_ok=True)
    shutil.copytree(root/'config',out/'config')
    shutil.copytree(root/'EU5ToVic3/Data_Files',out/'EU5ToVic3/Data_Files')
    native=out/'native';native.mkdir()
    for name in ('EU5ToVic3Converter.exe','rakaly.dll'):
        shutil.copy2(root/'build/Release-Windows/EU5ToVic3'/name,native/name)
    if include_local_rules:refresh_rules(root,out)
    write(out/'data/defaults.json',dict(candidate_paths=[],game='',eu5=''))
    shutil.copy2(root/'LICENSE',out/'LICENSE')
    (out/'README.txt').write_text('EU5 → Victoria 3 桌面转换器 0.12.2\n\n双击 EU5Converter.exe 打开独立桌面窗口。无需浏览器，无需另装 Python。\n首次使用点击“准备转换规则”，从自己的游戏安装和 V3 原版开局存档生成资源。\n请完整保留软件目录。软件关闭与详细说明见 docs/CONVERTER_WORKBENCH.md。\n',encoding='utf-8')
    (out/'docs').mkdir()
    if (root/'docs/CONVERTER_WORKBENCH.md').exists():shutil.copy2(root/'docs/CONVERTER_WORKBENCH.md',out/'docs/CONVERTER_WORKBENCH.md')
    copy_language_docs(root,out)
    write(out/'build_manifest.json',dict(python=sys.version,files={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()}))
    print(str(out),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--refresh-code',action='store_true');p.add_argument('--seal',action='store_true');p.add_argument('--archive',type=Path);p.add_argument('--include-local-rules',action='store_true')
    a=p.parse_args()
    if a.seal:seal(a.out,a.archive)
    else:(refresh if a.refresh_code else package)(a.root,a.out,a.include_local_rules)
