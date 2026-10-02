"""Native import diagnostics and exact, ordered installed-mod discovery."""
import json
from pathlib import Path
import re
import subprocess
from converter_project import read,write
from pdx_text import root

def import_error(run,code):
    path=Path(run)/'log.txt'
    lines=path.read_text(encoding='utf-8-sig',errors='replace').splitlines() if path.exists() else []
    errors=[line.split('[ERROR]',1)[-1].strip() for line in lines if '[ERROR]' in line]
    return '\n'.join(errors[-3:]) if errors else f'原生导入器退出，代码 {code}；请查看 log.txt 和 conversion.log'

def source_mods(decoded):
    # Metadata is at the start; cap reads rather than scanning a multi-GB world.
    with Path(decoded).open(encoding='utf-8-sig') as f:head=f.read(16*1024*1024)
    match=re.search(r'\blatest_mods_used\s*=\s*\{((?:"(?:\\.|[^"\\])*"|[^{}])*)\}',head)
    if not match:raise ValueError('无法读取存档模组清单；请手动填写模组目录。')
    return list(root(match.group(1)).entries())

def discover_mods(required,installation,extra_roots=()):
    installation=Path(installation).resolve()
    roots=[installation.parent.parent/'workshop/content/3450310',installation/'mod',installation/'game/mod',*map(Path,extra_roots)]
    found={}
    for folder in roots:
        for metadata in folder.glob('*/.metadata/metadata.json'):
            try:info=read(metadata)
            except (OSError,ValueError):continue
            key=(info.get('name'),info.get('version'))
            found.setdefault(key,set()).add(metadata.parent.parent.resolve())
    result=[]
    for name,version in required:
        matches=found.get((name,version),set())
        if len(matches)!=1:
            why='没有找到' if not matches else '发现多个匹配目录，无法确定使用哪一个'
            raise ValueError(f'存档需要模组 {name} {version}，但本机{why}。请在导入窗口添加正确的模组目录。')
        result.append(str(next(iter(matches))))
    return result

def audit(executable,original,installation,run,request):
    run=Path(run);decoded=run/'source/decoded.eu5'
    def invoke(save,mods,decode):
        command=[str(executable),'--audit-eu5',str(save),'--eu5-dir',str(installation),'--report-dir',str(run/'source/audit'),'--building-pop-policy','P001']
        if decode:command+=['--decoded-save',str(decoded)]
        for mod in mods:command+=['--mod',str(Path(mod).resolve())]
        result=subprocess.run(command,cwd=run,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return result.returncode,import_error(run,result.returncode) if result.returncode else ''
    code,error=invoke(original,request.get('mods',[]),True)
    if code and 'Supplied mod names/versions differ' in error and not request.get('mods') and request.get('auto_mods',True):
        required=source_mods(decoded);mods=discover_mods(required,installation)
        write(run/'source/resolved_mods.json',dict(basis='Exact name and version; order preserved from source latest_mods_used',required=required,directories=mods))
        print('Automatically resolved mods: '+', '.join(n+' '+v for n,v in required),flush=True)
        code,error=invoke(decoded,mods,False)
    if code:
        if 'Supplied mod names/versions differ' in error:error='存档使用的模组与所选目录不一致。请按存档版本添加对应模组目录。\n'+error
        raise ValueError(error+'\n原生导入日志：'+str(run/'log.txt'))
