"""Reject country label regressions and obsolete custom religion textures."""
from pathlib import Path
import re
from PIL import Image
from build_m3_world import load_localization
from economy_model import definitions


def verify(mod,game,countries):
    mod,game=Path(mod),Path(game);missing=[];wrong=[]
    references=set()
    for p in (mod/'common/dynamic_country_names').glob('*.txt'):
        references.update(re.findall(r'\b(?:name|adjective)\s*=\s*(EU5_\w+)',p.read_text(encoding='utf-8-sig')))
    for lang in ('english','simp_chinese'):
        labels=load_localization(game/'localization'/lang)
        labels.update(load_localization(mod/'localization'/lang));labels.update(load_localization(mod/'localization/replace'/lang))
        missing.extend(lang+':'+k for k in references if k not in labels)
        for tag,c in countries.items():
            expected=c.get('opening_name_'+lang,c.get('name_'+lang))
            if c.get('generated_uncolonized'):expected=labels.get(c['culture'],expected)
            if expected and labels.get(tag)!=expected:wrong.append((lang,tag,labels.get(tag),expected))
    if missing or wrong:raise ValueError('Country identity mismatch: '+str(dict(missing=missing,wrong=wrong))[:1500])
    icons=[]
    for p in (mod/'gfx/interface/icons/religion_icons').glob('eu5*.dds'):
        with Image.open(p) as im:
            if im.size!=(256,256) or im.mode!='RGBA':raise ValueError('Invalid religion icon: '+str(p))
            box=im.getchannel('A').getbbox()
            if not box or abs((box[0]+box[2])/2-128)>1 or abs((box[1]+box[3])/2-128)>1:raise ValueError('Uncentered religion icon: '+str(p))
        icons.append(p.name)
    cultures=definitions(game/'common/cultures');cultures.update(definitions(mod/'common/cultures'))
    traits=definitions(game/'common/discrimination_traits');traits.update(definitions(mod/'common/discrimination_traits'))
    for name,c in cultures.items():
        if c.get('heritage') not in traits or c.get('language') not in traits:raise ValueError('Missing culture group: '+name)
    from converter_identity_repair import verify_event_labels
    event_keys=verify_event_labels(mod)
    return dict(countries=len(countries),dynamic_keys=len(references),religion_icons=len(icons),culture_definitions=len(cultures),event_keys=event_keys,status='passed',runtime_verified=False)
