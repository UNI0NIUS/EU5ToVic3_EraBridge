"""Evidence-based partial colonial settlement and explicitly reviewed empty islands.

Culture alone never establishes sovereignty. An active source charter, its exact
target, and a strict majority of the charter country's primary culture are all
required. Only the settled target is represented as colonial territory in V3;
the remaining charter area is not annexed. This is a conversion approximation,
not a claim that the source location already has a formal owner.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json

from m3_world import digest
from pdx_text import Object, root
from extract_m3_politics import fields


def extract_charters(save, source_sha, cache):
    save, cache = Path(save), Path(cache)
    if digest(save) != source_sha:
        raise ValueError('Colonial evidence belongs to another source save')
    if cache.exists():
        saved = json.loads(cache.read_text(encoding='utf-8'))
        if saved['source_sha256'] == source_sha and saved.get('extractor_sha256') == digest(__file__):
            return saved
    doc = root(save.read_text(encoding='utf-8')).fields()
    db = fields(fields(doc.get('colony_manager')).get('database'))
    charters = []
    for cid, obj in db.items():
        if not isinstance(obj, Object):
            continue
        countries = {v for k, v in obj.entries() if k == 'country'}
        if len(countries) != 1:
            raise ValueError('Ambiguous charter country: ' + cid)
        f = fields(obj)
        charters.append({'id': cid, 'source_country': next(iter(countries)),
                         'target_location_id': f['target'], 'province': f.get('prov'),
                         'months': int(f.get('months', '0'))})
    result = {'source_sha256': source_sha, 'source_path': str(save.resolve()),
              'extractor_sha256': digest(__file__), 'charters': charters}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def classify(charters, locations, countries, population):
    by_id = {str(l['id']): l for l in locations.values()}
    tags = {c['source_id']: t for t, c in countries.items() if c.get('source_id')}
    results = []
    for charter in charters:
        row = dict(charter)
        loc = by_id[charter['target_location_id']]
        tag = tags.get(charter['source_country'])
        counts = population.get(loc['name'], {})
        total = sum(counts.values())
        culture = countries[tag]['source_culture'] if tag else None
        settlers = counts.get(culture, 0)
        reason = ('source_already_owned' if str(loc['owner']) != '0' else
                  'colonizer_not_represented' if not tag else
                  'no_population' if not total else
                  'settler_majority_active_charter' if settlers * 2 > total else
                  'native_or_tied_majority_retain_native')
        row.update(location=loc['name'], target_owner=tag, settler_culture=culture,
                   total_centipersons=total, settler_centipersons=settlers,
                   classification=reason)
        results.append(row)
    return results


def plan(owners, countries, classifications, province_rows, island_policy=None, edges=(), culture_map=None):
    settled = defaultdict(set)
    for r in classifications:
        if r['classification'] == 'settler_majority_active_charter':
            settled[r['location']].add(r['target_owner'])
    population = defaultdict(Counter)
    source_owners = defaultdict(set)
    source_cultures = defaultdict(Counter)
    for r in province_rows:
        if int(r['centipersons']) > 0:
            population[r['target_province']][r['source_location']] += int(r['centipersons'])
            source_owners[r['target_province']].add(str(r['source_owner']))
            source_cultures[r['target_province']][r['source_culture']] += int(r['centipersons'])
    flat = {p: t for ps in owners.values() for p, t in ps.items()}
    generated = {t for t, c in countries.items() if c.get('generated_uncolonized')}
    aliases, unresolved = {}, []
    # Retire a generated settler microstate only when every resident location
    # is independently qualified and has the same unique charter country.
    for tag in sorted(generated):
        names = {n for p, t in flat.items() if t == tag for n in population[p]}
        if not names or not any(n in settled for n in names):
            continue
        candidates = set.union(*(settled.get(n, set()) for n in names))
        if len(candidates) == 1 and all(settled.get(n) == candidates for n in names):
            aliases[tag] = next(iter(candidates))
        else:
            unresolved.append({'tag': tag, 'locations': sorted(names),
                               'reason': 'mixed_settled_and_native_or_competing_charters'})
    changes = [{'state': s, 'province': p, 'from': t, 'to': aliases[t],
                'reason': 'active_charter_settler_majority_settlement'}
               for s, ps in owners.items() for p, t in ps.items() if t in aliases]
    islands = []
    for r in (island_policy or {}).get('islands', []):
        s, p = r['state'], r['province']
        t = flat[r['anchor_province']] if r.get('anchor_province') else r['to']
        if owners[s][p] != r['from'] or t not in countries:
            raise ValueError('Reviewed island baseline changed: ' + p)
        if population[p] or countries[t].get('culture') != r['target_culture']:
            raise ValueError('Reviewed empty-island identity/evidence changed: ' + p)
        change = dict(r, to=t, reason='user_reviewed_empty_island_attachment')
        changes.append(change)
        islands.append(change)
    # A corrected geographic review may remove the spurious source-owned
    # residents that previously blocked native allocation. Reclaim only an
    # explicitly reviewed candidate, with fresh unowned population evidence
    # and a unique adjacent generated country of its actual primary culture.
    for r in (island_policy or {}).get('native_rechecks', []):
        s, p = r['state'], r['province']
        if source_owners[p] != {'0'} or not source_cultures[p]:
            raise ValueError('Native recheck is not exclusively source-unowned: ' + p)
        primary = min(source_cultures[p], key=lambda c: (-source_cultures[p][c], c))
        culture = (culture_map or {}).get(primary)
        if owners[s][p] in generated and countries[owners[s][p]]['culture'] == culture:
            continue  # Fresh builds can already allocate the corrected native population.
        if owners[s][p] != r['from']:
            raise ValueError('Native recheck ownership baseline changed: ' + p)
        neighbors = {b if a == p else a for a, b in edges if p in (a, b)}
        candidates = {flat[q] for q in neighbors if q in flat and flat[q] in generated and countries[flat[q]]['culture'] == culture}
        if len(candidates) != 1:
            raise ValueError('Native recheck has no unique same-culture neighbor: ' + p)
        changes.append(dict(r, to=next(iter(candidates)), reason='corrected_geography_source_native_majority', source_culture=primary))
    assert len({r['province'] for r in changes}) == len(changes)
    return {'schema': 1, 'classifications': classifications, 'changes': changes,
            'country_aliases': aliases, 'reviewed_islands': islands,
            'unresolved': unresolved,
            'representation': 'Partial colonial settlements only; source owner remains unowned in immutable evidence. No whole-charter annexation.'}


def apply(world, report):
    from m3_terrain_finalization import apply as apply_changes
    apply_changes(world, report)


def prepare(world, population_source, stage, policy_path=None, culture_path=None):
    from m3_uncolonized import population_evidence
    from package_m4_population_test import rows
    source_sha = world.profile['source_sha256']
    evidence = extract_charters(world.audit['source'], source_sha,
                               Path(__file__).resolve().parents[1] / '.local/m3/cache' / (source_sha + '-charters.json'))
    pops, inputs = population_evidence(population_source, source_sha)
    cultures = {n: Counter() for n in pops}
    for n, groups in pops.items():
        for (culture, religion), amount in groups.items():
            cultures[n][culture] += amount
    classified = classify(evidence['charters'], world.locations, world.countries, cultures)
    policy = {}
    if policy_path and Path(policy_path).exists():
        loaded = json.loads(Path(policy_path).read_text(encoding='utf-8'))
        if loaded['source_sha256'] == source_sha:
            if loaded['mapping_sha256'] != world.mapping_sha256:
                raise ValueError('Reviewed island mapping changed')
            policy = loaded
            inputs[str(Path(policy_path).resolve())] = digest(policy_path)
    if stage:
        source_rows = list(rows(Path(stage) / 'province_population_draft.csv'))
        inputs[str((Path(stage) / 'province_population_draft.csv').resolve())] = digest(Path(stage) / 'province_population_draft.csv')
    else:
        # Without reviewed geography, keep the ambiguity visible; do not use
        # inferred province ownership as colonial evidence.
        raise ValueError('Colonial frontier requires reviewed province population geography')
    for r in source_rows:
        correction = policy.get('population_corrections', {}).get(r['source_location'])
        if correction:
            # This source location is moved as a whole, preserving each pop ID
            # and exact centiperson count; staging independently redoes the split.
            r['target_province'] = correction['province']
    from m3_uncolonized import province_land_edges, read_crosswalk
    culture_path = Path(culture_path) if culture_path else Path(stage).parent/'demographics/resident_culture_crosswalk.csv'
    culture_map = read_crosswalk(culture_path, 'source_culture', 'target_culture')
    inputs[str(culture_path.resolve())] = digest(culture_path)
    report = plan(world.owners, world.countries, classified, source_rows, policy,
                  province_land_edges(world, Path(__file__).resolve().parents[1]/'.local/m3/cache/tribal_land_edges.json'), culture_map)
    report['population_corrections'] = policy.get('population_corrections', {})
    report.update(source_sha256=source_sha, input_sha256={**inputs, str(Path(__file__).resolve()): digest(__file__),
                   str(Path(world.audit['source']).resolve()): source_sha}, evidence=evidence)
    apply(world, report)
    world.frontier_finalization = report
    return report


def reallocate_original(original, old_rows, owners, cultures, religions, migrants, corrections):
    """Reallocate the immutable integer ledger, including cross-state corrections.

Split each old integer group by exact source centiperson evidence. This retains
all original persons, including template exceptions, and never rescales a
previously calibrated population. Only documented relocation changes a state.
"""
    from economy_model import apportioned
    weights = defaultdict(Counter)
    for r in old_rows:
        n = int(r['centipersons'])
        if not n:
            continue
        s, p = r['target_state'], r['target_province']
        old_c = migrants.get((r['source_culture'], s), cultures[r['source_culture']])
        faith = religions[r['source_religion']]
        old_key = (s, r['target_owner'], old_c, faith)
        correction = corrections.get(r['source_location'])
        if correction:
            s, p = correction['state'], correction['province']
        c = migrants.get((r['source_culture'], s), cultures[r['source_culture']])
        weights[old_key][s, owners[s][p], c, faith] += n
    result = Counter()
    if set(weights) - set(original):
        # Centiperson-positive groups can round to zero; a missing original
        # integer group is therefore legitimate and contributes zero persons.
        pass
    for key, n in original.items():
        if key in weights:
            result.update(apportioned(weights[key], n))
        else:
            if key[1] not in owners[key[0]].values():
                raise ValueError('Unaccounted original group lost its owner: ' + str(key))
            result[key] += n
    assert sum(result.values()) == sum(original.values())
    return {k: n for k, n in result.items() if n}
