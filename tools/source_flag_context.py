"""Source evidence for heraldry; prestige ranking and country tier are distinct."""
from copy import deepcopy
from pdx_text import Object, root

RANK_TIERS = {'rank_county':'city_state', 'rank_duchy':'principality',
              'rank_kingdom':'kingdom', 'rank_empire':'empire'}

def rank_evidence(raw, date, override=None):
    def stamp(value): return tuple(map(int, value.split('.')))
    history=[]
    for _,item in raw.get('country_rank_history',[]):
        row=dict(item)
        if row.get('country_rank') in RANK_TIERS and stamp(row.get('date','1.1.1'))<=stamp(date):
            history.append(row)
    latest=max(history,key=lambda r:stamp(r.get('date','1.1.1'))) if history else {}
    explicit=raw.get('country_rank')
    rank=override or (explicit if explicit in RANK_TIERS else latest.get('country_rank'))
    return {'rank':rank,'basis':'campaign_user_observation' if override else
            'explicit_country_rank' if explicit in RANK_TIERS else 'dated_rank_history' if rank else 'unresolved',
            'history':history,'serialized_level':raw.get('level'),
            'history_disagrees_with_override':bool(override and latest and override!=latest['country_rank'])}

def enrich(politics, raw, economy, eu5, overrides=None):
    """Do not interpret serialized `level` as a rank without serializer evidence."""
    result=deepcopy(politics); countries=result['countries']; overrides=overrides or {}
    continents={}
    def walk(obj, continent):
        for key,value in obj.entries():
            if isinstance(value,Object): walk(value,continent)
            elif key is None: continents[value]=continent
    for continent,obj in root((eu5/'in_game/map_data/definitions.txt').read_text(encoding='utf-8-sig')).entries():
        if isinstance(obj,Object):walk(obj,continent)
    audit={}
    for sid,src in countries.items():
        src['subject_ids']=[]
        if sid not in raw:continue
        data=dict(raw[sid]);evidence=rank_evidence(data,politics['date'],overrides.get(sid))
        audit[sid]=evidence
        src['country_rank']=evidence['rank']
        src['previous_tags']=[v for _,v in data.get('previous_tags',[])]
        src['variable_names']=[dict(v).get('flag') for _,v in dict(data.get('variables',[])).get('data',[])]
        capital=economy['locations'].get(src.get('capital'),{}).get('name')
        src['capital_continent']=continents.get(capital)
        src['subject_ids']=[]
    for edge in politics['subjects']:
        if edge['overlord'] in countries and edge['subject'] in countries:
            countries[edge['overlord']]['subject_ids'].append(edge['subject'])
            countries[edge['subject']]['subject_type']=edge['type']
    return result,audit
