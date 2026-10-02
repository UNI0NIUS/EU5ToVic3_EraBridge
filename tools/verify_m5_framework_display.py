"""Independent output checks for localization, flag geometry and UI textures."""
from collections import Counter
from pathlib import Path
import re
from PIL import Image
from build_m3_world import load_localization
from package_m4_population_test import effective, parse_pops, GAME
from package_m5_culture_refinement import homeland_pairs,read
from m3_world import digest
from extract_m3_politics import fields
from pdx_text import root
from build_m2_prototype import objects,strings
from m5_dynamic_identity import entries
from verify_dynamic_identity import choose


def txt(p):return p.read_text(encoding='utf-8-sig')


def verify_display(package,base,mod,policy):
    keys=set().union(*(set(effective(mod,x)) for x in ['common/cultures','common/discrimination_traits','common/discrimination_trait_groups']))
    for i,lang in enumerate(('english','simp_chinese')):
        loc={}
        for d in [GAME/'localization'/lang,mod/'localization'/lang,mod/'localization/replace'/lang]:loc.update(load_localization(d))
        assert all(loc.get(k) and loc[k]!=k for k in keys)
        assert not any(re.search(r'审核|审查|映射|待审|待定|暂定|未核|候选|review|pending|mapping|provisional|candidate',loc[k],re.I) for k in keys)
        for k,labels in policy['labels'].items():assert loc[k]==labels[i],k
    # Name triggers and every previous guard remain byte-identical. Only added
    # flag guards omit subject status; they inherit all other predicates.
    rel='common/scripted_triggers/zz_eu5_dynamic_identity.txt'
    old,new=entries(base/rel),entries(mod/rel)
    expected=set(old)
    for k,o in old.items():
        assert new[k].text()==o.text()
        if k.startswith('eu5_identity_start_'):
            n=k.replace('eu5_identity_start_','eu5_flag_start_',1);expected.add(n)
            wanted=re.sub(r'(?m)^\s*is_subject\s*=\s*(yes|no)\s*$','',o.text()).split()
            assert new[n].text().split()==wanted
    assert set(new)==expected
    checked=0
    scripts={k:v for folder in (GAME,mod) for p in (folder/'common/scripted_triggers').glob('*.txt') for k,v in entries(p).items()}
    for p in (base/'common/flag_definitions').glob('*.txt'):
        before=txt(p);after=txt(mod/p.relative_to(base))
        assert after==re.sub(r'\beu5_identity_start_(\w+)\b',r'eu5_flag_start_\1',before)
        for tag,o in entries(mod/p.relative_to(base)).items():
            for op,v in o.entries():
                if op!='flag_definition' or fields(v).get('priority')!='100000':continue
                f=fields(v);g='eu5_flag_start_'+tag
                if g not in scripts:continue
                laws=set(re.findall(r'has_law\s*=\s*law_type:(\w+)',scripts[g].text()))
                for subject in (True,False):
                    assert choose(o,dict(laws=laws,subject=subject,ideology='ideology_moderate'),scripts,'flag_definition')==f['coa']
                checked+=1
    assert checked>0
    art='common/coat_of_arms/coat_of_arms/zz_eu5_dynamic_identity.txt'
    expected_art=txt(base/art).replace('scale = { 0.46 0.46 } offset = { 0.50 0.46 }','scale = { 1 1 } offset = { 0 0 }').replace('position = { 0.65 0.23 } scale = { 0.23 0.32 }','position = { 0.82 0.22 } scale = { 0.16 0.22 }')
    assert txt(mod/art)==expected_art
    for p in (base/'common/dynamic_country_names').glob('*.txt'):assert digest(p)==digest(mod/p.relative_to(base))
    icons=0
    for p in (mod/'gfx/interface/icons/religion_icons').glob('eu5_religion_*.dds'):
        with Image.open(p) as im:
            assert im.size==(256,256)
            x0,y0,x1,y1=im.convert('RGBA').getchannel('A').getbbox()
            assert abs(x0+x1-256)<=2 and abs(y0+y1-256)<=2
            assert 238<=max(x1-x0,y1-y0)<=240
        icons+=1
    assert icons==8
    pops=parse_pops(mod/'common/history/pops/00_eu5_world.txt');totals=Counter();by_c=Counter()
    for (s,o,c,r),n in pops.items():totals[s]+=n;by_c[s,c]+=n
    report=read(package/'package_report.json');d=read(Path(report['demographic_run'])/'demographics/demographics_report.json')
    migrants={r['target'] for r in d['migrant_cultures']['cultures']}
    actual={(s,c) for s,c in homeland_pairs(txt(mod/'common/history/states/00_eu5_world.txt')) if c in migrants}
    wanted={(s,c) for (s,c),n in by_c.items() if c in migrants and 2*n>totals[s]}
    assert actual==wanted,('Migrant strict majority drift',actual^wanted)
    return {'status':'passed','localized_keys_per_language':len(keys),'missing_names':0,'review_marker_values':0,
            'status_only_flag_transitions':checked,'native_flag_conditions_and_dynamic_names_preserved':True,
            'full_size_source_flag_verified':True,'centered_256px_religion_icons':icons,
            'migrant_strict_majority_homelands':len(actual),'runtime_verified':False}
