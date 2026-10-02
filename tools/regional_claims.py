"""Opening regional claims, inferred from current identities and actual land.

Claims apply to whole V3 state regions. They do not transfer sovereignty or
grant colonization laws. Native interest, reachability and competing claims
continue to determine whether outsiders can colonize.
"""
import json
import re
from pathlib import Path
from pdx_text import Object, root
from extract_m3_politics import fields
from build_m2_prototype import patch, replace_body

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/'config/personal/regional_claims.json'
STATES='common/history/states/00_eu5_world.txt'
COUNTRIES='common/history/countries/00_eu5_world.txt'
CODE='common/on_actions/00_code_on_actions.txt'
HOOKS='common/on_actions/zz_eu5_regional_claims.txt'
EFFECTS='common/scripted_effects/zz_eu5_regional_claims.txt'


def definitions(game, category, outputs=None, mod=None):
    result={}
    paths={p.relative_to(game).as_posix():p.read_text(encoding='utf-8-sig')
           for p in sorted((game/'common'/category).glob('*.txt'))}
    if mod:
        paths.update({p.relative_to(mod).as_posix():p.read_text(encoding='utf-8-sig')
                      for p in sorted((mod/'common'/category).glob('*.txt'))})
    paths.update({k:v for k,v in (outputs or {}).items() if k.startswith('common/'+category+'/')})
    for _,text in sorted(paths.items()):
        result.update({k:fields(v) for k,v in root(text).entries() if isinstance(v,Object)})
    return result


def tokens(value):
    return [v for _,v in value.entries() if isinstance(v,str)] if isinstance(value,Object) else []


def source_tibetan_cultures(eu5, group):
    return {k for p in sorted((eu5/'in_game/common/cultures').glob('*.txt'))
            for k,v in root(p.read_text(encoding='utf-8-sig')).entries()
            if isinstance(v,Object) and group in tokens(fields(v).get('culture_groups'))}


def bloc_leaders(texts, identity):
    leaders=set()
    for text in texts:
        container=fields(root(text)).get('POWER_BLOCS')
        for country,obj in fields(container).items():
            for key,value in obj.entries():
                if key=='create_power_bloc' and fields(value).get('identity')==identity:
                    leaders.add(country.removeprefix('c:'))
    return leaders


def plan(state_text, country_text, country_defs, cultures, leaders, policy, source_cultures=None):
    states=fields(fields(root(state_text))['STATES'])
    histories=fields(fields(root(country_text))['COUNTRIES'])
    owners={}
    for state,obj in states.items():
        owners[state[2:]]={fields(v)['country'][2:] for k,v in obj.entries()
                          if k=='create_state' and tokens(fields(v).get('owned_provinces'))}
    active=set.union(set(),*owners.values())
    centralized={t for t in active if country_defs[t]['country_type']!='decentralized'}
    j=policy['japan'];t=policy['tibet']
    japan={tag:[] for tag in centralized}
    for tag,reasons in japan.items():
        history=histories.get('c:'+tag)
        laws=set(re.findall(r'\bactivate_law\s*=\s*law_type:(\w+)',history.text() if history else ''))
        if laws&set(j['laws']):reasons.append('shogunate_law')
        if tag in leaders:reasons.append('shogunate_bloc_leader')
    japan={tag:reasons for tag,reasons in japan.items() if reasons}
    if j['reserved_tag'] not in country_defs:raise ValueError('Reserved Japan tag is undefined')
    japan.setdefault(j['reserved_tag'],[]).append('japan_tag_including_dormant')
    tibet={}
    for tag in sorted(centralized):
        primary=tokens(country_defs[tag].get('cultures'))
        matched=[c for c in primary if c==t['native_culture'] or cultures.get(c,{}).get('heritage')==t['heritage']]
        if matched or tag in (source_cultures or {}):
            tibet[tag]={'primary_cultures':primary,'matched_target_cultures':matched,
                        'matched_source_culture':(source_cultures or {}).get(tag)}
    rows=[];skipped=[];regions=[]
    for rule,region_tags in [('japan',japan),('tibet',tibet)]:
        for state in policy[rule]['states']:
            if 's:'+state not in states:raise ValueError('Unknown protected state: '+state)
            white=sorted(o for o in owners[state] if country_defs[o]['country_type']=='decentralized')
            existing={v[2:] for k,v in states['s:'+state].entries() if k=='add_claim'}
            enabled=rule=='japan' or bool(white)
            regions.append({'rule':rule,'state':state,'decentralized_owners':white,'owners':sorted(owners[state]),
                            'claimants_present_in_state':sorted(set(region_tags)&owners[state]),
                            'preexisting_other_claims':sorted(existing-set(region_tags)),'enabled':enabled})
            if not enabled:
                skipped.append({'rule':rule,'state':state,'reason':'no_decentralized_land'});continue
            for tag in sorted(region_tags):
                rows.append({'rule':rule,'state':state,'tag':tag,'already_present':tag in existing})
    return {'policy_version':policy['version'],'japan_eligible':japan,'tibet_eligible':tibet,
            'claims':rows,'skipped':skipped,'regions':regions,
            'limitations':['State-wide claims, including already settled portions of split states.',
                           'Native interest and reachability required; other claimants can colonize too.',
                           'No forced colonial laws, interests, annexation, or perpetual claim restoration.']}


def apply(state_text, report):
    states=fields(fields(root(state_text))['STATES']);additions={}
    for row in report['claims']:
        additions.setdefault(row['state'],set()).add(row['tag'])
    edits=[]
    for state,tags in additions.items():
        obj=states['s:'+state];existing={v[2:] for k,v in obj.entries() if k=='add_claim'}
        new=sorted(tags-existing)
        if new:edits.append(replace_body(obj,obj.text()+'\n'+''.join('add_claim = c:'+tag+'\n' for tag in new)))
    return patch(state_text,edits)


def japan_runtime(code,policy):
    """A dead tag loses claims; grant them once on formation, with pulse fallback."""
    hooks={'on_game_started':'eu5_japan_claims_start',
           'on_country_formed':'eu5_japan_claims_country',
           'on_monthly_pulse_country':'eu5_japan_claims_country'}
    objs=root(code).fields();edits=[]
    for key,hook in hooks.items():
        obj=objs[key];existing=fields(obj).get('on_actions')
        if existing is not None:
            if hook not in tokens(existing):edits.append(replace_body(existing,existing.text()+'\n'+hook+'\n'))
        else:edits.append(replace_body(obj,obj.text()+'\non_actions = { '+hook+' }\n'))
    tag=policy['japan']['reserved_tag']
    effect='eu5_initialize_japan_claims = {\nif = {\nlimit = { NOT = { has_variable = eu5_japan_claims_initialized } }\n'
    effect+=''.join('s:'+state+' = { add_claim = c:'+tag+' }\n' for state in policy['japan']['states'])
    effect+='set_variable = { name = eu5_japan_claims_initialized value = yes }\n}\n}\n'
    action='eu5_japan_claims_start = { effect = { if = { limit = { exists = c:'+tag+' } c:'+tag+' = { eu5_initialize_japan_claims = yes } } } }\n'
    action+='eu5_japan_claims_country = { effect = { if = { limit = { c:'+tag+' ?= THIS } eu5_initialize_japan_claims = yes } } }\n'
    return {CODE:patch(code,edits),HOOKS:action,EFFECTS:effect}


def export(exporter):
    policy=json.loads(POLICY.read_text(encoding='utf-8'))
    outputs=exporter.outputs;world=exporter.w
    src=source_tibetan_cultures(world.eu5,policy['tibet']['source_culture_group'])
    source_cultures={tag:c['source_culture'] for tag,c in world.countries.items() if c.get('source_culture') in src}
    report=plan(outputs[STATES],outputs[COUNTRIES],definitions(world.game,'country_definitions',outputs),
                definitions(world.game,'cultures',outputs),
                bloc_leaders([v for k,v in outputs.items() if k.startswith('common/history/power_blocs/')],policy['japan']['bloc_identity']),
                policy,source_cultures)
    outputs[STATES]=apply(outputs[STATES],report)
    code=outputs[CODE] if CODE in outputs else world.read(CODE)
    outputs.update(japan_runtime(code,policy))
    exporter.regional_claims_report=report
    return report
