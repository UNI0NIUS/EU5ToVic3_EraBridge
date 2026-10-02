"""Source identity resolution with explicit aliases and reviewed custom cultures."""
import re
from pathlib import Path
from pdx_text import root
from build_m2_prototype import objects, strings
from m3_world import fields, digest


def resolve_culture(source, profile, valid):
    if not source: raise ValueError('Missing source culture')
    if source in profile.get('custom_cultures', {}):
        target, mode = 'eu5_' + source, 'preserved_custom_identity'
    elif source in profile['culture_aliases']:
        target, mode = profile['culture_aliases'][source], 'reviewed_alias'
    elif source in valid:
        target, mode = source, 'same_key'
    elif source.removesuffix('_culture') in valid:
        target, mode = source.removesuffix('_culture'), 'same_key_without_suffix'
    else:
        raise ValueError('Unreviewed source culture: ' + source)
    if target not in valid: raise ValueError('Target culture is undefined: ' + target)
    return target, mode


def prepare_cultures(exporter):
    from build_m3_world import block
    w=exporter.w
    directory=w.eu5/'in_game/common/cultures'
    source_defs={k:o for p in sorted(directory.glob('*.txt')) for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    exporter.source_culture_defs=source_defs
    exporter.source_culture_inputs={str(p):digest(p) for p in sorted(directory.glob('*.txt'))}
    traits={k:o for p in sorted((w.game/'common/discrimination_traits').glob('*.txt')) for k,o in objects(root(w.read(p.relative_to(w.game))))}
    groups={k for p in sorted((w.game/'common/discrimination_trait_groups').glob('*.txt')) for k,o in objects(root(w.read(p.relative_to(w.game))))}
    custom, new_traits, new_groups, report = {}, {}, {}, []
    for source,config in sorted(w.profile.get('custom_cultures',{}).items()):
        key='eu5_'+source; template=config['template']
        if key in exporter.valid_cultures: raise ValueError('Culture key collision: '+key)
        sf=fields(source_defs[source]); base=exporter.valid_cultures[template]; tf=fields(base)
        heritage='eu5_heritage_'+source
        heritage_group=fields(traits[tf['heritage']])['trait_group']
        language=config.get('language_trait') or 'eu5_language_'+sf['language']
        language_group=config.get('language_group')
        if language_group:
            if language_group not in groups: raise ValueError('Unknown language group: '+language_group)
        else:
            # Where a reliable V3 family correspondence is absent, keep a distinct
            # group instead of silently assigning the template's unrelated family.
            language_group='eu5_language_group_'+sf['language']
            new_groups[language_group]='type = language'
        new_traits[heritage]=f'type = heritage\ntrait_group = {heritage_group}'
        language_body=f'type = language\ntrait_group = {language_group}'
        if language in new_traits and new_traits[language] != language_body:raise ValueError('Conflicting source language families')
        if config.get('language_trait'):
            if language not in traits:raise ValueError('Unknown existing language trait: '+language)
            language_group=fields(traits[language])['trait_group']
        else:
            new_traits[language]=language_body
        body=re.sub(r'\bheritage\s*=\s*\w+',f'heritage = {heritage}',base.text())
        body=re.sub(r'\blanguage\s*=\s*\w+',f'language = {language}',body)
        custom[key]=body
        exporter.valid_cultures[key]=dict(objects(root(block(key,body))))[key]
        for lang in exporter.localization:
            label=exporter.localize(source,lang)
            exporter.localization[lang][key]=label
            exporter.localization[lang][heritage]=label+('传承' if lang=='simp_chinese' else ' Heritage')
            language_label=exporter.localize(sf['language'],lang)
            if language in new_traits:exporter.localization[lang][language]=language_label
            if language_group in new_groups:exporter.localization[lang][language_group]=language_label
        report.append({'source':source,'target':key,'template':template,'source_language':sf['language'],
                       'heritage':heritage,'heritage_group':heritage_group,'language':language,'language_group':language_group,
                       'limitation':'Template supplies graphics, default religion, name lists and traditions. Heritage and language remain distinct; unresolved families use an isolated group.'})
    exporter.write('common/cultures/zz_eu5_cultures.txt',''.join(block(k,v) for k,v in custom.items()))
    exporter.write('common/discrimination_traits/zz_eu5_cultures.txt',''.join(block(k,v) for k,v in sorted(new_traits.items())))
    exporter.write('common/discrimination_trait_groups/zz_eu5_languages.txt',''.join(block(k,v) for k,v in sorted(new_groups.items())))
    exporter.custom_culture_report=report


def source_culture_info(exporter, source):
    obj=exporter.source_culture_defs.get(source)
    if obj is None:return {}
    f=fields(obj)
    return {'language':f.get('language'),'groups':strings(f['culture_groups']) if 'culture_groups' in f else [],
            'name_english':exporter.localize(source,'english'),'name_simp_chinese':exporter.localize(source,'simp_chinese')}


def preserve_source_names(exporter):
    """Prevent a reused TAG's vanilla dynastic rules from overwriting source names."""
    from build_m3_world import block
    from build_m2_prototype import replace_body, patch
    wanted={t for t,c in exporter.w.countries.items() if c['source_id'] and t in exporter.w.country_defs}
    found=set()
    def override(tag):
        key='EU5_SOURCE_NAME_'+tag
        for lang in exporter.localization:exporter.localization[lang][key]=exporter.w.countries[tag]['name_'+lang]
        return block('dynamic_country_name',f'name = {key}\nadjective = {tag}_ADJ\nis_main_tag_only = yes\npriority = 10000\ntrigger = {{ }}')
    for p in sorted((exporter.w.game/'common/dynamic_country_names').glob('*.txt')):
        relative=p.relative_to(exporter.w.game).as_posix(); text=exporter.w.read(relative); edits=[]
        for tag,obj in objects(root(text)):
            if tag in wanted:
                # Keep lower-priority vanilla variants for dynamic/revolt tags.
                edits.append(replace_body(obj,'\n'+override(tag)+obj.text()));found.add(tag)
        if edits:exporter.write(relative,patch(text,edits))
    remaining=wanted-found
    if remaining:exporter.write('common/dynamic_country_names/zz_eu5_source_names.txt',''.join(block(t,override(t)) for t in sorted(remaining)))
    exporter.source_name_overrides=sorted(wanted)
