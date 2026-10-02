"""Contextual fallback banners using native heraldic layers, never fake originals.

EU5-specific motif names are reused as artwork, not as evidence of a historical
national flag. Selection uses reusable cultural and source-economy evidence only.
"""
import hashlib
from collections import Counter,defaultdict

IVORY=(244,239,218); GOLD=(219,175,64); BLUE=(24,65,112)
RED=(151,35,43); GREEN=(29,98,70); PURPLE=(85,48,99)

def eu5(name): return 'eu5_m3_'+name+'.dds'

def layer(emblem,color,pos=(.5,.5),scale=(.5,.6),background=False):
    return dict(emblem=emblem,color=color,position=pos,scale=scale,background=background)


def economic_features(countries,source_economy,coastal_states):
    """Aggregate source RGO employment, not V3 balancing output or real history.

    Input paths and country IDs belong to the caller. No campaign identity is
    encoded in the rules. Missing source evidence cannot imply a staple crop.
    """
    goods=defaultdict(Counter);counts=Counter()
    for loc in source_economy.get('locations',{}).values():
        owner=str(loc.get('owner'));counts[owner]+=1
        if loc.get('raw_material'):
            goods[owner][loc['raw_material']]+=max(0,float(loc.get('rgo_workers',0)))
    result={}
    for tag,c in countries.items():
        sid=str(c.get('source_id')); ranked=goods[sid].most_common();total=sum(goods[sid].values())
        staple,amount=ranked[0] if ranked else (None,0)
        result[tag]={'source_location_count':counts[sid],
            'small_coastal_country':counts[sid]>0 and counts[sid]<=3 and c.get('capital') in coastal_states,
            'capital_state_coastal':c.get('capital') in coastal_states,
            'dominant_resource':staple if total>0 and amount/total>=.45 else None,
            'resource_share':amount/total if total else None,
            'resource_basis':'source_rgo_workers' if total else 'unavailable'}
    return result

def contextual_design(identity,color,country,src,colonial,region,company=False):
    seed=hashlib.sha256(identity.encode()).digest()
    culture=country.get('source_culture',''); features=country.get('flag_features',{})
    # A consistent tint within each family; do not rotate the palette by identity.
    rgb=[float(v) for v in color] if len(color)==3 else list(BLUE)
    base=min((BLUE,RED,GREEN,PURPLE),key=lambda p:sum((a/max(sum(p),1)-b/max(sum(rgb),1))**2 for a,b in zip(p,rgb)))
    layers=[];field=base;metal=IVORY
    badge=eu5('ce_lymphad');basis='地域与政治文化生成设计；非原作旗帜复原'
    if colonial:
        # Ensigns, armorial flags and maritime flags are distinct families.
        # A single territorial device replaces the universal laurel/shield kit.
        style=seed[1]%3
        if culture in ('english','scottish'): style=0
        if culture=='french':style=1
        field=base if style==0 else IVORY
        ink=IVORY if style==0 else base
        if style==1:
            layers.append(layer(eu5('ce_solid'),base,(.5,.89),(1,.22),True))
            layers.append(layer(eu5('ce_solid'),GOLD,(.5,.765),(1,.018),True))
        elif style==2:
            layers.append(layer(eu5('ce_solid'),base,(.5,.91),(1,.18),True))
            layers.append(layer(eu5('ce_solid'),RED,(.5,.80),(1,.035),True))
        motifs={
            '05_north_america':('ce_tree_pine','ce_bear_passant'),
            '06_central_america':('ce_palm_tree_simple','ce_fish_naiant'),
            '07_south_america':('ce_mountain','ce_fish_naiant'),
            '03_north_africa':('ce_palm_tree_simple','ce_lymphad_beacon_random'),
            '04_subsaharan_africa':('ce_lion_passant','ce_palm_tree_simple'),
            '10_india':('ce_lotus_simple','ce_palm_tree_simple'),
            '11_east_asia':('ce_chinese_azure_dragon','ce_lymphad'),
            '12_indonesia':('ce_palm_tree_simple','ce_lymphad'),
            '13_australasia':('ce_lymphad','ce_fish_naiant')}
        choices=('ce_lymphad_beacon_random','ce_wheel_ship') if company else motifs.get(region,('ce_lymphad','ce_palm_tree_simple'))
        badge=eu5(choices[seed[2]%len(choices)])
        pos=(.67+.02*(seed[5]%5),.53);size=(.34+.01*(seed[6]%4),.46+.01*(seed[6]%4))
        if style==0:
            layers.append(layer('ce_circle.dds',IVORY,pos,(.43,.64)))
            ink=base;size=(.31,.40)
        elif style==1 and seed[3]%2:
            layers.append(layer('ce_shield_heater.dds',base,pos,(.36,.52)))
            layers.append(layer('ce_shield_heater.dds',GOLD,pos,(.32,.47)))
            ink=base;size=(.23,.32)
        charge=layer(badge,ink,pos,size)
        charge['color2']=GOLD if style==1 and seed[3]%2 else (IVORY if style in (0,2) else field)
        if any(x in badge for x in ('palm_tree','tree_pine')):charge['color2']=ink
        charge['color3']=ink
        layers.append(charge)
        if style!=0 and ('island' in country.get('capital','').lower() or 'indonesia' in region or company):
            layers.append(layer('ce_waves.dds',base,(.72,.715),(.40,.10)))
        basis='宗主色系与地区徽记：海旗 / 地方盾旗 / 商贸旗；保留动态宗主旗角标'
    else:
        # Cultural artwork already present in EU5 is richer than one generic
        # cross/crescent/sun for all countries sharing a religion.
        motifs={
            'kanienkehaka_culture':'ce_wampum_mohawk','onyotaaka_culture':'ce_wampum_oneida',
            'onondowaga_culture':'ce_wampum_seneca_antlers','tujia_culture':'ce_tujia_white_tiger',
            'hmong_culture':'ce_hmong_four_snails_cross','kam_culture':'ce_animist_drum_zhuang',
            'khanty_culture':'ce_khanty_double_headed_bird','mossi':'ce_african_mossi_pattern',
            'akan':'ce_african_ashanti_motif','mongolian_culture':'ce_mongol_cross_ornament',
            'saigoku_culture':'ce_mon_mitsu_kasamatsu','cahokia_culture':'ce_hopewell_bear_claw',
            'chincha_culture':'ce_andean_small_fish_double','aimara_culture':'ce_andean_cross_huari',
            'palta_culture':'ce_andean_chimu_bird','formosan_culture':'ce_asian_animist_sun',
            'jianghuai_culture':'ce_chinese_azure_dragon','utsang_culture':'ce_tibet_sky_mountains'}
        motif=motifs.get(culture)
        if 'wampum' in (motif or ''): field=PURPLE;metal=IVORY
        elif culture in ('saigoku_culture','tujia_culture'): field=RED;metal=IVORY
        elif not motif:
            if any(x in culture for x in ('nogai','kyrgyz','teleut','oirat','chelkans','qaliq','khorezm','turkoman')):
                motif=('ce_horse_courant','ce_bow_arrow')[seed[2]%2]
            elif any(x in culture for x in ('karel','muscov','swedish','mishar','bolghar')):
                motif=('ce_bear_passant','ce_tree_pine')[seed[2]%2]
            elif country.get('religion') in ('hindu','theravada'):
                motif=('ce_lotus_simple','ce_golden_fish_pair')[seed[2]%2]
            elif any(x in culture for x in ('kurd','farsi','khorasani')):
                motif=('ce_lion_passant','ce_horse_courant')[seed[2]%2]
            elif region in ('06_central_america','07_south_america'):
                motif=('ce_andean_small_bird','ce_fish_naiant')[seed[2]%2]
            elif region in ('04_subsaharan_africa','03_north_africa'):
                motif=('ce_african_crossed_spears_shield','ce_palm_tree_simple')[seed[2]%2]
            elif culture=='greek_culture':motif='ce_eagle_doubleheaded_wide'
            elif culture=='french':motif='ce_fleur_de_lis'
            else:motif=('ce_tree_pine','ce_wheat_garb')[seed[2]%2]
        # Evidence-backed maritime/trade identity can supersede a generic
        # regional fallback, but not an explicit cultural artwork mapping.
        if culture not in motifs and features.get('small_coastal_country'):
            motif='ce_lymphad'
            layers.append(layer('ce_waves.dds',metal,(.5,.82),(.75,.12)))
        resource_motifs={'fish':'ce_fish_naiant','lumber':'ce_tree_pine',
                         'wild_game':'ce_bear_passant','fur':'ce_bear_passant',
                         'horses':'ce_horse_courant'}
        staple=features.get('dominant_resource')
        if culture not in motifs and not features.get('small_coastal_country') and staple in resource_motifs:
            motif=resource_motifs[staple]
        # Republics can use a geometric civic field. Monarchy alone does not
        # manufacture a dynasty, crown, or historical coat of arms.
        civic=src.get('government')=='republic' and culture not in motifs
        if civic:
            layers.append(layer(eu5('ce_solid'),metal,(.10,.5),(.20,1),True))
        # Armorial banner or a bordered standard. No added European shields on
        # wampum/Asian textile motifs; no religion-based charge multiplicities.
        if seed[0]%3==0 and 'wampum' not in motif:
            layers.append(layer(eu5('ce_solid'),metal,(.5,.06),(1,.12),True))
            layers.append(layer(eu5('ce_solid'),metal,(.5,.94),(1,.12),True))
        badge=eu5(motif)
        pos=(.57,.46) if civic else (.5,.5);scale=(.48,.56) if civic else (.56,.66)
        if 'wampum' in motif:scale=(.80,.60)
        charge=layer(badge,metal,pos,scale)
        charge['color2']=field;charge['color3']=metal
        if 'wampum' in motif or motif=='ce_african_mossi_pattern':
            charge['color']=field;charge['color2']=metal
        layers.append(charge)
        # Small border differences allow sibling standards without fabricating
        # different cultures or confessions. Identity seed never selects culture.
        if seed[4]%2:
            layers.append(layer(eu5('ce_solid'),metal,(.03,.5),(.06,1),True))
        basis='EU5 文化/地域图案素材：'+motif+'；纹章旗式为生成设计，非原作完整旗帜'
        if features.get('small_coastal_country'):basis+='；源国家≤3地点且目标首都州沿海：海洋旗式'
        if staple:basis+='；源采集业就业主导物产：'+staple
    return dict(pattern='pattern_solid.tga',field=field,metal=metal,emblem=None,
                positions=[],position=(.5,.5),scale=(.5,.5),layers=layers,
                colonial=colonial,region=region,company=company,basis=basis,features=features,
                government=src.get('government'),culture=culture)

def compile_design(d):
    rgb=lambda c:'rgb { '+' '.join(map(str,c))+' }'
    vec=lambda c:'{ '+' '.join(f'{x:.4f}' for x in c)+' }'
    text=f'pattern = "{d["pattern"]}"\ncolor1 = {rgb(d["field"])}\ncolor2 = {rgb(d["metal"])}\n'
    for l in d['layers']:
        text+=('colored_emblem = {\n'+f'texture = "{l["emblem"]}"\ncolor1 = {rgb(l["color"])}\ncolor2 = {rgb(l.get("color2",l["color"]))}\ncolor3 = {rgb(l.get("color3",l["color"]))}\n'
               +f'instance = {{ position = {vec(l["position"])} scale = {vec(l["scale"])} }}\n}}\n')
    return text
