"""Source opening identities with live V3 political variants; no event polling.

The opening guard is derived from the final exported laws, not EU5 labels or a
borrowed vanilla template. Native conditions remain engine-evaluated verbatim.
"""
from collections import Counter
import re
from pathlib import Path
from pdx_text import Object, root
from extract_m3_politics import fields, sequence
from economy_model import block, definitions
from complete_economy import active_laws
from build_m2_prototype import patch, replace_body


# Generic variants sit below the equivalent original game's political variants.
# Higher ideological flags must still beat lower-level native republican flags.
VARIANTS = {
    'monarchy': ('coa_def_monarchy_flag_trigger', -20, 'ce_crown_simple.dds'),
    'republic': ('coa_def_republic_flag_trigger', -20, 'ce_laurel.dds'),
    'theocracy': ('coa_def_theocracy_flag_trigger', 9, 'ce_sun.dds'),
    'dictatorship': ('coa_def_dictatorship_flag_trigger', 18, 'ce_fasces.dds'),
    'communist': ('coa_def_communist_flag_trigger', 1400, 'ce_hammer_and_sickle.dds'),
    'fascist': ('coa_def_fascist_flag_trigger', 1401, 'ce_fasces.dds'),
    'anarchy': ('coa_def_anarchy_flag_trigger', 1900, 'ce_star_05.dds'),
    'technocracy': ('coa_def_technocracy_flag_trigger', 25, 'ce_star_08.dds'),
    'nihilist': ('coa_def_nihilist_flag_trigger', 1450, 'ce_star_05.dds'),
}
TITLES = {
    'english': {'monarchy':'Kingdom of {}','republic':'Republic of {}','theocracy':'Sacred State of {}',
                'dictatorship':'State of {}','communist':"People's Republic of {}",'fascist':'National State of {}',
                'anarchy':'Free Communes of {}','technocracy':'Technate of {}','nihilist':'Republic of {}'},
    'simp_chinese': {'monarchy':'{}王国','republic':'{}共和国','theocracy':'{}教国','dictatorship':'{}国',
                     'communist':'{}人民共和国','fascist':'{}民族国','anarchy':'{}自由公社','technocracy':'{}技术官僚国','nihilist':'{}共和国'},
}


def entries(path):
    return {k:v for k,v in root(path.read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}


def set_scalar(body, key, value):
    body = re.sub(r'(?m)^\s*'+re.escape(key)+r'\s*=\s*[^\s{}]+[^\S\n]*$', '', body)
    return body+'\n'+key+' = '+str(value)+'\n'


def referenced_law_groups(objects, scripted, lawdefs):
    """Only laws actually used by this TAG's native identity conditions matter."""
    groups={'lawgroup_governance_principles','lawgroup_distribution_of_power'}
    seen=set()
    def walk(obj):
        for key,value in obj.entries():
            if key in ('has_law','has_law_or_variant'):
                law=value.split(':')[-1]
                if law in lawdefs:groups.add(lawdefs[law]['group'])
            elif isinstance(value,Object):walk(value)
            elif key in scripted and key not in seen:
                seen.add(key);walk(scripted[key])
    for obj in objects:walk(obj)
    return groups


def guard_body(laws, lawdefs, subject, ideology, relevant_groups=None, *, preserve_flag=False):
    grouped = {lawdefs[l]['group']:l for l in laws}
    groups=relevant_groups or {'lawgroup_governance_principles','lawgroup_distribution_of_power'}
    chosen = [grouped[g] for g in sorted(groups) if g in grouped]
    actor = ''.join('has_law = law_type:'+l+'\n' for l in chosen)
    if not preserve_flag:
        actor += 'is_subject = '+('yes' if subject else 'no')+'\n'
    # These original triggers can change through a ruler as well as through law.
    # Preserve an already ideological source start, but don't freeze a later one.
    if ideology not in ('ideology_fascist','ideology_integralist') and not set(chosen)&{'law_corporate_state','law_social_monarchy'}:
        actor += 'coa_fascist_trigger = no\n'
    if ideology != 'ideology_nihilist': actor += 'coa_nihilist_trigger = no\n'
    return 'exists = scope:actor\n'+block('scope:actor',actor).replace(' = {',' ?= {',1)+'NOT = { coa_def_secessionist_or_revolutionary_trigger = yes }\n'


def politically_conditional(obj):
    trigger = fields(obj).get('trigger')
    return isinstance(trigger,Object) and bool(list(trigger.entries()))


def flag_body(coa, priority, trigger=None, canton=False):
    # Keep all priorities nonnegative; don't rely on an undocumented engine
    # sentinel for negative-priority fallback candidates.
    if priority<100000:priority+=100
    body = f'coa = {coa}\nsubject_canton = {coa}\npriority = {priority}\n'
    if canton:
        body += 'allow_overlord_canton = yes\noverlord_canton_offset = { 0 0 }\noverlord_canton_scale = { 0.4 0.4 }\n'
    if trigger: body += block('trigger',trigger)
    return block('flag_definition',body)


def name_body(key, tag, priority, trigger=None):
    if priority<100000:priority+=2000
    text = f'name = {key}\nadjective = {tag}_ADJ\nis_main_tag_only = yes\npriority = {priority}\n'
    if trigger: text += block('trigger', trigger)
    return block('dynamic_country_name',text)


def generic_art(base, color, mode, religion):
    """A full-size source flag plus a small political charge outside the canton.

    This uses native COA sub-composition, not flattened raster snapshots. The
    source COA stays immutable and can be reused by multiple countries.
    """
    emblem = VARIANTS[mode][2]
    if mode == 'theocracy':
        if religion in ('catholic','protestant','orthodox','oriental_orthodox'): emblem='ce_cross_couped.dds'
        elif religion in ('sunni','shiite'): emblem='ce_crescent.dds'
        elif religion in ('hindu','mahayana','theravada','vajrayana'): emblem='ce_lotus.dds'
    field = [155,23,32] if mode=='communist' else [26,28,31] if mode in ('fascist','anarchy','nihilist') else color
    if mode=='technocracy': field=[38,83,111]
    metal = [235,205,116] if mode in ('monarchy','theocracy','communist') else [239,235,218]
    rgb=lambda v:'rgb { '+' '.join(str(int(x)) for x in v)+' }'
    text = f'pattern = "pattern_solid.tga"\ncolor1 = {rgb(field)}\ncolor2 = {rgb(metal)}\n'
    # Native sub instances use offset (top-left), unlike emblem position (centre).
    text += block('sub',f'parent = "{base}"\ninstance = {{ scale = {{ 1 1 }} offset = {{ 0 0 }} }}')
    text += block('colored_emblem',f'texture = "{emblem}"\ncolor1 = {rgb(metal)}\ncolor2 = {rgb(metal)}\ninstance = {{ position = {{ 0.82 0.22 }} scale = {{ 0.16 0.22 }} }}')
    return text


def native_localizations(game, lang):
    path=game/'localization'/lang/('countries_l_'+lang+'.yml')
    return dict(re.findall(r'^\s*([\w-]+):\d*\s+"(.*)"\s*$',path.read_text(encoding='utf-8-sig'),re.M))


def apply(mod, game, world, *, refresh_legacy_names=True):
    """Rebase identity rules on any final package; return a per-country audit."""
    mod,game=Path(mod),Path(game)
    # Old M3 mapping reports predate EU5's saved territorial name overrides.
    # Refresh on every overlay so a later flag/politics package cannot regress them.
    import json
    from build_m3_world import Exporter, load_localization
    from types import SimpleNamespace
    from source_country_names import refresh_saved_names
    source_path=Path(__file__).resolve().parents[1]/'.local/m3/politics-with-constitution.json'
    if refresh_legacy_names and world.get('source_sha256') and source_path.exists():
        politics=json.loads(source_path.read_text(encoding='utf-8'))
        if politics.get('source_sha256')==world['source_sha256']:
            source_game=Path('D:/Steam/steamapps/common/Europa Universalis V/game')
            resolver=SimpleNamespace(source_loc={lang:load_localization(source_game/'main_menu/localization'/lang) for lang in TITLES})
            resolver.localize=lambda token,lang,depth=0:Exporter.localize(resolver,token,lang,depth)
            refresh_saved_names(world,politics,resolver.localize)
    countries=world['countries'];tags={t for t,c in countries.items() if c['source_id']}
    old_flags={k:v for p in (mod/'common/flag_definitions').glob('*.txt') for k,v in entries(p).items()}
    native_flags={k:v for p in (game/'common/flag_definitions').glob('*.txt') for k,v in entries(p).items()}
    native_names={k:v for p in (game/'common/dynamic_country_names').glob('*.txt') for k,v in entries(p).items()}
    native_tags={k for p in (game/'common/country_definitions').glob('*.txt') for k in entries(p)}
    scripted={k:v for p in (game/'common/scripted_triggers').glob('*.txt') for k,v in entries(p).items()}
    lawdefs=definitions(game/'common/laws')
    lawdefs.update(definitions(mod/'common/laws'))
    current_defs={k:v for p in (mod/'common/country_definitions').glob('*.txt') for k,v in entries(p).items()}
    from types import SimpleNamespace
    target=SimpleNamespace(game=game)
    history=fields(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES']
    history={k[2:]:v for k,v in history.entries()}
    parents={e['target_subject']:e['target_overlord'] for e in world['subjects']}
    chars=fields(root((mod/'common/history/characters/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['CHARACTERS']
    ideology={}
    for tag,obj in chars.entries():
        for k,v in obj.entries():
            if k=='create_character' and fields(v).get('ruler')=='yes': ideology[tag[2:]]=fields(v).get('ideology','ideology_moderate')
    loc={lang:{} for lang in TITLES};native_loc={lang:native_localizations(game,lang) for lang in TITLES}
    flags,names,guards,coas,audit={},{},[],[],{}
    for tag in sorted(tags):
        c=countries[tag];laws=active_laws(history[tag],target,c)
        current=fields(current_defs[tag])
        color=[int(float(x)) for x in sequence(current['color'])]
        guard='eu5_identity_start_'+tag
        relevant=referenced_law_groups([native_flags.get(tag,root('')),native_names.get(tag,root(''))],scripted,lawdefs)
        body=guard_body(laws,lawdefs,tag in parents,ideology.get(tag,'ideology_moderate'),relevant)
        guards.append(block(guard,body))
        flag_guard='eu5_flag_start_'+tag
        guards.append(block(flag_guard,guard_body(laws,lawdefs,tag in parents,ideology.get(tag,'ideology_moderate'),relevant,preserve_flag=True)))
        opening=guard+' = yes'
        changed='NOT = { '+guard+' = yes }\n'
        frozen=[]
        for k,v in old_flags.get(tag,root('')).entries():
            if k=='flag_definition':
                f=fields(v)
                if (int(f.get('priority',0))==1000 and not politically_conditional(v)) or (int(f.get('priority',0))==100000 and any(g+' = yes' in v.text() for g in (guard,flag_guard))): frozen.append(v)
        if len(frozen)>1: raise ValueError('Ambiguous source flag: '+tag)
        restored_flags=[]
        if frozen:
            f=fields(frozen[0]);base=f['coa'];canton=f.get('allow_overlord_canton')=='yes'
            # Current source art and geometry remain the exact opening definition.
            initial=flag_body(base,100000,flag_guard+' = yes',canton)
            contents=initial+flag_body(base,-100,canton=canton)
            for key,obj in native_flags.get(tag,root('')).entries():
                if key!='flag_definition' or not politically_conditional(obj): continue
                nf=fields(obj)
                nb=set_scalar(obj.text(),'subject_canton',nf['coa'])
                nb=set_scalar(nb,'priority',int(nf.get('priority',0))+100)
                # Existing native trigger/priority/art remain; force the opening
                # guard above them only while the actual converted polity survives.
                if canton:
                    for key,val in [('allow_overlord_canton','yes')]: nb=set_scalar(nb,key,val)
                contents+=block('flag_definition',nb);restored_flags.append(nf['coa'])
            for mode,(trigger,priority,_) in VARIANTS.items():
                key='EU5_DYNAMIC_'+tag+'_'+mode
                coas.append(block(key,generic_art(base,color,mode,current.get('religion',c['religion']))))
                contents+=flag_body(key,priority,'NOT = { '+flag_guard+' = yes }\n'+trigger+' = yes',canton)
            flags[tag]=contents
        # Native names remain available after a political transition. Country
        # identity conditions such as Manchu primary culture are never stripped.
        source_key='EU5_DYNAMIC_SOURCE_'+tag
        contents=name_body(source_key,tag,100000,opening)+name_body(source_key,tag,-1000)
        restored_names=[]
        for key,obj in native_names.get(tag,root('')).entries():
            if key!='dynamic_country_name' or not politically_conditional(obj): continue
            nf=fields(obj);contents+=block(key,set_scalar(obj.text(),'priority',int(nf.get('priority',0))+2000));restored_names.append(nf['name'])
        for lang in TITLES:
            loc[lang][source_key]=c.get('opening_name_'+lang,c['name_'+lang])
        for mode,(trigger,_,_) in VARIANTS.items():
            key='EU5_DYNAMIC_NAME_'+tag+'_'+mode
            # Generic national names stay below all applicable native names.
            # Mutually exclusive mode guards keep dictatorship above republic.
            excludes={'monarchy':['fascist','technocracy'],'republic':['communist','fascist','dictatorship','anarchy','technocracy','nihilist'],
                      'dictatorship':['communist','fascist','anarchy','technocracy','nihilist'],
                      'communist':['anarchy'],'theocracy':['technocracy']}.get(mode,[])
            when=changed+trigger+' = yes\n'+''.join(VARIANTS[x][0]+' = no\n' for x in excludes)
            contents+=name_body(key,tag,-100,when)
            for lang in TITLES:
                neutral=native_loc[lang].get(tag,c['name_'+lang]) if tag in native_tags else c['name_'+lang]
                title=TITLES[lang][mode]
                if mode=='monarchy':
                    tier=current.get('tier','kingdom')
                    title={'english':{'empire':'Empire of {}','principality':'Principality of {}','city_state':'City State of {}'},
                           'simp_chinese':{'empire':'{}帝国','principality':'{}公国','city_state':'{}城邦'}}[lang].get(tier,title)
                loc[lang][key]=title.format(neutral)
        names[tag]=contents
        audit[tag]={'name':c['name_simp_chinese'],'initial_laws':{lawdefs[l]['group']:l for l in sorted(laws) if lawdefs[l]['group'] in relevant},
                    'initial_subject':tag in parents,'initial_ideology':ideology.get(tag,'ideology_moderate'),
                    'opening_guard':guard,'opening_flag_guard':flag_guard,'source_coa':fields(frozen[0])['coa'] if frozen else None,
                    'native_flag_list_preserved':not bool(frozen),'restored_native_flags':restored_flags,
                    'restored_native_names':restored_names,'generic_flag_variants':len(VARIANTS) if frozen else 0}
    changed_files=[]
    def write(rel,text):
        p=mod/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8-sig');changed_files.append(rel)
    def replace_lists(folder,replacements,overflow):
        found=set()
        for p in sorted((mod/folder).glob('*.txt')):
            edits=[];text=p.read_text(encoding='utf-8-sig')
            for key,obj in entries(p).items():
                if key in replacements: edits.append(replace_body(obj,'\n'+replacements[key]+'\n'));found.add(key)
            if edits:write(p.relative_to(mod).as_posix(),patch(text,edits))
        missing=set(replacements)-found
        if missing:
            p=mod/overflow;text=p.read_text(encoding='utf-8-sig') if p.exists() else ''
            write(overflow,text+''.join(block(t,replacements[t]) for t in sorted(missing)))
    replace_lists('common/flag_definitions',flags,'common/flag_definitions/zz_eu5_world.txt')
    replace_lists('common/dynamic_country_names',names,'common/dynamic_country_names/zz_eu5_source_names.txt')
    write('common/scripted_triggers/zz_eu5_dynamic_identity.txt',''.join(guards))
    write('common/coat_of_arms/coat_of_arms/zz_eu5_dynamic_identity.txt',''.join(coas))
    for lang,values in loc.items():
        text='l_'+lang+':\n'+''.join(' '+k+':0 "'+v.replace('"','\\"')+'"\n' for k,v in sorted(values.items()))
        write('localization/'+lang+'/eu5_dynamic_identity_l_'+lang+'.yml',text)
    return {'countries':audit,'summary':{'source_countries':len(tags),'source_flags_unfrozen':len(flags),
            'native_dynamic_flags_restored':sum(len(a['restored_native_flags']) for a in audit.values()),
            'native_dynamic_names_restored':sum(len(a['restored_native_names']) for a in audit.values()),
            'generic_coas':len(coas)},'changed_files':sorted(set(changed_files)),
            'limitations':['Native script conditions are preserved, not all simulated offline.',
                          'Generated political ensigns are design fallbacks, not historical flag recoveries.',
                          'Same founding governance and power laws restore the source identity; tax/trade/education laws are irrelevant.',
                          'Runtime refresh, revolutions and subject cantons require in-game verification.']}
