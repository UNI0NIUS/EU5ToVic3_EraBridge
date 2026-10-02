"""Run the C++ M1 input audit in a fresh private directory with input hashes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

from collect_m0_baseline import digest

ROOT = Path(__file__).resolve().parents[1]


def resolved(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', choices=['main', 'opening'], default='main')
    parser.add_argument('--save', type=Path, help='Override the captured sample; provide its mods explicitly')
    parser.add_argument('--eu5-dir', type=Path)
    parser.add_argument('--mod', type=Path, action='append')
    parser.add_argument('--building-pop-policy', choices=['strict', 'P001'], default='P001',
                        help='Personal default: skip dangling building-pop references using P001; strict preserves raw rejection')
    args = parser.parse_args()
    baseline = json.loads((ROOT / '.local/m0/baseline.json').read_text(encoding='utf-8'))
    installation = args.eu5_dir or Path(baseline['games']['3450310']['installation'])
    if args.save:
        source, mods = args.save.resolve(), args.mod or []
    elif args.sample == 'main':
        source = resolved(baseline['samples']['main_eu5']['copy'])
        mods = args.mod if args.mod is not None else [Path(item['path']).parent.parent for item in baseline['games']['3450310']['current_mod_metadata']]
    else:
        opening = json.loads((ROOT / '.local/m0/clean-starts/manifest.json').read_text(encoding='utf-8'))
        source, mods = resolved(opening['games']['eu5']['sample']['copy']), args.mod or []
    installation = installation.resolve()
    mods = [mod.resolve() for mod in mods]
    executable = ROOT / 'build/Release-Windows/EU5ToVic3/EU5ToVic3Converter.exe'
    run = ROOT / '.local/m1/runs' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + args.sample + '-' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    record = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source': str(source), 'source_sha256': digest(source),
              'executable_sha256': digest(executable), 'rakaly_sha256': digest(executable.parent / 'rakaly.dll'),
              'installation': str(installation), 'game_executable_sha256': digest(installation / 'binaries/eu5.exe'), 'mods': []}
    # Record content, not just workshop version labels; files can change in place.
    for mod in mods:
        files = sorted(path for path in mod.rglob('*') if path.is_file())
        record['mods'].append({'path': str(mod), 'files': [{'path': path.relative_to(mod).as_posix(), 'sha256': digest(path)} for path in files]})
    record['static_files'] = []
    for relative in ['in_game/common/building_types', 'in_game/common/cultures', 'in_game/common/religions', 'in_game/common/pop_types', 'in_game/map_data/named_locations']:
        for path in sorted((installation / 'game' / relative).rglob('*.txt')):
            record['static_files'].append({'path': path.relative_to(installation).as_posix(), 'sha256': digest(path)})
    command = [str(executable), '--audit-eu5', str(source), '--eu5-dir', str(installation), '--report-dir', str(run / 'report'),
               '--building-pop-policy', args.building_pop_policy]
    record['building_pop_policy'] = args.building_pop_policy
    for mod in mods:
        command.extend(['--mod', str(mod)])
    record['command'] = command
    (run / 'inputs.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    with (run / 'audit.log').open('wb') as log:
        result = subprocess.run(command, cwd=run, stdout=log, stderr=subprocess.STDOUT, check=False)
    record['exit_code'] = result.returncode
    record['source_unchanged'] = digest(source) == record['source_sha256']
    if not record['source_unchanged']:
        record['failure'] = 'Source save changed during import; discard this run.'
    (run / 'inputs.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    report = run / 'report/import_report.json'
    summary = {'run': str(run), 'exit_code': result.returncode, 'source_unchanged': record['source_unchanged']}
    if report.exists():
        data = json.loads(report.read_text(encoding='utf-8'))
        summary.update(status=data['status'], player=data['player'], errors=len(data['errors']), report=str(report))
        summary['skipped_buildings'] = data.get('building_selection', {}).get('skipped_count', 0)
    print(json.dumps(summary, ensure_ascii=True))
    return result.returncode if record['source_unchanged'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
