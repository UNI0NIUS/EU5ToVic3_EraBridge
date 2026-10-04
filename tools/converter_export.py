"""Export an isolated candidate, applying reviewed decisions to real game history."""
from converter_i18n import Message
from collections import Counter, defaultdict
from pathlib import Path
import json
import math
import re
import shutil
import uuid
from converter_project import resolve_merges, settings, write, digest, mod_name
from converter_world import POPS, STATES, BUILDINGS, Candidate
from pdx_text import root, Object
from build_m2_prototype import objects, state_owners
from build_m3_world import block, entry
from economy_model import render_buildings, apportioned

def scoped(text, aliases):
    return re.sub(r'\b(c:|region_state:)([A-Z0-9]{3})(?![A-Za-z0-9_])',
                  lambda m:m[1]+aliases.get(m[2],m[2]),text)

def render_pops(groups):
    states=defaultdict(lambda:defaultdict(list))
    for (s,t,c,r),n in sorted(groups.items()):
        if n:states[s][t].append(block('create_pop',f'culture = {c}\nreligion = {r}\nsize = {n}'))
    return block('POPS',''.join(block('s:'+s,''.join(block('region_state:'+t,''.join(v)) for t,v in ts.items())) for s,ts in states.items()))

def rewrite_investors(text, transfers):
    """Change an investor only if its exact country AND physical host state moved."""
    patches=[]
    def walk(o):
        for _,v in o.entries():
            if not isinstance(v,Object):continue
            pairs=list(v.entries());f={k:x for k,x in pairs if k}
            if isinstance(f.get('country'),str) and isinstance(f.get('region'),str):
                old=f['country'].removeprefix('c:');new=transfers.get((f['region'],old))
                if new and new!=old:
                    body=re.sub(r'(\bcountry\s*=\s*"?c:)'+re.escape(old)+r'\b',lambda m:m[1]+new,v.text())
                    patches.append((v.start,v.end,body));continue
            walk(v)
    walk(root(text))
    for a,b,value in sorted(patches,reverse=True):text=text[:a]+value+text[b:]
    return text

def merged_buildings(rows):
    grouped=defaultdict(list)
    for row in rows:grouped[row['state'],row['owner'],row['building']].append(row)
    result=[]
    for key,items in grouped.items():
        if len(items)==1:result+=items;continue
        if any(i['guards'] for i in items) or len({tuple(i['pms']) for i in items})!=1:
            raise ValueError(Message('合并后同类建筑的生产方式或条件不一致，需先统一：{0}', '/'.join(key)))
        # Repeated ownership instructions are additive. Direct level histories are consolidated.
        bodies=[];level=0
        for index,row in enumerate(items):
            for k,v in root(row['body']).entries():
                if k=='level':level+=int(v)
                elif k in ('building','reserves','activate_production_methods'):
                    if index==0:bodies.append(entry(k,v))
                elif k=='add_ownership':bodies.append(entry(k,v))
                else:raise ValueError(Message('未知建筑合并操作，已停止导出：{0}', str(k)))
        if level:bodies.append(f'level = {level}\n')
        result.append(dict(items[0],levels=sum(i['levels'] for i in items),body=''.join(bodies)))
    return result

def export_candidate(world, project, output):
    from converter_output_language import output_language,verify as verify_language,write_guide
    language=output_language(project.get('output_language','zh-CN'))
    name=mod_name(project.get('mod_name',project.get('name',Message('EU5 通用转换项目'))))
    project=dict(project,mod_name=name)
    options=settings(project['settings']); operations=project['merges']
    world.verify_unchanged()
    preview=world.preview(options,operations)
    from converter_edits import materialize,write_geography,rewrite_hosts
    from converter_reconcile import reconcile
    original=world;world=materialize(original,operations)
    political_files,political_notes=reconcile(original,world)
    aliases=world._edit_aliases;transfers={}
    if any(r['overbuilt_arable'] for r in preview['rows']):
        raise ValueError(Message('调整后耕地小于现有农业建筑占地，请提高耕地系数或更改合并方案'))
    out=Path(output).resolve()
    if out.exists():raise ValueError(Message('输出目录已存在；每次导出必须使用新目录'))
    if out==world.mod or world.mod in out.parents:raise ValueError(Message('输出不能位于输入模组内'))
    temp=out.with_name(out.name+'.building-'+uuid.uuid4().hex[:8]);mod=temp/'eu5_converted'
    shutil.copytree(world.mod,mod)
    # Countries with source-core release territories remain defined after annexation.
    release_path=mod/'common/country_creation/00_releasable_countries.txt'
    releasable=set(dict(objects(root(release_path.read_text(encoding='utf-8-sig'))))) if release_path.exists() else set()
    def save(rel,body):
        p=mod/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body,encoding='utf-8-sig')
    try:
        # Keep survivor laws, identity and country-level literacy; populations retain their cultures.
        for path in sorted(mod.rglob('*.txt')):
            rel=path.relative_to(mod).as_posix();body=path.read_text(encoding='utf-8-sig')
            if aliases and (rel.startswith('common/history/countries/') or rel.startswith('common/history/population/')):
                containers=[]
                for key,obj in objects(root(body)):
                    containers.append(block(key,''.join(block(k+' ?',v.text()) for k,v in objects(obj) if k.removeprefix('c:') not in aliases)))
                body=''.join(containers)
            elif aliases and rel.startswith('common/country_definitions/'):
                body=''.join(block(k,v.text()) for k,v in objects(root(body)) if k not in aliases or k in releasable)
            # A source core is retained by its original nation after annexation;
            # it must not silently become a conqueror's claim.
            body=re.sub(r'(\badd_claim\s*=\s*)c:([A-Z0-9]{3})',lambda m:m[1]+'EU5_CORE_KEEP_'+m[2],body)
            body=rewrite_hosts(body,world)
            if rel!='common/scripted_effects/zz_eu5_source_cores.txt':body=scoped(body,aliases)
            body=body.replace('EU5_CORE_KEEP_','c:')
            path.write_text(body,encoding='utf-8-sig')
        for rel,body in political_files.items():save(rel,body)
        state_bodies=[]
        for key,obj in world.state_objects.items():
            s=key[2:];groups=defaultdict(list);other=[]
            for k,v in obj.entries():
                if k=='create_state':
                    t=v.fields()['country'].removeprefix('c:');groups[transfers.get((s,t),t)].append((t,v))
                else:other.append(entry(k,v) if k=='add_claim' else scoped(entry(k,v),aliases))
            bodies=[]
            for t,items in sorted(groups.items()):
                selected=next((v for old,v in items if old==t),items[0][1]);fields=selected.fields()
                provinces=sorted(p for old,v in items for p in state_owners(root(block('create_state',v.text()))))
                body=f'country = c:{t}\nowned_provinces = {{ '+ ' '.join(provinces)+' }\n'
                body+=''.join(entry(k,v) for k,v in fields.items() if k not in ('country','owned_provinces'))
                bodies.append(block('create_state',body))
            state_bodies.append(block(key,''.join(bodies+other)))
        save(STATES,block('STATES',''.join(state_bodies)))
        scaled=apportioned({k:n*options['population_multiplier'] for k,n in world.population.items()});groups=Counter()
        for (s,t,c,r),n in scaled.items():groups[s,transfers.get((s,t),t),c,r]+=n
        groups=Counter({k:n for k,n in groups.items() if n>0})
        save(POPS,render_pops(groups))
        rows=[]
        for row in world.buildings:
            row=dict(row);row['owner']=transfers.get((row['state'],row['owner']),row['owner'])
            row['body']=scoped(rewrite_hosts(row['body'],world),aliases);rows.append(row)
        rows=merged_buildings(rows);save(BUILDINGS,render_buildings(rows))
        if hasattr(world,'target'):write_geography(world,mod,options['arable_multiplier'])
        # Counted readback catches lost population, duplicate provinces and building levels.
        from package_m4_population_test import parse_pops
        from economy_model import building_rows
        actual=parse_pops(mod/POPS)
        if actual!=dict(groups):raise ValueError(Message('人口回读不守恒'))
        newowners={}
        for s,obj in objects(root((mod/STATES).read_text(encoding='utf-8-sig')).fields()['STATES']):
            newowners[s[2:]]=state_owners(obj)
        expected={p:r['country'] for r in world.parts.values() for p in r['provinces']}
        if {p:t for ps in newowners.values() for p,t in ps.items()}!=expected:raise ValueError(Message('地块归属回读不一致'))
        if newowners!=world.owners:raise ValueError(Message('地块所属州回读不一致'))
        if hasattr(world,'target'):
            from economy_model import definitions
            from build_m2_prototype import strings
            state_defs=definitions(world.game/'map_data/state_regions');state_defs.update(definitions(mod/'map_data/state_regions'))
            province_states={}
            for state,f in state_defs.items():
                for p in strings(f['provinces']) if f.get('provinces') else []:
                    p=p[0]+p[1:].upper()
                    if p in province_states:raise ValueError(Message('州定义重复地块：{0}', p))
                    province_states[p]=state
            for state,owners in newowners.items():
                if any(province_states.get(p)!=state for p in owners):raise ValueError(Message('地图州界与开局地块归属不一致：{0}', state))
            for tag,f in definitions(mod/'common/country_definitions').items():
                if tag in expected.values() and f.get('capital') and tag not in newowners.get(f['capital'],{}).values():raise ValueError(Message('首都不属于本国：{0}', tag))
        actual_buildings=building_rows(mod/BUILDINGS)
        def totals(rows):
            result=Counter()
            for r in rows:result[r['state'],r['owner'],r['building']]+=r['levels']
            return result
        if totals(actual_buildings)!=totals(world.buildings):raise ValueError(Message('各地区建筑等级回读不一致'))
        for (s,t,c,r),n in actual.items():
            if t not in newowners[s].values():raise ValueError(Message('人口所属地区不存在'))
        descriptor=f'name={json.dumps(name,ensure_ascii=False)}\nversion="0.12.2-workbench"\nsupported_version="1.13.*"\npath="mod/eu5_converted"\n'
        (temp/'eu5_converted.mod').write_text(descriptor,encoding='utf-8-sig')
        metadata=mod/'.metadata/metadata.json'
        data=json.loads(metadata.read_text(encoding='utf-8-sig')) if metadata.exists() else dict(supported_game_version='1.13.*')
        data.update(name=name,id='eu5-workbench-'+out.name,version='0.12.2',short_description='Player-configured EU5 conversion; runtime verification pending.')
        write(metadata,data)
        world.verify_unchanged()
        core_report=None
        if hasattr(original,'package') and (original.package/'source_claims.json').exists():
            from converter_source_claims import reproject
            from converter_project import read
            core_report=reproject(mod,read(original.package/'source_claims.json'))
            write(temp/'source_claims.json',core_report)
        from converter_command_capacity import install as install_command_capacity
        # Tiny synthetic export fixtures have no installed game rules.
        if hasattr(world,'game') and (world.game/'common/commander_ranks').exists():
            write(temp/'command_capacity_verification.json',install_command_capacity(world.game,mod))
        if world.report.get('startup_compatibility_revision'):
            from converter_startup_compatibility import apply as startup_compatibility
            # Recalculate the law whitelist after country edits, while keeping
            # the already reconciled war history intact.
            write(temp/'startup_compatibility.json',startup_compatibility(mod,world.game))
        if world.report.get('refresh_signature'):
            from converter_identity_audit import verify as verify_identity
            write(temp/'identity_verification.json',verify_identity(mod,world.game,{t:c for t,c in world.countries.items() if t not in aliases}))
        localization=verify_language(mod,getattr(world,'game',temp/'no-base-game'),language)
        write(temp/'localization_verification.json',localization)
        report=dict(status='passed_static_runtime_pending',mod_directory='eu5_converted',mod_name=name,output_language=language,
                    source_date=world.report.get('source_date'),source_sha256=world.report.get('source_sha256'),
                    output_sha256={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()},
                    input_fingerprint=world.fingerprint,settings=options,merges=operations,runtime_verified=False,
                    countries={t:c for t,c in world.countries.items() if t not in aliases},
                    startup_compatibility_revision=world.report.get('startup_compatibility_revision'),
                    source_run=world.report.get('source_run'),refresh_signature=world.report.get('refresh_signature'),identity_policy=world.report.get('identity_policy'),source_claims_revision=core_report['revision'] if core_report else None,
                    checks=dict(population=sum(actual.values()),provinces=len(expected),building_levels=sum(r['levels'] for r in actual_buildings)),
                    population_groups_rounded_to_zero=sum(n==0 for n in scaled.values()),
                    adjustments=world._edit_notes+political_notes,bulk_outcomes=world._bulk_outcomes,limitations=preview['assumptions'])
        for name in ('identity_refresh.json','source_claims.json','opening_balance.json','startup_compatibility.json'):
            if not (temp/name).exists() and hasattr(original,'package') and (original.package/name).exists():shutil.copyfile(original.package/name,temp/name)
        write(temp/'package_report.json',report);write(temp/'risk_report.json',preview);write(temp/'project.json',project)
        write_guide(temp,language)
        temp.rename(out)
        return dict(directory=str(out),mod_name=report['mod_name'],**report['checks'])
    except Exception:
        # Preserve failed staging evidence, never publish a misleading successful package.
        write(temp/'FAILED.json',dict(status='failed_not_for_installation'))
        raise
