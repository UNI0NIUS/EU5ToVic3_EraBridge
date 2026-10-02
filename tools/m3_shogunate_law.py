"""Keep converted shogunates separate from JAP-only DLC scripts and PU bans."""
import re
from pdx_text import root
from build_m2_prototype import patch,replace_body
from build_m3_world import block

LAW='law_eu5_bakufu'
LAWS='common/laws/zz_eu5_shogunate.txt'
GOVS='common/government_types/00_00_eu5_shogunate.txt'
COUNTRIES='common/history/countries/00_eu5_world.txt'
GUARDS='common/scripted_triggers/zz_eu5_dynamic_identity.txt'
HERO='gfx/map/power_block_statues/heroes/zz_eu5_shogunate.txt'
PEDESTAL='gfx/map/power_block_statues/pedestals/zz_eu5_shogunate.txt'
PATHS={LAWS,GOVS,COUNTRIES,GUARDS,HERO,PEDESTAL}

def law_body(native):
    source=root(native).fields()['law_bakufu']
    # Economic/political modifiers and legal parent are exact native copies.
    return _law_body(source.text())

def _law_body(source):
    f=root(source).fields()
    return patch(source,[
        replace_body(f['is_visible'],'\nOR = { has_law = law_type:'+LAW+' has_variable = eu5_shogunate_seat }\n'),
        replace_body(f['on_activate'],'\nscripted_effect_parties_disappearence = yes\n'),
        replace_body(f['on_deactivate'],'\n# Do not summon a vanilla Japanese Emperor in an imported country.\n')])

def rewrite_country_history(text,source_tags):
    obj=root(text).fields()['COUNTRIES'];edits=[];changed=[]
    for key,c in obj.entries():
        tag=key.removeprefix('c:')
        if tag not in source_tags:continue
        body,n=re.subn(r'\b(activate_law\s*=\s*law_type:)law_bakufu\b',r'\g<1>'+LAW,c.text())
        if n:edits.append(replace_body(c,body));changed.append(tag)
    return patch(text,edits),changed

def assert_union_laws(history,edges):
    countries=root(history).fields()['COUNTRIES'].fields()
    checked=[]
    for edge in edges:
        if edge['target_type']!='personal_union':continue
        pair=[edge['target_overlord'],edge['target_subject']]
        for tag in pair:
            body=countries['c:'+tag].text()
            laws=set(re.findall(r'\bactivate_law\s*=\s*law_type:(\w+)',body))
            if 'law_bakufu' in laws:
                raise ValueError('Native bakufu automatically breaks personal union: '+tag)
            if not laws&{'law_monarchy','law_social_monarchy'}:
                raise ValueError('Personal union needs a monarchy on both sides: '+tag)
        checked.append(pair)
    return checked

def export_law_adapter(out):
    read=lambda rel:out.outputs[rel] if rel in out.outputs else out.w.read(rel)
    source_tags={t for t,c in out.w.countries.items() if c.get('source_id')}
    text=read(COUNTRIES);updated,changed=rewrite_country_history(text,source_tags)
    has_converted=bool(changed) or ('law_type:'+LAW in updated)
    if has_converted:
        if COUNTRIES in out.outputs:out.outputs[COUNTRIES]=updated
        else:out.write(COUNTRIES,updated)
        out.write(LAWS,block(LAW,law_body(out.w.read('common/laws/00_distribution_of_power.txt'))))
        base=root(out.w.read('common/government_types/01_monarchies.txt')).fields()['gov_shogunate'].text()
        regency=root(out.w.read('common/government_types/01_regencies.txt')).fields()['gov_regency_shogunate'].text()
        regent='OR = { has_gov_regency = yes AND = { is_subject_type = subject_type_personal_union overlord = { has_gov_regency = yes } } }'
        def adapt(body):
            return re.sub(r'country_has_primary_culture\s*=\s*cu:japanese','',body).replace('law_type:law_bakufu','law_type:'+LAW)
        base=adapt(base).replace('has_gov_regency = no','NOT = { '+regent+' }')
        regency=adapt(regency).replace('has_gov_regency = yes',regent)
        # Government selection is ordered: specific variants precede generic monarchies.
        out.write(GOVS,block('gov_eu5_regency_shogunate',regency)+block('gov_eu5_shogunate',base))
        # Existing opening identity should survive the equivalent-law migration.
        try:guard=read(GUARDS)
        except FileNotFoundError:guard=None
        if guard is not None:
            out.write(GUARDS,re.sub(r'\blaw_type:law_bakufu\b','law_type:'+LAW,guard))
        for lang in out.localization:
            out.localization[lang][LAW]='Imported Shogunate' if lang=='english' else '转档幕府'
            out.localization[lang][LAW+'_desc']=('The source shogunal constitution retains Bakufu modifiers, without the vanilla Japanese ruler scripts or ban on personal unions.' if lang=='english' else '继承源存档的幕府体制，保留幕府法数值效果；不调用原版日本专属人物脚本，不禁止共主邦联。')
            out.localization[lang]['gov_eu5_shogunate']='$gov_shogunate$'
            out.localization[lang]['gov_eu5_shogunate_desc']='$gov_shogunate_desc$'
            out.localization[lang]['gov_eu5_regency_shogunate']='$gov_regency_shogunate$'
            out.localization[lang]['gov_eu5_regency_shogunate_desc']='$gov_regency_shogunate_desc$'
    return {'changed_countries':changed,'native_japan_law_unchanged':True,'modifiers_preserved':True}

def export_statue_defaults(out):
    for source,key,newkey,path in [
        ('gfx/map/power_block_statues/heroes/00_heroes.txt','hero_wavingman','eu5_shogunate_hero',HERO),
        ('gfx/map/power_block_statues/pedestals/00_pedestals.txt','pedestal_03','eu5_shogunate_pedestal',PEDESTAL)]:
        body=root(out.w.read(source)).fields()[key].text()
        f=dict(root(body).entries())['default_choice_for_identities']
        out.write(path,block(newkey,patch(body,[replace_body(f,'\nidentity_eu5_shogunate\n')])))
        for lang in out.localization:out.localization[lang][newkey]='$'+key+'$'
