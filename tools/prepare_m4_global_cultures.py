"""Freeze global V3-scale categories; no automatic per-source asset expansion.

The existing source-group taxonomy supplies bounded umbrella categories where
vanilla has no suitable broad category. These are gameplay aggregates, not a
claim that their members share one ethnicity, language or appearance.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from build_m3_world import load_localization
from m3_world import load_json, digest
from m4_religions import definitions

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'.local/m4/runs/20261001-065707-148fbda9/demographics_profile.snapshot.json'
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')

def prepare(apply=False):
    profile=load_json(BASE)
    live=load_json(ROOT/'config/personal/m4_demographics.json')
    if set(live['custom_resident_cultures'])!=set(profile['custom_resident_cultures']):
        raise ValueError('Source culture pool changed; revise global policy instead of overwriting it')
    for key,value in live.items():
        if key not in ('custom_resident_cultures','culture_compaction','culture_budget','global_culture_policy','migrant_cultures'):profile[key]=value
    profile['migrant_cultures']={k:v for k,v in live['migrant_cultures'].items() if k!='macro_regions'}
    pool=profile['custom_resident_cultures']; plans=profile['culture_compaction']
    native=definitions(GAME/'common/cultures');traits=definitions(GAME/'common/discrimination_traits')
    summary=load_json(ROOT/'.local/m4/source-1780-population/source_summary.json')
    def add(names,target,reason):
        for c in names.split() if isinstance(names,str) else names:
            if c not in pool:raise ValueError('Unknown source: '+c)
            if c in plans:raise ValueError('Duplicate policy: '+c)
            d=pool[c]
            plans[c]={'target':target,'source_language':d['source_language'],'source_groups':d['source_groups'],
                      'target_language':native[target]['language'],'target_heritage':native[target]['heritage'],
                      'rule':'global_v3_category','basis':'User-authorized global gameplay granularity; original identities remain in source ledger.',
                      'reason':reason+' This is a gameplay category, not ethnic equivalence; population and resident religion stay unchanged.',
                      'previous_target':'eu5_resident_'+c}
    def group(group,target,reason=None):
        add([c for c,d in pool.items() if c not in plans and group in d['source_groups']],target,
            reason or 'Use the installed broad '+target+' category for the explicitly frozen '+group+' subdivisions.')
    # Native broad umbrellas, rather than a nearby majority ethnic identity.
    for g,t in {
        'mordvinic_group':'mordvin','mapudungun_group':'patagonian','tshon_group':'patagonian',
        'kawesqar_group':'patagonian','yaghan_group':'patagonian','chono_group':'patagonian',
        'charrua_group':'patagonian','henia_kamiare_group':'patagonian','warpe_group':'patagonian',
        'australian_group':'aborigine','papuan_group':'melanesian',
        'maya_group':'mayan','cherokee_group':'cherokee','haudenosaunee_group':'iroquoian',
        'skarureh_group':'iroquoian','lenape_group':'algonquian','siksika_group':'algonquian',
        'hinonoeitiit_group':'algonquian','tsehesenestsestotse_group':'algonquian',
        'nuuchi_nuwu_group':'paiute','shoshoni_group':'paiute','paiute_group':'paiute',
        'puebloan_group':'pueblo','tutelo_group':'siouan','yupik_group':'inuit',
        'caribe_group':'cariban','tupi_group':'tupinamba',
        'macro_je_group':'amazonian','mura_group':'amazonian','ta_arawakan_group':'amazonian',
        'tucanoan_group':'amazonian','guahibo_group':'amazonian','bora_huitoto_group':'amazonian',
        'movima_group':'amazonian','pano_group':'amazonian','txapakura_group':'amazonian',
        'sihni_group':'amazonian','moseten_group':'amazonian','aingae_group':'amazonian',
        'manoki_group':'amazonian','kwaza_group':'amazonian','tarairiu_group':'amazonian',
        'chicham_group':'amazonian','kru_group':'kru','nilotic_group':'nilotic',
        'tungusic_group':'siberian','polish_group':'polish','romanian_group':'romanian',
        'tibetan_group':'tibetan','luba_group':'luba',
    }.items():
        # Jurchen identities have a native Manchu category; preserve Sibe there.
        if g=='tungusic_group':
            add('sibe_culture haixi_culture hurga_culture','manchu','Use the native Manchu category for the named Jurchen subdivisions.')
        group(g,t)
    explicit={
        'tarascan':'purepecha_culture','burmese':'rakhine_culture kado_culture',
        'kanuri':'kanembu_culture','lacustrine_bantu':'rutara_culture haya_culture shi_culture lega bembe luhya_culture',
        'sumatran':'acehnese_culture minangkabau_culture lampung_culture rejang_culture nias_culture mentawai_culture orang_rimba_culture enggano_culture gayo_culture',
        'dayak':'iban_culture kayan_culture ngaju_culture kenyah_culture bidayuh_culture punan_culture',
        'bornean':'melanau_culture dusun_culture kutai_culture','malay':'banjar_culture bacan_culture orang_laut_culture',
        'moluccan':'tobelo_culture tanimbar_culture maaya_culture aru_culture galela_culture wetarese_culture',
        'javan':'madurese_culture','balinese':'sasak_culture',
        'visayan':'butuanon_culture cebuano_culture waray_culture cuyonon_culture',
        'tagalog':'kapampangan_culture','ilocano':'pangasinan_culture ibanag_culture',
        'moro':'maguindanao_culture tausug_culture iranun_culture',
        'lumad':'subanon_culture tagakaulo_culture giangan_culture',
        'melanesian':'itaukei_culture ghari_culture ndrumbea_culture saa_culture nakanamanga_culture arosi_culture drehu_culture tolomako_culture kwaraae_culture kwaio_culture lenakel_culture cheke_holo_culture marovo_culture roviana_culture numee_culture nduke_culture malakula_culture ambrym_culture sakao_culture vaghua_culture ambae_culture gela_culture apma_culture vangunu_culture ughele_culture maewo_culture valpei_culture paici_culture natugu_culture mwotlap_culture',
        'micronesian':'kajoor_ri_majel_culture refaluwasch_culture kosrae_culture belauan_culture',
        'polynesian':'mu_ngava_culture futuna_culture',
        'assamese':'kamarupi','marathi':'konkani khandeshi','rajput':'harauti mewari mewati bagri',
        'pahari':'kumaoni','panjabi':'kohistani','nepali':'khas_culture',
        'pashtun':'afghan_culture','mazanderani':'gilak_culture','persian':'semnani_culture dehwar_culture',
        'azerbaijani':'azeri_culture','kurdish':'zaza_culture','yakut':'sakha_culture','tuvan':'soyot_culture',
        'bedouin':'omani_culture kaliji_culture','yemenite':'hadhrami_culture',
        'assyrian':'syriac_culture','mashriqi':'alawite_culture','maghrebi':'andalusi',
        'north_german':'german_baltic german_transylvanian german_carpathian',
        'north_italian':'ladin dalmatian','alemannic':'romansh','south_italian':'sardinian',
        'lithuanian':'samogitian curonian pruthenian','greek':'cappadocian_greek_culture','bosniak':'bosnian',
        'ukrainian':'cossack_culture rusyn_culture','finnish':'tavastian','ugrian':'mansi_culture merya_culture bjarmian',
        'udmurt':'besermyan','scottish_gaelic':'norse_gael','scottish':'norn_culture','irish':'anglo_irish',
        'georgian':'laz_culture svan_culture mingrelian_culture','circassian':'abkhazian_culture abazin_culture',
        'chechen':'nakh_culture','north_caucasian':'lezgin_culture avar_culture dargin_culture lak_culture karachay_culture kumyk_culture balkar_culture alan_culture',
        'tigray':'tigrinya tigre','amhara':'gurage','khoisan':'kung_culture amkoe_culture xegwi_culture hai_om_culture',
        'sotho':'lozi_culture','shona':'kalanga_culture','ovimbundu':'ambundu haneka_humbe',
        'lunda':'mbunda luvale luchazi_culture','bakongo':'yaka suku',
        'fluvian_bantu':'bangi komo kusu_culture bashilele dinga teke wumbu mbuun kolo_culture kuyu',
        'equatorial_bantu':'mbaka bakele basingui bulu_culture bubi_culture','fang':'fang_gabun',
        'kavango_bantu':'owambo_culture xindonga','chewa':'tumbuka_culture nsenga',
        'sukuma':'rukwa_culture bena_culture','swahili':'mbugu_culture ruvu_culture seuta_culture matuumbi_culture',
        'teda':'toubou_culture','tuareg':'messufa_culture lamtuna_culture','berber':'guanche',
        'mossi':'gurma gurunsi mamprusi',
        'sara':'mbay_culture gula_iro_culture','nuba':'nyimang_culture katla_culture',
        'zhuang':'bo_culture mulam_culture maonan_culture','thai':'khon_muang_culture','shan':'dai_culture',
        'kachin':'jingpo_culture ngacang_culture','manipuri':'meitei_culture','lushai':'zo_culture',
        'yi':'lisu_culture mi_niah_culture hani_culture lahu_culture jino_culture',
        'khmer':'kuy_culture','khmu':'bru_culture','vietnamese':'muong_culture',
        'siberian':'yandyr_culture selkup_culture nenets_culture chukchi_culture nimchan_culture khoromboy_culture kolyms_culture omok_culture vadul_culture yandin_culture itelmen_culture onoid_culture chuvan_culture sakkyryr_culture alyutor_culture koryak_culture olyuben_culture shoromba_culture kerek_culture anauls_culture evesel_culture',
        'inuit':'yupighyt_culture','aimara':'chango_culture','patagonian':'cunco_culture',
        'nez_perce':'nimiipuu_culture','pueblo':'ancestral_pueblo_culture','nahua':'toltec_culture',
        'oodham':'pima_culture',
    }
    for target,names in explicit.items():add(names,target,'Adopt the named regional/subdivision correspondence at installed V3 granularity; membership is explicit and immutable in the run snapshot.')
    # Keep distinctive identities without a suitable vanilla umbrella. Everything
    # else is coalesced by an explicit source cultural group, never by its ruler.
    protected=set('nubian coptic_culture hui_muslim_culture daur_culture hlai_culture yao_china_culture beyte_yisrael cornish domari_culture andamanese_culture bemba tsonga_culture kuba twa_culture'.split())
    grouped=defaultdict(list)
    for c,d in pool.items():
        if c in plans:continue
        # Broad continental groups are not sufficient to merge distinct peoples.
        specific=[g for g in d['source_groups'] if g not in ('indian_group','confucian_group','andean_group','bantu_group','austronesian_group','west_african_group','central_african_group','arabic_group','slavic_group','carpathian_group','steppe_group')]
        key=tuple(specific) if specific and c not in protected else ('identity',c)
        grouped[key].append(c)
    # Explicit functional umbrellas for remaining minor regional subdivisions.
    # These names disclose heterogeneity instead of borrowing a majority identity.
    umbrellas={
        'sulawesi':('Sulawesi peoples','苏拉威西诸族','buginese_culture torajan_culture makassarese_culture tolaki_culture gorontalo_culture minahasan_culture kaili_culture mandarese_culture mori_culture mongondow_culture moronene_culture pamona_culture bungku_culture tomini_culture talaud_culture sangirese_culture'),
        'nusa_tenggara':('Lesser Sunda peoples','小巽他诸族','atoni_culture sumba_culture dompu_culture bima_culture mambai_culture'),
        'philippine_uplands':('Philippine upland peoples','菲律宾山地诸族','tagbanwa_culture bontoc_culture kalinga_culture mangyan_culture kankanaey_culture aeta_culture isnag_culture'),
        'central_sudanic':('Central Sudanic peoples','中苏丹诸族','madi_culture lugbara_culture moru_culture'),
        'ubangian':('Ubangian peoples','乌班吉诸族','gbaya_culture ngbandi_culture banda_culture mandja_culture'),
        'andean':('Other Andean peoples','安第斯其他诸族','chimu_culture tallan_culture kanari_culture puruha_culture pazioca_culture tastil_culture guancavilca_culture chicha_culture omaguaca_culture licanantay_culture cara_culture casma_culture pashash_culture charka_culture yampara_culture chiribaya_culture guayacundo_culture uru_culture cholon_culture bagua_culture chillque_culture collique_culture canta_culture'),
    }
    labels={lang:load_localization(EU5/'main_menu/localization'/lang) for lang in ('english','simp_chinese')}
    overrides={}
    for key,(en,zh,members) in umbrellas.items():
        names=members.split()
        for c in names:
            if c in plans:raise ValueError('Umbrella overlap: '+c)
            for values in grouped.values():
                if c in values:values.remove(c)
        grouped[('umbrella',key)]=names;overrides[('umbrella',key)]={'english':en,'simp_chinese':zh}
    aggregates=[]
    for key,members in grouped.items():
        if not members:continue
        representative=max(members,key=lambda c:summary['culture_centipersons'].get(c,0));d=pool[representative]
        # Remove the per-source independent heritage-group explosion. Reuse the
        # native template's broad heritage family, disclosing this approximation.
        d['heritage_group']=traits[native[d['template']]['heritage']]['trait_group']
        d['reason']='User-authorized global gameplay category. Original source identity remains in the ledger; names, appearance and acceptance relationships are provisional. No automatic asset creation per source identity.'
        if len(members)>1:
            d['review_status']='generated_preservation_candidate_not_historically_reviewed'
            label=overrides.get(key) or {lang:labels[lang].get(key[0],key[0])+(' other peoples' if lang=='english' else '其他诸族') for lang in labels}
            d['aggregate_members']=sorted(members);d['display_labels']=label
            d['aggregate_language_labels']={lang:label[lang]+(' languages (gameplay aggregate)' if lang=='english' else '诸语言（游戏合并）') for lang in label}
            d['language_trait']=None
            # A mixed umbrella must not claim that all members speak its seed's
            # language. Its neutral aggregate language/group is explicitly scoped.
            d['aggregate_language']=True
            d['template_limitation']+=' This heterogeneous game category uses a neutral aggregate language, not the seed identity language. Names/appearance remain provisional.'
            for c in members:
                if c==representative:continue
                config=pool[c]
                plans[c]={'target':'eu5_resident_'+representative,'source_language':config['source_language'],'source_groups':config['source_groups'],
                    'target_language':'eu5_aggregate_language_'+representative,'target_heritage':'eu5_resident_heritage_'+representative,
                    'rule':'explicit_source_group_umbrella','basis':'User-authorized bounded heterogeneous game category; all source identities remain auditable.',
                    'reason':'Frozen umbrella '+label['english']+'; no claim of ethnic or linguistic equivalence. Population and religion unchanged.',
                    'previous_target':'eu5_resident_'+c}
        aggregates.append({'representative':representative,'members':sorted(members),'labels':d.get('display_labels')})
    macro={
        'north_america':('North America','北美',['region_canada','region_pacific_coast','region_great_plains','region_atlantic_coast']),
        'central_america':('Central America and Caribbean','中美与加勒比',['region_central_america']),
        'south_america':('South America','南美',['region_brazil','region_andes','region_la_plata','region_gran_colombia']),
        'sub_saharan_africa':('Sub-Saharan Africa','撒哈拉以南非洲',['region_west_africa','region_equatorial_africa','region_southern_africa','region_east_africa']),
        'asia':('Asia','亚洲',['region_indochina','region_indonesia','region_south_china','region_north_china','region_northeast_asia','region_siberia','region_south_india','region_north_india','region_himalayas']),
    }
    profile['migrant_cultures']['macro_regions']={k:{'labels':{'english':en,'simp_chinese':zh},'regions':rs} for k,(en,zh,rs) in macro.items()}
    profile['culture_budget']={'max_used_cultures':400,'max_resident_assets':100,'max_migrant_assets':16,'max_political_assets':40,
        'max_resident_heritage_groups':0,'max_resident_language_groups':100,'max_population_groups':15000,'max_effective_culture_definitions':480,
        'policy':'Hard limits; fail candidate validation instead of silently creating cultures, dropping population or forcing unrelated identities together.'}
    profile['global_culture_policy']={'schema':1,'baseline_profile':str(BASE),'baseline_sha256':digest(BASE),
        'status':'gameplay_granularity_pass_not_historical_asset_certification','aggregates':aggregates}
    result={'compacted_sources':len(plans),'resident_assets':len(aggregates),'aggregate_members':sum(len(a['members']) for a in aggregates),'by_native':dict(Counter(v['target'] for v in plans.values() if not v['target'].startswith('eu5_')))}
    if apply:(ROOT/'config/personal/m4_demographics.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'.local/m4/global-culture-plan.json').write_text(json.dumps({'summary':result,'aggregates':aggregates,'budget':profile['culture_budget']},ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args();print(json.dumps(prepare(a.apply)))
