"""Build private, campaign-pinned map assets for the local location reviewer."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image

from pdx_text import Object, root
from build_m3_world import load_localization
from build_m2_prototype import strings
from m3_world import digest, load_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / '.local/m4/location-workstation'


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def packed(im):
    a = np.asarray(im.convert('RGB'), dtype=np.uint32)
    return (a[:, :, 0] << 16) | (a[:, :, 1] << 8) | a[:, :, 2]


def wrapped_distances(points, point, width):
    delta = np.asarray(points, dtype=float) - np.asarray(point, dtype=float)
    delta[:, 0] = (delta[:, 0] + width/2) % width - width/2
    return np.sum(delta**2, axis=1)


def wrapped_mean(points, width, weights=None):
    points = np.asarray(points, dtype=float).copy()
    anchor = points[0, 0]
    points[:, 0] = anchor + (points[:, 0] - anchor + width/2) % width - width/2
    mean = np.average(points, axis=0, weights=weights)
    mean[0] %= width
    return mean


def source_centers(image, colors):
    """Use native pixels, including tiny islands; bounded stripe memory."""
    lookup = np.zeros(1 << 24, dtype=np.int32)
    names = sorted(colors)
    for i, name in enumerate(names, 1):
        lookup[colors[name]] = i
    n = len(names) + 1
    counts = np.zeros(n); xs = np.zeros(n); ys = np.zeros(n)
    left = np.zeros(n); far_left = np.zeros(n); far_right = np.zeros(n)
    width, height = image.size
    for y in range(0, height, 128):
        h = min(128, height-y)
        grid = lookup[packed(image.crop((0, y, width, y+h)))]
        labels = grid.ravel()
        counts += np.bincount(labels, minlength=n)
        xs += np.bincount(labels, weights=np.tile(np.arange(width), h), minlength=n)
        ys += np.bincount(labels, weights=np.repeat(np.arange(y, y+h), width), minlength=n)
        left += np.bincount(grid[:, :width//2].ravel(), minlength=n)
        far_left += np.bincount(grid[:, :width//4].ravel(), minlength=n)
        far_right += np.bincount(grid[:, 3*width//4:].ravel(), minlength=n)
    # Province polygons crossing the longitude seam must be averaged in one
    # unwrapped interval. Ordinary x averaging puts Bering Sea islands inland.
    wrapped = (far_left > 0) & (far_right > 0)
    xs[wrapped] += width * left[wrapped]
    return {name: [round((xs[i]/counts[i] % width)/2, 2), round(ys[i]/counts[i]/2, 2)]
            for i, name in enumerate(names, 1) if counts[i]}


def paint(image, colors, path):
    ids = packed(image)
    palette = np.full((1 << 24, 3), (20, 39, 57), dtype=np.uint8)
    for color, rgb in colors.items():
        palette[color] = rgb
    rgb = palette[ids]
    borders = np.zeros(ids.shape, dtype=bool)
    borders[:, 1:] |= ids[:, 1:] != ids[:, :-1]
    borders[1:, :] |= ids[1:, :] != ids[:-1, :]
    rgb[borders] = (31, 48, 61)
    Image.fromarray(rgb).save(path)


def build(out, stage, game, eu5, run):
    if (out / 'data.json').exists():
        raise ValueError('Dataset exists; reuse it, or build in a new --out directory.')
    out.mkdir(parents=True, exist_ok=True)
    sr = load_json(stage / 'staging_report.json')
    report = load_json(run / 'conversion_report.json')
    owner_path = run / 'province_owners.json'
    owners = load_json(owner_path)
    if owners != load_json(Path(sr['political_run']) / 'province_owners.json'):
        raise ValueError('Political map differs from population staging')
    if sr['source_sha256'] != report['source_sha256']:
        raise ValueError('Source mismatch')
    for name, sha in sr['files_sha256'].items():
        if digest(stage / name) != sha:
            raise ValueError('Staging file changed: ' + name)
    print('Reading names and existing links...', flush=True)
    audit = load_json(ROOT / '.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json')
    source = ROOT / '.local/m4/source-1780-population'
    summary = load_json(source / 'source_summary.json')
    if summary['source_sha256'] != sr['source_sha256']:
        raise ValueError('Ledger source mismatch')
    for name, sha in summary['files_sha256'].items():
        if digest(source / name) != sha:
            raise ValueError('Source ledger changed: ' + name)
    sloc = load_localization(eu5 / 'main_menu/localization/simp_chinese')
    en = load_localization(eu5 / 'main_menu/localization/english')
    vloc = load_localization(game / 'localization/simp_chinese')
    countries = report['countries']
    country_names = {c['source_id']: c['name_simp_chinese'] for c in countries.values() if c['source_id']}
    for c in audit['countries']:
        country_names.setdefault(str(c['id']), c.get('tag', str(c['id'])))
    cross = csv_rows(stage / 'location_crosswalk.csv')
    missing = {r['source_location']: r for r in cross if r['status'] == 'geometry_pending'}
    anchors = {r['source_location']: r['target_provinces'].split(';') for r in cross if r['target_provinces']}
    colors = {}
    for p in sorted((eu5 / 'in_game/map_data/named_locations').glob('*.txt')):
        for m in re.finditer(r'^\s*(\w+)\s*=\s*([0-9a-fA-F]{6})\b', p.read_text(encoding='utf-8-sig'), re.M):
            colors[m[1]] = int(m[2], 16)
    region = {}
    def descend(obj, chain=()):
        for k, v in obj.entries():
            if isinstance(v, Object):
                descend(v, chain+(k,))
            elif k is None:
                region[v] = list(chain)
    descend(root((eu5 / 'in_game/map_data/definitions.txt').read_text(encoding='utf-8-sig')))
    Image.MAX_IMAGE_PIXELS = 150_000_000  # Known installed game bitmap.
    source_path = eu5 / 'in_game/map_data/locations.png'
    sim = Image.open(source_path).convert('RGB')
    print('Locating source locations from native map pixels...', flush=True)
    centers = source_centers(sim, colors)
    small = sim.resize((sim.width//2, sim.height//2), Image.Resampling.NEAREST)
    small.save(out / 'source-ids.png')
    del sim
    land_names = {r['location'] for r in csv_rows(source / 'source_locations.csv')}
    map_defs = root((eu5 / 'in_game/map_data/default.map').read_text(encoding='utf-8-sig')).fields()
    water = {n for key in ('sea_zones', 'lakes') for n in strings(map_defs[key])}
    paint(small, {c: (73, 110, 119) if name in land_names and name not in water else (20, 39, 57) for name, c in colors.items()}, out / 'source-map.png')
    del small
    target_path = game / 'map_data/provinces.png'
    tim = Image.open(target_path).convert('RGB')
    tim.save(out / 'target-ids.png')
    points = load_json(ROOT / '.local/m3/cache/centroids.json')
    if points['sha256'] != digest(target_path):
        raise ValueError('Target centroid cache is stale')
    points = points['points']
    political_colors = [(66, 110, 133), (91, 126, 115), (129, 113, 95), (109, 104, 138), (83, 124, 142), (135, 121, 101)]
    tags = {t: political_colors[i % len(political_colors)] for i, t in enumerate(sorted(countries))}
    targets = {p: {'state': s, 'state_name': vloc.get(s, s), 'owner': t,
                   'owner_name': countries[t].get('name_simp_chinese', vloc.get(t, t)), 'xy': points[p], 'sources': []}
               for s, ps in owners.items() for p, t in ps.items()}
    paint(tim, {int(p[1:], 16): tags[d['owner']] for p, d in targets.items()}, out / 'target-map.png')
    target_size = list(tim.size)
    del tim
    for name, ps in anchors.items():
        for p in ps:
            if p in targets:
                targets[p]['sources'].append(name)
    populations = defaultdict(Counter)
    for row in csv_rows(source / 'source_populations.csv'):
        if row['location'] in missing:
            populations[row['location']][row['source_culture']] += int(row['centipersons'])
    all_source = {name: {'name': sloc.get(name, en.get(name, name)), 'english': en.get(name, name),
                         'xy': xy, 'color': f'{colors[name]:06X}', 'targets': anchors.get(name, [])}
                  for name, xy in centers.items() if name in land_names}
    known = [n for n in anchors if n in centers and all(p in targets for p in anchors[n])]
    known_xy = np.array([centers[n] for n in known])
    target_keys = list(targets)
    target_xy = np.array([targets[p]['xy'] for p in target_keys])
    todo = []
    for name, row in sorted(missing.items(), key=lambda x: -int(x[1]['source_centipersons'])):
        if name not in all_source:
            raise ValueError('Missing location has no native-map centroid: ' + name)
        xy = np.array(centers[name])
        distances = wrapped_distances(known_xy,xy,8192)
        near = np.argsort(distances)[:8]
        neighbors = [known[i] for i in near]
        # Local mapped neighbors account for differing game projections. These
        # are navigation aids only; no suggestion is automatically accepted.
        positions = np.array([wrapped_mean([targets[p]['xy'] for p in anchors[n]],target_size[0]) for n in neighbors])
        guess = wrapped_mean(positions,target_size[0],weights=1/np.maximum(distances[near], 1))
        candidates = [target_keys[i] for i in np.argsort(wrapped_distances(target_xy,guess,target_size[0]))[:12]]
        todo.append({'id': name, **all_source[name], 'centipersons': int(row['source_centipersons']),
                     'owner_id': row['source_owner'], 'owner_name': country_names.get(row['source_owner'], row['source_owner']),
                     'region': ' / '.join(sloc.get(k, k) for k in region.get(name, [])),
                     'cultures': [{'name': sloc.get(c, c), 'id': c, 'centipersons': n} for c, n in populations[name].most_common(5)],
                     'neighbors': neighbors, 'guess': [round(float(v), 2) for v in guess], 'candidates': candidates})
    data = {'schema': 1, 'source_sha256': sr['source_sha256'], 'political_map_sha256': digest(owner_path),
            'source_map_sha256': digest(source_path), 'target_map_sha256': digest(target_path),
            'stage': str(stage.resolve()), 'political_run': str(run.resolve()),
            'source_size': [8192, 4096], 'target_size': target_size,
            'total_centipersons': sum(r['centipersons'] for r in todo),
            'locations': todo, 'sources': all_source, 'targets': targets}
    (out / 'data.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'locations': len(todo), 'targets': len(targets), 'out': str(out)}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=DEFAULT)
    p.add_argument('--stage', type=Path, default=ROOT / '.local/m4/staging-20260930-0.3.6')
    p.add_argument('--run', type=Path, default=Path(load_json(ROOT / '.local/m3/latest.json')['run']))
    p.add_argument('--game', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    p.add_argument('--eu5', type=Path, default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    a = p.parse_args(); build(a.out, a.stage, a.game, a.eu5, a.run)
