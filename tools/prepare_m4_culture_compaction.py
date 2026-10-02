"""Freeze a bounded set of explicitly selected V3-scale population categories.

This is a game-granularity policy, not a claim of historical ethnic equivalence.
Only the provisional preservation pool is eligible; political identities and
the earlier reviewed mapping rules remain untouched.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from m3_world import load_json,digest
from m4_religions import definitions

ROOT=Path(__file__).resolve().parents[1]


def prepare(apply=False):
    path=ROOT/'config/personal/m4_demographics.json';profile=load_json(path)
    native=definitions(Path('D:/Steam/steamapps/common/Victoria 3/game/common/cultures'))
    pool={c:d for c,d in profile['custom_resident_cultures'].items() if d.get('review_status')=='generated_preservation_candidate_not_historically_reviewed'}
    plans={}
    def add(names,target,rule,reason):
        for source in names:
            if source not in pool:raise ValueError('Not a provisional identity: '+source)
            if source in plans:raise ValueError('Overlapping compaction: '+source)
            d=pool[source]
            plans[source]={'target':target,'source_language':d['source_language'],'source_groups':d['source_groups'],
                           'target_language':native[target]['language'],'target_heritage':native[target]['heritage'],
                           'rule':rule,'basis':'Explicit V3 game-granularity choice authorized by user; not historical ethnic equivalence.',
                           'reason':reason+' Source identity stays in the audit ledger; resident religion and population are unchanged.',
                           'previous_target':'eu5_resident_'+source}
    def select(languages,group,target,exclude=()):
        names=[c for c,d in pool.items() if d['source_language'] in languages and group in d['source_groups'] and c not in exclude]
        add(names,target,'v3_'+target+'_category','Use the installed V3 '+target+' population category for the explicitly enumerated source subdivisions in '+group+'. This is a bounded game abstraction, not a language-only rule.')
    select(['malagasy_language'],'malagasy_group','malagasy')
    select(['salishan_language'],'salishan_group','salish')
    select(['caddoan_language'],'caddoan_group','caddoan')
    select(['iroquoian_language'],'iroquoian_group','iroquoian')
    select(['wendat_language'],'wendat_group','iroquoian')
    select(['muskogee_language'],'muskogee_group','muskogean')
    select(['chickasaw_choctaw_language'],'chickasaw_choctaw_group','muskogean')
    for language,group in [('myaamia_language','myaamia_group'),('shawnee_language','shawnee_group'),('abenakian_language','abenakian_group'),('powhatan_language','powhatan_group'),('massachusett_language','massachusett_group'),('anishinabe_language','anishinabe_group')]:
        select([language],group,'algonquian')
    select(['cree_language'],'cree_group','cree',exclude=('beothuk_culture',))
    select(['inuit_language'],'inuit_group','inuit')
    select(['hokan_language'],'hokan_group','hokan',exclude=('tolupan_culture',))
    select(['nahuatl_language'],'nahua_group','nahua')
    select(['aymara_language'],'aymara_group','aimara',exclude=('chango_culture',))
    select(['khoe_language'],'khoisan_group','khoisan',exclude=('hadza_culture','sandawe_culture'))
    select(['mande_language'],'west_african_group','mande')
    select(['dhegiha_language'],'dhegiha_group','siouan')
    select(['chiwere_language'],'chiwere_group','siouan')
    select(['apsaalooke_hiraaca_language'],'apsaalooke_hiraaca_group','siouan')
    select(['dakota_language'],'dakota_group','dakota')
    # Preserve the source's distinct Pueblo grouping and Tlingit/Eyak exceptions.
    select(['nadene_language'],'nadene_group','athabaskan',exclude=('dine_culture','tinde_culture','lepai_nde_culture','inde_culture','tlingit_culture','eyak_culture'))
    add(['dine_culture'],'navajo','navajo_name_correspondence','Use V3 Navajo for the explicit Dine source identity.')
    add(['tinde_culture','lepai_nde_culture','inde_culture'],'apache','apache_subdivisions','Use the V3 Apache category for these explicitly listed Apache subdivisions; no generic Nadene-to-Apache rule.')
    # The pinned vanilla New Guinea POP history actually uses Melanesian; this
    # deliberately adopts that broad game bucket, not a linguistic family claim.
    papua=[c for c,d in pool.items() if Path(d['asset_basis']['source_file']).name=='papuan.txt' and d['source_groups']==['papuan_group']]
    add(papua,'melanesian','vanilla_new_guinea_granularity','Adopt vanilla New Guinea Melanesian POP granularity for this frozen Papuan-file member list. Native 12_indonesia.txt uses melanesian in Eastern and Western New Guinea. This intentionally collapses internal language distinctions for gameplay; it does not claim one real-world ethnicity.')
    add(['yap_culture','i_kiribati_culture','pohnpeian_culture','chamoru_culture','chuukese_culture'],'micronesian','explicit_micronesian_island_members','Use the installed Micronesian category for these named island identities. Do not sweep every source micronesian_group member into it.')
    add(['tagata_samoa_culture','maohi_culture','enana_culture','tuvaluan_culture','tokelauan_culture'],'polynesian','explicit_polynesian_island_members','Use the installed Polynesian category for these named island identities.')
    add(['kongo','yombe','solongo','mushikongo','vili','bwende','kakongo','mboma','bazombo'],'bakongo','explicit_kongo_subdivisions','Use V3 Bakongo for this bounded Kongo subdivision list; retain Ambundu, Yaka and Suku separately.')
    add(['kharchin_culture','tumed_culture','khamag_culture'],'mongol','mongolian_subdivisions','Use V3 Mongol granularity for these named Mongolian subdivisions; Daur and Sibe stay separate.')
    select(['shan_dialect'],'shan_group','shan')
    add(['highland'],'scottish_gaelic','highland_scottish','Use the installed Scottish Gaelic category for the source Highland identity.')
    add(['northumbrian'],'british','english_regional','Use the installed British category for the Northumbrian regional identity; preserve Cornish, Anglo-Irish and Norse-Gael.')
    add(['prussian','hanseatic','eastern_pomeranian'],'north_german','low_german_regional','Use North German for these explicitly Low German regional/institutional source identities.')
    add(['german_silesian'],'east_german','silesian_german_regional','Use installed East German granularity for the explicitly German Silesian source identity.')
    add(['halychian_culture'],'ukrainian','ukrainian_regional','Use Ukrainian for the Halychian regional source identity; retain Rusyn and Cossack candidates separately.')
    add(['polesian_culture'],'byelorussian','belarusian_regional','Use Byelorussian for the Polesian source identity explicitly assigned Belarusian dialect.')
    add(['pomor'],'russian','russian_regional','Use Russian for the Pomor regional identity.')
    add(['acciaioli_bank_culture','bardi_bank_culture','peruzzi_bank_culture'],'north_italian','tuscan_bank_institutions','Collapse these three Tuscan-speaking bank identities to North Italian gameplay culture; keep original institution keys in source provenance.')
    existing=profile.get('culture_compaction',{})
    for c,rule in existing.items():
        if c not in plans or plans[c]!=rule:raise ValueError('Refusing to overwrite another compaction rule: '+c)
    result={'source_cultures':len(plans),'native_categories':len({r['target'] for r in plans.values()}),
            'by_target':dict(Counter(r['target'] for r in plans.values())),'rules':plans,
            'script_sha256':digest(Path(__file__)),'definition_inputs':{str(p):digest(p) for p in Path('D:/Steam/steamapps/common/Victoria 3/game/common/cultures').glob('*.txt')}}
    evidence=Path('D:/Steam/steamapps/common/Victoria 3/game/common/history/pops/12_indonesia.txt')
    result['definition_inputs'][str(evidence)]=digest(evidence)
    if apply:
        profile['culture_compaction']=plans
        path.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'.local/m4/culture-compaction-plan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('rules','definition_inputs')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');a=p.parse_args();print(json.dumps(prepare(a.apply)))
