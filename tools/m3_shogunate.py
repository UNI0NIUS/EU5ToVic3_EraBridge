"""An inherited shogunate based on the Sovereign Empire, without changing sovereignty."""
import re
from pdx_text import root
from build_m2_prototype import patch, replace_body
from m3_flags import block
from m3_shogunate_runtime import PATHS, MEMBER, ELIGIBLE, export_runtime
from m3_shogunate_law import PATHS as LAW_PATHS,export_law_adapter,export_statue_defaults

IDENTITY='identity_eu5_shogunate'
TRIGGER='eu5_is_shogunate_leader'
RULES='common/scripted_rules/00_scripted_rules.txt'
GROUPS='common/power_bloc_principle_groups/00_power_bloc_principle_groups.txt'
IDENTITIES='common/power_bloc_identities/00_power_bloc_identities.txt'
STYLES='common/power_bloc_identities/zz_eu5_shogunate.txt'
PRINCIPLES='common/power_bloc_principles/zz_eu5_shogunate.txt'
TRIGGERS='common/scripted_triggers/zz_eu5_shogunate.txt'
HISTORY='common/history/power_blocs/01_eu5_shogunate.txt'
LOCS=['localization/'+lang+'/eu5_shogunate_l_'+lang+'.yml' for lang in ['english','simp_chinese']]
ALLOWED={'.metadata/metadata.json',RULES,GROUPS,STYLES,PRINCIPLES,TRIGGERS,HISTORY,*LOCS,*PATHS,*LAW_PATHS,
    'localization/english/eu5_world_l_english.yml',
    'localization/simp_chinese/eu5_world_l_simp_chinese.yml',
    'localization/english/eu5_dynamic_identity_l_english.yml',
    'localization/simp_chinese/eu5_dynamic_identity_l_simp_chinese.yml'}

def patch_rules(text):
    rules=root(text).fields();changes=[]
    lead=rules['can_lead_power_bloc'];weak=rules['is_weak_power_bloc']
    if TRIGGER not in lead.text():
        changes.append(replace_body(lead,'\nNOT = { has_variable = eu5_shogunate_dissolving }\nOR = {\n'+lead.text()+'\n'+TRIGGER+' = yes\n}\n'))
    elif 'has_variable = eu5_shogunate_dissolving' not in lead.text():
        changes.append(replace_body(lead,'\nNOT = { has_variable = eu5_shogunate_dissolving }\n'+lead.text()))
    if 'identity:'+IDENTITY not in weak.text():
        changes.append(replace_body(weak,weak.text()+'\nNOT = { has_identity = identity:'+IDENTITY+' }\n'))
    return patch(text,changes)

def export_shogunate(exporter,blocs):
    exporter.shogunate_law_report=export_law_adapter(exporter)
    affected=[b for b in blocs if b['source_type']=='japanese_shogunate']
    if not affected:return
    def read(rel):
        return exporter.outputs[rel] if rel in getattr(exporter,'outputs',{}) else exporter.w.read(rel)
    def write(rel,text):
        if rel in getattr(exporter,'outputs',{}):exporter.outputs[rel]=text
        else:exporter.write(rel,text)
    source=root(exporter.w.read(IDENTITIES)).fields()['identity_sovereign_empire'].text()
    parts=root(source).fields()
    modifiers,count=re.subn(r'power_bloc_cohesion_per_member_add\s*=\s*-3\b',
        'power_bloc_cohesion_add = 15 # inherited charter +25, fixed size penalty -10',parts['power_bloc_modifier'].text())
    assert count==1,'Unsupported Sovereign Empire definition'
    body=patch(source,[replace_body(parts['power_bloc_modifier'],modifiers),
                       replace_body(parts['can_leave'],'''custom_tooltip = {
text = eu5_shogunate_exit_tt
is_subject = no
is_power_bloc_leader = no
power_bloc = {
    power_bloc_leader = { var:eu5_shogunate_crisis_months >= 12 }
    leverage_advantage = { target = root value <= 30 }
}
}'''),
                       replace_body(parts['visible'],'\nalways = no\n')])
    exporter.write(STYLES,block(IDENTITY,body))
    # Both HRE and shogunate changes compose on the exporter output.
    rules=read(RULES)
    write(RULES,patch_rules(rules))
    exporter.write(TRIGGERS,block(TRIGGER,'''is_power_bloc_leader = yes
is_subject = no
NOT = { is_country_type = decentralized }
power_bloc = { has_identity = identity:identity_eu5_shogunate }
''')+block('eu5_shogunate_member',MEMBER)+block('eu5_shogunate_can_petition',ELIGIBLE))
    group_text=read(GROUPS);groups=root(group_text).fields()
    group='principle_group_eu5_shogunate_vassalization'
    if group not in groups:
        original=groups['principle_group_vassalization']
        group_text=patch(group_text,[replace_body(original,original.text()+'\nblocking_identity = '+IDENTITY+'\n')])
        group_text+=block(group,'primary_for_identity = '+IDENTITY+'\nunlocking_identity = '+IDENTITY+'\n'+
            block('levels','\n'.join(f'principle_eu5_shogunate_vassalization_{i}' for i in range(1,4))))
    write(GROUPS,group_text)
    principles=root(exporter.w.read('common/power_bloc_principles/00_power_bloc_principles.txt')).fields()
    exporter.write(PRINCIPLES,''.join(block(f'principle_eu5_shogunate_vassalization_{i}',
        principles[f'principle_vassalization_{i}'].text().replace('identity:identity_sovereign_empire','identity:'+IDENTITY)) for i in range(1,4)))
    labels={IDENTITY:('Shogunal Empire','幕府至高帝国'),
        IDENTITY+'_desc':('An inherited shogunal order based on the Sovereign Empire. Existing unions and vassals remain intact. Bloc leadership, shogunal office and the imperial court are distinct. Peaceful exit requires a sustained authority crisis; see the journal.',
                          '以至高帝国为基础延续的幕府秩序。保留源存档的共主邦联与附庸关系；集团领导国不等于幕府席位或将军本人。和平退出须满足持续权威危机条件，详见幕府日志。'),
        'eu5_shogunate_exit_tt':('Independent members may leave after authority remains below 30 for 12 consecutive months and leverage is at most 30. Otherwise use the Leave Power Bloc diplomatic play.',
                                '独立成员须在幕府权威连续 12 个月低于 30 且影响力不高于 30 时和平退出；否则须使用退出集团外交博弈。'),
        TRIGGER:('Independent leader of the inherited Shogunate','继承幕府的独立集团领袖')}
    for suffix in ('','_desc'):labels[group+suffix]=('$principle_group_vassalization'+suffix+'$',)*2
    for i in range(1,4):labels[f'principle_eu5_shogunate_vassalization_{i}_desc']=('$principle_group_vassalization_desc$',)*2
    for b in affected:
        labels[b['name']]=('Japanese Shogunate','日本幕府')
        b['stability']={'identity':IDENTITY,'initial_cohesion_add':50,'fixed_cohesion_add':15,
            'weak_rank_exempt':True,'independent_leader_rank_exempt':True,
            'peaceful_exit':'12_month_authority_crisis_and_leverage_at_most_30','runtime_verified':False}
    for key,values in labels.items():
        for lang,value in zip(('english','simp_chinese'),values):exporter.localization[lang][key]=value
    export_runtime(exporter,affected)
    export_statue_defaults(exporter)

def history(blocs,countries,politics):
    bodies=[]
    for b in blocs:
        if b['source_type']!='japanese_shogunate':continue
        sid=countries[b['leader']]['source_id'];color=' '.join(politics['countries'][sid]['color'])
        body=f'name = {b["name"]}\nmap_color = {{ {color} }}\nfounding_date = {b["founding_date"]}\nidentity = {IDENTITY}\nprinciple = {b["principle"]}\n'
        body+=''.join(f'member = c:{tag}\n' for tag in b['direct_members'])
        bodies.append('c:'+b['leader']+' ?= {\n'+block('create_power_bloc',body)+block('power_bloc','add_cohesion_number = 50')+'}\n')
    return block('POWER_BLOCS',''.join(bodies))
