"""Build a separate 1337 target-oriented review workstation from audited facts."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import numpy as np
from PIL import Image
from build_location_workstation import ROOT, source_centers, paint, wrapped_mean, wrapped_distances
from build_m3_world import load_localization
from build_m2_prototype import objects, strings
from m3_world import digest, province, fields
from pdx_text import root

DEFAULT = ROOT/'.local/m3/terrain-workstation-1337'
REPORT = ROOT/'outputs/terrain-1337-reviewed-geography-20261002'


def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))


def political_color(key):
    b = hashlib.sha256(key.encode()).digest()
    return tuple(75+x%95 for x in b[:3])


def build(out, report, audit_path, eu5, game):
    if (out/'data.json').exists(): raise ValueError('Dataset already exists; use a new output directory')
    out.mkdir(parents=True, exist_ok=True)
    audit, plan, evidence, seeds = [read(p) for p in (audit_path, report/'plan.json', report/'source_evidence.json', report/'seeds.json')]
    assert digest(audit_path) == evidence['audit_sha256'] and audit['date'] == evidence['source_date']
    geo = read(ROOT/'config/geography/reviewed_location_links.json')
    source_path, target_path = eu5/'in_game/map_data/locations.png', game/'map_data/provinces.png'
    assert digest(source_path) == geo['source_map_sha256'] and digest(target_path) == geo['target_map_sha256']
    sloc = load_localization(eu5/'main_menu/localization/simp_chinese')
    en = load_localization(eu5/'main_menu/localization/english')
    vloc = load_localization(game/'localization/simp_chinese')
    colors = {}
    for path in sorted((eu5/'in_game/map_data/named_locations').glob('*.txt')):
        colors.update({m[1]:int(m[2],16) for m in re.finditer(r'^\s*(\w+)\s*=\s*([0-9a-fA-F]{6})\b',path.read_text(encoding='utf-8-sig'),re.M)})
    defs = root((eu5/'in_game/map_data/default.map').read_text(encoding='utf-8-sig')).fields()
    water = {n for k in ('sea_zones','lakes') for n in strings(defs[k])}
    barren = {n for k in ('impassable_mountains','non_ownable') for n in strings(defs[k])}
    source = {r['name']:r for r in audit['locations']}
    countries = {str(c['id']):sloc.get(c['tag'],en.get(c['tag'],c['tag'])) for c in audit['countries']}
    Image.MAX_IMAGE_PIXELS = 150_000_000
    print('Building source map and wrap-aware coordinates...',flush=True)
    sim = Image.open(source_path).convert('RGB'); centers = source_centers(sim, colors)
    small = sim.resize((sim.width//2,sim.height//2), Image.Resampling.NEAREST); del sim
    small.save(out/'source-ids.png')
    sources = {}
    palette = {}
    for n, xy in centers.items():
        if n in water: continue
        l = source.get(n,{}); owner = str(l.get('owner',0)); cultures = evidence['location_cultures'].get(n,{})
        primary = min(cultures,key=lambda c:(-cultures[c],c)) if cultures else ''
        usable = n not in barren and (owner != '0' or sum(cultures.values())>0)
        sources[n] = dict(name=sloc.get(n,en.get(n,n)),english=en.get(n,n),xy=xy,color=f'{colors[n]:06X}',
                          owner=owner,owner_name=countries.get(owner,'无主'),population=l.get('population_persons','0'),
                          culture=sloc.get(primary,primary),culture_key=primary,barren=n in barren,evidence=usable)
        palette[colors[n]] = (96,106,115) if n in barren else political_color('source:'+owner) if owner!='0' else (211,219,210)
    paint(small,palette,out/'source-map.png'); del small
    print('Building target coverage map...',flush=True)
    points = read(ROOT/'.local/m3/cache/centroids.json'); assert points['sha256']==geo['target_map_sha256']
    province_states = {p:r['state'] for p,r in plan['provinces'].items()}
    # Use the actual V3 definitions for unresolved components that span states.
    for path in sorted((game/'map_data/state_regions').glob('*.txt')):
        for state,obj in objects(root(path.read_text(encoding='utf-8-sig'))):
            for p in strings(fields(obj).get('provinces',[])):
                p=province(p)
                if any(p in c['provinces'] for c in plan['unresolved_components']): province_states[p]=state
    targets = {}
    for p,state in province_states.items():
        row = plan['provinces'].get(p,{})
        owner = row.get('owner',''); seed = seeds.get(row.get('root'),{})
        owner_name = countries.get(owner.removeprefix('source:'),'') if owner.startswith('source:') else sloc.get(owner.split(':')[1],owner.split(':')[1]) if owner else '待匹配'
        targets[p] = dict(state=state,state_name=vloc.get(state,state),xy=points['points'][p],
                          owner=owner,owner_name=owner_name,kind=row.get('kind','unresolved'),sources=seed.get('source_locations',[]))
    tim=Image.open(target_path).convert('RGB'); tim.save(out/'target-ids.png')
    paint(tim,{int(p[1:],16):(222,84,98) if not r['owner'] else political_color(r['owner'].split(':x')[0]) for p,r in targets.items()},out/'target-map.png')
    size=list(tim.size);del tim
    anchor_keys=[p for p,r in seeds.items() if any(n in sources for n in r['source_locations'])]
    anchor_xy=np.array([targets[p]['xy'] for p in anchor_keys])
    components=[]
    for c in sorted(plan['unresolved_components'],key=lambda c:(-len(c['provinces']),c['component'])):
        xy=wrapped_mean([targets[p]['xy'] for p in c['provinces']],size[0])
        neighbors=[anchor_keys[i] for i in np.argsort(wrapped_distances(anchor_xy,xy,size[0]))[:10]]
        names=list(dict.fromkeys(n for p in neighbors for n in seeds[p]['source_locations'] if n in sources))[:24]
        guess=wrapped_mean([sources[n]['xy'] for n in names],8192).tolist() if names else [xy[0],xy[1]*4096/size[1]]
        components.append(dict(c,xy=xy.tolist(),source_guess=guess,candidates=names,
                               state_names=[vloc.get(s,s) for s in c['states']]))
    data=dict(schema='terrain-workstation-v1',source_date=audit['date'],source_sha256=evidence['source_sha256'],
              source_map_sha256=geo['source_map_sha256'],target_map_sha256=geo['target_map_sha256'],
              source_size=[8192,4096],target_size=size,components=components,sources=sources,targets=targets,
              summary=plan['summary'],report=str(report.resolve()),
              input_sha256={str(p):digest(p) for p in [audit_path,report/'plan.json',report/'seeds.json',report/'source_evidence.json',ROOT/'config/geography/reviewed_location_links.json']})
    from terrain_display_geometry import refresh_geometry
    refresh_geometry(data,Image.open(target_path).convert('RGB'))
    (out/'data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(dict(components=len(components),provinces=sum(len(c['provinces']) for c in components),sources=len(sources),out=str(out))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=DEFAULT);p.add_argument('--report',type=Path,default=REPORT)
    p.add_argument('--audit',type=Path,default=ROOT/'.local/m1/start-report/import_report.json')
    p.add_argument('--eu5',type=Path,default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    p.add_argument('--game',type=Path,default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    a=p.parse_args();build(a.out,a.report,a.audit,a.eu5,a.game)
