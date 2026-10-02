"""Cross-check C++ population output against the separate Python/Decimal scan.

Matching population statistics does not clear source-reference errors or prove
game UI equivalence. Both readers explicitly default omitted EU5 size to zero.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path

from collect_m0_baseline import digest
from extract_m0_statistics import eu5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cpp = json.loads(args.report.read_text(encoding='utf-8'))
    py = eu5(args.save.read_text(encoding='utf-8'))
    mismatches = []

    def equal(label, left, right):
        if left != right:
            mismatches.append({'check': label, 'cpp': left, 'python': right})

    equal('population_count', cpp['counts']['populations'], py['checks']['population_database_count'])
    equal('world_population', Decimal(cpp['world_population_persons']), Decimal(py['checks']['world_population_thousands']) * 1000)
    equal('player_population', Decimal(cpp['player']['population_persons']), Decimal(py['population']['persons']))
    equal('player_tag', cpp['player']['tag'], py['country_tag'])
    countries = {str(country['id']): country for country in cpp['countries']}
    expected_totals = {}
    for key, amount in py['country_population_thousands'].items():
        key = '0' if key == '<unowned>' else key
        expected_totals[key] = expected_totals.get(key, Decimal(0)) + Decimal(amount)
    for key in set(countries) | set(expected_totals):
        left = cpp['unowned_population_persons'] if key == '0' else countries.get(key, {}).get('population_persons', '0')
        equal('country:' + key, Decimal(left), expected_totals.get(key, Decimal(0)) * 1000)
    player = countries[py['country_id']]
    for cpp_key, py_key in [('cultures', 'culture'), ('religions', 'religion'), ('classes', 'type')]:
        expected = py['population']['distributions_thousands'][py_key]
        for key in set(player[cpp_key]) | set(expected):
            equal(cpp_key + ':' + key, Decimal(player[cpp_key].get(key, '0')), Decimal(expected.get(key, '0')) * 1000)
    omitted = next((item['pop_ids'] for item in cpp['warnings'] if item['kind'] == 'omitted_size_defaults_to_zero'), [])
    equal('omitted_size_ids', sorted(map(int, omitted)), sorted(map(int, py['checks']['omitted_size_treated_as_zero_ids'])))
    result = {'status': 'matched' if not mismatches else 'mismatch', 'mismatches': mismatches,
              'country_rows_checked': len(set(countries) | set(expected_totals)),
              'player': cpp['player'], 'save_sha256': digest(args.save), 'cpp_report_sha256': digest(args.report),
              'cpp_validation_status': cpp['status'], 'cpp_reference_errors': len(cpp['errors']),
              'cpp_source_building_pop_issues': cpp['checks']['building_pop_reference_errors'],
              'cpp_skipped_buildings': cpp.get('building_selection', {}).get('skipped_count', 0),
              'limitation': 'Independent arithmetic/parser check; no live UI verification; omitted size defaults to zero in both implementations.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'mismatches'}, ensure_ascii=True))
    return 0 if not mismatches else 1


if __name__ == '__main__':
    raise SystemExit(main())
