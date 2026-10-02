"""Compile imported religion UI textures to V3's native 256-pixel canvas.

This is an asset-format conversion: preserve the source artwork/aspect ratio,
center its alpha bounds, and use the native icon footprint. No new symbols.
"""
from pathlib import Path
from PIL import Image


def compile_icon(source, target):
    with Image.open(source) as decoded:
        src = decoded.convert('RGBA')
    bbox = src.getchannel('A').getbbox()
    if not bbox:
        raise ValueError('Empty religion icon: ' + str(source))
    symbol = src.crop(bbox)
    ratio = 240 / max(symbol.size)
    size = tuple(max(1, round(x * ratio)) for x in symbol.size)
    symbol = symbol.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (256, 256))
    canvas.alpha_composite(symbol, ((256-size[0])//2, (256-size[1])//2))
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format='DDS')
    with Image.open(target) as check:
        assert check.size == (256, 256)
        assert check.convert('RGBA').tobytes() == canvas.tobytes()
    return {'source_size':list(src.size), 'source_bounds':list(bbox),
            'output_size':[256,256], 'output_bounds':list(canvas.getchannel('A').getbbox()),
            'format':'RGBA DDS; native-sized centered alpha footprint'}
