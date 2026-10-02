"""Verify a portable candidate and optionally run a player's end-to-end sample."""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import io
import json
import platform
from pathlib import Path
import sys
import traceback


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_payload(root):
    manifest = json.loads((root / 'build_manifest.json').read_text(encoding='utf-8-sig'))
    expected = manifest['files']
    for name, digest in expected.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or sha256(path) != digest:
            raise ValueError('发行文件缺失或摘要不符：' + name)
    extras = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts[0] == 'data' or '__pycache__' in rel.parts or rel.as_posix() == 'build_manifest.json':
            continue
        if rel.as_posix() not in expected:
            extras.append(rel.as_posix())
    if extras:
        raise ValueError('发行目录含额外文件：' + ', '.join(extras[:10]))
    return {'files_checked': len(expected), 'manifest_sha256': sha256(root / 'build_manifest.json'), 'version': manifest['version']}


def runtime_smoke(root, workspace):
    import numpy as np
    import PIL
    from PIL import Image
    import tkinter as tk
    from converter_desktop import Workbench
    if not Path(sys.executable).resolve().is_relative_to(root):
        raise ValueError('请使用发行包附带的 runtime/python.exe 运行验收。')
    if any(not Path(p).resolve().is_relative_to(root) for p in sys.path if p):
        raise ValueError('Python 搜索路径包含发行目录外部路径。')
    assert np.linalg.det(np.eye(2)) == 1
    image = io.BytesIO(); Image.new('RGB', (16, 16)).save(image, format='PNG')
    with Image.open(io.BytesIO(image.getvalue())) as decoded:
        assert decoded.size == (16, 16)
    library = ctypes.CDLL(str(root / 'native/rakaly.dll'))
    assert library.rakaly_vic3_file and library.rakaly_eu5_file
    window = tk.Tk(); window.withdraw()
    try:
        ui = Workbench(window, workspace, autoload=False)
        window.update_idletasks()
        ui.initialize_dialog()
        window.update_idletasks()
        dialogs = [w for w in window.winfo_children() if isinstance(w, tk.Toplevel)]
        assert dialogs
        for dialog in dialogs:
            dialog.destroy()
        ui.close()
    finally:
        try: window.destroy()
        except tk.TclError: pass
    return {'python': platform.python_version(), 'numpy': np.__version__, 'pillow': PIL.__version__,
            'tk': tk.TkVersion, 'isolated_python_paths': True, 'native_library_loaded': True,
            'desktop_and_initialization_dialog': 'passed'}


def check_project(package, game, workspace):
    from converter_controller import App
    from converter_export import export_candidate
    from converter_world import Candidate
    app = App(workspace)
    loaded = app.load_project({'package': str(package), 'game': str(game), 'name': 'Release acceptance'})
    snapshot = app.preview
    identity = app.project['id']
    app.load_project({'id': identity})
    if app.preview != snapshot:
        raise ValueError('项目保存后重开与原预览不一致。')
    exported = workspace / 'exports/acceptance'
    export_candidate(app.world, app.project, exported)
    reloaded = Candidate(exported, game, workspace / 'readback-cache')
    preview = reloaded.preview(app.project['settings'], [])
    # File formatting and report provenance may differ; game-state rows must not.
    if snapshot['rows'] != preview['rows']:
        raise ValueError('导出后重新载入的地区数据与原预览不一致。')
    return {'project_save_reopen': 'passed', 'export_readback': 'passed', 'regions': loaded['regions']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--environment', default='not independently classified')
    for name in ('eu5', 'game', 'baseline', 'save', 'package'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out.exists():
        parser.error('验收目录已存在，请使用新目录。')
    if any((args.eu5, args.baseline, args.save)) and not all((args.eu5, args.game, args.baseline, args.save)):
        parser.error('完整转换验收需同时提供 --eu5 --game --baseline --save。')
    if args.package and not args.game:
        parser.error('--package 需同时提供 --game。')
    if args.package and args.save:
        parser.error('--package 与 --save 请选择一种验收方式。')
    if out == root or (out.is_relative_to(root) and not out.is_relative_to(root / 'data')):
        parser.error('包内验收目录必须放在 data/ 下，也可以选发行目录外的新目录。')
    out.mkdir(parents=True)
    report = {'status': 'running', 'time_utc': datetime.now(timezone.utc).isoformat(),
              'environment_description': args.environment, 'windows': platform.version(),
              'architecture': platform.machine(), 'clean_machine_verified': False,
              'game_runtime_verified': False}
    try:
        report['integrity'] = verify_payload(root)
        report['smoke'] = runtime_smoke(root, out / 'workspace')
        package = args.package
        if args.save:
            from initialize_converter import initialize
            from converter_pipeline import run_conversion
            initialized = initialize(root, out / 'workspace', args.eu5, args.game, args.baseline)
            report['initialization'] = initialized['validation']
            args.game = Path(initialized['game'])
            result = run_conversion(root, out / 'workspace', {'save': str(args.save.resolve()),
                                    'eu5': initialized['eu5'], 'game': initialized['game'],
                                    'rules': initialized['rules'], 'mods': []})
            report['conversion'] = 'passed'
            package = Path(result['directory'])
        if package:
            report['project'] = check_project(package, args.game, out / 'workspace')
        report['status'] = 'passed'
        report['scope'] = ('static_conversion_and_export' if args.save else
                           'existing_project_and_export' if package else 'integrity_and_runtime_smoke_only')
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        (out / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
    (out / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
