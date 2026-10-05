"""Prepare a Windows candidate and evidence; never upload or publish a release.

Private generated resources and user data are omitted; reconstruction recipes are included. A successful run means
that preparation finished, not that the candidate is approved for distribution.
"""
import argparse
import base64
import csv
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

VERSION = '0.12.2-beta.3'
PUBLIC_DOCUMENTS = (
    'README.md', 'BUILDING.md', 'ARCHITECTURE.md', 'CONVERSION_RULES.md',
    'README.en.md', 'BUILDING.en.md', 'CONVERTER_WORKBENCH.en.md', 'LOCALIZATION.md', 'LOCALIZATION.en.md',
    'CONVERTER_WORKBENCH.md', 'CONVERTER_IDENTITY_SETTINGS.md',
    'CONVERTER_SOURCE_CORES.md', 'FLAG_GENERATION_RULES.md',
    'LICENSING.md', 'PUBLICATION.md', 'RELEASING.md', 'ACCEPTANCE.md',
    'releases/v0.12.2-beta.1.md', 'releases/v0.12.2-beta.2.md', 'releases/v0.12.2-beta.3.md',
    'ACCEPTANCE.en.md',
    'ARCHITECTURE.en.md',
    'CONVERSION_RULES.en.md',
    'CONVERTER_IDENTITY_SETTINGS.en.md',
    'CONVERTER_SOURCE_CORES.en.md',
    'FLAG_GENERATION_RULES.en.md',
    'LICENSING.en.md',
    'PUBLICATION.en.md',
    'RELEASING.en.md',
    'SUPPORT.en.md',
    'SUPPORT.md',
    'releases/v0.12.2-beta.1.en.md',
    'releases/v0.12.2-beta.2.en.md',
    'releases/v0.12.2-beta.3.en.md',
)
EXCLUDED_PARTS = {'__pycache__', '.git', '.local', 'tests', 'test', 'logs'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.obj', '.pdb', '.lib', '.res', '.eu5', '.v3'}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def copy_tree(source, target):
    """Copy a selected subtree, rejecting links rather than following them."""
    source = Path(source)
    if source.is_symlink():
        raise ValueError('Linked input directory: ' + str(source))
    for item in sorted(source.rglob('*')):
        rel = item.relative_to(source)
        if item.is_symlink():
            raise ValueError('Linked input: ' + str(item))
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if not item.is_file() or item.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        dest = Path(target) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)


def copy_public_docs(root, stage):
    """Allowlist maintained docs; never package local conversation/installation logs."""
    for name in PUBLIC_DOCUMENTS:
        source = Path(root) / 'docs' / name
        target = Path(stage) / 'docs' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def seal(stage, archive, public_preview=False, source_commit=None):
    """Record exact payload bytes and archive only those files plus the manifest."""
    stage = Path(stage)
    paths = sorted(p for p in stage.rglob('*') if p.is_file() and p.name != 'build_manifest.json')
    manifest = {'version': VERSION, 'internal_candidate': not public_preview,
                'channel': 'community_preview' if public_preview else 'internal',
                'files': {p.relative_to(stage).as_posix(): sha256(p) for p in paths}}
    if source_commit:
        manifest['source_commit'] = source_commit
    write_json(stage / 'build_manifest.json', manifest)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for path in paths + [stage / 'build_manifest.json']:
            out.write(path, stage.name + '/' + path.relative_to(stage).as_posix())
    return manifest


def visual_cpp_sources(visual_studio):
    versions = sorted((Path(visual_studio) / 'VC/Redist/MSVC').glob('[0-9]*'),
                      key=lambda p: tuple(int(n) for n in p.name.split('.')))
    if not versions:
        raise ValueError('Installed Visual Studio x64 redistributables not found')
    sources = {p.name.lower(): p for p in (versions[-1] / 'x64').rglob('*.dll')}
    if not {'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'} <= sources.keys():
        raise ValueError('Incomplete Visual Studio x64 redistributables')
    return sources


def stage_visual_cpp(stage, sources):
    # Replace the Python distribution's copies with the installed release redist.
    for path in (stage / 'runtime').rglob('*.dll'):
        if path.name.lower() in sources:
            shutil.copy2(sources[path.name.lower()], path)
    # The importer is a separate process; Python's DLL search path does not apply.
    for name, source in sources.items():
        if source.parent.name.endswith('.CRT'):
            shutil.copy2(source, stage / 'native' / name)


def license_inventory(stage, python_base, microsoft_sources=None):
    """Match runtime binary bytes to cached conda packages, not just filenames.

Package metadata is provenance evidence, not a redistribution approval. Pip may
have replaced files belonging to conda packages, so unmatched files stay unknown.
"""
    owners = {}
    for metadata in sorted((Path(python_base) / 'conda-meta').glob('*.json')):
        data = json.loads(metadata.read_text(encoding='utf-8'))
        cache = Path(data.get('link', {}).get('source', ''))
        for rel in data.get('files', []):
            if Path(rel).suffix.lower() in {'.dll', '.pyd', '.exe'}:
                owners.setdefault(Path(rel).name.lower(), []).append((data, cache, rel))
    wheel_hashes = {}
    wheel_packages = []
    site = stage / 'runtime/Lib/site-packages'
    for info in sorted(site.glob('*.dist-info')):
        if not (info / 'RECORD').is_file() or not (info / 'METADATA').is_file():
            continue
        metadata = Parser().parsestr((info / 'METADATA').read_text(encoding='utf-8'))
        key = metadata['Name'] + '-' + metadata['Version'] + '-wheel-record'
        with (info / 'RECORD').open(encoding='utf-8', newline='') as stream:
            for rel, checksum, size in csv.reader(stream):
                if Path(rel).suffix.lower() not in {'.dll', '.pyd', '.exe'} or not checksum.startswith('sha256='):
                    continue
                encoded = checksum.partition('=')[2]
                digest = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).hex()
                wheel_hashes.setdefault((Path(rel).name.lower(), digest), []).append(key)
        wheel_packages.append({'package': key, 'declared_license': metadata.get('License-Expression') or metadata.get('License'),
                               'license_files': sorted(p.relative_to(stage).as_posix() for p in info.rglob('*')
                                                       if p.is_file() and any('license' in part.lower() or 'copying' in part.lower() for part in p.relative_to(info).parts)),
                               'record': (info / 'RECORD').relative_to(stage).as_posix(),
                               'redistribution_review': 'pending'})
    binaries = []
    matched_packages = {}
    for path in sorted((stage / 'runtime').rglob('*')):
        if path.suffix.lower() not in {'.dll', '.pyd', '.exe'}:
            continue
        digest = sha256(path)
        matches = list(wheel_hashes.get((path.name.lower(), digest), []))
        for data, cache, rel in owners.get(path.name.lower(), []):
            cached = cache / rel
            if cached.is_file() and sha256(cached) == digest:
                key = data['name'] + '-' + data['version'] + '-' + data.get('build', '')
                matches.append(key)
                matched_packages[key] = (data, cache)
        source = (microsoft_sources or {}).get(path.name.lower())
        if source and sha256(source) == digest:
            matches.append('microsoft-vc143-official-redist')
        binaries.append({'file': path.relative_to(stage).as_posix(), 'sha256': digest,
                         'matched_packages': matches})
    packages = wheel_packages
    for key, (data, cache) in sorted(matched_packages.items()):
        source = cache / 'info/licenses'
        dest = stage / 'licenses/runtime' / key
        if source.is_dir():
            copy_tree(source, dest)
        packages.append({'package': key, 'declared_license': data.get('license'),
                         'license_files': sorted(p.relative_to(stage).as_posix() for p in dest.rglob('*') if p.is_file()),
                         'redistribution_review': 'pending'})
    if microsoft_sources:
        packages.append({'package': 'microsoft-vc143-official-redist',
                         'declared_license': 'Microsoft Visual Studio Community 2022',
                         'source': 'Visual Studio 2022 VC/Redist/MSVC/<version>/x64',
                         'license_files': ['licenses/microsoft-community-2022/LICENSE.docx',
                                           'licenses/microsoft-community-2022/LICENSE.txt'],
                         'redistribution_review': 'See docs/LICENSING.md'})
    return {'binaries': binaries, 'packages': packages,
            'unmatched_binaries': [p['file'] for p in binaries if not p['matched_packages']],
            'note': 'Exact cached-file or wheel RECORD SHA-256 matches only. No license approval is inferred.'}


def prepare(root, app, out, python_base, make_archive=True, public_preview=False):
    root, app, out = (Path(p).resolve() for p in (root, app, out))
    if not out.is_relative_to(root / 'build') or out == root / 'build':
        raise ValueError('Output must be a new subdirectory of the workspace build directory')
    if out == app or out.is_relative_to(app) or app.is_relative_to(out):
        raise ValueError('Output and application input must be separate directories')
    required = ['EU5Converter.exe', 'runtime/python.exe', 'native/EU5ToVic3Converter.exe', 'native/rakaly.dll']
    for rel in required:
        if not (app / rel).is_file():
            raise ValueError('Missing application input: ' + rel)
    if out.exists():
        raise ValueError('Output already exists; choose a new directory')
    out.mkdir(parents=True)
    stage = out / ('EraBridge-' + VERSION + '-windows-x64' + ('' if public_preview else '-INTERNAL'))
    stage.mkdir()
    for name in ('runtime', 'native'):
        copy_tree(app / name, stage / name)
    microsoft_sources = None
    if public_preview:
        microsoft_sources = visual_cpp_sources(root / '.tools/VisualStudio2022')
        stage_visual_cpp(stage, microsoft_sources)
    shutil.copy2(app / 'EU5Converter.exe', stage / 'EU5Converter.exe')
    shutil.copy2(root / 'tools/Test-PortableRelease.ps1', stage / 'Test-PortableRelease.ps1')
    (stage / 'tools').mkdir()
    for path in sorted((root / 'tools').glob('*.py')):
        if not path.name.startswith('test_') and path.name not in {'prepare_release.py', 'package_converter_app.py'}:
            shutil.copy2(path, stage / 'tools' / path.name)
    copy_tree(root / 'tools/converter_ui', stage / 'tools/converter_ui')
    copy_tree(root / 'tools/converter_locales', stage / 'tools/converter_locales')
    copy_tree(root / 'config', stage / 'config')
    copy_tree(root / 'EU5ToVic3/Data_Files', stage / 'EU5ToVic3/Data_Files')
    copy_public_docs(root, stage)
    for name in ('NamingConvention.txt', 'NamingConvention.zh-CN.txt'):
        shutil.copy2(root / 'EU5ToVic3' / name, stage / 'EU5ToVic3' / name)
    shutil.copy2(root / 'LICENSE', stage / 'LICENSE')
    (stage / 'licenses').mkdir(exist_ok=True)
    shutil.copy2(root / 'licenses/README.md', stage / 'licenses/README.md')
    shutil.copy2(root / 'licenses/README.en.md', stage / 'licenses/README.en.md')
    shutil.copy2(root / 'licenses/THIRD_PARTY_NOTICES.md', stage / 'licenses/THIRD_PARTY_NOTICES.md')
    shutil.copy2(root / 'licenses/THIRD_PARTY_NOTICES.en.md', stage / 'licenses/THIRD_PARTY_NOTICES.en.md')
    shutil.copy2(root / 'licenses/END_USER_TERMS.txt', stage / 'licenses/END_USER_TERMS.txt')
    copy_tree(root / 'licenses/microsoft-community-2022', stage / 'licenses/microsoft-community-2022')
    for source, name in [(root / 'commonItems/LICENSE', 'commonItems-LICENSE'),
                         (root / 'commonItems/external/json/LICENSE.MIT', 'nlohmann-json-LICENSE'),
                         (root / 'commonItems/external/zip/UNLICENSE', 'zip-UNLICENSE')]:
        if source.is_file():
            (stage / 'licenses').mkdir(exist_ok=True)
            shutil.copy2(source, stage / 'licenses' / name)
    lock = json.loads((root / 'tools/toolchain-lock.json').read_text(encoding='utf-8'))
    rakaly_hashes = {entry['sha256'] for entry in lock['files']
                     if entry['path'].startswith('.tools/rakaly-') and entry['path'].endswith('/rakaly.dll')}
    rakaly_version = lock['rakaly'] if sha256(stage / 'native/rakaly.dll') in rakaly_hashes else None
    rakaly_license = root / 'licenses' / ('rakaly-' + str(rakaly_version)) / 'LICENSE.txt'
    if rakaly_version and rakaly_license.is_file():
        target = stage / 'licenses' / ('rakaly-' + rakaly_version)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rakaly_license, target / 'LICENSE.txt')
        if (rakaly_license.parent / 'dependencies').is_dir():
            copy_tree(rakaly_license.parent / 'dependencies', target / 'dependencies')
    write_json(stage / 'data/defaults.json', {'candidate_paths': [], 'game': '', 'eu5': ''})
    excluded = []
    rules = app / 'data/rules'
    if rules.is_dir():
        excluded = [{'file': p.relative_to(app).as_posix(), 'sha256': sha256(p)}
                    for p in sorted(rules.rglob('*')) if p.is_file()]
    inventory = license_inventory(stage, python_base, microsoft_sources)
    if microsoft_sources:
        inventory['native_runtime_binaries'] = [
            {'file': p.relative_to(stage).as_posix(), 'sha256': sha256(p),
             'matched_packages': ['microsoft-vc143-official-redist']}
            for p in sorted((stage / 'native').glob('*.dll'))
            if p.name.lower() in microsoft_sources and sha256(p) == sha256(microsoft_sources[p.name.lower()])]
    if public_preview and (not rakaly_version or inventory['unmatched_binaries']):
        raise ValueError('Public preview requires a known Rakaly version and matched runtime provenance')
    write_json(stage / 'licenses/runtime-inventory.json', inventory)
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True, check=True).stdout.strip())
    limitations = [
        '完整规则及基准存档由使用者本机生成；独立 Windows 环境的初始化与端到端验收仍待执行。',
        '游戏资源采用本机引用重建，原始素材不随包分发；当前规则限定已验证地图和资源版本。',
        '尚未完成无开发环境机器上的安装、端到端转换、导出和游戏内验收。',
        '开发机首周引擎检查仍发现资源建筑容量和原版脚本报错，游戏内验收尚未整体通过。',
    ]
    report = {'version': VERSION, 'ready_for_publication': False, 'source_commit': revision,
              'channel': 'community_preview' if public_preview else 'internal',
              'source_worktree_dirty': dirty, 'rakaly_version_matching_lock': rakaly_version, 'input_binaries': {rel: sha256(app / rel) for rel in required},
              'excluded_rules': excluded, 'unmatched_runtime_binaries': inventory['unmatched_binaries'],
              'blockers': ['此准备报告尚未附上最终包的完整性与运行验收结果。'],
              'known_limitations': limitations, 'checks': {'empty_user_defaults': True, 'user_data_copied': False,
              'rules_copied': False, 'relocated_runtime_smoke_test': 'not_run', 'clean_machine_test': 'not_run'}}
    write_json(out / 'release-readiness.json', report)
    (stage / 'README.txt').write_text(
        'EraBridge ' + VERSION + (' — 社区测试版\n\n' if public_preview else ' — 内部发布候选\n\n') +
        ('本版供社区测试，已知问题包括资源建筑容量和部分游戏脚本报错。长期战役与独立 Windows 环境尚未验证。\n' if public_preview else '本目录用于检查发布结构与运行环境，尚未通过公开发行验收。\n') +
        '双击 EU5Converter.exe 启动。保留整个目录，不要单独复制 EXE。首次启动请阅读并接受第三方组件条款。\n'
        '首次使用点击“准备转换规则”，选择两款游戏安装及自己的 V3 原版 1836.1.1 开局存档。\n'
        '游戏素材与基准存档仅在本机读取或生成，不随软件分发。独立验收用 Test-PortableRelease.ps1。\n'
        '发布流程见 docs/RELEASING.md；依赖清单见 licenses/runtime-inventory.json。\n\n'
        'English: run EU5Converter.exe and choose English under 语言 / Language. Keep the entire folder together.\n'
        'Read the bundled third-party terms on first launch. Use Prepare rules with your installed games and vanilla V3 starting save.\n'
        'Choose Game display language on import/export and set the same language in Victoria 3.\n'
        'See docs/CONVERTER_WORKBENCH.en.md and docs/LOCALIZATION.en.md.\n', encoding='utf-8')
    if make_archive:
        archive = out / (stage.name + '.zip')
        manifest = seal(stage, archive, public_preview, revision)
        (out / 'SHA256SUMS.txt').write_text(sha256(archive) + '  ' + archive.name + '\n', encoding='ascii')
        report['archive'] = {'file': archive.name, 'sha256': sha256(archive), 'payload_files': len(manifest['files'])}
        write_json(out / 'release-readiness.json', report)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--python-base', type=Path, default=Path(sys.base_prefix))
    parser.add_argument('--no-archive', action='store_true')
    parser.add_argument('--public-preview', action='store_true', help='Prepare community preview packaging; does not publish or certify testing')
    args = parser.parse_args()
    print(prepare(args.root, args.app, args.out, args.python_base, not args.no_archive, args.public_preview))
