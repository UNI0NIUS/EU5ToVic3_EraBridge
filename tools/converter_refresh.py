"""Upgrade old desktop baselines in a new package before replaying player edits."""
from collections import Counter,defaultdict
from pathlib import Path
from copy import deepcopy
import csv,re,shutil,uuid,hashlib
from converter_project import read,write,digest,apportion
from pdx_text import root,Object
from build_m2_prototype import objects
from build_m3_world import block,entry,load_localization
from economy_model import definitions

REVISION='desktop-0.12-identity-cores-economy-5'


def source_run(package,report):
    candidates=[Path(report.get('source_run') or ''),
                Path(report.get('political_run',str(Path(package)/'political'))).parent,Path(package).parent]
    return next((p for p in candidates if (p/'fresh_context.json').is_file() and (p/'source/politics.json').is_file()),None)


def country_labels(mod,game,countries,preserve_dynamic=False):
    """Remove campaign country keys from every old localization, then write once."""
    pattern=re.compile(r'^\s*([\w.-]+):\d*\s+"(.*)"\s*$')
    for p in (mod/'localization').rglob('*.yml'):
        kept=[]
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            m=pattern.match(line)
            if m:
                if preserve_dynamic:
                    if m[1].removesuffix('_ADJ') in countries or (m[1].startswith('EU5_SOURCE_NAME_') and m[1].removeprefix('EU5_SOURCE_NAME_') in countries):continue
                elif re.fullmatch(r'[A-Z0-9]{3}(?:_ADJ)?',m[1]) or m[1].startswith(('EU5_SOURCE_NAME_','EU5_DYNAMIC_SOURCE_','EU5_DYNAMIC_NAME_')):continue
            kept.append(line)
        p.write_text('\n'.join(kept)+'\n',encoding='utf-8-sig')
    for lang in ('english','simp_chinese'):
        labels=load_localization(game/'localization'/lang)
        labels.update(load_localization(mod/'localization'/lang));labels.update(load_localization(mod/'localization/replace'/lang))
        values={}
        for tag,c in countries.items():
            name=c.get('opening_name_'+lang,c.get('name_'+lang))
            if c.get('generated_uncolonized'):name=labels.get(c['culture'],name)
            if not name or name.startswith('EU5_'):raise ValueError('国家缺少名称：'+tag+'/'+lang)
            values[tag]=name;values[tag+'_ADJ']=c.get('adjective_'+lang,c.get('name_'+lang,name))
            # Old saves may retain this key in their serialized naming data.
            values['EU5_SOURCE_NAME_'+tag]=name
        p=mod/'localization/replace'/lang/('zzzz_converter_countries_l_'+lang+'.yml');p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('l_'+lang+':\n'+''.join(' '+k+':0 "'+v.replace('"','\\"')+'"\n' for k,v in sorted(values.items())),encoding='utf-8-sig')


def refresh_identity(mod,game,run,rules,countries):
    from converter_identity_policy import dated_mapping
    from converter_export import render_pops
    from package_m4_population_test import parse_pops
    context=read(run/'fresh_context.json');old=context['mapping'];policy=read(rules/'identity_policy.json')
    new=dated_mapping(read(rules/'culture_mapping.json'),policy,read(run/'source/politics.json')['date'])
    assets=rules/'assets'
    from converter_identity_assets import sync
    sync(mod,assets)
    # Definitions can appear under older filenames that sort after the new
    # bundle. Remove duplicate updated objects, preserving campaign migrants.
    for kind in ('cultures','religions','discrimination_traits','discrimination_trait_groups'):
        replaced=set(definitions(assets/'common'/kind))
        for p in (mod/'common'/kind).glob('*.txt'):
            if (assets/'common'/kind/p.name).exists():continue
            p.write_text(''.join(block(k,o.text()) for k,o in objects(root(p.read_text(encoding='utf-8-sig'))) if k not in replaced),encoding='utf-8-sig')
    weights=defaultdict(Counter)
    with (run/'demographic/staging/province_population_draft.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            sc=r['source_culture'];weights[r['target_state'],r['target_owner'],old[sc],context['religions'][r['source_religion']]][new[sc]]+=int(r['centipersons'])
    pops=parse_pops(mod/'common/history/pops/00_eu5_world.txt');updated=Counter();crosswalk=defaultdict(set)
    for sc,target in old.items():crosswalk[target].add(new.get(sc,target))
    for k,n in pops.items():
        choices=weights.get(k)
        if choices:
            for culture,number in apportion(n,choices).items():updated[k[0],k[1],culture,k[3]]+=number
        else:updated[k]+=n
    if sum(updated.values())!=sum(pops.values()):raise ValueError('身份升级人口不守恒')
    (mod/'common/history/pops/00_eu5_world.txt').write_text(render_pops(updated),encoding='utf-8-sig')
    for tag,c in countries.items():
        source=c.get('source_culture')
        if source in new:c['culture']=new[source];c['cultures']=[new[source]]
    for p in (mod/'common/country_definitions').glob('*.txt'):
        from build_m2_prototype import patch,replace_body
        body=p.read_text(encoding='utf-8-sig');edits=[]
        for tag,o in objects(root(body)):
            value=dict(o.entries()).get('cultures')
            if isinstance(value,Object) and tag in countries and countries[tag].get('cultures'):edits.append(replace_body(value,' '+' '.join(countries[tag]['cultures'])+' '))
        p.write_text(patch(body,edits),encoding='utf-8-sig')
    # Unambiguous culture renames also update characters and old homeland keys.
    replacements={k:next(iter(v)) for k,v in crosswalk.items() if len(v)==1 and k not in v}
    for folder in ('common/history/characters',):
        for p in (mod/folder).glob('*.txt'):
            body=p.read_text(encoding='utf-8-sig')
            body=re.sub(r'(\bculture\s*=\s*(?:cu:)?)'+r'([\w]+)',lambda m:m[1]+replacements.get(m[2],m[2]),body)
            p.write_text(body,encoding='utf-8-sig')
    # Recompute evidenced homelands using upgraded identities and exact source geography.
    from converter_identity_policy import homelands
    from v3_startup_validation import rewrite_homelands,culture_modifiers
    states_path=mod/'common/history/states/00_eu5_world.txt';state_text=states_path.read_text(encoding='utf-8-sig')
    inverse=defaultdict(set);lookup={p:(s,t) for s,ps in read(run/'political/province_owners.json').items() for p,t in ps.items()}
    for p,names in context['geography_mapping'].items():
        for n in names:inverse[n].add(p)
    with (run/'source/population/source_populations.csv').open(encoding='utf-8-sig',newline='') as f:source=list(csv.DictReader(f))
    home,reasons=homelands(read(rules/'identity_homelands.json'),updated,source,new,inverse,lookup,{})
    states_path.write_text(rewrite_homelands(state_text,home),encoding='utf-8-sig')
    country_labels(mod,game,countries)
    culture_modifiers(game,mod,write=True)
    return dict(policy=policy['revision'],mapping=new,changed_mappings={k:dict(before=v,after=new[k]) for k,v in old.items() if k in new and v!=new[k]},population=sum(updated.values()),homeland_pairs=sum(map(len,home.values())))


def upgrade(package,game,rules,output):
    """Cache immutable upgrades. Caller replays edits after this baseline stage."""
    package,game,rules,output=map(Path,(package,game,rules,output));report=read(package/'package_report.json')
    if not (rules/'identity_policy.json').exists():return package
    signature=REVISION+':'+digest(rules/'manifest.json')
    from converter_source_claims import REVISION as CLAIMS_REVISION
    if report.get('refresh_signature')==signature and report.get('source_claims_revision')==CLAIMS_REVISION:return package
    run=source_run(package,report)
    if run is None:return package
    politics=read(run/'source/politics.json')
    if report.get('source_sha256') and report['source_sha256']!=politics['source_sha256']:raise ValueError('旧项目与源存档政治资料不匹配，不能升级')
    request=read(run/'request.json');eu5=Path(request['eu5'])
    if (eu5/'game').exists():eu5=eu5/'game'
    from converter_pipeline import validate_rules
    validate_rules(rules/'manifest.json',game,eu5)
    key=digest(package/'package_report.json')[:16]+'-'+digest(rules/'manifest.json')[:12]+'-'+hashlib.sha256((REVISION+CLAIMS_REVISION).encode()).hexdigest()[:8]
    out=output/key
    if (out/'package_report.json').exists():return out
    if digest(run/'source/decoded.eu5')!=politics['source_sha256']:raise ValueError('源存档证据已变化，不能升级')
    from converter_world import Candidate
    # Validate before copying; don't legitimize an externally modified baseline.
    old=Candidate(package,game,output/'cache');old.verify_unchanged()
    # Leave room for long source flag filenames on Windows.
    temp=out.with_name('.building-'+uuid.uuid4().hex[:8]);temp.mkdir(parents=True)
    mod=temp/'eu5_converted';shutil.copytree(old.mod,mod);countries=deepcopy(old.countries)
    # A verified identity repair must not repeat the economic pass,
    # remap already converted POPs, or discard edits in an imported export.
    previous=report.get('refresh_signature','').removeprefix(REVISION+':')
    if report.get('refresh_signature')==signature or (report.get('refresh_signature','').startswith(REVISION+':') and previous in read(rules/'manifest.json').get('identity_repair_predecessors',[])):
        from converter_identity_assets import sync
        from converter_identity_audit import verify
        for name in ('identity_refresh.json','source_claims.json','opening_balance.json','command_capacity_verification.json','dynamic_identity_manifest.json'):
            if (package/name).exists():shutil.copy2(package/name,temp/name)
        write(temp/'identity_asset_refresh.json',sync(mod,rules/'assets'))
        country_labels(mod,game,countries,preserve_dynamic=True)
        from converter_identity_repair import repair
        write(temp/'identity_repair.json',repair(mod,game,run))
        if report.get('source_claims_revision')!=CLAIMS_REVISION:
            from converter_source_claims import install as claims
            from converter_identity_policy import dated_mapping
            selected=dated_mapping(read(rules/'culture_mapping.json'),read(rules/'identity_policy.json'),politics['date'])
            prior=read(package/'source_claims.json') if (package/'source_claims.json').exists() else None
            write(temp/'source_claims.json',claims(mod,game,run,rules,countries,selected,previous=prior))
        write(temp/'identity_verification.json',verify(mod,game,countries))
        report.update(mod_directory='eu5_converted',version='0.12.2',source_claims_revision=CLAIMS_REVISION,countries=countries,source_run=str(run.resolve()),refresh_signature=signature,
                      output_sha256={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()},upgraded_from=str(package.resolve()))
        write(temp/'package_report.json',report);temp.rename(out)
        return out
    identity=refresh_identity(mod,game,run,rules,countries);write(temp/'identity_refresh.json',identity)
    from converter_identity_repair import repair
    write(temp/'identity_repair.json',repair(mod,game,run))
    mapping=read(run/'political/conversion_report.json');mapping['countries']=countries
    from m5_dynamic_identity import apply
    write(temp/'dynamic_identity_manifest.json',apply(mod,game,mapping,refresh_legacy_names=False))
    from converter_source_claims import install as claims
    write(temp/'source_claims.json',claims(mod,game,run,rules,countries,identity['mapping'],previous=read(package/'source_claims.json') if (package/'source_claims.json').exists() else None))
    from converter_opening_balance import install as balance
    write(temp/'opening_balance.json',balance(mod,game,rules,countries,run))
    from converter_command_capacity import install as commands
    write(temp/'command_capacity_verification.json',commands(game,mod))
    from converter_identity_audit import verify
    write(temp/'identity_verification.json',verify(mod,game,countries))
    report.update(mod_directory='eu5_converted',countries=countries,source_run=str(run.resolve()),refresh_signature=signature,version='0.12.2',source_claims_revision=CLAIMS_REVISION,identity_policy=identity['policy'],runtime_verified=False,
                  output_sha256={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()},upgraded_from=str(package.resolve()))
    report.pop('political_run',None)
    write(temp/'package_report.json',report);temp.rename(out)
    return out
