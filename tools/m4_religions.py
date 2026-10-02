"""Preserve explicitly configured source religions as private target asset candidates."""
import colorsys
import json
from pathlib import Path
import re
import shutil

from build_m2_prototype import objects, strings
from build_m3_world import block, load_localization
from m3_world import digest, fields
from pdx_text import root


def definitions(directory):
    return {key:fields(obj) for p in sorted(directory.glob('*.txt'))
            for key,obj in objects(root(p.read_text(encoding='utf-8-sig')))}


def source_color(text, name):
    match = re.search(r'^\s*'+re.escape(name)+r'\s*=\s*(rgb|hsv360|hsv)\s*\{([^}]+)\}', text, re.M)
    if not match:
        raise ValueError('Unresolved source religion color: '+name)
    values = [float(v) for v in match[2].split()]
    if len(values) != 3:
        raise ValueError('Invalid source color components: '+name)
    changes = []
    if match[1] == 'rgb':
        clamped = [max(0,min(255,v)) for v in values]
        if clamped != values:
            changes.append('Explicit display-only clamp of source RGB to 0..255: '+str(values)+' -> '+str(clamped))
        rgb = [v/255 for v in clamped]
    elif match[1] == 'hsv':
        if not all(0 <= v <= 1 for v in values):raise ValueError('Invalid source HSV color: '+name)
        rgb = colorsys.hsv_to_rgb(*values)
    else:
        h,s,v = values
        if not (0 <= h <= 360 and 0 <= s <= 100 and 0 <= v <= 100):
            raise ValueError('Invalid source HSV color: '+name)
        rgb = colorsys.hsv_to_rgb(h/360,s/100,v/100)
    return [round(v,6) for v in rgb], changes


def write_custom_religions(out, game, eu5, source_defs, profile):
    configs = profile.get('custom_religions',{})
    if not configs:
        return {'religions':[], 'inputs_sha256':{}}
    target = definitions(game/'common/religions')
    traits = definitions(game/'common/discrimination_traits')
    groups = definitions(game/'common/discrimination_trait_groups')
    goods = definitions(game/'common/goods')
    color_path = eu5/'main_menu/common/named_colors/02_map.txt'
    colors = color_path.read_text(encoding='utf-8-sig')
    localization = {lang:load_localization(eu5/'main_menu/localization'/lang) for lang in ('simp_chinese','english')}
    labels = {lang:{} for lang in localization}
    bodies, new_traits, new_groups, records = {}, {}, {}, []
    inputs = {str(color_path):digest(color_path)}
    for directory in (game/'common/discrimination_traits',game/'common/discrimination_trait_groups',game/'common/goods'):
        inputs.update({str(p):digest(p) for p in sorted(directory.glob('*.txt'))})
    for source,config in sorted(configs.items()):
        if not re.fullmatch(r'[a-z][a-z0-9_]*',source):
            raise ValueError('Invalid custom religion source key')
        key = 'eu5_religion_'+source
        if source not in source_defs or source_defs[source].get('group') != config['source_group']:
            raise ValueError('Custom religion source group changed: '+source)
        if key in target or source in profile['religion_aliases']:
            raise ValueError('Custom religion identity collision: '+source)
        heritage = config['heritage']
        if heritage:
            if heritage not in traits or traits[heritage].get('type') != 'heritage':
                raise ValueError('Invalid religious heritage: '+heritage)
            group = traits[heritage]['trait_group']
            if group not in groups or groups[group].get('type') != 'heritage':
                raise ValueError('Invalid religious heritage group: '+group)
        else:
            group = 'eu5_religious_group_'+config['source_group']
            heritage = 'eu5_religious_heritage_'+config['source_group']
            if group in groups or heritage in traits:
                raise ValueError('Custom religious trait collision: '+source)
            new_groups[group] = 'type = heritage'
            new_traits[heritage] = 'type = heritage\ntrait_group = '+group
        taboos = config.get('taboos',[])
        if len(taboos) != len(set(taboos)) or any(g not in goods for g in taboos):
            raise ValueError('Invalid religious taboo goods: '+source)
        icon_source = eu5/'main_menu/gfx/interface/icons/religion'/(source+'.dds')
        if icon_source.read_bytes()[:4] != b'DDS ':
            raise ValueError('Invalid religion DDS: '+source)
        from PIL import Image
        with Image.open(icon_source) as image:
            image.load(); dimensions = list(image.size)
        relative = Path('gfx/interface/icons/religion_icons')/(key+'.dds')
        icon_target = out/relative;icon_target.parent.mkdir(parents=True,exist_ok=True)
        from religion_icon_texture import compile_icon
        icon_conversion = compile_icon(icon_source,icon_target)
        dimensions = icon_conversion['output_size']
        inputs[str(icon_source)] = digest(icon_source)
        color, color_notes = source_color(colors,source_defs[source]['color'])
        from religion_palette import color as palette_color, POLICY
        selected = palette_color(source)
        if selected is not None:
            color = selected
            color_notes.append('Explicit map display palette: '+str(POLICY))
            inputs[str(POLICY)] = digest(POLICY)
        bodies[key] = f'icon = "{relative.as_posix()}"\nheritage = {heritage}\ncolor = {{ '+ ' '.join(map(str,color))+' }\n'
        if taboos:
            bodies[key] += 'taboos = { '+' '.join(taboos)+' }\n'
        for lang,loc in localization.items():
            if source not in loc:
                raise ValueError('Missing custom religion localization: '+source+'/'+lang)
            labels[lang][key] = loc[source]
            if heritage in new_traits:
                labels[lang][heritage] = loc[source]+('传承' if lang=='simp_chinese' else ' Heritage')
                labels[lang][group] = loc[source]+('传统' if lang=='simp_chinese' else ' Tradition')
        records.append({'source':source,'target':key,'source_group':config['source_group'],'heritage':heritage,
                        'heritage_group':group,'isolated_heritage':config['heritage'] is None,'icon':relative.as_posix(),
                        'icon_sha256':digest(icon_target),'icon_dimensions':dimensions,'icon_conversion':icon_conversion,'color':color,'color_notes':color_notes,
                        'taboos':taboos,'reason':config['reason']})
    for relative, rows in [('common/religions/zz_eu5_resident_religions.txt',bodies),
                           ('common/discrimination_traits/zz_eu5_resident_religions.txt',new_traits),
                           ('common/discrimination_trait_groups/zz_eu5_resident_religions.txt',new_groups)]:
        path = out/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(block(k,v) for k,v in sorted(rows.items())),encoding='utf-8')
    for lang,values in labels.items():
        path=out/'localization'/lang/('eu5_resident_religions_l_'+lang+'.yml');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('l_'+lang+':\n'+''.join(' '+k+':0 '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in sorted(values.items())),encoding='utf-8-sig')
    return {'religions':records,'inputs_sha256':inputs}
