"""Extract auditable opening-save statistics from Rakaly-decoded local files.

This diagnoses the two pinned game versions. It does not implement conversion,
evaluate scripts, infer absent UI values, or parse arbitrary binary saves.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path

from collect_m0_baseline import digest
from pdx_text import Object, root


def database(obj):
    return obj.fields()['database'].fields()


def values(obj):
    result = []
    for key, value in obj.entries():
        if key is not None or isinstance(value, Object):
            raise ValueError('Expected a plain scalar list')
        result.append(value)
    return result


def plain(obj):
    """Preserve duplicates, anonymous entries and sparse-array headers as pairs."""
    if not isinstance(obj, Object):
        return obj
    return [[key, plain(value)] for key, value in obj.entries()]


def trend(obj):
    channels = obj.fields().get('channels')
    if channels is None:
        return None
    channel = channels.fields()['0'].fields()
    samples = values(channel['values'])
    if len(samples) != 1:
        raise ValueError('M0 extractor expects exactly one opening trend sample')
    return {'date': channel['date'], 'value': samples[0]}


def distributions(pop_rows, size_key, labels):
    result = {key: defaultdict(Decimal) for key in labels}
    for pop in pop_rows:
        size = Decimal(pop[size_key])
        for key, names in labels.items():
            raw = pop.get(key, '<missing>')
            result[key][names.get(raw, raw)] += size
    return {key: dict(sorted(data.items(), key=lambda item: -item[1])) for key, data in result.items()}


def eu5(source):
    data = root(source).fields()
    meta = data['metadata'].fields()
    countries = database(data['countries'])
    player = data['played_country'].fields()['country']
    country = countries[player].fields()
    cultures = {key: obj.fields().get('culture_definition', key) for key, obj in database(data['culture_manager']).items() if isinstance(obj, Object)}
    religions = {key: obj.fields().get('definition', key) for key, obj in database(data['religion_manager']).items() if isinstance(obj, Object)}
    pops = {key: obj.fields() for key, obj in database(data['population']).items() if isinstance(obj, Object)}
    omitted_sizes = [key for key, pop in pops.items() if 'size' not in pop]
    for pop in pops.values():
        pop.setdefault('size', '0')  # EU5 omits default zero values; record every occurrence below.
    locations = data['locations'].fields()['locations'].fields()
    used = Counter()
    selected, owned = [], []
    country_totals = defaultdict(Decimal)
    for location_id, obj in locations.items():
        loc = obj.fields()
        pop_data = loc.get('population')
        if pop_data is None:
            continue
        references = pop_data.fields().get('pops')
        if references is None:
            continue
        owner = loc.get('owner', '<unowned>')
        if owner == player:
            owned.append(location_id)
        for pop_id in values(references):
            used[pop_id] += 1
            pop = pops[pop_id]  # Missing references fail instead of silently undercounting.
            country_totals[owner] += Decimal(pop['size'])
            if owner == player:
                selected.append(pop)
    duplicates = [key for key, count in used.items() if count != 1]
    unreferenced = [key for key, pop in pops.items() if key not in used and Decimal(pop.get('size', '0')) != 0]
    if duplicates or unreferenced:
        raise ValueError(f'EU5 population references: duplicates={len(duplicates)}, unreferenced nonzero={len(unreferenced)}')
    total = sum((Decimal(pop['size']) for pop in selected), Decimal(0))
    economy = country['economy'].fields()
    money = country['currency_data'].fields()
    weighted = {key: sum((Decimal(pop['size']) * Decimal(pop.get(key, '0')) for pop in selected), Decimal(0)) / total for key in ['literacy', 'satisfaction']}
    return {
        'date': meta['date'], 'version': meta['version'], 'country_id': player,
        'country_tag': data['countries'].fields()['tags'].fields()[player],
        'country_definition': country['definition'], 'country_name': meta['player_country_name'],
        'dlcs': values(meta['enabled_dlcs']), 'playset': plain(meta['playthrough_playset_info']),
        'game_rules': plain(data['game_rules']),
        'population': {'raw_size_thousands': total, 'persons': total * 1000,
                       'previous_month_cache_thousands': country.get('last_months_population'),
                       'pop_groups': len(selected), 'populated_owned_locations': len(owned),
                       'weighted_pop_literacy_percent': weighted['literacy'],
                       'weighted_pop_satisfaction_fraction': weighted['satisfaction'],
                       'distributions_thousands': distributions(selected, 'size', {'type': {}, 'culture': cultures, 'religion': religions})},
        'economy': {'gold': money['gold'], 'income_raw': economy['income'], 'expense_raw': economy['expense'],
                    'income_minus_expense_raw': Decimal(economy['income']) - Decimal(economy['expense']),
                    'note': 'Saved economy fields; period/UI equivalence not independently verified.'},
        'government': plain(country['government']),
        'checks': {'duplicate_pop_references': len(duplicates), 'unreferenced_nonzero_pops': len(unreferenced),
                   'omitted_size_treated_as_zero_ids': omitted_sizes,
                   'population_database_count': len(pops), 'population_referenced_count': len(used),
                   'world_population_thousands': sum(country_totals.values(), Decimal(0)),
                   'player_owned_locations_match': set(owned) == set(values(country['owned_locations']))},
        'country_population_thousands': dict(country_totals),
        'unit_evidence': 'EU5 game/loading_screen/common/defines/00_defines.txt:1038: 1 unit = 1000 actual pops',
        'notes': ['Country scope is directly owned locations, excluding subjects.',
                  'Weighted pop statistics are computed diagnostics, not a UI screenshot.',
                  'Opaque named tokens remain semantically unresolved even when Rakaly reports no unknown tokens.'],
    }


def vic3(source):
    data = root(source).fields()
    meta = data['meta_data'].fields()
    players = database(data['player_manager'])
    if len(players) != 1:
        raise ValueError('Expected one baseline player')
    player = next(iter(players.values())).fields()['country']
    countries = {key: obj.fields() for key, obj in database(data['country_manager']).items() if isinstance(obj, Object)}
    country = countries[player]
    states = {key: obj.fields() for key, obj in database(data['states']).items() if isinstance(obj, Object)}
    cultures = {key: obj.fields()['type'] for key, obj in database(data['cultures']).items() if isinstance(obj, Object)}
    totals, workforces, dependents = Counter(), Counter(), Counter()
    selected, count = [], 0
    for _, obj in database(data['pops']).items():
        if not isinstance(obj, Object):
            continue
        pop = obj.fields()
        workforce, dependent = int(pop.get('workforce', '0')), int(pop.get('dependents', '0'))
        population = workforce + dependent
        if not population:
            continue
        owner = states[pop['location']]['country']
        totals[owner] += population
        workforces[owner] += workforce
        dependents[owner] += dependent
        count += 1
        if owner == player:
            pop['persons'] = str(population)
            selected.append(pop)
    discrepancies = []
    for key, total in totals.items():
        stats = countries[key]['pop_statistics'].fields()
        cached = sum(int(stats.get('population_' + strata + '_strata', '0')) for strata in ['lower', 'middle', 'upper'])
        if cached != total:
            discrepancies.append({'country': key, 'pop_sum': total, 'strata_sum': cached})
    if discrepancies:
        raise ValueError(f'V3 population cache mismatches: {discrepancies[:10]}')
    stats, budget = country['pop_statistics'].fields(), country['budget'].fields()
    income = sum(map(Decimal, values(budget['weekly_income'])), Decimal(0))
    expense = sum(map(Decimal, values(budget['weekly_expenses'])), Decimal(0))
    laws = []
    for obj in database(data['laws']).values():
        if isinstance(obj, Object):
            fields = obj.fields()
            if fields.get('country') == player and fields.get('active') == 'yes':
                laws.append(fields['law'])
    return {
        'date': data['date'], 'version': meta['version'], 'country_id': player,
        'country_tag': country['definition'], 'country_name': meta['name'],
        'dlcs': values(meta['dlcs']), 'mods_metadata': plain(meta.get('mods')),
        'game_rules': plain(meta['game_rules']),
        'population': {'persons': totals[player], 'workforce': workforces[player], 'dependents': dependents[player],
                       'nonzero_pop_groups': len(selected), 'strata': {key: stats['population_' + key + '_strata'] for key in ['lower', 'middle', 'upper']},
                       'trend': trend(stats['trend_population']),
                       'distributions_persons': distributions(selected, 'persons', {'type': {}, 'culture': cultures, 'religion': {}})},
        'economy': {'gdp_trend': trend(country['gdp']), 'weekly_income_sum': income, 'weekly_expenses_sum': expense,
                    'weekly_array_balance': income - expense, 'saved_balance_trend_current': budget['balance_trend'].fields()['current'],
                    'saved_money': budget['money'], 'weekly_income_raw': values(budget['weekly_income']),
                    'weekly_expenses_raw': values(budget['weekly_expenses']),
                    'price_report_raw': plain(budget.get('current_price_report'))},
        'society': {'literacy_trend': trend(country['literacy']), 'standard_of_living_trend': trend(country['avgsoltrend']),
                    'active_laws': laws, 'government': country['government'], 'state_religion': country['religion'],
                    'primary_cultures': [cultures[key] for key in values(country['cultures'])]},
        'checks': {'country_population_cache_mismatches': discrepancies, 'countries_with_population': len(totals),
                   'world_population_persons': sum(totals.values()), 'nonzero_pop_groups': count,
                   'player_population_matches_trend': Decimal(trend(stats['trend_population'])['value']) == totals[player]},
        'country_population_persons': dict(totals),
        'notes': ['Population is workforce + dependents; subjects remain separate countries.',
                  'Price report retains numeric goods IDs; market shortages have not been inferred from prices.',
                  'Saved trend and weekly-array balance are reported separately; UI projection may differ.'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--eu5', type=Path, required=True)
    parser.add_argument('--vic3', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for game, extractor in [('eu5', eu5), ('vic3', vic3)]:
        path = getattr(args, game)
        report = extractor(path.read_text(encoding='utf-8'))
        report['source'] = {'path': str(path), 'sha256': digest(path)}
        output = args.output_dir / (game + '-statistics.json')
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(json.dumps({'game': game, 'country': report['country_tag'], 'population': report['population']['persons'],
                          'checks': report['checks'], 'output': str(output)}, default=str), flush=True)


if __name__ == '__main__':
    main()
