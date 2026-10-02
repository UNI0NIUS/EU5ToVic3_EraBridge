"""Smoke-test the bundled Rakaly DLL on a real save without running conversion."""
import argparse
import ctypes as c
import json
from pathlib import Path
from collect_m0_baseline import block

ROOT = Path(__file__).resolve().parents[1]


def inspect(path: Path, game: str, library: Path, full_output: Path | None = None):
    dll = c.CDLL(str(library.resolve()))
    signatures = {
        'rakaly_' + game + '_file': (c.c_void_p, [c.c_char_p, c.c_size_t]),
        'rakaly_file_error': (c.c_void_p, [c.c_void_p]),
        'rakaly_file_value': (c.c_void_p, [c.c_void_p]),
        'rakaly_file_meta': (c.c_void_p, [c.c_void_p]),
        'rakaly_file_meta_melt': (c.c_void_p, [c.c_void_p]),
        'rakaly_file_melt': (c.c_void_p, [c.c_void_p]),
        'rakaly_file_is_binary': (c.c_bool, [c.c_void_p]),
        'rakaly_melt_error': (c.c_void_p, [c.c_void_p]),
        'rakaly_melt_value': (c.c_void_p, [c.c_void_p]),
        'rakaly_melt_data_length': (c.c_size_t, [c.c_void_p]),
        'rakaly_melt_is_verbatim': (c.c_bool, [c.c_void_p]),
        'rakaly_melt_binary_unknown_tokens': (c.c_bool, [c.c_void_p]),
        'rakaly_melt_write_data': (c.c_size_t, [c.c_void_p, c.c_void_p, c.c_size_t]),
        'rakaly_error_length': (c.c_int, [c.c_void_p]),
        'rakaly_error_write_data': (c.c_int, [c.c_void_p, c.c_void_p, c.c_int]),
        'rakaly_free_error': (None, [c.c_void_p]),
        'rakaly_free_file': (None, [c.c_void_p]),
        'rakaly_free_melt': (None, [c.c_void_p]),
    }
    for name, (returns, args) in signatures.items():
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = returns, args

    def check(error):
        if error:
            try:
                size = dll.rakaly_error_length(error)
                if not 0 <= size <= 1024 * 1024:
                    raise RuntimeError('Invalid Rakaly error size')
                buffer = c.create_string_buffer(size + 1)
                written = dll.rakaly_error_write_data(error, buffer, size)
                if written < 0:
                    raise RuntimeError('Rakaly error-message extraction failed')
                raise RuntimeError(buffer.raw[:written].decode('utf-8', errors='replace'))
            finally:
                dll.rakaly_free_error(error)

    data = path.read_bytes()  # The FFI borrows this buffer until the file is freed.
    result = getattr(dll, 'rakaly_' + game + '_file')(data, len(data))
    if not result:
        raise RuntimeError('Rakaly returned null file result')
    check(dll.rakaly_file_error(result))
    file = dll.rakaly_file_value(result)
    if not file:
        raise RuntimeError('Rakaly returned null file')
    try:
        output = {'game': game, 'save': str(path), 'bytes': len(data), 'binary': bool(dll.rakaly_file_is_binary(file))}
        if full_output is not None:
            if full_output.resolve() == path.resolve():
                raise ValueError('Decoded output must not overwrite the source save')
            full_result = dll.rakaly_file_melt(file)
            if not full_result:
                raise RuntimeError('Rakaly returned null full-save result')
            check(dll.rakaly_melt_error(full_result))
            full = dll.rakaly_melt_value(full_result)
            if not full:
                raise RuntimeError('Rakaly returned null full-save buffer')
            try:
                unknown = bool(dll.rakaly_melt_binary_unknown_tokens(full))
                full_output.parent.mkdir(parents=True, exist_ok=True)
                if dll.rakaly_melt_is_verbatim(full):
                    full_output.write_bytes(data)
                    size = len(data)
                else:
                    size = dll.rakaly_melt_data_length(full)
                    if size > 2 * 1024**3:
                        raise RuntimeError('Decoded save exceeds 2 GiB safety limit')
                    buffer = c.create_string_buffer(size)
                    if dll.rakaly_melt_write_data(full, buffer, size) != size:
                        raise RuntimeError('Incomplete full-save copy')
                    with full_output.open('wb') as stream:
                        stream.write(memoryview(buffer).cast('B'))
                    del buffer
                output['full_save'] = {'path': str(full_output), 'bytes': size, 'unknown_tokens': unknown}
            finally:
                dll.rakaly_free_melt(full)
        meta = dll.rakaly_file_meta(file)
        if not meta:
            output['metadata_status'] = 'not_exposed_by_dll'
            return output
        melted_result = dll.rakaly_file_meta_melt(meta)
        if not melted_result:
            raise RuntimeError('Rakaly returned null metadata result')
        check(dll.rakaly_melt_error(melted_result))
        melted = dll.rakaly_melt_value(melted_result)
        if not melted:
            raise RuntimeError('Rakaly returned null metadata')
        try:
            if dll.rakaly_melt_is_verbatim(melted):
                # Verbatim means no output buffer: use the still-alive source text.
                source = data[:16 * 1024 * 1024].decode('utf-8', errors='replace')
                content = block(source, 'metadata') or block(source, 'meta_data')
                if content is None:
                    raise RuntimeError('Verbatim metadata block not found within 16 MiB')
                output.update(metadata_status='decoded', metadata_source='verbatim_source', unknown_tokens=False, metadata='metadata={' + content + '}')
                return output
            size = dll.rakaly_melt_data_length(melted)
            if size > 16 * 1024 * 1024:
                raise RuntimeError('Metadata exceeds 16 MiB safety limit')
            buffer = c.create_string_buffer(size + 1)
            written = dll.rakaly_melt_write_data(melted, buffer, size)
            if written != size:
                raise RuntimeError('Incomplete metadata copy')
            output.update(metadata_status='decoded', metadata_source='melted_buffer', unknown_tokens=bool(dll.rakaly_melt_binary_unknown_tokens(melted)), metadata=buffer.raw[:size].decode('utf-8', errors='replace'))
            return output
        finally:
            dll.rakaly_free_melt(melted)
    finally:
        dll.rakaly_free_file(file)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', choices=['eu5', 'vic3'], required=True)
    ap.add_argument('--save', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--dll', type=Path, default=ROOT / 'EU5ToVic3/Resources/rakaly.dll')
    ap.add_argument('--full-output', type=Path, help='Optionally decode the complete save to a separate local file')
    args = ap.parse_args()
    try:
        report = inspect(args.save, args.game, args.dll, args.full_output)
        report['status'] = 'unknown_tokens' if report.get('unknown_tokens') or report.get('full_save', {}).get('unknown_tokens') else ('ok' if report.get('metadata_status') == 'decoded' else 'missing_metadata')
    except Exception as error:
        report = {'status': 'error', 'game': args.game, 'save': str(args.save), 'error': str(error)}
    report['dll'] = str(args.dll.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'metadata'}, ensure_ascii=True))
    raise SystemExit(0 if report['status'] == 'ok' else 1)
