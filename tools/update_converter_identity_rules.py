"""Upgrade a reusable rules bundle from verified identity assets, never campaign history."""
import argparse
import json
import shutil
from pathlib import Path
from converter_project import read,write,digest
from build_m3_world import block,load_localization
from build_m2_prototype import objects
from pdx_text import root as parse
from converter_identity_policy import clean_label

KINDS=('cultures','religions','discrimination_traits','discrimination_trait_groups')


def upgrade(root,base,package,out,game):
    root,base,package,out,game=map(lambda p:Path(p).resolve(),(root,base,package,out,game))
    if out.exists():raise ValueError('Output must be a new directory')
    manifest=read(base/'manifest.json')
    for rel,sha in manifest['files'].items():
        if not (base/rel).resolve().is_relative_to(base):raise ValueError('Invalid rules path')
        if digest(base/rel)!=sha:raise ValueError('Changed base rule: '+rel)
    report=read(package/'package_report.json');latest=Path(report['mod_directory'])
    if not latest.is_absolute():latest=package/latest
    allowed={p:sha for p,sha in report['output_sha256'].items() if p.startswith(tuple('common/'+k+'/' for k in KINDS)+('localization/','gfx/interface/icons/religion_icons/'))}
    for rel,sha in allowed.items():
        if digest(latest/rel)!=sha:raise ValueError('Changed identity asset: '+rel)
    shutil.copytree(base,out,ignore=shutil.ignore_patterns('assets','manifest.json'))
    assets=out/'assets';keys=set();definitions={}
    for kind in KINDS:
        data={}
        for source in (base/'assets',latest):
            for p in sorted((source/'common'/kind).glob('*.txt')):
                data.update({k:o.text() for k,o in objects(parse(p.read_text(encoding='utf-8-sig')))})
        definitions[kind]=data;keys.update(data)
        if kind=='religions':
            from religion_palette import apply
            data.update({k:apply(k.removeprefix('eu5_religion_'),v) for k,v in data.items() if k.startswith('eu5_religion_')})
        p=assets/'common'/kind/'zz_converter_identity.txt';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(''.join(block(k,v) for k,v in sorted(data.items())),encoding='utf-8-sig')
    # Include base-game identity keys for purposeful composite display overrides.
    for kind in KINDS:
        for p in (game/'common'/kind).glob('*.txt'):keys.update(k for k,o in objects(parse(p.read_text(encoding='utf-8-sig'))))
    labels={}
    for lang in ('english','simp_chinese'):
        loc={}
        for source in (game,base/'assets',latest):
            for directory in (source/'localization'/lang,source/'localization/replace'/lang):loc.update(load_localization(directory))
        current_labels=read(root/'config/personal/m5_culture_framework.json')['labels']
        loc.update({k:v[0 if lang=='english' else 1] for k,v in current_labels.items()})
        labels[lang]={k:clean_label(v) for k,v in loc.items() if k in keys}
        p=assets/f'localization/replace/{lang}/zz_converter_identity_l_{lang}.yml';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('l_'+lang+':\n'+''.join(' '+k+':0 '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in sorted(labels[lang].items())),encoding='utf-8-sig')
    for source in (base/'assets',latest):
        directory=source/'gfx/interface/icons/religion_icons'
        if directory.exists():shutil.copytree(directory,assets/'gfx/interface/icons/religion_icons',dirs_exist_ok=True)
    from religion_icon_texture import compile_icon
    for icon in (assets/'gfx/interface/icons/religion_icons').glob('eu5_religion_*.dds'):
        compile_icon(icon,icon)
    mapping=read(base/'culture_mapping.json');before=mapping.copy()
    history=read(root/'config/personal/m5_historical_homelands.json')
    policies={}
    for name in ('m5_culture_identity_corrections','m5_culture_framework'):
        policy=read(root/f'config/personal/{name}.json');policies[name]=policy
        mapping.update(policy['mappings'])
        replaced=set(policy['assets'])
        history['entries']=[r for r in history['entries'] if r['culture'] not in replaced]
        for culture,spec in policy['assets'].items():
            history['entries'].append(dict(culture=culture,status='candidate_core' if spec['homelands'] else 'deferred',states=spec['homelands'],anchors={a:spec['homelands'] for a in spec['anchors']},sources=spec['homeland_sources'],limitation=spec['homeland_basis']))
    write(out/'culture_mapping.json',mapping)
    # Runtime reads a self-contained policy, not an audit under .local or a save snapshot.
    # Do not export the pre-1830 Luyi design unconditionally to later saves.
    previous_policy=read(base/'identity_policy.json') if (base/'identity_policy.json').exists() else {}
    lozi=previous_policy.get('dated_mappings',{}).get('lozi_culture',{}).get('target',before.get('lozi_culture'))
    if lozi and lozi!=mapping.get('lozi_culture'):
        spec=policies['m5_culture_framework']['assets']['eu5_framework_lozi']
        history['entries'].append(dict(culture=lozi,status='candidate_core',states=spec['homelands'],anchors={a:spec['homelands'] for a in spec['anchors']},sources=spec['homeland_sources'],limitation='Conservative historical-core reuse; later source identity is retained from the existing cross-save review.'))
    write(out/'identity_homelands.json',history)
    write(out/'identity_policy.json',dict(schema=1,revision='m5-framework-test33',mapping_precedence=['existing cross-save reviews','explicit M5 identity corrections','explicit M5 framework decisions'],ordinary_homelands='historical_core_with_current_local_presence',migrant_homelands='strict_statewide_majority',unknown_identity='stop_for_review',limitations=policies['m5_culture_framework']['asset_limitations'],date_sensitive={'eu5_framework_lozi':'Pre-Makololo Luyi design; source-language setting retained, not a simulated historical language shift.'}))
    policy=read(out/'identity_policy.json')
    policy['dated_mappings']={'lozi_culture':dict(from_year=1830,target=lozi,basis='Conservative cutoff for the explicitly pre-1830 Luyi design; retain existing cross-save source identity thereafter, without simulating the date of language change.')} if lozi else {}
    write(out/'identity_policy.json',policy)
    shutil.copy2(root/'config/personal/m4_demographics.json',out/'config/personal/m4_demographics.json')
    available=set(definitions['cultures'])
    for p in (game/'common/cultures').glob('*.txt'):available.update(k for k,o in objects(parse(p.read_text(encoding='utf-8-sig'))))
    if set(mapping.values())-available:raise ValueError('Missing culture assets: '+str(sorted(set(mapping.values())-available)))
    result=dict(revision='m5-framework-test33',mapping_count=len(mapping),changed_mappings={s:dict(before=before.get(s),after=t) for s,t in mapping.items() if before.get(s)!=t},asset_counts={k:len(v) for k,v in definitions.items()},historical_core_entries=sum(r['status']=='candidate_core' for r in history['entries']),only_identity_localizations=True,source_package_report_sha256=digest(package/'package_report.json'),runtime_verified=False)
    write(out/'identity_update_report.json',result)
    manifest['identity_revision']=result['revision'];manifest['files']={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()}
    # Permit an in-place identity repair only if all conversion policies,
    # mappings and history evidence are byte-identical to the previous rules.
    def substantive(files):
        return {k:v for k,v in files.items() if not k.startswith('assets/') and k!='identity_update_report.json'}
    prior=read(base/'manifest.json')
    manifest['identity_repair_predecessors']=(prior.get('identity_repair_predecessors',[])+[digest(base/'manifest.json')]
        if substantive(prior['files'])==substantive(manifest['files']) else [])
    write(out/'manifest.json',manifest)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('root','base','package','out','game'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();print(json.dumps(upgrade(**vars(args)),ensure_ascii=False,indent=2))
