"""Freeze explicit preservation candidates for every currently unresolved culture.

This never calls them reviewed ethnic correspondences. Scaffolds only supply
provisional asset fields; language and heritage identities remain separate.
"""
import argparse
from collections import Counter,defaultdict
import csv
import json
from pathlib import Path

from build_m2_prototype import objects,strings
from m3_world import digest,fields,load_json
from m4_cultures import checked_source_language
from m4_religions import definitions,source_color
from pdx_text import root

ROOT=Path(__file__).resolve().parents[1]


def prepare(run, apply=False):
    profile_path=ROOT/'config/personal/m4_demographics.json';profile=load_json(profile_path)
    policy_path=ROOT/'config/personal/m4_culture_asset_scaffolds.json';policy=load_json(policy_path)
    game=Path('D:/Steam/steamapps/common/Victoria 3/game');eu5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')
    source={k:(p,fields(o)) for p in sorted((eu5/'in_game/common/cultures').glob('*.txt')) for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    languages=definitions(eu5/'in_game/common/languages');templates=definitions(game/'common/cultures')
    index=defaultdict(list)
    for name,d in languages.items():
        index[name].append((None,d.get('family')))
        if 'dialects' in d:
            for dialect,o in objects(d['dialects']):index[dialect].append((name,fields(o).get('family',d.get('family'))))
    previous_language_groups={c['source_language']:c.get('language_group') for c in profile['custom_resident_cultures'].values() if not c['language_trait']}
    color_text=(eu5/'main_menu/common/named_colors/02_map.txt').read_text(encoding='utf-8-sig')
    with (run/'demographics/resident_culture_crosswalk.csv').open(encoding='utf-8-sig',newline='') as f:
        pending=[r for r in csv.DictReader(f) if not r['target_culture']]
    plans={};review=[]
    for row in pending:
        c=row['source_culture'];path,d=source[c];language=d['language'];ancestry=index[language];scope=None
        # Pinned source quirk: Greek's top-level language contains a default dialect
        # with the identical key. Select the top-level definition explicitly.
        if c=='cappadocian_greek_culture' and ancestry==[(None,None),('greek_language',None)]:
            ancestry=[(None,None)];scope='top_level'
        if len(ancestry)!=1:raise ValueError('Language ancestry requires explicit handling: '+c)
        parent,family=ancestry[0];template=policy['templates_by_source_file'][path.name]
        if template not in templates:raise ValueError('Undefined asset scaffold: '+template)
        config={'source_language':language,'source_language_parent':parent,'source_language_scope':scope,
                'source_language_family':family,'source_groups':strings(d['culture_groups']) if 'culture_groups' in d else [],
                'template':template,'heritage_group':None,'language_trait':None,'language_group':previous_language_groups.get(language),
                'review_status':'generated_preservation_candidate_not_historically_reviewed',
                'asset_basis':{'source_file':str(path),'source_file_sha256':digest(path),'scaffold_policy':str(policy_path),'scaffold_policy_sha256':digest(policy_path)},
                'reason':'First-pass preservation of the explicit source identity, source language and separate heritage. No ethnic alias or ruler substitution. Heritage relationship is an independent provisional group; unresolved language family correspondence remains separately scoped. This generated candidate is not a historically reviewed mapping.',
                'template_limitation':'Asset-only scaffold '+template+' selected by source definition file '+path.name+'. Names, portraits, graphics, traditions and default religion are provisional inherited implementation fields, NOT evidence of ethnic equivalence or validated appearance. Resident religion remains explicit. Heritage acceptance, language-family acceptance, names, appearance and homelands require review.'}
        checked_source_language(languages,config)
        try:color,notes=source_color(color_text,d['color'])
        except ValueError:
            if c!='teimani' or d['color']!='map_teimani' or 'map_teimani = hsv360 { 222 70 182 }' not in color_text:raise
            config['display_color_override']={'source_color':'map_teimani','rgb':[0.3,0.51,1.0],
                'reason':'Display-only correction for installed map_teimani HSV360 {222 70 182}: clamp V=182 to 100, preserving H/S. Does not alter identity or people.'}
        old=profile['custom_resident_cultures'].get(c)
        if old and old!=config:raise ValueError('Refusing to overwrite existing identity configuration: '+c)
        if c in profile['culture_aliases']:raise ValueError('Refusing to overwrite explicit alias: '+c)
        plans[c]=config
        review.append({'source':c,'name':row['name'],'centipersons':int(row['centipersons']),
                       'source_file':path.name,'source_language':language,'source_language_parent':parent,
                       'template':template,'review_status':config['review_status'],
                       'issues':['provisional_heritage_relationship','provisional_language_family_correspondence','template_names_appearance_traditions','homelands_not_set']})
    result={'schema':1,'baseline_run':str(run.resolve()),'new_cultures':len(plans),'centipersons':sum(r['centipersons'] for r in review),
            'by_source_file':dict(Counter(r['source_file'] for r in review)),'identity_mapping_reviewed':False,
            'profile_before_sha256':digest(profile_path),'scaffold_policy_sha256':digest(policy_path),'entries':review}
    if apply:
        profile['custom_resident_cultures'].update(plans)
        profile_path.write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result['profile_after_sha256']=digest(profile_path)
    path=ROOT/'.local/m4/culture-sweep-plan.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('entries','by_source_file')}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);parser.add_argument('--apply',action='store_true');a=parser.parse_args()
    print(json.dumps(prepare(a.run,a.apply)))
