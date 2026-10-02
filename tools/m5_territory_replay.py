"""Replay the verified empty-terrain cleanup for later demographic stages."""
from collections import Counter
from pathlib import Path


def restore(world,report):
    changes=report.get('empty_terrain_attachments',[])
    if not changes:return
    from package_m5_uncolonized import terrain_assignments
    from m3_uncolonized import province_land_edges
    removed={r['from'] for r in changes}
    for tag in removed:
        if world.countries[tag]['source_id'] is not None:
            raise ValueError('Terrain cleanup cannot retire a source country')
    expected=terrain_assignments(removed,set(report['uncolonized_tribes']['countries']),world.owners,
        world.mapping,world.locations,world.uninhabitable,
        province_land_edges(world,Path(__file__).resolve().parents[1]/'.local/m3/cache/tribal_land_edges.json'))
    if sorted(expected,key=lambda r:r['province'])!=sorted(changes,key=lambda r:r['province']):
        raise ValueError('Terrain cleanup no longer matches source/map evidence')
    for r in changes:world.owners[r['state']][r['province']]=r['to']
    for tag in removed:del world.countries[tag]
    world.substates={s:Counter(ps.values()) for s,ps in world.owners.items()}
    for tag,c in world.countries.items():c['provinces']=sum(ps[tag] for ps in world.substates.values())
    for s,old in world.original.items():
        for tag in set(old.values()):
            overlaps=Counter(world.owners[s][p] for p,t in old.items() if t==tag and p in world.owners[s])
            if not overlaps:raise ValueError('Template state has no population destination')
            world.transfers[s,tag]=overlaps
