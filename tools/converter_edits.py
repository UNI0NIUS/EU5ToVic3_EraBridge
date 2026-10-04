"""Replay desktop decisions into an isolated, deterministic candidate view."""
from converter_i18n import Message
from collections import Counter, defaultdict
from copy import copy, deepcopy
import json
import re
import math
from converter_project import apportion
from pdx_text import root, Object
from build_m3_world import block, entry
from build_m2_prototype import strings


def integer(value, label, maximum=1000000):
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=maximum:
        raise ValueError(Message('{0}必须为 0–{1} 的整数', label, str(maximum)))
    return value


def risk_reasons(row,risks,food_threshold=.2):
    result=[]
    for risk in risks:
        if risk in ('market_food','local_food'):
            value=row.get('market_food_shortfall' if risk=='market_food' else 'local_food_shortfall')
            if value is not None and value+1e-12>=food_threshold:result.append(risk)
        elif risk in row['risks']:result.append(risk)
    return result


def plan_bulk(rows,mode='risk',state=None,risks=('food','unemployment'),grouping='state',region=None,food_threshold=.2):
    """Freeze dominant owners from the current preview, avoiding order-dependent targets."""
    if mode not in ('risk','state'):raise ValueError(Message('未知批量模式'))
    if grouping not in ('state','strategic_region'):raise ValueError(Message('未知整合层级'))
    if grouping=='strategic_region' and state is not None:raise ValueError(Message('战略地区整合不能只用一个州统计最大国家；请按战略地区筛选'))
    if mode=='state' and not (state or region):raise ValueError(Message('请先选择一个州或战略地区'))
    if set(risks)-{'food','unemployment','market_food','local_food'}:raise ValueError(Message('未知批量风险条件'))
    by_state=defaultdict(list)
    for row in rows:
        if state is not None and row['state']!=state:continue
        if region is not None and row.get('strategic_region')!=region:continue
        key=row.get(grouping)
        if not key:raise ValueError(Message('地区缺少战略地区定义，不能在此层级整合'))
        by_state[key].append(row)
    transfers=[]
    for s,parts in sorted(by_state.items()):
        counts=Counter()
        for part in parts:counts[part['country']]+=part['province_count']
        dominant=min(counts,key=lambda t:(-counts[t],t))
        for part in sorted(parts,key=lambda r:(r['state'],r['country'])):
            if part['country']==dominant:continue
            reasons=risk_reasons(part,risks,food_threshold)
            if mode=='risk' and not reasons:continue
            transfers.append(dict(state=part['state'],source=part['country'],target=dominant,group=s,reasons=reasons,
                market_food_shortfall=part.get('market_food_shortfall'),local_food_shortfall=part.get('local_food_shortfall')))
    if not transfers:raise ValueError(Message('当前范围内没有需要整合到其他国家的地区；已属该层级最大地块国家的地区保持原状'))
    return dict(kind='bulk',mode=mode,state=state,region=region,grouping=grouping,risks=list(risks),food_threshold=food_threshold,transfers=transfers)


def plan_population(world,options,operations,region_ids,mode='percent',percent=10):
    if mode not in ('percent','jobs'):raise ValueError(Message('未知人口削减方式'))
    if mode=='percent' and (isinstance(percent,bool) or not isinstance(percent,(int,float)) or not math.isfinite(percent) or not 0<percent<100):raise ValueError(Message('削减比例须大于 0 且小于 100%'))
    preview=world.preview(options,operations);rows={r['id']:r for r in preview['rows']};selected=set(region_ids)
    if not selected or not selected<=rows.keys():raise ValueError(Message('请选择仍存在的地区'))
    view=materialize(world,operations);totals=Counter()
    for (s,t,_,_),n in view.population.items():totals[s,t]+=n
    targets=[];skipped=[]
    for key in sorted(selected):
        row=rows[key];before=totals[row['state'],row['country']]
        if mode=='jobs':
            if row['job_capacity'] is None:skipped.append(key);continue
            value=math.floor(row['job_capacity']/options['workforce_share']/options['population_multiplier'])
        else:value=math.floor(before*(1-percent/100))
        value=max(1,min(before,value)) if before else 0
        if value<before:targets.append(dict(state=row['state'],country=row['country'],before=before,value=value))
    if not targets:raise ValueError(Message('当前范围内没有可削减的人口；岗位未知或岗位已足够的地区不会自动削减'))
    return dict(kind='population',mode=mode,percent=percent if mode=='percent' else None,targets=targets,skipped_unknown=skipped)


def resize_building(row, levels):
    """Scale all ownership tranches, retaining their investors and production methods."""
    row=dict(row,levels=levels)
    if 'body' not in row:return row
    body=row['body'];matches=list(re.finditer(r'\b(levels|level)\s*=\s*(\d+)\b',body))
    if not matches:
        raise ValueError(Message('建筑缺少可编辑等级：{0}', row['building']))
    allocation=apportion(levels,{i:int(m[2]) for i,m in enumerate(matches)})
    if levels and not sum(int(m[2]) for m in matches):raise ValueError(Message('建筑所有权等级为零'))
    for i,m in reversed(list(enumerate(matches))):body=body[:m.start(2)]+str(allocation[i])+body[m.end(2):]
    row['body']=body
    return row


def parts_for(owners,states):
    result={}
    for p,t in sorted(owners.items()):
        s=states[p];result.setdefault(s+'|'+t,dict(state=s,country=t,provinces=[]))['provinces'].append(p)
    return result


def destinations(oldowners,oldstates,owners,states):
    result=defaultdict(Counter)
    for p,t in oldowners.items():result[oldstates[p],t][states[p],owners[p]]+=1
    return result


def rewrite_investor_locations(text,mapping):
    patches=[]
    def walk(obj):
        for _,value in obj.entries():
            if not isinstance(value,Object):continue
            f=dict(value.entries());country=f.get('country');state=f.get('region')
            if isinstance(country,str) and isinstance(state,str):
                pair=state,country.removeprefix('c:');dest=mapping.get(pair)
                if dest:
                    s,t=dest
                    body=re.sub(r'(\bcountry\s*=\s*"?c:)[A-Z0-9]{3}\b',lambda m:m[1]+t,value.text())
                    body=re.sub(r'(\bregion\s*=\s*"?)'+re.escape(state)+r'\b',lambda m:m[1]+s,body)
                    patches.append((value.start,value.end,body));continue
            walk(value)
    walk(root(text))
    for a,b,body in sorted(patches,reverse=True):text=text[:a]+body+text[b:]
    return text


def rewrite_hosts(text,view):
    """Relocate investor districts only when their former physical region vanished."""
    live={(r['state'],r['country']) for r in view.parts.values()}
    mapping={pair:max(dest,key=lambda k:(dest[k],k)) for pair,dest in view._final_destinations.items() if pair not in live}
    return rewrite_investor_locations(text,mapping)


def redistribute(view,weights):
    pops=Counter()
    for (s,t,c,r),n in view.population.items():
        if len(weights[s,t])==1 and (s,t) in weights[s,t]:
            pops[s,t,c,r]+=n;continue
        for (ds,dt),amount in apportion(n,weights[s,t]).items():
            if amount:pops[ds,dt,c,r]+=amount
    rows=[]
    for row in view.buildings:
        source=row['state'],row['owner']
        if len(weights[source])==1 and source in weights[source]:
            rows.append(row);continue
        for (s,t),n in apportion(row['levels'],weights[source]).items():
            if not n:continue
            moved=resize_building(row,n);moved.update(state=s,owner=t,_changed=True)
            # A self-owned establishment travels with its physical host.
            if (s,t)!=source and 'body' in moved:
                moved['body']=rewrite_investor_locations(moved['body'],{source:(s,t)})
            rows.append(moved)
    view.population=pops;view.buildings=rows


def normalize_buildings(view,notes):
    from converter_export import merged_buildings
    groups=defaultdict(list)
    for row in view.buildings:groups[row['state'],row['owner'],row['building']].append(row)
    normalized=[]
    for (s,t,kind),rows in groups.items():
        if hasattr(view,'target') and (len(rows)>1 or any(r.get('_changed') for r in rows)):
            target=view.target
            unlocking=target.buildings[kind].get('unlocking_technologies')
            if not set(strings(unlocking) if unlocking else [])<=view.techs[t]:
                raise ValueError(Message('接收国家尚未解锁建筑：{0} → {1}；请先在建筑编辑器移除该建筑', kind, t))
            need=len({tuple(r['pms']) for r in rows})>1 or any(not target.available(pm,view.techs[t],view.laws[t]) for r in rows for pm in r['pms'])
            if need:
                methods=target.select(kind,view.techs[t],set(),view.laws[t])
                updated=[]
                for row in rows:
                    row=dict(row,pms=methods)
                    if 'body' in row:
                        row['body']=re.sub(r'activate_production_methods\s*=\s*\{[^{}]*\}',
                            lambda _: 'activate_production_methods = { '+' '.join(methods)+' }',row['body'])
                    updated.append(row)
                rows=updated;notes.append(Message('生产方式统一为接收国可用配置：{0} / {1} / {2}', s, t, kind))
        normalized.extend(rows)
    # render_buildings can generate a complete body for newly added establishments.
    from economy_model import render_buildings,building_rows
    for row in normalized:
        if 'body' not in row:
            text=render_buildings([row]);obj=root(text)
            for _ in range(3):obj=next(v for _,v in obj.entries() if isinstance(v,Object))
            row['body']=next(v for k,v in obj.entries() if k=='create_building').text()
        row.setdefault('guards',())
        row.pop('_changed',None)
    view.buildings=merged_buildings(normalized)


def rebuild_states(view,original,owners,states):
    source_fields={}
    for key,obj in original.state_objects.items():
        for k,v in obj.entries():
            if k=='create_state':source_fields[key[2:],v.fields()['country'][2:]]=v
    objects={};groups=defaultdict(lambda:defaultdict(list));defaults={}
    for (s,t),obj in source_fields.items():defaults.setdefault(s,obj)
    for p,t in owners.items():groups[states[p]][t].append(p)
    for s in sorted(groups):
        body=[]
        for t in sorted(groups[s]):
            source=source_fields.get((s,t))
            if source is None:source=defaults.get(s)
            extras=''.join(entry(k,v) for k,v in source.entries() if k not in ('country','owned_provinces')) if source else ''
            provinces=sorted(groups[s][t])
            body.append(block('create_state','country = c:'+t+'\nowned_provinces = { '+' '.join(provinces)+' }\n'+extras))
        old=original.state_objects.get('s:'+s)
        if old:body.extend(entry(k,v) for k,v in old.entries() if k!='create_state')
        objects['s:'+s]=root(''.join(body))
    view.state_objects=objects
    view.owners={s:{p:t for t,ps in by_country.items() for p in ps} for s,by_country in groups.items()}
    view.parts=parts_for(owners,states)


def materialize(world,operations):
    key=json.dumps(operations,sort_keys=True,ensure_ascii=False)
    cached=getattr(world,'_edit_cache',None)
    if cached and cached[0]==key:return cached[1]
    previous=cached[1] if cached and operations and operations[:-1]==cached[1]._edit_operations else None
    base=previous or world
    view=copy(base);view._preview_cache={};view.population=Counter(base.population);view.buildings=deepcopy(base.buildings)
    if hasattr(world,'target'):
        view.target=copy(base.target);view.target.states={s:dict(v) for s,v in base.target.states.items()}
    owners={p:r['country'] for r in base.parts.values() for p in r['provinces']}
    states={p:r['state'] for r in base.parts.values() for p in r['provinces']}
    aliases=dict(previous._edit_aliases) if previous else {}
    notes=list(previous._edit_notes) if previous else []
    edited_states=set(previous._edited_states) if previous else set()
    history=list(previous._territory_history) if previous else []
    bulk_outcomes=list(previous._bulk_outcomes) if previous else []
    for op in operations[-1:] if previous else operations:
        kind=op.get('kind');s=op.get('state');t=op.get('country')
        if kind=='population':
            targets=op.get('targets');seen=set();removed=0
            if not isinstance(targets,list) or not targets:raise ValueError(Message('人口削减方案为空'))
            live={(states[p],owners[p]) for p in owners};by_pair=defaultdict(dict)
            for key,n in view.population.items():by_pair[key[:2]][key]=n
            for item in targets:
                pair=item['state'],item['country']
                if pair in seen:raise ValueError(Message('人口削减方案重复地区'))
                seen.add(pair)
                if pair not in live:raise ValueError(Message('人口所属地区已不存在'))
                groups=by_pair[pair];before=sum(groups.values())
                value=integer(item.get('value'),Message('地区人口'),1000000000000)
                if before!=item.get('before'):raise ValueError(Message('地区人口已变化，请重新生成削减预览'))
                if not 1<=value<before:raise ValueError(Message('削减后每个有人地区至少保留 1 人，且不得增加人口'))
                allocation=apportion(value,groups)
                for key in groups:
                    if allocation[key]:view.population[key]=allocation[key]
                    else:view.population.pop(key,None)
                removed+=before-value
            notes.append(Message('人口方案削减 {0} 人（全局人口系数前），涉及 {1} 个地区；文化与宗教按原比例取整。', str(removed), str(len(targets))))
            continue
        if kind=='bulk':
            moves=op.get('transfers')
            if not isinstance(moves,list) or not moves:raise ValueError(Message('批量整合方案为空'))
            before_owners=dict(owners);before_states=dict(states)
            counts=Counter((states[p],t) for p,t in owners.items())
            grouping=op.get('grouping','state')
            if grouping not in ('state','strategic_region'):raise ValueError(Message('未知整合层级'))
            state_groups={ss:(view.strategic_regions.get(ss) if grouping=='strategic_region' else ss) for ss,_ in counts}
            groups=defaultdict(Counter)
            for (ss,tt),n in counts.items():groups[state_groups[ss]][tt]+=n
            leaders={group:min(ts,key=lambda tt:(-ts[tt],tt)) for group,ts in groups.items()}
            lookup={}
            for move in moves:
                ss,source,target=move['state'],move['source'],move['target']
                if source==target or not counts[ss,source] or state_groups.get(ss) is None or leaders.get(state_groups.get(ss))!=target:raise ValueError(Message('批量目标已改变，请重新生成预览'))
                if (ss,source) in lookup:raise ValueError(Message('批量方案重复地区'))
                lookup[ss,source]=target
            blocked={};conflicts=[];remove_ids=set()
            for row in view.buildings:
                pair=row['state'],row['owner'];target=lookup.get(pair)
                if not target:continue
                kind=row['building'];unlocking=view.target.buildings[kind].get('unlocking_technologies')
                reason=None
                if not set(strings(unlocking) if unlocking else [])<=view.techs[target]:
                    reason=Message('接收国尚未解锁 {0}', kind)
                elif row.get('guards'):reason=Message('存在需要单独处理的条件建筑 {0}', kind)
                else:
                    try:view.target.select(kind,view.techs[target],set(),view.laws[target])
                    except (ValueError,KeyError):reason=Message('接收国没有可用生产方式 {0}', kind)
                if reason:
                    blocked[pair]=reason;remove_ids.add(id(row))
                    conflicts.append(dict(state=pair[0],source=pair[1],target=target,building=kind,levels=row['levels'],reason=reason))
            skipped=[];demolitions=[]
            if op.get('demolish') is True:
                demolitions=conflicts;blocked={}
                view.buildings=[row for row in view.buildings if id(row) not in remove_ids]
                for r in demolitions:notes.append(Message('自动拆除 {0} / {1}：{2} × {3}', r['state'], r['source'], r['building'], str(r['levels'])))
            for (ss,source),reason in sorted(blocked.items()):
                skipped.append(dict(state=ss,source=source,target=lookup.pop((ss,source)),reason=reason))
                notes.append(Message('跳过 {0} / {1}：{2}', ss, source, reason))
            bulk_outcomes.append(dict(requested=len(moves),applied=len(lookup),skipped=skipped,conflicts=conflicts,demolitions=demolitions))
            for p,t in before_owners.items():owners[p]=lookup.get((states[p],t),t)
            for source in sorted(set(before_owners.values())-set(owners.values())):
                successors=Counter(owners[p] for p,t in before_owners.items() if t==source)
                target=min(successors,key=lambda t:(-successors[t],t))
                for old,new in list(aliases.items()):
                    if new==source:aliases[old]=target
                aliases[source]=target
                if len(successors)>1:notes.append(Message('国家领土分入多个接收国，外交由接收地块最多者继承：{0} → {1}', source, target))
            weights=destinations(before_owners,before_states,owners,states)
            redistribute(view,weights);normalize_buildings(view,notes)
            history.append(deepcopy(op))
            notes.append(Message('批量整合 {0} 个分属地区 / {1} 个州；跳过 {2} 个地区', str(len(lookup)), str(len({ss for ss, _ in lookup})), str(len(skipped))))
            continue
        if kind=='arable_bulk':
            targets=op.get('targets');seen=set();factor=op.get('max_multiplier')
            if not isinstance(targets,list) or not targets:raise ValueError(Message('批量耕地方案为空'))
            if isinstance(factor,bool) or not isinstance(factor,(int,float)) or not math.isfinite(factor) or not 1<factor<=100:raise ValueError(Message('耕地倍率上限无效'))
            for item in targets:
                ss=item['state']
                if ss in seen or ss not in view.target.states:raise ValueError(Message('批量耕地方案重复州或州不存在'))
                seen.add(ss);before=int(view.target.states[ss].get('arable_land',0));value=integer(item.get('value'),Message('耕地数量'))
                if before!=item.get('before'):raise ValueError(Message('州耕地已变化，请重新预览批量补地'))
                if not before<value<=math.floor(before*factor):raise ValueError(Message('批量补地超过倍率上限或未增加耕地'))
                view.target.states[ss]['arable_land']=str(value);edited_states.add(ss)
            notes.append(Message('批量补耕地：{0} 个州，新增 {1} 基础耕地；上限为各州操作前的 {2} 倍。', str(len(targets)), str(sum((i['value'] - i['before'] for i in targets))), str(factor)))
            continue
        if kind=='arable':
            if s not in view.target.states:raise ValueError(Message('州不存在'))
            view.target.states[s]['arable_land']=str(integer(op.get('value'),Message('耕地数量')))
            edited_states.add(s);continue
        if kind=='building':
            if not any(states[p]==s and owners[p]==t for p in owners):raise ValueError(Message('建筑所属地区已不存在'))
            levels=op.get('levels')
            if not isinstance(levels,dict) or not levels:raise ValueError(Message('请选择需要调整的建筑'))
            for building,n in levels.items():
                integer(n,Message('建筑等级'),100000)
                if building not in view.target.buildings:raise ValueError(Message('未知建筑：{0}', building))
                if building.startswith('building_subsistence'):raise ValueError(Message('自给建筑由剩余耕地自动生成，请调整耕地或农业建筑'))
                matches=[r for r in view.buildings if (r['state'],r['owner'],r['building'])==(s,t,building)]
                if any(r.get('guards') for r in matches):raise ValueError(Message('带条件的建筑请先在游戏中确认条件，不能直接覆盖：{0}', building))
                view.buildings=[r for r in view.buildings if r not in matches]
                if n:
                    if matches:
                        for i,amount in apportion(n,{i:r['levels'] for i,r in enumerate(matches)}).items():
                            if amount:view.buildings.append(dict(resize_building(matches[i],amount),_changed=True))
                    else:
                        methods=view.target.select(building,view.techs[t],set(),view.laws[t])
                        row=dict(state=s,owner=t,building=building,levels=n,pms=methods,guards=(),_changed=True)
                        # State/military buildings have government levels, not private investors.
                        if building in ('building_barrack','building_naval_administration','building_government_administration','building_university','building_construction_sector','building_railway'):
                            row['body']=f'building = {building}\nlevel = {n}\nreserves = 1\nactivate_production_methods = {{ '+ ' '.join(methods)+' }'
                        view.buildings.append(row)
            normalize_buildings(view,notes);continue
        if kind not in ('country','region','province'):raise ValueError(Message('未知编辑类型'))
        before_owners=dict(owners);before_states=dict(states)
        if kind=='province':
            selected=set(op.get('provinces',[]));target=op.get('target');dest=op.get('target_state')
            if not selected or not selected<=owners.keys():raise ValueError(Message('请选择现有陆地地块'))
            if len({(states[p],owners[p]) for p in selected})!=1:raise ValueError(Message('一次请选择同一分属地区内的地块'))
            source=owners[next(iter(selected))];source_state=states[next(iter(selected))]
            if not any(states[p]==dest and owners[p]==target and p not in selected for p in owners):raise ValueError(Message('目标必须是仍有地块的现有地区'))
            if dest==source_state and source==target:raise ValueError(Message('地块已经属于目标地区'))
            if dest!=source_state and not any(states[p]==source_state and p not in selected for p in owners):raise ValueError(Message('原州至少保留一个地块；不能删除整州定义'))
        else:
            source=op.get('source');target=op.get('target');dest=None
            selected={p for p in owners if owners[p]==source and (kind=='country' or states[p]==s)}
            if not selected or source==target or target not in owners.values():raise ValueError(Message('请选择两个仍存在的不同国家'))
        def adjacent(a,b):
            return a in selected and b not in selected and owners.get(b)==target and (kind=='country' or states.get(b)==(dest if kind=='province' else s))
        if not any(adjacent(a,b) or adjacent(b,a) for a,b in view.edges):raise ValueError(Message('目标必须与所选地块陆地相邻；地区合并需在同一州'))
        for p in selected:
            owners[p]=target
            if dest:states[p]=dest
        if kind=='province' and dest!=source_state:edited_states.update((source_state,dest))
        if source not in owners.values():
            for old,new in list(aliases.items()):
                if new==source:aliases[old]=target
            aliases[source]=target
            if kind!='country':notes.append(Message('来源国最后一个地区已转移，按整个国家合并同步关系：{0} → {1}', source, target))
        weights=destinations(before_owners,before_states,owners,states)
        redistribute(view,weights);normalize_buildings(view,notes)
        history.append(deepcopy(op))
    rebuild_states(view,world,owners,states)
    view._edit_aliases=aliases;view._edit_notes=notes;view._edited_states=edited_states;view._territory_history=history;view._edit_operations=operations
    view._bulk_outcomes=bulk_outcomes
    view._original_world=world
    view._final_destinations=destinations({p:r['country'] for r in world.parts.values() for p in r['provinces']},
                                        {p:r['state'] for r in world.parts.values() for p in r['provinces']},owners,states)
    view.coefficients={}
    if hasattr(view,'target'):
        cache=getattr(world,'_edit_coefficients',None)
        if cache is None:
            cache={(r['owner'],r['building'],tuple(r['pms'])):world.coefficients[i] for i,r in enumerate(world.buildings) if hasattr(world,'coefficients') and i in world.coefficients}
            world._edit_coefficients=cache
        for i,row in enumerate(view.buildings):
            signature=row['owner'],row['building'],tuple(row['pms'])
            if signature in cache:view.coefficients[i]=cache[signature];continue
            try:
                methods=view.target.complete_methods(row['building'],row['pms'],view.target.select(row['building'],view.techs[row['owner']],set(),view.laws[row['owner']]))
                view.coefficients[i]=view.target.coefficients(row['building'],methods,view.techs[row['owner']])
            except (ValueError,KeyError):view.coefficients[i]=None
            cache[signature]=view.coefficients[i]
    world._edit_cache=(key,view)
    return view


def write_geography(view,mod,multiplier):
    """Patch complete effective state files, retaining unrelated fields and states."""
    import math
    paths={p.name:p for base in (view.game,view.mod) for p in (base/'map_data/state_regions').glob('*.txt')}
    original=view._original_world
    oldstates={p:r['state'] for r in original.parts.values() for p in r['provinces']}
    newstates={p:r['state'] for r in view.parts.values() for p in r['provinces']}
    moved={p for p in oldstates if oldstates[p]!=newstates[p]}
    for name,path in paths.items():
        text=path.read_text(encoding='utf-8-sig');patches=[]
        for s,obj in root(text).entries():
            if not isinstance(obj,Object) or s not in view.target.states:continue
            if multiplier==1 and s not in view._edited_states:continue
            body=obj.text();arable=int(math.floor(int(view.target.states[s].get('arable_land',0))*multiplier+.5))
            body=re.sub(r'\barable_land\s*=\s*\d+',lambda _:f'arable_land = {arable}',body)
            if not re.search(r'\barable_land\s*=',body):body+='\narable_land = '+str(arable)+'\n'
            provinces=set(strings(dict(obj.entries()).get('provinces')))
            provinces={p[0]+p[1:].upper() for p in provinces}
            provinces-=moved;provinces.update(p for p in moved if newstates[p]==s)
            if any(oldstates[p]==s or newstates[p]==s for p in moved):
                body=re.sub(r'\bprovinces\s*=\s*\{[^{}]*\}',lambda _:'provinces = { '+' '.join(sorted(provinces))+' }',body)
                for marker in ('city','farm','mine','wood','port'):
                    match=re.search(r'\b'+marker+r'\s*=\s*"?(x[0-9a-fA-F]{6})"?',body)
                    if match and match[1][0]+match[1][1:].upper() not in provinces:
                        if marker=='port':body=body[:match.start()]+body[match.end():]
                        elif provinces:body=body[:match.start()]+marker+' = '+sorted(provinces)[0]+body[match.end():]
            patches.append((obj.start,obj.end,body))
        if not patches:continue
        for a,b,body in sorted(patches,reverse=True):text=text[:a]+body+text[b:]
        output=mod/'map_data/state_regions'/name;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(text,encoding='utf-8-sig')
