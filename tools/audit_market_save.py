"""Read actual serialized production and price samples; never infer unrecorded orders."""
from collections import Counter,defaultdict
from pathlib import Path
from statistics import median
from pdx_text import root,Object
from extract_m3_politics import fields,sequence
from economy_model import definitions
from converter_project import digest,write


def audit(save,game):
    save,game=Path(save),Path(game);doc=root(save.read_text(encoding='utf-8-sig')).fields()
    goods=definitions(game/'common/goods');order=list(goods)
    def db(key):return {i:fields(o) for i,o in fields(fields(doc.get(key)).get('database')).items() if isinstance(o,Object)}
    countries=db('country_manager');states=db('states');buildings=db('building_manager')
    def amounts(obj):
        return {order[int(i)]:float(fields(v).get('value',0)) for i,v in fields(fields(obj).get('goods')).items()}
    # Goods IDs follow the installed declaration order. Verify against explicit
    # names in state trade records, rejecting an incompatible save/mod layout.
    checks=0
    for s in states.values():
        if s.get('traded_goods') and fields(fields(s.get('trade')).get('goods')):
            if set(amounts(s['trade']))!=set(sequence(s['traded_goods'])):raise ValueError('Save goods IDs do not match installed goods order')
            checks+=1
    if not checks:raise ValueError('Cannot independently verify saved goods IDs')
    markets=defaultdict(lambda:dict(inputs=Counter(),outputs=Counter(),buildings=defaultdict(Counter),members=[]))
    for i,c in countries.items():
        if 'market' in c:markets[c['market']]['members'].append(c.get('definition',i))
    for b in buildings.values():
        s=states.get(b.get('state'),{});c=countries.get(s.get('country'),{});market=c.get('market')
        if market is None:continue
        m=markets[market];m['inputs'].update(amounts(b.get('input_goods')));m['outputs'].update(amounts(b.get('output_goods')))
        a=m['buildings'][b['building']];a['levels']+=int(b.get('levels',0));a['staffed_levels']+=float(b.get('staffing',0))
    channels=fields(fields(fields(fields(doc['market_manager'])['world_market'])['price_trend'])['channels'])
    prices={}
    for i,o in channels.items():
        f=fields(o);values=[float(v) for v in sequence(f.get('values'))]
        if values:
            good=order[int(i)];base=float(goods[good]['cost'])
            prices[good]=dict(base=base,min=min(values),max=max(values),median=median(values),median_vs_base=median(values)/base-1,date=f.get('date'),samples=len(values))
    result=dict(save=str(save.resolve()),sha256=digest(save),date=doc.get('date'),goods_id_crosschecks=checks,
                world_market_price_samples=prices,markets={},limitations=['Prices are serialized WORLD market historical samples, not a country market quote.',
                'Building flows are actual recorded production and intermediate consumption; population, construction, military and trade orders are not reconstructed here.',
                'A later save describes runtime outcomes, not the opening day.'])
    for k,m in markets.items():
        result['markets'][k]=dict(members=sorted(m['members']),buildings=dict(m['buildings']),goods={g:dict(output=m['outputs'][g],building_input=m['inputs'][g],building_net=m['outputs'][g]-m['inputs'][g]) for g in order if m['outputs'][g] or m['inputs'][g]})
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--save',type=Path,required=True);p.add_argument('--game',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.save.resolve()==a.output.resolve():raise ValueError('Cannot overwrite save')
    write(a.output,audit(a.save,a.game))
