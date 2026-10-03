"""Deterministic opening-war planning and native history script generation."""
from collections import Counter, defaultdict
import csv
import re
from copy import deepcopy
from extract_m3_politics import fields
from pdx_text import root, Object
from build_m2_prototype import patch

HISTORY='common/history/diplomatic_plays/00_eu5_world_wars.txt'
PLAYS='common/diplomatic_plays/zz_eu5_opening_wars.txt'
DEPLOY='common/history/military_deployments/00_eu5_opening_wars.txt'
TESTS='tools/scripted_tests/eu5_opening_wars.txt'
GOALS='common/war_goal_types/zz_eu5_opening_wars.txt'
PREFIX='dp_eu5_opening_war_'


def select_state(weights, enemies, capital_states=()):
    candidates={pair:n for pair,n in weights.items() if pair[1] in enemies}
    if not candidates: raise ValueError('No mapped enemy-owned state intersects source objective')
    return min(candidates,key=lambda p:(-candidates[p],p[0] not in capital_states,p))


def plan(source, policy, mapping, source_names, staging, owners, state_provinces, claims, parents):
    tags={str(c['source_id']):tag for tag,c in mapping['countries'].items() if c.get('source_id') is not None}
    weights=defaultdict(Counter); cap_states=defaultdict(set); target_names=defaultdict(set)
    for w in source['wars']:
        for lid in w['goals'][0]['location_ids']:target_names[source_names[lid]].add(w['id'])
    with staging.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            for wid in target_names.get(row['source_location'],[]):
                weights[wid][row['target_state'],row['target_owner']]+=int(row['centipersons'])
            for w in source['wars']:
                capital=w['goals'][0].get('province_capital')
                if capital and row['source_location']==source_names[capital]:cap_states[w['id']].add(row['target_state'])
    result=[]
    for w in source['wars']:
        override=policy['war_overrides'][w['id']]; active=[p for p in w['participants'] if p['status']=='Active']
        sides={side:sorted(tags[p['source_id']] for p in active if p['side']==side and p['source_id'] in tags)
               for side in ('Attacker','Defender')}
        attacker=tags.get(w['original_attacker']); target=tags.get(w['original_target'])
        if not attacker or not target: raise ValueError('Missing principal country')
        if attacker not in sides['Attacker'] or target not in sides['Defender']: raise ValueError('Original principal left war; explicit leader resolution required')
        if set(sides['Attacker']) & set(sides['Defender']): raise ValueError('Mapped countries on both sides')
        row={'id':w['id'],'source_start':w['start_date'],'attacker':attacker,'target':target,
             'attackers':sides['Attacker'],'defenders':sides['Defender'],'route':override['route'],
             'omitted_participants':[p for p in active if p['source_id'] not in tags],
             'excluded_participants':[p for p in w['participants'] if p['status']!='Active'],
             'occupation_restored':False,'runtime_verified':False}
        route=row['route']
        if route=='one_state_territorial_goal':
            state,owner=select_state(weights[w['id']],{target},cap_states[w['id']])
            # Weights are only geographic evidence; current ownership is independently checked.
            provinces=[p for p in state_provinces[state] if owners.get(p)==owner]
            if not provinces: raise ValueError('Selected state has no surviving enemy province')
            row.update(state=state,owner=owner,provinces=sorted(provinces),
                       goal='return_state' if attacker in claims.get(state,set()) else 'conquer_state',
                       overlap_weights=[{'state':s,'owner':o,'centipersons':n} for (s,o),n in sorted(weights[w['id']].items())])
            leader=override.get('candidate_defender_leader',target)
            if leader!=target:
                cursor=target;seen=set()
                while cursor in parents and cursor not in seen:seen.add(cursor);cursor=parents[cursor]
                if cursor!=leader or leader not in sides['Defender']:raise ValueError('Invalid source-side overlord leader')
            row['leader_target']=leader
        elif route=='humiliation_approximation':row.update(goal='humiliation',leader_target=target)
        elif route=='native_civil_war_annexation':
            if w['goals'][0]['kind']!='civil_war':raise ValueError('Missing source civil-war evidence')
            row.update(goal='annex_country',leader_target=target,native_play='dp_revolution',
                       civil_war_bridge=True,limitation='Existing converted factions use native mutual annexation; no engine revolutionary identity or ideology is invented.')
        elif route=='native_independence_with_suspended_dependency_bridge':
            dep=dict(w['dependency'] or [])
            if dep.get('first')!=w['original_target'] or dep.get('second')!=w['original_attacker']:
                raise ValueError('No source suspended dependency evidence')
            if attacker in parents:raise ValueError('Suspended independence subject already has an overlord')
            row.update(goal='independence',leader_target=target,bridge_subject_type='puppet')
        elif route=='native_secession_bridge':
            if not w['revolt'] or w['dependency']:raise ValueError('Not a source secession')
            row.update(goal='secession',leader_target=target)
        else:raise ValueError('Unknown war route')
        row['play_type']=PREFIX+w['id']
        row['forbidden_extra_participant']=override.get('forbidden_extra_participant')
        if row['forbidden_extra_participant'] in sides['Attacker']+sides['Defender']:raise ValueError('Colonial overlord in source side')
        result.append(row)
    return result


def effect_block(key,body,indent=0):
    head=key[:-2]+' ?=' if key.endswith(' ?') else key+' ='
    return ' '*indent+head+' {\n'+''.join(' '*(indent+4)+line+'\n' for line in body.splitlines())+' '*indent+'}\n'


def allowed_members(row):
    return 'OR = { '+' '.join('this = c:'+t for t in row['attackers']+row['defenders'])+' }'


def valid_play(row,setup=False):
    goal_check='OR = { has_play_goal = secession has_play_goal = annex_country }' if row['goal']=='secession' else 'has_play_goal = '+row['goal']
    if 'candidates' in row and not setup:goal_check='OR = { has_play_goal = conquer_state has_play_goal = return_state }'
    checks=['initiator = { this = c:'+row['attacker']+' }','target = { this = c:'+row['leader_target']+' }',goal_check]
    # Involved countries include neutral observers, which are not war members.
    aligned='OR = { is_diplomatic_play_ally_of = c:'+row['attacker']+' is_diplomatic_play_enemy_of = c:'+row['attacker']+' }'
    checks.append('NOT = { any_scope_play_involved = { '+aligned+' NOT = { '+allowed_members(row)+' } } }')
    for tag in row['attackers']:
        checks.append('any_scope_play_involved = { this = c:'+tag+' is_diplomatic_play_ally_of = c:'+row['attacker']+' }' if tag!=row['attacker'] else 'any_scope_play_involved = { this = c:'+tag+' }')
    for tag in row['defenders']:
        checks.append('any_scope_play_involved = { this = c:'+tag+' is_diplomatic_play_enemy_of = c:'+row['attacker']+' }')
    return '\n'.join(checks)


def initial_war_goals(row, native_play=None):
    """Model native seeded goals by side; a mirrored play has no default humiliation."""
    native = fields(native_play) if native_play is not None else {}
    goal = native.get('war_goal', row['goal'])
    if native.get('mirror_war_goal') == 'yes' or (native_play is None and row.get('civil_war_bridge')):
        return {'initiator': goal, 'target': goal}
    if goal == 'secession':
        return {'initiator': 'revoke_all_claims', 'target': 'secession'}
    return {'initiator': goal, 'target': 'humiliation'}


def remove_seed_goal(row, who, goal):
    seeded = row.get('initial_war_goals') or initial_war_goals(row)
    if seeded.get(who) != goal:
        raise ValueError(f'Cannot remove absent seed war goal: {row["id"]} {who} {goal}; seeded={seeded}')
    return effect_block('if', f'limit = {{ has_play_goal = {goal} }}\nremove_war_goal = {{ who = {who} type = {goal} }}')


def validate_seed_removals(row, script, native_play=None):
    """Reject wrong-side or repeated seed removal before exporting any save."""
    remaining = initial_war_goals(row, native_play)
    from build_m2_prototype import walk
    for key, obj in walk(root(script)):
        if key != 'remove_war_goal': continue
        f = fields(obj);who, goal = f['who'], f['type']
        if remaining.get(who) != goal:
            raise ValueError(f'Absent/repeated war goal removal in war {row["id"]}: {who} {goal}')
        del remaining[who]


def render(rows, native_plays, recognition_goal=None):
    histories=[];plays=[];deploy=[];tests=[];loc={}
    for original in rows:
        row = dict(original)
        wid=row['id'];att=row['attacker'];target=row['leader_target'];ptype=row['play_type']
        native='dp_'+row['goal']; native='dp_secession' if row['goal']=='secession' else native
        obj=native_plays[row.get('native_play',native)];body=obj.text()
        row['initial_war_goals']=initial_war_goals(row,obj)
        # Make isolated historical types; preserve vanilla victory semantics and flags.
        changes=[]
        for k,v in obj.entries():
            if (k=='selectable_in_lens' or (row.get('civil_war_bridge') and k=='possible')) and isinstance(v,Object):changes.append((v.start-obj.start,v.end-obj.start,' always = yes ' if k=='possible' else ' always = no '))
        body=patch(body,changes)
        if 'selectable_in_lens' not in fields(obj):body+='\nselectable_in_lens = { always = no }\n'
        # This is an inherited conflict; do not charge fresh declaration infamy.
        for side in ('initiator','target'):
            key='add_infamy_for_starting_'+side+'_wargoals'
            body=re.sub(r'\b'+key+r'\s*=\s*(?:yes|no)',key+' = no',body) if key in fields(obj) else body+'\n'+key+' = no\n'
        plays.append(effect_block(ptype,body.strip()))
        loc[ptype]='承接战争：'+wid;loc['eu5_opening_war_'+wid]='承接战争 '+att+'—'+row['target']
        create=['name = eu5_opening_war_'+wid,'type = '+ptype,'war = no','target_country = c:'+target]
        if row.get('state'):
            # Target country may be the overlord: explicit goal still targets the actual state owner.
            create.append('target_state = s:'+row['state']+'.region_state:'+row['owner'])
        create += ['add_initiator_backers = { '+' '.join('c:'+t for t in row['attackers'] if t!=att)+' }',
                   'add_target_backers = { '+' '.join('c:'+t for t in row['defenders'] if t!=target)+' }']
        content=[]
        if row.get('bridge_subject_type'):
            histories.append(effect_block('c:'+target+' ?', 'create_diplomatic_pact = { country = c:'+att+' type = '+row['bridge_subject_type']+' }'))
        content.append(effect_block('create_diplomatic_play','\n'.join(create)).strip())
        # Stage before set_war: remove automatically pulled non-source supporters with native effects.
        cleanup='limit = { is_diplomatic_play_type = '+ptype+' }\n'
        cleanup+=effect_block('every_scope_play_involved','limit = { NOT = { '+allowed_members(row)+' } }\n'
                    'save_temporary_scope_as = eu5_extra_backer\n'
                    'prev = { remove_initiator_backers = { scope:eu5_extra_backer } remove_target_backers = { scope:eu5_extra_backer } }')
        goals=''
        if row['goal']=='secession':
            goals+=remove_seed_goal(row,'initiator','revoke_all_claims')
            # Imported rebels are existing countries, not engine-generated civil-war
            # entities. Native secession cannot reintegrate them; only the mother
            # country gets the equivalent native annexation demand.
            goals+=remove_seed_goal(row,'target','secession')
            goals+='add_war_goal = { holder = c:'+att+' type = eu5_recognize_secession target_country = c:'+target+' primary_demand = yes }\n'
            goals+='add_war_goal = { holder = c:'+target+' type = annex_country target_country = c:'+att+' primary_demand = no }\n'
        elif row['initial_war_goals']['target']=='humiliation':
            goals+=remove_seed_goal(row,'target','humiliation')
        if row.get('state') and target!=row['owner']:
            goals+=remove_seed_goal(row,'initiator',row['goal'])
            goals+='add_war_goal = { holder = c:'+att+' type = '+row['goal']+' target_country = c:'+row['owner']+' target_state = s:'+row['state']+'.region_state:'+row['owner']+' primary_demand = yes }\n'
        if 'candidates' in row:
            from border_war_goals import allocation_script
            goals=allocation_script(row)
        cleanup+=effect_block('if',effect_block('limit',valid_play(row,setup=True))+'set_war = yes\n'+goals+'debug_log = "EU5_WAR_STARTED_'+wid+'"')
        abort='debug_log = "EU5_WAR_BLOCKED_MEMBERSHIP_'+wid+'"\nend_play = yes\n'
        if row.get('bridge_subject_type'):abort+='c:'+target+' = { remove_diplomatic_pact = { country = c:'+att+' type = '+row['bridge_subject_type']+' } }\n'
        cleanup+=effect_block('else',abort)
        content.append(effect_block('every_diplomatic_play',cleanup).strip())
        if row.get('bridge_subject_type'):
            content.append('if = { limit = { NOT = { any_diplomatic_play = { is_diplomatic_play_type = '+ptype+' is_war = yes } } } c:'+target+' = { remove_diplomatic_pact = { country = c:'+att+' type = '+row['bridge_subject_type']+' } } debug_log = "EU5_WAR_BRIDGE_ROLLBACK_'+wid+'" }')
        history=effect_block('c:'+att+' ?', '\n'.join(content))
        validate_seed_removals(row,history,obj)
        histories.append(history)
        # Only mobilize if the intended war actually exists after membership validation.
        for tag in row['attackers']+row['defenders']:
            deploy.append(effect_block('c:'+tag+' ?',effect_block('if',
                'limit = { any_diplomatic_play = { is_diplomatic_play_type = '+ptype+' is_war = yes } }\n'
                'every_military_formation = { limit = { is_army = yes } fully_mobilize_army = yes }')))
        tests.append(effect_block('eu5_war_'+wid,
            'success = { game_date > 1836.1.1 c:'+att+' = { any_diplomatic_play = { is_diplomatic_play_type = '+ptype+' is_war = yes '+valid_play(row)+' } } }\n'
            'fail = { game_date > 1836.1.2 }'))
    output={HISTORY:effect_block('DIPLOMATIC_PLAYS',''.join(histories)),PLAYS:'\n'.join(plays),
            DEPLOY:effect_block('MILITARY_DEPLOYMENTS',''.join(deploy)),
            TESTS:'last_date = "1836.1.4"\n'+effect_block('tests',''.join(tests))}
    if any(r['goal']=='secession' for r in rows):
        if recognition_goal is None:raise ValueError('Native revoke-all-claims definition required')
        # Some EU5 revolts have no surviving V3 state claims. Preserve native peace
        # execution while allowing recognition even when there are no claims to revoke.
        output[GOALS]=effect_block('eu5_recognize_secession',recognition_goal.text().replace('validate_revoke_claims','').strip())
        loc['eu5_recognize_secession']='承认分离独立'
        loc['eu5_recognize_secession_desc']='承认分离国家，并撤销对其领土的所有宣称。'
    for lang in ('english','simp_chinese'):
        output['localization/'+lang+'/eu5_opening_wars_l_'+lang+'.yml']='l_'+lang+':\n'+''.join(' '+k+':0 "'+(v if lang=='simp_chinese' else 'Converted war '+k.removeprefix(PREFIX).removeprefix('eu5_opening_war_'))+'"\n' for k,v in loc.items())
    return output
