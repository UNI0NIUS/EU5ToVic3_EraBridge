"""Stage a bounded, reversible patch for an existing converted mod."""
import argparse
from pathlib import Path
import shutil
from converter_command_capacity import render
from converter_project import digest,read,write


def stage(game,mod,output):
    game,mod,output=Path(game).resolve(),Path(mod).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('Patch output already exists')
    files,report=render(game,mod);records={}
    for rel,text in files.items():
        original=mod/rel;target=output/'overlay'/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8-sig')
        records[rel]=dict(before=digest(original) if original.exists() else None,after=digest(target))
        if original.exists():
            backup=output/'backup'/rel;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,backup)
    write(output/'patch.json',dict(mod=str(mod),game=str(game),files=records,policy=report))
    return report


def apply(output):
    output=Path(output).resolve();manifest=read(output/'patch.json');mod=Path(manifest['mod']).resolve()
    for rel,record in manifest['files'].items():
        target=(mod/rel).resolve();source=(output/'overlay'/rel).resolve()
        if not target.is_relative_to(mod) or not source.is_relative_to(output/'overlay'):raise ValueError('Invalid patch path')
        if digest(source)!=record['after']:raise ValueError('Patch changed: '+rel)
        current=digest(target) if target.exists() else None
        if current not in (record['before'],record['after']):raise ValueError('Mod changed since staging: '+rel)
    for rel,record in manifest['files'].items():
        target=mod/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(output/'overlay'/rel,target)
        if digest(target)!=record['after']:raise ValueError('Patch verification failed: '+rel)
    write(output/'applied.json',dict(mod=str(mod),files=list(manifest['files']),verified=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--game');p.add_argument('--mod');p.add_argument('--output',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    if a.apply:apply(a.output)
    else:print(stage(a.game,a.mod,a.output))
