"""Source-conditioned historical analogies, backed by installed V3 1836 scripts.

This is deliberately not a general Clausewitz script interpreter: native templates
include only unconditional startup effects and direct law assignments. Conditional
branches are recorded as skipped, never flattened into simultaneous laws.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
from pdx_text import Object, root
from extract_m3_politics import fields, sequence


AMERICAS = {'05_north_america','06_central_america','07_south_america'}
# The native map file puts Hawaii with the USA; physical geography does not.
GEOGRAPHIC_REGION_OVERRIDES={'STATE_HAWAIIAN_ISLANDS':'13_australasia'}


def macro_region(region):
    if region in AMERICAS:return 'americas'
    if region in {'00_west_europe','01_south_europe','02_east_europe','15_russia'}:return 'europe'
    if region in {'03_north_africa','04_subsaharan_africa'}:return 'africa'
    if region=='13_australasia':return 'oceania'
    return 'asia' if region else None
KNOWN_ORIGIN_GROUPS = {
    'heritage_group_african','heritage_group_central_asian','heritage_group_east_asian',
    'heritage_group_european','heritage_group_indigenous_oceanic','heritage_group_middle_eastern',
    'heritage_group_north_asian','heritage_group_south_asian','heritage_group_southeast_asian',
}


def load_native(game, mod=None):
    manifest={}
    def parse(path):
        manifest[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return root(path.read_text(encoding='utf-8-sig'))
    effects={}
    for p in sorted((game/'common/scripted_effects').glob('*political_setup*.txt')):
        effects.update(fields(parse(p)))
    cultures={};heritages={};states={};countries={};definitions={}
    for p in sorted((game/'common/cultures').glob('*.txt')):
        cultures.update({k:fields(v).get('heritage') for k,v in parse(p).entries() if k and isinstance(v,Object)})
    if mod:
        for p in sorted((mod/'common/cultures').glob('*.txt')):
            cultures.update({k:fields(v).get('heritage') for k,v in parse(p).entries() if k and isinstance(v,Object)})
    for p in sorted((game/'common/discrimination_traits').glob('*cultural_heritages*.txt')):
        heritages.update({k:fields(v).get('trait_group') for k,v in parse(p).entries() if k and isinstance(v,Object)})
    for p in sorted((game/'map_data/state_regions').glob('*.txt')):
        for key,obj in parse(p).entries():
            if not isinstance(obj,Object) or not key or p.stem=='99_seas':continue
            f=fields(obj)
            states[key]={'region':GEOGRAPHIC_REGION_OVERRIDES.get(key,p.stem),
                         'port':f.get('port'),'coastal':'naval_exit_id' in f,'file':str(p)}
    for p in sorted((game/'common/country_definitions').glob('*.txt')):
        for key,obj in parse(p).entries():
            if key and isinstance(obj,Object):
                f=fields(obj);definitions[key]={'cultures':sequence(f.get('cultures')),'capital':f.get('capital')}
    for p in sorted((game/'common/history/countries').glob('*.txt')):
        for _,container in parse(p).entries():
            if not isinstance(container,Object):continue
            for key,obj in container.entries():
                if not key or not key.startswith('c:') or not isinstance(obj,Object):continue
                laws=[];skipped=[]
                def expand(block, stack=()):
                    for k,v in block.entries():
                        if k=='activate_law' and isinstance(v,str):laws.append(v.removeprefix('law_type:'))
                        elif k and k.startswith('effect_starting_politics_') and v=='yes':
                            if k not in effects or k in stack:raise ValueError('Unknown/recursive native political effect '+k)
                            expand(effects[k],stack+(k,))
                        elif k in ('if','else','else_if'):skipped.append(k)
                expand(obj)
                d=definitions.get(key[2:],{});region=states.get(d.get('capital'),{}).get('region')
                countries[key[2:]]={'law_sequence':laws,'file':str(p),'skipped_conditional_blocks':len(skipped),
                                     'region':region,'heritages':[cultures.get(c) for c in d.get('cultures',[])]}
    return {'countries':countries,'cultures':cultures,'heritages':heritages,'states':states,'files_sha256':manifest}


def classify_migration(capital_region, independent, primary_heritages, heritage_groups, country_type):
    in_americas=capital_region in AMERICAS
    # Require EVERY reviewed primary culture to have a known immigrant origin.
    # A tolerated/accepted immigrant minority never suffices for this exception.
    immigrant=bool(primary_heritages) and all(h and heritage_groups.get(h) in KNOWN_ORIGIN_GROUPS for h in primary_heritages)
    return dict(capital_in_americas=in_americas,independent=independent,
                immigrant_primary_cultures=immigrant,primary_heritages=primary_heritages,
                eligible=in_americas and independent and immigrant and country_type not in ('decentralized','colonial','company'))


def prepare_contexts(mapping, politics, features, audit, metrics, observations, native, owners):
    if any(x['source_sha256']!=mapping['source_sha256'] for x in (politics,features,observations)):
        raise ValueError('Historical context source mismatch')
    audited={str(c['id']):c for c in audit['countries']}
    all_subjects={s['subject'] for s in politics['subjects']}
    types={s['subject']:s['type'] for s in politics['subjects']}
    capitals={k:v['capital'] for k,v in mapping['countries'].items()}
    # Geometry comes from this immutable M3 run, not vanilla country borders.
    regions={k:set() for k in capitals};coast={k:False for k in capitals}
    for state,provinces in owners.items():
        info=native['states'].get(state,{})
        for tag in set(provinces.values()):
            if tag in regions:
                if info.get('region'):regions[tag].add(info['region'])
                coast[tag] |= bool(info.get('port') and provinces.get(info['port'])==tag)
    percap={}
    for tag,t in mapping['countries'].items():
        cid=t['source_id'];pop=metrics.get(cid,{}).get('population',0)
        value=observations['countries'].get(cid,{}).get('last_months_tax_income')
        if pop>0 and value is not None:percap[tag]=max(0,float(value))*10000/pop
    result={}
    for tag,t in mapping['countries'].items():
        cid=t['source_id']
        if not cid:continue
        c=politics['countries'][cid];f=features['countries'][cid];a=audited[cid]
        pop=float(a['population_persons']);classes={k:float(v) for k,v in a['classes'].items()}
        shares={k:v/pop for k,v in classes.items()} if pop else {}
        capital_region=native['states'].get(t['capital'],{}).get('region')
        primary=t.get('cultures') or [t.get('culture')]
        heritage=[native['cultures'].get(culture) for culture in primary]
        migration=classify_migration(capital_region,cid not in all_subjects,heritage,native['heritages'],t['country_type'])
        peers=[v for p,v in percap.items() if native['states'].get(capitals[p],{}).get('region')==capital_region]
        rank=sum(v<=percap[tag] for v in peers)/len(peers) if tag in percap and peers else None
        institutions=set(f.get('institutions',[]));reforms=set(c.get('reforms',[]));lit=metrics.get(cid,{}).get('literacy_percent')
        # No GDP conversion: tax receipts depend on tax rates/control, and laborers
        # include agricultural work. Require independent corroborating indicators.
        commercial=(shares.get('burghers',0)>=0.04 or bool(reforms & {'merchant_republic','bank_ledgers_system','capitalistic_cities','trade_office_network'}))
        financial={'banking','global_trade'} <= institutions
        fiscal=rank is not None and rank>=0.5 and percap.get(tag,0)>0
        knowledge=lit is not None and lit>=40 and 'manufactories' in institutions
        market_admin=commercial and financial and fiscal and knowledge
        settled=c.get('government') not in ('tribe','steppe_horde') and t['country_type']!='decentralized'
        facts=set()
        if migration['eligible']:facts.add('american_independent_immigrant')
        if migration['capital_in_americas'] and migration['immigrant_primary_cultures']:facts.add('american_immigrant_society')
        if cid not in all_subjects:facts.add('independent')
        if settled:facts.add('settled_state')
        if commercial:facts.add('commercial_society')
        if market_admin:facts.add('developed_market_administration')
        if settled and not market_admin and (shares.get('peasants',0)>=0.25 or
                (migration['capital_in_americas'] and migration['immigrant_primary_cultures'])):facts.add('agrarian_settled_state')
        if types.get(cid)=='trade_company':facts.add('trade_company')
        if coast[tag]:facts.add('owns_port_province')
        policies={dict(body).get('object') for _,body in c.get('laws',[])}
        orientation=bool(policies & {'merchant_navy','protect_trade_routes'})
        if len({macro_region(r) for r in regions[tag]})>=2 and coast[tag] and commercial and financial and orientation:
            facts.add('maritime_trade_network')
        if 'medical_school_advance' in f.get('advances',[]) and market_admin:facts.add('medical_admin_capacity')
        if 'public_welfare_act' in reforms:facts.add('public_relief_reform')
        result[tag]={'facts':sorted(facts),'migration':migration,'capital_region':capital_region,
            'owned_regions':sorted(regions[tag]),'source_culture':c.get('culture'),
            'primary_cultures':primary,'primary_heritages':heritage,'source_subject_type':types.get(cid),
            'source_class_shares':shares,'source_tax_per_10000_people':percap.get(tag),
            'same_region_tax_capacity_percentile':rank,'literacy_percent':lit,
            'economy_interpretation':'Tax capacity and burgher/reform/knowledge proxies, NOT GDP or industrial worker share',
            'coast_interpretation':'Port province ownership checked against mapped province_owners; Hawaii assigned to Oceania'}
    return result


# A prior is admitted only if a named, installed reference actually has this final
# law. Source laws/reforms retain priorities >=55; all analogies rank <=50.
PROFILES=[
 ('market_administration','economic_system','interventionism',50,['developed_market_administration','settled_state'],[],['GBR','NET','BEL','FRA'],
  '商业与金融组织、识字/工场知识及相对税收能力共同支持近代市场行政；参考原版干预主义'),
 ('settled_agrarian','economic_system','agrarianism',40,['agrarian_settled_state'],[],['MEX','BRZ'],
  '定居农业/美洲移民农业社会，尚缺成熟市场行政；参考原版墨西哥、巴西农本主义'),
 ('imperial_trade_network','colonization','colonial_exploitation',45,['maritime_trade_network','developed_market_administration','independent'],['american_immigrant_society'],['NET'],
  '实际跨区域商业网络与行政能力，采用原版荷兰式海外商业殖民取向；不保证立即有可殖民目标'),
 ('american_frontier','colonization','frontier_colonization',50,['american_independent_immigrant'],[],['USA','MEX'],
  '美洲独立移民社会参考原版美国/墨西哥的边疆殖民取向；实际邻接与扩张资格另检'),
 ('fiscal_administration','taxation','per_capita_based_taxation',40,['developed_market_administration','settled_state'],[],['GBR','NET','FRA'],
  '成熟市场行政与税收能力支持较普遍税基，参考原版近代财政制度；不等同所得税'),
 ('agrarian_tax','taxation','land_based_taxation',30,['agrarian_settled_state'],[],['MEX','CHI'],
  '农业社会以土地税基为历史补全'),
 ('merchant_protection','trade_policy','protectionism',35,['developed_market_administration','independent'],[],['GBR','USA'],
  '无明确源贸易政策时，成熟商业国家参考原版保护本国市场取向'),
 ('frontier_land','land_reform','homesteading',35,['american_independent_immigrant','agrarian_settled_state'],[],['USA'],
  '缺直接土地法时采用美洲移民国家的授地取向；不覆盖已实行的农奴/自由农民特权'),
 ('professional_trade_navy','navy_model','professional_navy',35,['maritime_trade_network','developed_market_administration'],[],['GBR'],
  '跨区域贸易与财政组织支持常设海军，参考原版英国；不覆盖源海军学说'),
 ('mercantile_unions','labour_associations','anti_strike_laws',30,['developed_market_administration','settled_state'],[],['GBR','USA'],
  '缺结社政策时，近代商业社会参考原版有限结社、限制罢工取向；不生成现代工人保护'),
 ('medical_charity','health_system','charitable_health_system',25,['medical_admin_capacity','settled_state'],[],['GBR'],
  '医疗知识与行政财政能力支持历史性慈善医疗近似；是低置信补全，不是源已证实服务网络'),
]


def historical_candidates(context,native,lawdefs):
    facts=set(context['facts']);out=[]
    for key,group,law,rank,required,forbidden,references,reason in PROFILES:
        if not set(required)<=facts or set(forbidden)&facts:continue
        valid=[]
        for tag in references:
            row=native['countries'].get(tag)
            if not row:continue
            # Apply startup overrides in order, not membership in an unordered list.
            final={}
            for l in row['law_sequence']:
                if l in lawdefs:final[lawdefs[l]['group']]=l
            if final.get('lawgroup_'+group)=='law_'+law:
                valid.append({'tag':tag,'file':row['file'],'law':'law_'+law,
                              'same_heritage':bool(set(row['heritages']) & set(context['primary_heritages'])),
                              'same_region':row['region']==context['capital_region']})
        if not valid:continue
        valid.sort(key=lambda r:(-r['same_heritage'],-r['same_region'],r['tag']))
        out.append(dict(id='historical.'+key,group='lawgroup_'+group,law='law_'+law,priority=rank,
                        reason=reason,evidence=['context:'+f for f in required],
                        confidence='historical_inference',references=valid))
    # Cultural/regional common practice is weaker than economic-role analogies.
    # Never copy constitutions, slavery, citizenship or immigration by ancestry.
    allowed={
        'lawgroup_economic_system':{'law_traditionalism'},
        'lawgroup_taxation':{'law_land_based_taxation'},
        'lawgroup_labour_associations':{'law_guild_system','law_combination_acts','law_anti_strike_laws','law_right_to_associate'},
        'lawgroup_health_system':{'law_no_health_system'},
        'lawgroup_welfare':{'law_no_social_security'},
    }
    if 'developed_market_administration' in facts:
        allowed['lawgroup_economic_system'].add('law_interventionism')
        allowed['lawgroup_taxation'].add('law_per_capita_based_taxation')
        allowed['lawgroup_welfare'].add('law_poor_laws')
    if 'agrarian_settled_state' in facts:allowed['lawgroup_economic_system'].add('law_agrarianism')
    if 'medical_admin_capacity' in facts:allowed['lawgroup_health_system'].add('law_charitable_health_system')
    cohort=[]
    for tag,row in native['countries'].items():
        if row['region']!=context['capital_region'] or not (set(row['heritages']) & (set(context['primary_heritages'])-{None})):continue
        final={}
        for law in row['law_sequence']:
            if law in lawdefs:final[lawdefs[law]['group']]=law
        cohort.append((tag,row,final))
    for group, permitted in allowed.items():
        votes=Counter(final[group] for _,_,final in cohort if group in final)
        if not votes:continue
        law,count=sorted(votes.items(),key=lambda x:(-x[1],x[0]))[0]
        if law not in permitted or count<2 or count/len(cohort)<2/3:continue
        refs=[{'tag':tag,'file':row['file'],'law':law} for tag,row,final in cohort if final.get(group)==law]
        out.append(dict(id='historical.cultural_regional.'+group,group=group,law=law,priority=20,
                        reason='同文化传承、同地区原版参照至少两国且占全部同类参照 2/3；通过本战役经济条件筛选的弱补全',
                        evidence=['heritage:'+h for h in context['primary_heritages'] if h]+['region:'+context['capital_region']],
                        confidence='historical_inference',references=refs))
    return out
