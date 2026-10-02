"""Read-only game discovery and immutable local sample capture for M0.

Run with Python 3.11+. Private paths, game data and saves stay under .local/.
This is an inventory, not a converter or a complete Paradox script parser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def field(text: str, key: str):
    match = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*=\s*(?:"([^"\r\n]*)"|([^\s{}]+))', text)
    return (match[1] if match[1] is not None else match[2]) if match else None


def block(text: str, key: str):
    match = re.search(r'(?m)^\s*' + re.escape(key) + r'\s*=\s*\{', text)
    if not match:
        return None
    depth, quoted, escaped, comment = 1, False, False, False
    start = match.end()
    for i in range(start, len(text)):
        c = text[i]
        if comment:
            comment = c != '\n'
        elif quoted:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '#':
            comment = True
        elif c == '"':
            quoted = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i]
    return None


def describe_save(path: Path):
    with path.open('rb') as stream:
        prefix = stream.read(2 * 1024 * 1024)
    result = {'path': str(path), 'bytes': path.stat().st_size, 'header': prefix[:32].decode('ascii', errors='replace')}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            result['entries'] = [{'name': i.filename, 'size': i.file_size, 'compression': i.compress_type} for i in archive.infolist()]
            if 'meta' in archive.namelist():
                if archive.getinfo('meta').file_size > 16 * 1024 * 1024:
                    result['metadata_status'] = 'over_size_limit'
                    return result
                prefix = archive.read('meta')
    text = prefix.decode('utf-8', errors='replace')
    meta = block(text, 'metadata') or block(text, 'meta_data')
    if meta is not None:
        result['metadata_status'] = 'text_metadata'
        result['metadata'] = {k: field(meta, k) for k in ['date', 'version', 'save_label', 'player_country_name', 'checksum']}
        for k in ['enabled_dlcs', 'mods', 'enabled_mods', 'latest_mods_used', 'history_mods_used']:
            value = block(meta, k)
            result['metadata'][k] = value.strip() if value is not None else None
    else:
        # Only a hint, not a semantic binary parser. Never use this as a baseline verdict.
        result['metadata_status'] = 'binary_or_unrecognized'
        result['version_string_hints'] = sorted(set(re.findall(rb'(?<![0-9])1\.[0-9]{1,2}\.[0-9]{1,2}(?![0-9])', prefix)))
        result['version_string_hints'] = [x.decode('ascii') for x in result['version_string_hints']]
    return result


def capture(path: Path, dest_dir: Path):
    before = path.stat()
    source_hash = digest(path)
    dest = dest_dir / (source_hash[:12] + '-' + path.name)
    if not dest.exists():
        shutil.copy2(path, dest)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Source changed during capture: ' + str(path))
    if digest(dest) != source_hash:
        raise RuntimeError('Snapshot hash mismatch: ' + str(dest))
    dest.chmod(stat.S_IREAD)
    return {'source': str(path), 'copy': str(dest), 'sha256': source_hash, 'bytes': before.st_size, 'readonly': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steam-root', type=Path, required=True)
    parser.add_argument('--documents', type=Path, required=True, help='Paradox Interactive documents root')
    parser.add_argument('--main-save', type=Path, required=True)
    args = parser.parse_args()
    out = ROOT / '.local/m0'
    snapshots = out / 'samples'
    snapshots.mkdir(parents=True, exist_ok=True)
    report = {'captured_utc': datetime.now(timezone.utc).isoformat(), 'target': {'eu5': '1.3.11', 'vic3': '1.13.11'}, 'games': {}, 'samples': {}}
    for game, app in [('Europa Universalis V', '3450310'), ('Victoria 3', '529340')]:
        installation = args.steam_root / 'steamapps/common' / game
        docs = args.documents / game
        manifest = args.steam_root / 'steamapps' / f'appmanifest_{app}.acf'
        text = manifest.read_text(encoding='utf-8')
        build = re.search(r'"buildid"\s+"(\d+)"', text)
        entry = {'installation': str(installation), 'documents': str(docs), 'steam_build_id': build[1] if build else None, 'evidence': []}
        evidence = out / 'evidence' / app
        evidence.mkdir(parents=True, exist_ok=True)
        candidates = [manifest, installation / 'launcher/launcher-settings.json', docs / 'playsets.json', docs / 'content_load.json', docs / 'logs/code_revisions.log', docs / 'logs/system.log', docs / 'logs/error.log', docs / 'logs/checksum.log']
        for source in candidates:
            if source.is_file():
                copied = evidence / source.name
                shutil.copy2(source, copied)
                entry['evidence'].append({'source': str(source), 'copy': str(copied), 'sha256': digest(copied)})
        launcher = installation / 'launcher/launcher-settings.json'
        if launcher.is_file():
            entry['launcher_version'] = json.loads(launcher.read_text(encoding='utf-8-sig')).get('rawVersion')
        if (docs / 'playsets.json').is_file():
            entry['active_playsets'] = [p for p in json.loads((docs / 'playsets.json').read_text(encoding='utf-8-sig')).get('playsets', []) if p.get('isActive')]
        if (docs / 'content_load.json').is_file():
            entry['content_load'] = json.loads((docs / 'content_load.json').read_text(encoding='utf-8-sig'))
        if app == '3450310':
            mods = [m for p in entry.get('active_playsets', []) for m in p.get('orderedListMods', []) if m.get('isEnabled')]
        else:
            mods = entry.get('content_load', {}).get('enabledMods', [])
        entry['current_mod_metadata'] = []
        for mod in mods:
            descriptor = Path(mod['path']) / '.metadata/metadata.json'
            if descriptor.is_file():
                copied = evidence / ('mod-' + Path(mod['path']).name + '.json')
                shutil.copy2(descriptor, copied)
                entry['current_mod_metadata'].append({'path': str(descriptor), 'sha256': digest(copied), 'metadata': json.loads(copied.read_text(encoding='utf-8-sig'))})
        pattern = '*.eu5' if app == '3450310' else '*.v3'
        saves = list((docs / 'save games').glob(pattern))
        entry['save_count'] = len(saves)
        entry['save_inventory'] = [{'name': p.name, 'bytes': p.stat().st_size} for p in saves]
        report['games'][app] = entry

    copied = capture(args.main_save, snapshots)
    copied['description'] = describe_save(Path(copied['copy']))
    report['samples']['main_eu5'] = copied
    early = sorted((args.documents / 'Europa Universalis V/save games').glob('SP_GEN_1338_*.eu5'))
    if early:
        sample = capture(early[0], snapshots)
        sample['description'] = describe_save(Path(sample['copy']))
        sample['role'] = 'early_campaign_reference_not_fresh_start'
        report['samples']['early_eu5'] = sample
    v3_candidates = list((args.documents / 'Victoria 3/save games').glob('*1836_01_01.v3'))
    report['vic3_start_candidates'] = [describe_save(p) for p in v3_candidates]
    report['acceptance'] = {
        'main_save_snapshotted': True,
        'fresh_eu5_start': 'missing',
        'vanilla_vic3_1_13_11_start': 'missing',
        'vanilla_runtime_population_economy_baseline': 'missing',
        'note': 'Existing logs are modded-session evidence, not a vanilla baseline. Gameplay checksum remains unverified.'
    }
    # Opening-save verification is a separate, immutable-sample workflow. A
    # later installation inventory must not reset its evidence to "missing".
    opening_manifest = out / 'clean-starts/manifest.json'
    if opening_manifest.is_file():
        opening = json.loads(opening_manifest.read_text(encoding='utf-8'))
        for game in opening['games'].values():
            sample = game['sample']
            sample_path = Path(sample['copy'])
            if not sample_path.is_absolute():
                sample_path = ROOT / sample_path
            if digest(sample_path) != sample['sha256']:
                raise RuntimeError('Opening snapshot changed: ' + str(sample_path))
        report['opening_baseline_manifest'] = str(opening_manifest)
        report['opening_acceptance'] = opening.get('acceptance', {})
        for key in ['fresh_eu5_start', 'vanilla_vic3_1_13_11_start', 'vanilla_runtime_population_economy_baseline']:
            report['acceptance'][key] = 'see_verified_opening_manifest'
        report['acceptance']['note'] = 'Opening evidence is preserved separately; checksum values are user-reported. See opening_acceptance for measurement limits.'
    report['git_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report['rakaly_sha256'] = digest(ROOT / 'EU5ToVic3/Resources/rakaly.dll')
    (out / 'baseline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(out / 'baseline.json'), 'main': copied['description'].get('metadata'), 'samples': len(report['samples'])}, ensure_ascii=True))


if __name__ == '__main__':
    main()
