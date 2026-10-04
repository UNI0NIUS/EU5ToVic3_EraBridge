"""Reconcile capital and generated political history after player territory edits."""
from converter_i18n import Message
from collections import Counter, defaultdict
import re
from pdx_text import root, Object
from build_m2_prototype import objects
from build_m3_world import block,entry
from converter_project import apportion

SUBJECTS={'puppet','vassal','tributary','personal_union','protectorate','dominion','colony'}

def reconcile(world,view):
    from converter_export import scoped
    aliases=view._edit_aliases;notes=[];files={}
    live={r['country'] for r in view.parts.values()}
    shares=Counter({(r['state'],r['country']):len(r['provinces']) for r in view.parts.values()})
    pops=Counter()
    for (s,t,c,r),n in view.population.items():pops[s,t]+=n
    def tag(t):return aliases.get(t.removeprefix('c:'),t.removeprefix('c:'))
    def read(folder):
        return [(p.relative_to(world.mod).as_posix(),p.read_text(encoding='utf-8-sig')) for p in sorted((world.mod/folder).glob('*.txt'))]
    release=world.mod/'common/country_creation/00_releasable_countries.txt'
    releasable=set(dict(objects(root(release.read_text(encoding='utf-8-sig'))))) if release.exists() else set()
    for rel,text in read('common/country_definitions'):
        bodies=[]
        for t,obj in objects(root(text)):
            if t in aliases and t not in releasable:continue
            body=obj.text();capital=dict(obj.entries()).get('capital')
            if t in live and capital and not shares[capital,t]:
                new=max((s for s,c in shares if c==t),key=lambda s:(pops[s,t],shares[s,t],s))
                body=re.sub(r'\bcapital\s*=\s*\w+',lambda _:'capital = '+new,body)
                notes.append(Message('迁都：{0} / {1} → {2}', t, capital, new))
            bodies.append(block(t,body))
        files[rel]=''.join(bodies)
    if aliases:
        records=[];original_files=read('common/history/diplomacy')
        for rel,text in original_files:
            for container,outer in objects(root(text)):
                for owner,obj in objects(outer):
                    old=owner.removeprefix('c:');new=tag(old)
                    for k,v in obj.entries():
                        body=scoped(entry(k,v),aliases)
                        fields=dict(v.entries()) if isinstance(v,Object) else {}
                        other=fields.get('country');dest=tag(other) if isinstance(other,str) else None
                        if dest==new:
                            notes.append(Message('清除合并后的自身外交关系：{0} / {1}', new, str(k)));continue
                        typ=fields.get('type');is_subject=k=='create_diplomatic_pact' and typ in SUBJECTS
                        records.append(dict(owner=new,other=dest,kind=k,type=typ,body=body,subject=is_subject,
                                            priority=(old!=new)+(other is not None and tag(other)!=other.removeprefix('c:'))))
        parents={};seen=set();groups=defaultdict(list)
        for rec in sorted(records,key=lambda r:r['priority']):
            a,b=rec['owner'],rec['other'];key=(a,b,rec['kind'],rec['type'])
            if key in seen:continue
            if rec['subject']:
                ancestor=a;visited=set()
                while ancestor in parents and ancestor not in visited:
                    visited.add(ancestor);ancestor=parents[ancestor]
                if b in parents or ancestor==b:
                    notes.append(Message('移除冲突或成环的附属关系：{0} → {1}；优先保留接收国原关系', a, b));continue
                parents[b]=a
            seen.add(key);groups[a].append(rec['body'])
        if original_files:
            for rel,_ in original_files:files[rel]='DIPLOMACY = {}\n'
            files[original_files[0][0]]=block('DIPLOMACY',''.join(block('c:'+t+' ?',''.join(bs)) for t,bs in sorted(groups.items())))
        seen=set()
        for rel,text in read('common/history/treaties'):
            output=[]
            for outer,obj in objects(root(text)):
                inner=[]
                for k,v in objects(obj):
                    body=scoped(v.text(),aliases);f=dict(root(body).entries())
                    if f.get('first_country')==f.get('second_country'):
                        notes.append(Message('清除合并后的内部条约：{0}', str(f.get('name', ''))));continue
                    signature=re.sub(r'\s+','',re.sub(r'\bname\s*=\s*\S+','',body))
                    if signature not in seen:inner.append(block(k,body));seen.add(signature)
                output.append(block(outer,''.join(inner)))
            files[rel]=''.join(output)
        blocs=[];blocfiles=read('common/history/power_blocs')
        for rel,text in blocfiles:
            for _,outer in objects(root(text)):
                for owner,obj in objects(outer):
                    for k,v in objects(obj):
                        blocs.append((tag(owner)!=owner[2:],tag(owner),k,v))
        original_leaders={leader for changed,leader,k,obj in blocs if not changed}
        membership={};kept=[];newleaders=set()
        for changed,leader,k,obj in blocs:
            if not changed:
                membership.setdefault(leader,leader)
                for key,value in obj.entries():
                    if key=='member' and tag(value)==value.removeprefix('c:'):membership.setdefault(tag(value),leader)
        for changed,leader,k,obj in sorted(blocs,key=lambda r:(r[0],r[1])):
            if changed and (leader in original_leaders or leader in newleaders):
                notes.append(Message('合并重叠组织：保留接收国原组织 / {0}', leader));continue
            if changed:newleaders.add(leader)
            kept.append((leader,k,obj))
        groups=defaultdict(list)
        for leader,k,obj in kept:
            body=[];members={leader}
            for key,value in obj.entries():
                if key=='member':
                    member=tag(value)
                    if member in members:continue
                    if member!=value.removeprefix('c:') and member in membership and membership[member]!=leader:continue
                    members.add(member)
                    membership[member]=leader;value='c:'+member
                body.append(scoped(entry(key,value),aliases))
            groups[leader].append(block(k,''.join(body)))
        if blocfiles:
            for rel,_ in blocfiles:files[rel]='POWER_BLOCS = {}\n'
            files[blocfiles[0][0]]=block('POWER_BLOCS',''.join(block('c:'+t+' ?',''.join(bs)) for t,bs in sorted(groups.items())))
    # Preserve a valid external war; retire only wars whose sides/territorial
    # objectives cease to exist because of this player's edits.
    for rel,text in read('common/history/diplomatic_plays'):
        patches=[]
        for _,outer in objects(root(text)):
            for owner,obj in objects(outer):
                create=next((v for k,v in obj.entries() if k=='create_diplomatic_play'),None)
                if create is None:continue
                f=dict(create.entries());a=tag(owner);b=tag(f['target_country'])
                def refs(v):return {tag(t) for t in re.findall(r'\bc:([A-Z0-9]{3})\b',v.text())} if isinstance(v,Object) else set()
                first={a}|refs(f.get('add_initiator_backers'));second={b}|refs(f.get('add_target_backers'))
                body=scoped(obj.text(),aliases)
                invalid=[(s,t) for s,t in re.findall(r'\bs:(STATE_\w+)\.region_state:([A-Z0-9]{3})\b',body) if not shares[s,t]]
                if first&second or invalid:
                    patches.append((obj.start,obj.end,'# Retired after player territory edit\n'))
                    notes.append(Message('结束因合并失去有效对手或目标地区的开局战争：{0}', str(f.get('name', ''))));continue
                # A former ally that is now the leader must not test "ally of self".
                body=re.sub(r'(this\s*=\s*c:([A-Z0-9]{3}))\s+is_diplomatic_play_ally_of\s*=\s*c:\2\b',r'\1',body)
                def unique_backers(m):
                    side=first if m[1]=='add_initiator_backers' else second
                    principal=a if m[1]=='add_initiator_backers' else b
                    return m[1]+' = { '+' '.join('c:'+t for t in sorted(side-{principal}))+' }'
                body=re.sub(r'(add_initiator_backers|add_target_backers)\s*=\s*\{[^{}]*\}',unique_backers,body)
                patches.append((obj.start,obj.end,body))
        for a,b,body in sorted(patches,reverse=True):text=text[:a]+body+text[b:]
        files[rel]=scoped(text,aliases)
    # Army establishments follow their transferred state and owner. Split rows
    # use the same stable province weights as the population/building editor.
    from economy_model import definitions
    from extract_m3_politics import sequence
    strategic={s:k for k,f in definitions(world.game/'common/strategic_regions').items() for s in sequence(f.get('states'))} if hasattr(world,'game') else {}
    for rel,text in read('common/history/military_formations'):
        result=[]
        for outer,obj in objects(root(text)):
            groups=defaultdict(list)
            for owner,country in objects(obj):
                old=owner[2:]
                for k,formation in objects(country):
                    by_owner=defaultdict(list);common=[];has_units=False
                    for field,v in formation.entries():
                        if field=='combat_unit' and isinstance(v,Object):
                            f=dict(v.entries());state=f.get('state_region','').removeprefix('s:')
                            weights=view._final_destinations.get((state,old))
                            if weights and 'count' in f:
                                has_units=True
                                for (ds,dt),n in apportion(int(f['count']),weights).items():
                                    if n:by_owner[dt,strategic.get(ds)].append(block(field,''.join(entry(a,('s:'+ds if a=='state_region' else str(n) if a=='count' else b)) for a,b in v.entries())))
                                continue
                        common.append(entry(field,v))
                    if has_units:
                        for (t,hq),units in by_owner.items():
                            body=scoped(''.join(common+units),aliases)
                            if hq:body=re.sub(r'\bhq_region\s*=\s*sr:\w+',lambda _:'hq_region = sr:'+hq,body)
                            groups[t].append(block(k,body))
                    else:groups[tag(old)].append(block(k,scoped(formation.text(),aliases)))
            result.append(block(outer,''.join(block('c:'+t+' ?',''.join(rows)) for t,rows in sorted(groups.items()))))
        files[rel]=''.join(result)
    military_edits=bool(view._territory_history) or any(op['kind']=='building' and 'building_barrack' in op.get('levels',{}) for op in view._edit_operations)
    if military_edits:
        # Formation history also creates battalions; keep it in step with the
        # edited barracks so the engine cannot silently recreate removed levels.
        capacities=Counter()
        for row in view.buildings:
            if row['building']=='building_barrack':capacities[row['state'],row['owner']]+=row['levels']
        units=defaultdict(list);forms=[]
        for rel,text in files.items():
            if not rel.startswith('common/history/military_formations/'):continue
            for _,outer in objects(root(text)):
                for owner,country in objects(outer):
                    for k,form in objects(country):
                        if dict(form.entries()).get('type')!='army':continue
                        forms.append((rel,owner,k,form))
                        for field,v in objects(form):
                            if field=='combat_unit':
                                f=dict(v.entries());pair=f['state_region'].removeprefix('s:'),owner[2:]
                                units[pair].append((rel,v,int(f['count'])))
        replacement={}
        for pair,rows in units.items():
            n=capacities[pair];old=sum(r[2] for r in rows)
            if n==old:continue
            allocated=apportion(n,{i:r[2] for i,r in enumerate(rows)})
            for i,(rel,obj,count) in enumerate(rows):replacement[rel,obj.start]=allocated[i]
            notes.append(Message('兵营与营数同步：{0} / {1} → {2}', '/'.join(pair), str(old), str(n)))
        patches=defaultdict(list)
        for rel,owner,k,form in forms:
            body=[]
            for field,v in form.entries():
                if field=='combat_unit' and (rel,v.start) in replacement:
                    n=replacement[rel,v.start]
                    if n:body.append(block(field,re.sub(r'\bcount\s*=\s*\d+',lambda _:'count = '+str(n),v.text())))
                else:body.append(entry(field,v))
            patches[rel].append((form.start,form.end,''.join(body)))
        for rel,changes in patches.items():
            text=files[rel]
            for a,b,body in sorted(changes,reverse=True):text=text[:a]+body+text[b:]
            files[rel]=text
        new=[]
        for (s,t),n in sorted(capacities.items()):
            if n and (s,t) not in units and s in strategic:
                new.append(block('c:'+t+' ?',block('create_military_formation','type = army\nhq_region = sr:'+strategic[s]+'\n'+block('combat_unit',f'type = unit_type:combat_unit_type_irregular_infantry\nstate_region = s:{s}\ncount = {n}'))))
                notes.append(Message('按新增兵营配置基础步兵营：{0} / {1} / {2}', s, t, str(n)))
        if new:
            rel=next((r for r in files if r.startswith('common/history/military_formations/')),'common/history/military_formations/00_eu5_world.txt')
            text=files.get(rel,'MILITARY_FORMATIONS = {}');outer=root(text).fields()['MILITARY_FORMATIONS']
            files[rel]=text[:outer.end]+''.join(new)+text[outer.end:]
    return files,list(dict.fromkeys(notes))
