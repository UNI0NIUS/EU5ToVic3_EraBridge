"""Installable, bounded shogunate overlay preserving other M5 work."""
import argparse
from datetime import datetime
import html
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from package_m5_dynamic_identity import ROOT,GAME,read,dump,digest
from pdx_text import root
from build_m2_prototype import objects
from m3_organizations import plan_blocs
from m3_shogunate import export_shogunate,history,ALLOWED,HISTORY,STYLES,IDENTITY,RULES,GROUPS,PRINCIPLES,TRIGGERS,LOCS,patch_rules
from build_m3_world import Exporter,load_localization
from source_country_names import refresh_saved_names
from m3_shogunate_runtime import PATHS,GLOBAL,EVENTS,JOURNAL
from m3_shogunate_law import PATHS as LAW_PATHS,LAWS,COUNTRIES,assert_union_laws

EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')
WORKSHOP=Path('D:/Steam/steamapps/workshop/content/529340')
WORKSHOP_FILES=[
    '3035507518/common/journal_entries/00_Make_Shogunate_Great_Again.txt',
    '3035507518/common/journal_entries/00_nippon_unification.txt',
    '3035507518/common/government_types/22_monarchies_daimyo.txt',
    '3035507518/events/Nippon_unification.txt',
    '3274883468/common/power_bloc_identities/UPB_power_bloc_identities.txt',
    '3274883468/common/scripted_rules/zz_UPB_scripted_rules.txt',
    '3274883468/common/decisions/UPB_decisions.txt',
    '3385002128/common/scripted_effects/com_dissolve_power_bloc.txt']

class Overlay:
    def __init__(self,mod,world,politics,source_loc=None):
        self.outputs={};self.localization={'english':{},'simp_chinese':{}}
        self.w=SimpleNamespace(read=lambda rel:((mod/rel) if (mod/rel).is_file() else (GAME/rel)).read_text(encoding='utf-8-sig'))
        self.w.countries=world['countries'];self.w.politics=politics
        self.w.profile=read(ROOT/'config/personal/m3_world.json')
        self.source_loc=source_loc or {lang:load_localization(EU5/'main_menu/localization'/lang) for lang in self.localization}
        self.valid_cultures={k for folder in [GAME/'common/cultures',mod/'common/cultures'] for p in folder.glob('*.txt') for k,_ in objects(root(p.read_text(encoding='utf-8-sig')))}
    def localize(self,token,lang,depth=0):return Exporter.localize(self,token,lang,depth)
    def write(self,rel,text):
        assert rel in ALLOWED,rel
        self.outputs[rel]=text

def build(output):
    installed=read(ROOT/'.local/economy/installation-latest.json');prior=Path(installed['package']);previous=read(prior/'package_report.json')
    base=Path(previous['mod_directory'])
    for rel,h in previous['output_sha256'].items():assert digest(base/rel)==h,rel
    assert not output.exists()
    mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    mapping=ROOT/'.local/m3/runs/20261001-073149-d689a0e7/conversion_report.json'
    source=ROOT/'.local/m3/politics-with-constitution.json'
    world=read(mapping);politics=read(source);assert world['source_sha256']==politics['source_sha256']
    tags={c['source_id']:t for t,c in world['countries'].items() if c.get('source_id')}
    edges=world['subjects']+world.get('vanilla_fallback_subjects',[])
    plan=plan_blocs(politics,tags,world['countries'],edges)
    blocs=[b for b in plan['power_blocs'] if b['source_type']=='japanese_shogunate']
    assert blocs,'No surviving eligible source shogunate'
    parents={e['target_subject']:e['target_overlord'] for e in edges}
    existing=set()
    for file in (mod/'common/history/power_blocs').glob('*.txt'):
        if file.name==Path(HISTORY).name:continue
        text=file.read_text(encoding='utf-8-sig')
        existing.update(re.findall(r'\bc:([A-Z0-9]+)',text))
    # Subjects of an existing bloc member also already belong to that bloc.
    while True:
        expanded=existing|{c for c,p in parents.items() if p in existing}
        if expanded==existing:break
        existing=expanded
    for b in blocs:
        assert not existing.intersection(b['members']),('Existing bloc conflict',existing.intersection(b['members']))
        assert b['leader'] not in parents
        for tag in [b['leader'],*b['direct_members']]:assert tag not in parents
    definitions={k:o for p in (mod/'common/country_definitions').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    country_history=dict(objects(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['COUNTRIES']))
    for b in blocs:
        assert set(b['members'])<=definitions.keys()
        assert 'activate_law = law_type:law_monarchy' in country_history['c:'+b['leader']].text(),'Shogunate leader must satisfy native monarchy condition'
    out=Overlay(mod,world,politics)
    name_changes=refresh_saved_names(world,politics,out.localize,{t for b in blocs for t in b['members']})
    # Patch existing keys instead of relying on duplicate localization load order.
    for lang in out.localization:
        for filename in ['eu5_world_l_'+lang+'.yml','eu5_dynamic_identity_l_'+lang+'.yml']:
            path=mod/'localization'/lang/filename;text=path.read_text(encoding='utf-8-sig')
            for row in name_changes:
                tag=row['tag'];c=world['countries'][tag]
                def rename(m):
                    key,value=m[1],m[2]
                    if key in [tag,'EU5_SOURCE_NAME_'+tag]:value=c['name_'+lang]
                    elif key==tag+'_ADJ':value=c['adjective_'+lang]
                    elif key=='EU5_DYNAMIC_SOURCE_'+tag:value=c['opening_name_'+lang]
                    elif key.startswith('EU5_DYNAMIC_NAME_'+tag+'_'):value=value.replace(row['old'][lang],c['name_'+lang])
                    return ' '+key+':0 "'+value+'"'
                text=re.sub(r'^\s*([\w]+):\d*\s+"(.*)"\s*$',rename,text,flags=re.M)
            path.write_text(text,encoding='utf-8-sig')
    export_shogunate(out,blocs);out.write(HISTORY,history(blocs,world['countries'],politics))
    for lang,loc in out.localization.items():
        text='l_'+lang+':\n'+''.join(' '+k+':0 "'+v.replace('"','\\"').replace('\n','\\n')+'"\n' for k,v in loc.items())
        out.write('localization/'+lang+'/eu5_shogunate_l_'+lang+'.yml',text)
    for rel,text in out.outputs.items():
        path=mod/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8-sig')
    # Read back scripted structure, references and preservation of native exit semantics.
    new=root((mod/STYLES).read_text(encoding='utf-8-sig')).fields()[IDENTITY].fields()
    native=root((GAME/'common/power_bloc_identities/00_power_bloc_identities.txt').read_text(encoding='utf-8-sig')).fields()['identity_sovereign_empire'].fields()
    for key in ['possible','cohesion','leader_modifier','non_leader_modifier']:
        if key in native:assert new[key].text()==native[key].text(),key
    assert 'eu5_shogunate_crisis_months >= 12' in new['can_leave'].text()
    assert 'is_subject = no' in new['can_leave'].text() and 'value <= 30' in new['can_leave'].text()
    rules=(mod/RULES).read_text(encoding='utf-8-sig');assert patch_rules(rules)==rules
    original_rules=root((base/RULES).read_text(encoding='utf-8-sig')).fields();new_rules=root(rules).fields()
    for key,obj in original_rules.items():
        if key not in ['can_lead_power_bloc','is_weak_power_bloc']:assert new_rules[key].text()==obj.text(),key
    assert 'eu5_is_chartered_hre_leader' in rules and 'identity:identity_eu5_hre_empire' in rules
    group=root((mod/GROUPS).read_text(encoding='utf-8-sig')).fields()['principle_group_eu5_shogunate_vassalization']
    assert dict(group.entries())['primary_for_identity']==IDENTITY
    principles=root((mod/PRINCIPLES).read_text(encoding='utf-8-sig')).fields()
    for i in range(1,4):assert f'principle_eu5_shogunate_vassalization_{i}' in principles
    parsed=root((mod/HISTORY).read_text(encoding='utf-8-sig')).fields()['POWER_BLOCS']
    for leader,obj in objects(parsed):
        bloc=next(b for b in blocs if 'c:'+b['leader']==leader)
        init=dict(dict(obj.entries())['create_power_bloc'].entries())
        assert init['identity']==IDENTITY and init['principle']==bloc['principle']
        assert [v.removeprefix('c:') for k,v in init_obj_entries(obj) if k=='member']==bloc['direct_members']
    second=Overlay(mod,world,politics,out.source_loc);export_shogunate(second,blocs)
    for rel,text in second.outputs.items():assert text==(mod/rel).read_text(encoding='utf-8-sig'),rel
    for rel in PATHS|LAW_PATHS|{STYLES,TRIGGERS,PRINCIPLES}:
        if not (mod/rel).exists():continue
        # Force a full parse of every nested block, not just the outer wrapper.
        def walk(obj):
            from pdx_text import Object
            for k,v in obj.entries():
                if isinstance(v,Object):walk(v)
        walk(root((mod/rel).read_text(encoding='utf-8-sig')))
    for b in blocs:
        if b.get('shogun_character_basis')=='heir_during_regency':
            assert b.get('heir_conversion'), 'Shared source monarch was not preserved'
            assert 'heir = yes' in (mod/GLOBAL).read_text(encoding='utf-8-sig')
    runtime_text='\n'.join((mod/rel).read_text(encoding='utf-8-sig') for rel in PATHS|{TRIGGERS,STYLES})
    declarations={k for rel in PATHS|{TRIGGERS,STYLES} for k,_ in root((mod/rel).read_text(encoding='utf-8-sig')).entries()}
    calls=set(re.findall(r'\b(eu5_shogunate_\w+)\s*=\s*(?:yes|no)\b',runtime_text))
    assert calls<=declarations,('Undefined scripted calls',calls-declarations)
    assert set(re.findall(r'\bid\s*=\s*(eu5_shogunate\.\d+)',runtime_text))<=declarations
    assert set(re.findall(r'\btype\s*=\s*(je_eu5_shogunate_\w+)',runtime_text))<=declarations
    for lang,loc in out.localization.items():
        for key in re.findall(r'\b(?:title|desc|name)\s*=\s*(eu5_shogunate\.\d+\.\w+)',runtime_text):assert key in loc,key
        locfile=(mod/('localization/'+lang+'/eu5_shogunate_l_'+lang+'.yml')).read_text(encoding='utf-8-sig')
        assert len(re.findall(r'^\s*\w[\w.]*:\d*\s+".*"$',locfile,re.M))==len(loc),'Broken localization escaping'
    for asset in set(re.findall(r'\bicon\s*=\s*"([^"]+)"',runtime_text)):
        assert (GAME/asset).is_file(),asset
    effects=GAME/'common/scripted_effects/00_victoria_ip4_scripted_effects.txt'
    native_effects=root(effects.read_text(encoding='utf-8-sig')).fields()
    assert {'add_regency_modifier','designate_character_as_regent'}<=native_effects.keys()
    # Initial sovereignty and every HRE-specific file must remain exact.
    union_checks=assert_union_laws((mod/COUNTRIES).read_text(encoding='utf-8-sig'),edges)
    if (mod/LAWS).exists():
        original=root((GAME/'common/laws/00_distribution_of_power.txt').read_text(encoding='utf-8-sig')).fields()['law_bakufu'].fields()
        adapted=root((mod/LAWS).read_text(encoding='utf-8-sig')).fields()['law_eu5_bakufu'].fields()
        assert adapted['modifier'].text()==original['modifier'].text()
        assert 'country_restore_japanese_emperor' not in (mod/LAWS).read_text(encoding='utf-8-sig')
    original_countries=root((base/COUNTRIES).read_text(encoding='utf-8-sig')).fields()['COUNTRIES'].fields()
    new_countries=root((mod/COUNTRIES).read_text(encoding='utf-8-sig')).fields()['COUNTRIES'].fields()
    for key,obj in original_countries.items():
        assert re.sub(r'law_type:law_bakufu\b','law_type:law_eu5_bakufu',obj.text())==new_countries[key].text(),key
    for rel in previous['output_sha256']:
        if 'hre' in rel.lower() or rel.startswith('common/history/diplomacy/'):
            assert digest(mod/rel)==previous['output_sha256'][rel],rel
    meta=read(mod/'.metadata/metadata.json');m=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',installed['version']);assert m
    meta['version']=f'0.5.{int(m[1])+1}-m5-test{int(m[2])+1}';dump(mod/'.metadata/metadata.json',meta)
    current={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}
    changed=[p for p,h in current.items() if previous['output_sha256'].get(p)!=h]
    assert set(previous['output_sha256'])<=set(current) and set(changed)<=ALLOWED
    audit={'blocs':blocs,'law_adapter':out.shogunate_law_report,'personal_union_maintenance_checked':union_checks,
           'name_changes':name_changes,'workshop_code_sha256':{str(WORKSHOP/p):digest(WORKSHOP/p) for p in WORKSHOP_FILES},
           'dlc_meiji_integration':'Coexists; native JAP-specific Meiji chain is not activated. Native generic regency is reused.',
           'omitted':[b for b in plan['omitted_organizations'] if b['source_type']=='japanese_shogunate'],
           'source_relationships_unchanged':True,'existing_blocs_unchanged':True,'runtime_verified':False}
    dump(output/'shogunate.json',audit)
    b=blocs[0];labels=lambda ts:'、'.join(world['countries'][t]['name_simp_chinese']+' ('+t+')' for t in ts)
    (output/'review.html').write_text('''<!doctype html><meta charset="utf-8"><title>幕府机制与源身份</title>
<style>body{font:17px system-ui;max-width:1000px;margin:40px auto;line-height:1.8}pre{white-space:pre-wrap}td,th{padding:10px;border-bottom:1px solid #ddd}a{color:#156a83}</style>'''+
        '<h1>幕府至高帝国 · '+meta['version']+'</h1><p>集团领导国：'+html.escape(labels([b['leader']]))+'；幕府席位：'+html.escape(labels([b['nominal_shogun']]))+'；天皇朝廷：'+html.escape(labels(b['imperial_court']))+'</p><p>成员：'+html.escape(labels(b['members']))+'</p>'+
        '<h2>源存档核对</h2><table><tr><th>TAG</th><th>旧译名</th><th>当前开局名</th></tr>'+''.join('<tr><td>'+r['tag']+'</td><td>'+html.escape(r['old']['simp_chinese'])+'</td><td>'+html.escape(r['new']['simp_chinese'])+'</td></tr>' for r in name_changes)+'</table>'+
        '<p>组织领袖在摄政期间取继承人；本档将军与共主继承人是同一个萨摩家人物（源 ID '+str(b['shogun_character'])+'）。转换到邦联宗主一次，接入 V3 通用摄政／成年归政机制。V3 共主邦联共享宗主统治者，不能同时显示源档各支国的独立摄政者。</p>'+
        '<h2>已实现</h2><p>至高帝国模板与三级附庸原则；8 国开局保留源宗属树。固定凝聚力 +15、初始凝聚力 +50，独立领袖豁免列强排名限制。另设幕府权威，依源法律、合法性、地主政治地位和战争状态每月计算。</p><p>和平退出要求权威连续 12 个月低于 30，且影响力不高于 30；附庸不能借此摆脱宗主。其余独立成员可用原版退出集团外交博弈。版籍奉还需民族主义、友好关系、权威至少 60，并由申请国与领袖双方确认；本轮 AI 不自行提出吞并申请。领袖废除君主制后可决议解散集团。</p>'+
        '<h2>兼容性与限制</h2><p>幕府法改为兼容源存档的独立变体，数值效果不变，移除 JAP 专属人物钩子；原版法律不改。神罗专属文件、其他国家法律、经济人口及开局外交关系保留。没有完整接入 JAP 专属明治维新链，没有新增自动天皇复辟、幕府战争夺位或重建路线。版籍奉还保留当前领袖 TAG，不强制变为日本。须开新战役验证，尚未游戏内实测。</p>'+
        '<p>参考实际脚本：<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=3035507518">Make Tennou Great Again</a>、<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=3274883468">China Power Bloc</a>、Community Mod Framework。代码哈希见 shogunate.json；不要求启用这些模组，不分发其资产。</p>'+
        '<h2>测试顺序</h2><p>开新局，检查厚岸幕府／镰仓藩／大和朝廷；选择镰仓检查萨摩家继承人及摄政。确认幕府 8 成员与一级附庸原则，推进一个月看日志权威，再推进一年查看成员稳定性。版籍奉还请在独立测试存档中进行。</p><pre>'+html.escape(str(b['authority']))+'</pre>',encoding='utf-8')
    inputs=[prior/'package_report.json',mapping,source,Path(__file__),ROOT/'tools/m3_shogunate.py',ROOT/'tools/m3_organizations.py',ROOT/'tools/m3_shogunate_runtime.py',ROOT/'tools/source_country_names.py',ROOT/'config/personal/m3_world.json',
            GAME/'common/power_bloc_identities/00_power_bloc_identities.txt',GAME/'common/power_bloc_principles/00_power_bloc_principles.txt']
    inputs += [WORKSHOP/p for p in WORKSHOP_FILES]
    inputs += [EU5/'in_game/common'/rel for rel in ['international_organizations/japanese_shogunate.txt','international_organizations/union.txt','customizable_localization/country_ranks.txt','laws/20_shogunate.txt']]
    inputs += [effects,GAME/'events/iberia_events/regency_events.txt']
    inputs += [ROOT/'tools/m3_shogunate_law.py',GAME/'common/laws/00_distribution_of_power.txt',GAME/'common/diplomatic_actions/22_subject_personal_union.txt',GAME/'common/government_types/01_monarchies.txt']
    report={'status':'m5_shogunate_static_verified_runtime_pending','version':meta['version'],'mod_name':meta['name'],'mod_directory':str(mod),
        'prior_package':str(prior),'update_scope':'m5_shogunate','new_campaign_required':True,'changed_files':changed,'output_sha256':current,
        'input_sha256':{str(p.resolve()):digest(p) for p in inputs}}
    dump(output/'package_report.json',report)
    dump(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
        'shogunate':{'status':'passed','crisis_exit_verified':True,'subject_trees_preserved':True,'existing_blocs_preserved':True,'references_valid':True,'idempotent':True,'runtime_verified':False},
        'unrelated_files_byte_identical':True,'package_report_sha256':digest(output/'package_report.json'),
        'audit_sha256':{n:digest(output/n) for n in ['shogunate.json','review.html']}})
    print({'package':str(output),'version':meta['version'],'leader':b['leader'],'members':b['members'],'changed_files':changed})

def init_obj_entries(obj):return dict(obj.entries())['create_power_bloc'].entries()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'.local/economy/packages'/('m5-shogunate-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    build(parser.parse_args().output.resolve())
