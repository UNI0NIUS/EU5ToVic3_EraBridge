"""Source cores become explicit release territories and state claims, not new owners."""
from collections import defaultdict,Counter
from pathlib import Path
from types import SimpleNamespace
import re
from converter_project import read,write,digest
from pdx_text import root,Object
from extract_m3_politics import fields,sequence
from economy_model import definitions
from build_m3_world import block,entry,Exporter,load_localization
from native_country_tags import allocate
from source_country_names import source_name_parts
from converter_core_geometry import province_states,project,coverage,CLAIM_PERCENT,PROVINCE_PERCENT

REVISION='source-cores-v2-30pct-provinces-source-flags'


def extract(run):
    path=run/'source/decoded.eu5';context=read(run/'fresh_context.json');audit=read(run/'source/audit/import_report.json')
    doc=root(path.read_text(encoding='utf-8-sig')).fields();locations=fields(fields(doc['locations'])['locations'])
    location_names={str(r['id']):r['name'] for r in audit['locations']};cores=defaultdict(set)
    for i,o in locations.items():
        f=fields(o)
        # Only extant cores, not scripted historical grants that may have expired.
        for sid in sequence(f.get('cores')):
            if isinstance(sid,str) and i in location_names:cores[sid].add(location_names[i])
    return {sid:sorted(names) for sid,names in cores.items()}


def install(mod,game,run,rules,countries,mapping,previous=None,core_cache=None):
    mod,game,run,rules=map(Path,(mod,game,run,rules));context=read(run/'fresh_context.json')
    politics=read(run/'source/politics.json');request=read(run/'request.json');eu5=Path(request['eu5'])
    if (eu5/'game').exists():eu5=eu5/'game'
    cores=core_cache if core_cache is not None else extract(run)
    initial=read(run/'political/conversion_report.json')['countries']
    by_source={r['source_id']:r['tag'] for r in (previous or {}).get('countries',[])}
    by_source.update({c['source_id']:t for t,c in initial.items() if c.get('source_id')})
    for t,c in countries.items():
        if c.get('source_id'):
            if c['source_id'] in by_source and by_source[c['source_id']]!=t:raise ValueError('Source country TAG changed during core upgrade')
            by_source[c['source_id']]=t
    province_state=province_states(mod)
    evidence,ambiguous=project(cores,context['geography_mapping'],province_state)
    defs=definitions(game/'common/country_definitions');defs.update(definitions(mod/'common/country_definitions'))
    religions=definitions(game/'common/religions');religions.update(definitions(mod/'common/religions'))
    cultures=definitions(game/'common/cultures');cultures.update(definitions(mod/'common/cultures'))
    eligible=[];skipped=[]
    for sid,ps in sorted(evidence.items()):
        src=politics['countries'].get(sid,{})
        if not ps:skipped.append(dict(source_id=sid,reason='no_core_province_meets_mapping_support_threshold'));continue
        if sid not in by_source and (src.get('culture') not in mapping or mapping[src['culture']] not in cultures):
            skipped.append(dict(source_id=sid,reason='no_reviewed_primary_culture'));continue
        eligible.append(sid)
    # Exact reviewed correspondences may reuse a dormant vanilla TAG, never a live or unrelated generated tag.
    approved=read(rules/'config/personal/country_tag_mappings.json')['matches'];matches=defaultdict(set)
    for row in approved.values():matches[row['source_tag']].add(row['target_tag'])
    used=set(countries)|set(by_source.values());pending=[];dormant={}
    for sid in sorted(set(eligible)-set(by_source),key=int):
        definition=politics['countries'][sid].get('definition');choices=matches.get(definition,set())
        if len(choices)==1 and next(iter(choices)) not in used:
            t=next(iter(choices));by_source[sid]=t;used.add(t)
        else:pending.append(sid)
    by_source.update(allocate(pending,set(defs)|used,preferred_prefix='R'))
    resolver=SimpleNamespace(source_loc={lang:load_localization(eu5/'main_menu/localization'/lang) for lang in ('english','simp_chinese')})
    resolver.localize=lambda token,lang,depth=0:Exporter.localize(resolver,token,lang,depth)
    definitions_text=[];loc=defaultdict(dict);flags=[];coas=[];fallbacks=[]
    for sid in sorted(set(eligible)-{c.get('source_id') for c in initial.values()},key=int):
        tag=by_source[sid];src=politics['countries'][sid];culture=mapping[src['culture']]
        religion=context['religions'].get(src.get('religion'),src.get('religion'))
        if religion not in religions:religion=cultures[culture]['religion'];fallbacks.append(dict(source_id=sid,field='religion',basis='primary_culture_definition'))
        counts=Counter(province_state[p] for p in evidence[sid]);capital=min(counts,key=lambda s:(-counts[s],s))
        color=src.get('color') or [100,130,160];color=[int(float(v)) for v in color]
        kind='recognized' if tag in defs and defs[tag].get('country_type')=='recognized' else 'unrecognized'
        body='color = { '+' '.join(map(str,color))+' }\ncountry_type = '+kind+'\ntier = principality\ncultures = { '+culture+' }\nreligion = '+religion+'\ncapital = '+capital+'\n'
        definitions_text.append(block(tag,body))
        custom,token,adj=source_name_parts(src,src.get('definition') or tag)
        names={}
        for lang in resolver.source_loc:
            name=custom or resolver.localize(token,lang)
            if not name or '$' in name or '[' in name:name=resolver.localize(src.get('definition') or token,lang)
            loc[lang][tag]=name;adjective=custom or resolver.localize(adj,lang);loc[lang][tag+'_ADJ']=name if adjective.endswith('_ADJ') else adjective
            names['name_'+lang]=name
        dormant[tag]=dict(source_id=sid,source_tag=src.get('definition'),culture=culture,religion=religion,capital=capital,**names)
    def save(rel,text):
        p=mod/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8-sig')
    save('common/country_definitions/zzzz_eu5_core_countries.txt',''.join(definitions_text))
    from converter_core_flags import install as install_flags
    flag_report=install_flags(mod,game,eu5,politics,dormant)
    for lang,values in loc.items():save('localization/replace/'+lang+'/zzzz_eu5_core_countries_l_'+lang+'.yml','l_'+lang+':\n'+''.join(' '+k+':0 "'+v.replace('"','\\"')+'"\n' for k,v in sorted(values.items())))
    state_claims=defaultdict(set);release=[];records=[]
    for sid in sorted(eligible,key=int):
        tag=by_source[sid];state_rows=coverage(evidence[sid],province_state)
        states=[r['state'] for r in state_rows if r['claim']]
        for s in states:state_claims[s].add(tag)
        release.append(block(tag,'provinces = { '+' '.join(sorted(evidence[sid]))+' }\nai_will_do = { always = no }\n'))
        records.append(dict(source_id=sid,tag=tag,dormant=tag in dormant,states=states,release_provinces=sorted(evidence[sid]),coverage=state_rows,source_core_locations=len(cores[sid]),mapped_core_provinces=len(evidence[sid])))
    # Replace the native release list: its unrelated historical territories do not
    # describe this save. Live source countries remain releasable after extinction.
    save('common/country_creation/00_releasable_countries.txt',''.join(release))
    # Dead tags can lose opening claims in the engine. Restore their evidenced
    # claims when actually released/formed, once per newly created country.
    effect=[]
    for r in records:
        effect.append(block('if',block('limit','c:'+r['tag']+' ?= THIS\nNOT = { has_variable = eu5_source_core_claims_initialized }')+
            ''.join('s:'+s+' = { add_claim = c:'+r['tag']+' }\n' for s in r['states'])+
            'set_variable = { name = eu5_source_core_claims_initialized value = yes }\n'))
    save('common/scripted_effects/zz_eu5_source_cores.txt',block('eu5_restore_source_core_claims',''.join(effect)))
    from build_m2_prototype import patch,replace_body
    code_path=mod/'common/on_actions/00_code_on_actions.txt'
    code=(code_path if code_path.exists() else game/'common/on_actions/00_code_on_actions.txt').read_text(encoding='utf-8-sig')
    actions=root(code).fields();edits=[]
    for action in ('on_country_released_as_independent','on_country_released_as_own_subject','on_country_released_as_company_subject','on_country_released_as_overlord_subject','on_country_formed'):
        obj=fields(actions[action])['effect']
        call='eu5_restore_source_core_claims = yes'
        if action!='on_country_formed':call='scope:target ?= { '+call+' }'
        if 'eu5_restore_source_core_claims' not in obj.text():edits.append(replace_body(obj,obj.text()+'\n'+call+'\n'))
    save('common/on_actions/00_code_on_actions.txt',patch(code,edits))
    base=run/'base/eu5_converted/common/history/states/00_eu5_world.txt'
    protected={(s[2:],v[2:]) for s,o in objects_local(root(base.read_text(encoding='utf-8-sig')).fields()['STATES']) for k,v in o.entries() if k=='add_claim'}
    old_pairs={(s,r['tag']) for r in (previous or {}).get('countries',[]) for s in r['states']}
    path=mod/'common/history/states/00_eu5_world.txt';states=fields(root(path.read_text(encoding='utf-8-sig')))['STATES'];bodies=[]
    for s,o in objects_local(states):
        kept=[(k,v) for k,v in o.entries() if not (k=='add_claim' and (s[2:],v[2:]) in old_pairs-protected)]
        existing={v[2:] for k,v in kept if k=='add_claim'}
        bodies.append(block(s,''.join(entry(k,v) for k,v in kept)+'\n'+''.join('add_claim = c:'+t+'\n' for t in sorted(state_claims[s[2:]]-existing))))
    save('common/history/states/00_eu5_world.txt',block('STATES',''.join(bodies)))
    # Country definitions must override duplicate vanilla entries as complete objects.
    replaced=set(dormant)
    for p in (mod/'common/country_definitions').glob('*.txt'):
        if p.name=='zzzz_eu5_core_countries.txt':continue
        text=p.read_text(encoding='utf-8-sig')
        save(p.relative_to(mod),''.join(block(k,o.text()) for k,o in objects_local(root(text)) if k not in replaced))
    return dict(revision=REVISION,source_sha256=politics['source_sha256'],countries=records,dormant_countries=dormant,skipped=skipped,fallbacks=fallbacks,flags=flag_report,
                policy=dict(claim_percent=CLAIM_PERCENT,province_support_percent=PROVINCE_PERCENT,denominator='all_owned_land_provinces_in_state',ambiguous_map_provinces=ambiguous),protected_claims=sorted(protected),
                claims=sum(map(len,state_claims.values())),limitations=['State claims require at least 30% of the whole state land provinces; this is a gameplay threshold, not a historical entitlement.',
                'Release uses only mapped core provinces, including countries too small to obtain a whole-state claim.',
                'Where a target province maps to multiple source locations, at least half must support the core; projection cannot subdivide a target province.',
                'No new independent countries are created at start; release uses the native diplomatic UI.',
                'Historical scripted grants and colony treaty claims are not treated as current sovereign cores.',
                'Unavailable source flags use reviewed native flags or an explicitly audited generated fallback.'])


def objects_local(obj):return ((k,v) for k,v in obj.entries() if isinstance(v,Object) and k)


def reproject(mod, previous):
    """Re-evaluate state thresholds after province/state edits, without reimporting flags."""
    from copy import deepcopy
    from build_m2_prototype import patch,replace_body
    result=deepcopy(previous);mod=Path(mod);ps=province_states(mod)
    if result.get('revision')!=REVISION:raise ValueError('Source core data must be upgraded before export')
    old_pairs={(s,r['tag']) for r in result['countries'] for s in r['states']}
    protected={tuple(r) for r in result.get('protected_claims',[])}
    new_pairs=set();releases=[];effects=[];records=[]
    for r in result['countries']:
        r['release_provinces']=sorted(set(r['release_provinces'])&set(ps))
        if not r['release_provinces']:continue
        r['coverage']=coverage(r['release_provinces'],ps)
        r['states']=[row['state'] for row in r['coverage'] if row['claim']]
        r['mapped_core_provinces']=len(r['release_provinces']);records.append(r)
        new_pairs.update((s,r['tag']) for s in r['states'])
        releases.append(block(r['tag'],'provinces = { '+' '.join(r['release_provinces'])+' }\nai_will_do = { always = no }'))
        effects.append(block('if',block('limit','c:'+r['tag']+' ?= THIS\nNOT = { has_variable = eu5_source_core_claims_initialized }')+
            ''.join('s:'+s+' = { add_claim = c:'+r['tag']+' }\n' for s in r['states'])+
            'set_variable = { name = eu5_source_core_claims_initialized value = yes }'))
    def save(rel,body):
        path=mod/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8-sig')
    save('common/country_creation/00_releasable_countries.txt',''.join(releases))
    save('common/scripted_effects/zz_eu5_source_cores.txt',block('eu5_restore_source_core_claims',''.join(effects)))
    path=mod/'common/history/states/00_eu5_world.txt';text=path.read_text(encoding='utf-8-sig');edits=[]
    for s,o in objects_local(root(text).fields()['STATES']):
        kept=[(k,v) for k,v in o.entries() if not (k=='add_claim' and (s[2:],v[2:]) in old_pairs-protected)]
        existing={(s[2:],v[2:]) for k,v in kept if k=='add_claim'}
        addition=''.join('add_claim = c:'+tag+'\n' for state,tag in sorted(new_pairs-existing) if state==s[2:])
        edits.append(replace_body(o,''.join(entry(k,v) for k,v in kept)+addition))
    save(path.relative_to(mod),patch(text,edits))
    capitals={r['tag']:min(r['coverage'],key=lambda c:(-c['core_provinces'],c['state']))['state'] for r in records if r['dormant']}
    path=mod/'common/country_definitions/zzzz_eu5_core_countries.txt'
    text=path.read_text(encoding='utf-8-sig');edits=[]
    for tag,o in objects_local(root(text)):
        if tag in capitals:
            edits.append(replace_body(o,re.sub(r'\bcapital\s*=\s*\w+','capital = '+capitals[tag],o.text())))
            result['dormant_countries'][tag]['capital']=capitals[tag]
    save(path.relative_to(mod),patch(text,edits))
    result.update(countries=records,claims=len(new_pairs))
    return result
