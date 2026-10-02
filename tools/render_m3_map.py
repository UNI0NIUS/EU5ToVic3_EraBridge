"""Render exported ownership on the installed V3 province bitmap for visual review."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from m3_world import load_json


def render(run, game):
    report = load_json(run / 'conversion_report.json')
    owners = load_json(run / 'province_owners.json')
    politics = load_json(Path(__file__).resolve().parents[1] / '.local/m3/politics-final.json')
    image = np.asarray(Image.open(game / 'map_data/provinces.png').convert('RGB'), dtype=np.uint32)
    packed = (image[:, :, 0] << 16) | (image[:, :, 1] << 8) | image[:, :, 2]
    palette = np.zeros((1 << 24, 3), dtype=np.uint8)
    palette[:] = (38, 61, 78)
    idmap = np.zeros(1 << 24, dtype=np.uint16)
    labels = {}
    for idx, (tag, country) in enumerate(sorted(report['countries'].items()), 1):
        src = politics['countries'].get(country['source_id'], {})
        color = src.get('color')
        if len(color or []) != 3:
            color = [130, 135, 120]
        color = tuple(int(x) for x in color)
        labels[tag] = (idx, color)
    for state, provinces in owners.items():
        for p, tag in provinces.items():
            n = int(p[1:], 16)
            idmap[n] = labels[tag][0]; palette[n] = labels[tag][1]
    rgb = palette[packed]
    countries = idmap[packed]
    borders = np.zeros(countries.shape, dtype=bool)
    borders[:, 1:] |= countries[:, 1:] != countries[:, :-1]
    borders[1:, :] |= countries[1:, :] != countries[:-1, :]
    rgb[borders & (countries != 0)] = (28, 34, 38)
    map_image = Image.fromarray(rgb)
    font_file = Path('C:/Windows/Fonts/msyh.ttc')
    font = ImageFont.truetype(str(font_file), 22) if font_file.exists() else ImageFont.load_default()
    font_small = ImageFont.truetype(str(font_file), 17) if font_file.exists() else ImageFont.load_default()
    view = map_image.resize((2048, 904), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', (2048, 996), '#142330'); canvas.paste(view, (0, 82))
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 14), 'EU5 1780.7.4 → V3 1.13.11 · 全世界政治映射预览', font=font, fill='#f3f3ef')
    draw.text((24, 49), '各国单独着色，附庸保留自身颜色。此图来自导出数据，并非游戏截图；人口、经济仍用 V3 模板。', font=font_small, fill='#b8cad8')
    canvas.save(run / 'world-map.png')
    # The bitmap coordinate bounds are derived from actual European state provinces.
    europe_states = {s for s in owners if s in {
        'STATE_HOME_COUNTIES', 'STATE_ILE_DE_FRANCE', 'STATE_PIEDMONT', 'STATE_LATIUM',
        'STATE_SICILY', 'STATE_HIGHLANDS', 'STATE_SVEALAND', 'STATE_BRANDENBURG',
        'STATE_WESTERN_GALICIA', 'STATE_MAZOVIA', 'STATE_AUSTRIA', 'STATE_NEW_CASTILE', 'STATE_ESTREMADURA'}}
    european_colors = np.array([int(p[1:], 16) for s in europe_states for p in owners[s]], dtype=np.uint32)
    yy, xx = np.where(np.isin(packed, european_colors))
    box = (max(0, int(xx.min())-160), max(0, int(yy.min())-80), min(packed.shape[1], int(xx.max())+160), min(packed.shape[0], int(yy.max())+100))
    map_image.crop(box).save(run / 'europe-map.png')
    return {'world': str(run / 'world-map.png'), 'europe': str(run / 'europe-map.png')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('run', type=Path)
    p.add_argument('--game', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    a = p.parse_args(); print(json.dumps(render(a.run, a.game)))
