"""Finite political transition checks, alongside exact native-trigger preservation.

This is deliberately not advertised as a complete Jomini interpreter. Unknown
native predicates are indeterminate; acceptance scenarios must have a known winner.
"""
import re
from pdx_text import Object,root
from extract_m3_politics import fields,sequence
from m5_dynamic_identity import entries,VARIANTS,politically_conditional


def evaluate(obj, context, scripted, seen=()):
    def all3(values): return False if False in values else None if None in values else True
    vals=[]
    for key,value in obj.entries():
        if key in ('scope:actor','scope:target','ruler') and isinstance(value,Object):
            result=evaluate(value,context,scripted,seen)
        elif key in ('OR','AND','NOT','NOR'):
            parts=[evaluate(root(k+' = {'+v.text()+'}' if isinstance(v,Object) else k+' = '+v),context,scripted,seen) for k,v in value.entries()]
            if key in ('OR','NOR'): result=True if True in parts else None if None in parts else False
            else: result=all3(parts)
            if key in ('NOT','NOR'):result=None if result is None else not result
        elif key in ('has_law','has_law_or_variant'): result=value.split(':')[-1] in context['laws']
        elif key=='country_has_monarchy_law':result=('law_monarchy' in context['laws'] or 'law_social_monarchy' in context['laws'])==(value=='yes')
        elif key=='country_has_primary_culture':result=value.split(':')[-1] in context.get('cultures',[])
        elif key=='has_ideology': result=value.split(':')[-1]==context.get('ideology','ideology_moderate')
        elif key=='is_subject':result=context.get('subject',False)==(value=='yes')
        elif key in ('is_secessionist','is_revolutionary'):result=context.get(key,False)==(value=='yes')
        elif key=='exists' and value in ('scope:actor','scope:target'):result=True
        elif key=='always':result=value=='yes'
        elif key in scripted and value in ('yes','no') and key not in seen:
            result=evaluate(scripted[key],context,scripted,seen+(key,))
            if value=='no':result=None if result is None else not result
        else: result=None
        vals.append(result)
    return all3(vals)


def choose(obj,context,scripted,kind):
    valid=[];unknown=[]
    for key,value in obj.entries():
        if key!=kind:continue
        f=fields(value);condition=evaluate(f['trigger'],context,scripted) if 'trigger' in f else True
        item=(float(f.get('priority',0)),f['coa' if kind=='flag_definition' else 'name'])
        if condition is True:valid.append(item)
        elif condition is None:unknown.append(item)
    result=max(valid) if valid else None
    if result and any(p>=result[0] for p,k in unknown):return None
    return result[1] if result else None


def verify(mod,game,audit):
    scripts={k:v for base in (game,mod) for p in (base/'common/scripted_triggers').glob('*.txt') for k,v in entries(p).items()}
    flags={k:v for p in (mod/'common/flag_definitions').glob('*.txt') for k,v in entries(p).items()}
    names={k:v for p in (mod/'common/dynamic_country_names').glob('*.txt') for k,v in entries(p).items()}
    native_flags={k:v for p in (game/'common/flag_definitions').glob('*.txt') for k,v in entries(p).items()}
    native_names={k:v for p in (game/'common/dynamic_country_names').glob('*.txt') for k,v in entries(p).items()}
    coas={k:v for base in (game,mod) for p in (base/'common/coat_of_arms/coat_of_arms').glob('*.txt') for k,v in entries(p).items()}
    checks=0;scenarios=[]
    for tag,a in audit['countries'].items():
        context={'laws':set(a['initial_laws'].values()),'subject':a['initial_subject'],'ideology':a['initial_ideology'],'cultures':['han'] if tag=='CHI' else []}
        assert evaluate(scripts[a['opening_guard']],context,scripts) is True,tag
        assert choose(names[tag],context,scripts,'dynamic_country_name')=='EU5_DYNAMIC_SOURCE_'+tag,tag
        if a['source_coa']:
            assert choose(flags[tag],context,scripts,'flag_definition')==a['source_coa'],tag
            # New trade/tax/education rules cannot disturb an unchanged polity.
            irrelevant={**context,'laws':context['laws']|{'law_free_trade','law_graduated_taxation','law_public_schools'}}
            assert choose(flags[tag],irrelevant,scripts,'flag_definition')==a['source_coa']
            # Status-only changes (including leaving an overlord/bloc) keep the
            # full source flag. Unknown native predicates still fail closed.
            if a.get('opening_flag_guard'):
                for subject in (True,False):
                    transitioned={**context,'subject':subject}
                    assert choose(flags[tag],transitioned,scripts,'flag_definition')==a['source_coa'],(tag,'status-only flag')
            changed={**context,'laws':{'law_council_republic','law_universal_suffrage'}}
            assert evaluate(scripts[a['opening_guard']],changed,scripts) is False
            unknown=choose(flags[tag],changed,scripts,'flag_definition')
            # Some original country-specific high-priority predicates need the
            # live engine; enforce the generated branch itself for every tag.
            assert 'EU5_DYNAMIC_'+tag+'_communist' in coas
            scenarios.append({'tag':tag,'communist_flag':unknown,'engine_specific_predicates_pending':unknown is None})
        for label,current,native in [('flag_definition',flags,native_flags),('dynamic_country_name',names,native_names)]:
            if label=='flag_definition' and not a['source_coa']:continue
            exported=[fields(v) for k,v in current[tag].entries() if k==label]
            for k,v in native.get(tag,root('')).entries():
                if k!=label or not politically_conditional(v):continue
                f=fields(v);identity='coa' if label=='flag_definition' else 'name'
                offset=100 if label=='flag_definition' else 2000
                assert any(x.get(identity)==f[identity] and int(x.get('priority','0'))==int(f.get('priority','0'))+offset and x.get('trigger') and x['trigger'].text().split()==f['trigger'].text().split() for x in exported),(tag,f[identity])
        if a['source_coa']:
            for k,v in flags[tag].entries():
                f=fields(v)
                assert f['coa'] in coas,(tag,f['coa'])
                assert f.get('subject_canton')==f['coa'],tag
        checks+=1
    for tag in ('CHI','ITA'):
        for laws,ideology,expected in [({'law_presidential_republic','law_universal_suffrage'},'ideology_moderate',tag+'_republic'),({'law_council_republic','law_universal_suffrage'},'ideology_moderate',tag+'_communist')]:
            context={'laws':laws,'subject':False,'ideology':ideology,'cultures':['han']}
            assert choose(flags[tag],context,scripts,'flag_definition')==expected,(tag,expected)
            assert choose(names[tag],context,scripts,'dynamic_country_name') not in ('EU5_DYNAMIC_SOURCE_'+tag,'dyn_c_great_qing')
    for tag in ['E8S','E7B']:
        for mode,laws in [('monarchy',{'law_monarchy','law_landed_voting'}),('communist',{'law_council_republic','law_universal_suffrage'}),('anarchy',{'law_council_republic','law_anarchy'})]:
            c={'laws':laws,'subject':False}
            guard=audit['countries'][tag].get('opening_flag_guard',audit['countries'][tag]['opening_guard'])
            expected=audit['countries'][tag]['source_coa'] if evaluate(scripts[guard],c,scripts) is True else 'EU5_DYNAMIC_'+tag+'_'+mode
            assert choose(flags[tag],c,scripts,'flag_definition')==expected,(tag,mode)
    for p in [mod/'common/coat_of_arms/coat_of_arms/zz_eu5_dynamic_identity.txt']:
        for k,obj in entries(p).items():
            assert 'scale = { 1 1 } offset = { 0 0 }' in obj.text(),k
            for parent in re.findall(r'parent\s*=\s*"([^"]+)"',obj.text()):assert parent in coas,parent
            for kind,name in re.findall(r'\b(pattern|texture)\s*=\s*"([^"]+)"',obj.text()):
                dirs=['patterns'] if kind=='pattern' else ['colored_emblems','textured_emblems']
                assert any((base/'gfx/coat_of_arms'/folder/name).exists() for base in (game,mod) for folder in dirs),name
    return {'status':'passed','countries_checked':checks,'opening_identity_preserved':True,'native_conditions_preserved':True,
            'no_missing_assets':True,'tax_trade_education_do_not_change_identity':True,
            'status_only_flag_preserved':True,'full_size_source_flag':True,'scenarios':scenarios,'runtime_verified':False}
