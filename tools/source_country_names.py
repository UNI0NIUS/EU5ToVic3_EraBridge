"""Resolve saved names before historic TAG labels; keep territorial and political names separate."""

def source_name_parts(source, fallback):
    raw=source.get('name')
    data=dict(raw) if isinstance(raw,list) else {'name':raw}
    custom=dict(data.get('key',[])).get('Custom_Name')
    token=data.get('override_name') or data.get('name') or fallback
    adjective=data.get('override_adj') or dict(data.get('key',[])).get('Adjective') or fallback+'_ADJ'
    return custom,token,adjective

def opening_name(source, neutral, lang):
    reforms=set(source.get('reforms',[]))
    # These titles are explicit EU5 reforms, not inferred from geography or TAG.
    if 'shogunate' in reforms:
        return neutral+'幕府' if lang=='simp_chinese' else neutral+' Shogunate'
    if 'daimyo' in reforms:
        return neutral+'藩' if lang=='simp_chinese' else neutral+' Domain'
    if 'japanese_imperial_family' in reforms:
        return neutral+'朝廷' if lang=='simp_chinese' else neutral+' Court'
    return neutral

def shogunate_roles(politics, org):
    """EU5 japanese_shogunate.leader explicitly selects the heir during a regency."""
    country=politics.get('countries',{}).get(org.get('leader'),{})
    regent=country.get('regent')
    person=country.get('heir') if regent else country.get('ruler')
    shared=sorted(sid for sid in org['members'] if person and
        politics.get('countries',{}).get(sid,{}).get('heir')==person)
    return {'shogun_character':person,'shogun_character_basis':'heir_during_regency' if regent else 'ruler',
            'shogun_regent':regent,'shared_heir_countries':shared,
            'shogun_person':politics.get('characters',{}).get(person),
            'interpretation':'Organization office, country regency and union seniority are distinct.'}

def refresh_saved_names(world, politics, localize, tags=None):
    changed=[]
    for tag,c in world['countries'].items():
        if tags is not None and tag not in tags:continue
        src=politics['countries'].get(c.get('source_id'))
        if not src:continue
        custom,token,adj=source_name_parts(src,c['source_tag'])
        data=dict(src['name']) if isinstance(src.get('name'),list) else {}
        japanese=bool(set(src.get('reforms',[]))&{'shogunate','daimyo','japanese_imperial_family'})
        if not data.get('override_name') and not japanese:continue
        old={lang:c.get('name_'+lang) for lang in ['english','simp_chinese']}
        for lang in old:
            neutral=custom or localize(token,lang)
            c['name_'+lang]=neutral
            c['opening_name_'+lang]=opening_name(src,neutral,lang)
            translated_adj=custom or localize(adj,lang)
            c['adjective_'+lang]=neutral if translated_adj.endswith('_ADJ') else translated_adj
        changed.append({'tag':tag,'source_id':c['source_id'],'old':old,'name_token':token,
                        'new':{lang:c['opening_name_'+lang] for lang in old}})
    return changed
