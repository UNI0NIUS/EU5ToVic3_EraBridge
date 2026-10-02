"""Export installed EU5/Vic3 interface textures as PNGs and an offline catalog.

Usage: python tools/extract_game_ui_assets.py
Requires Pillow. Output is local-only under .local/game-ui-assets by default.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image, ImageDraw, ImageFont


GALLERY = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EU5 / Victoria 3 · UI 素材库</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#151c24;color:#e5eaf0;font:14px system-ui,"Microsoft YaHei",sans-serif}
header{padding:28px 32px 20px;border-bottom:1px solid #384452;background:#1b2530}h1{margin:0 0 8px;font-size:26px;color:#e9cb91}p{color:#aab9c9;margin:6px 0;line-height:1.7}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}input,select,button,.link{background:#263342;color:#e5eaf0;border:1px solid #46596c;border-radius:7px;padding:10px;font:inherit}input{flex:1;min-width:230px}button,.link{cursor:pointer;text-decoration:none}button:hover,.link:hover{border-color:#e9cb91}button:disabled{opacity:.35;cursor:default}
main{padding:20px 32px}.bar{display:flex;gap:14px;align-items:center;margin-bottom:18px;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}
.card{padding:10px;border:1px solid #344252;background:#202b37;border-radius:10px;cursor:pointer}.card:hover{border-color:#d7b576}.preview{height:144px;display:flex;align-items:center;justify-content:center;background:repeating-conic-gradient(#313944 0% 25%,#252d37 0% 50%) 50%/20px 20px;border-radius:6px}.preview img{max-width:100%;max-height:136px;object-fit:contain}.name{overflow-wrap:anywhere;margin:10px 0 6px;line-height:1.4}.meta{color:#9dacbc;font-size:12px}.light .preview{background:repeating-conic-gradient(#ddd 0% 25%,#fff 0% 50%) 50%/20px 20px}
dialog{background:#202b37;color:#e5eaf0;border:1px solid #61778e;border-radius:12px;max-width:1000px;width:90vw;max-height:92vh}dialog::backdrop{background:#000b}.detail-image{height:45vh;margin:16px 0}.detail-image img{max-height:100%;max-width:100%;object-fit:contain}#path,#source{overflow-wrap:anywhere;user-select:all}#path{color:#e9cb91}#notice{color:#e9cb91}footer{margin:24px 0;color:#9dacbc}label{display:flex;gap:6px;align-items:center}label input{min-width:0;flex:0}
</style>
<header><h1>EU5 / Victoria 3 · UI 素材库</h1><p>图标、按钮、面板、边框与背景 · 原尺寸 PNG · 透明通道保留</p><p>按名称或目录搜索；点击素材查看大图、下载 PNG 或复制相对路径。英文目录支持中文关键词别名搜索。</p>
<div class="controls"><input id="query" placeholder="搜索：金币 / 人口 / 建筑 / 按钮 / gold / frame…" aria-label="搜索素材"><select id="game" aria-label="游戏"><option value="">全部游戏</option><option>EU5</option><option>Victoria 3</option></select><select id="category" aria-label="分类"><option value="">全部分类</option></select><select id="size" aria-label="尺寸"><option value="">全部尺寸</option><option value="small">小图标 ≤ 128 px</option><option value="medium">中型 ≤ 512 px</option><option value="large">大图 > 512 px</option></select><button id="bg">切换底色</button></div></header>
<main><div class="bar"><span id="count"></span><button id="prev">上一页</button><span id="page"></span><button id="next">下一页</button></div><div class="grid" id="grid"></div><footer>png/ 为完整素材，thumbs/ 仅供预览。manifest.json 记录尺寸、透明度及源文件位置。多状态贴图保留整张；程序内可能还需九宫格拉伸、裁切或着色。</footer></main>
<dialog id="detail"><button id="close">关闭</button><h2 id="title"></h2><div class="preview detail-image"><img id="large" alt=""></div><p id="dimensions"></p><p id="path"></p><p id="source"></p><div class="controls"><a class="link" id="download" download>下载 PNG</a><button id="copy">复制素材路径</button></div><p id="notice"></p></dialog>
<script src="catalog-data.js"></script><script>
const $=id=>document.getElementById(id), data=window.ASSETS;let page=0,filtered=[],selected;const pageSize=96;
const aliases={'金币':['gold','money','treasury'],'经济':['economy','goods','trade','budget'],'人口':['pop','population'],'建筑':['building'],'宗教':['religion'],'文化':['culture'],'科技':['advance','invention','tech'],'按钮':['button'],'边框':['frame','border','divider'],'背景':['background','texture','tile'],'军事':['military','army','navy','war'],'地图':['map'],'设置':['setting'],'关闭':['close'],'确认':['confirm','check','accept'],'资源':['goods','resource'],'贸易':['trade','market'],'国家':['country','flag','coat_of_arms']};
for(const c of [...new Set(data.map(x=>x.category))].sort()){const o=document.createElement('option');o.value=c;o.textContent=c;$('category').append(o)}
function filter(){page=0;const q=$('query').value.trim().toLowerCase();const terms=aliases[q]||[q];filtered=data.filter(x=>{let m=Math.max(x.width,x.height),s=$('size').value;return (!$('game').value||x.game===$('game').value)&&(!$('category').value||x.category===$('category').value)&&(!s||(s==='small'?m<=128:s==='medium'?m>128&&m<=512:m>512))&&terms.some(t=>(x.name+' '+x.relative_source).toLowerCase().includes(t))});render()}
function render(){const total=Math.max(1,Math.ceil(filtered.length/pageSize));$('count').textContent=`${filtered.length.toLocaleString()} / ${data.length.toLocaleString()} 张素材`;$('page').textContent=`${page+1} / ${total}`;$('prev').disabled=page===0;$('next').disabled=page+1>=total;$('grid').replaceChildren();for(const a of filtered.slice(page*pageSize,(page+1)*pageSize)){const c=document.createElement('button');c.className='card';c.style.textAlign='left';const p=document.createElement('div');p.className='preview';const img=document.createElement('img');img.loading='lazy';img.src=a.thumbnail;img.alt=a.name;p.append(img);const n=document.createElement('div');n.className='name';n.textContent=a.name;const m=document.createElement('div');m.className='meta';m.textContent=`${a.game} · ${a.width} × ${a.height}`;c.append(p,n,m);c.onclick=()=>openDetail(a);$('grid').append(c)}}
function openDetail(a){selected=a;$('title').textContent=a.name;$('large').src=a.png;$('large').alt=a.name;$('dimensions').textContent=`${a.game} / ${a.category} · ${a.width} × ${a.height} · ${a.has_transparency?'含透明像素':'不透明'}`;$('path').textContent=a.png;$('source').textContent='来源：'+a.source;$('download').href=a.png;$('download').download=a.name+'.png';$('notice').textContent='';$('detail').showModal()}
for(const id of ['query','game','category','size'])$(id).addEventListener(id==='query'?'input':'change',filter);
$('prev').onclick=()=>{page--;render()};$('next').onclick=()=>{page++;render();window.scrollTo(0,0)};$('bg').onclick=()=>document.body.classList.toggle('light');$('close').onclick=()=>$('detail').close();$('copy').onclick=async()=>{try{await navigator.clipboard.writeText(selected.png);$('notice').textContent='路径已复制'}catch(e){const range=document.createRange();range.selectNodeContents($('path'));getSelection().removeAllRanges();getSelection().addRange(range);$('notice').textContent='已选中路径，请按 Ctrl+C 复制'}};filter();
</script></html>'''


def open_texture(source):
    try:
        return Image.open(source)
    except NotImplementedError:
        # BC1/2/3 sRGB blocks have the same compressed layout as UNORM.
        # Pillow 12 omits these enum values. Decode unchanged encoded pixels,
        # using an in-memory header; never modify the installed DDS file.
        data = bytearray(source.read_bytes())
        if data[:4] == b'DDS ' and data[84:88] == b'DX10' and len(data) >= 148:
            fmt = struct.unpack_from('<I', data, 128)[0]
            if fmt in {72, 75, 78}:
                struct.pack_into('<I', data, 128, {72: 71, 75: 74, 78: 77}[fmt])
                return Image.open(io.BytesIO(data))
        raise


def export_one(job):
    game, root, source, out = job
    rel = source.relative_to(root)
    key = f'{game}/{rel.as_posix()}'
    ident = hashlib.sha256(key.encode()).hexdigest()[:20]
    # Keep the original suffix to prevent collisions between foo.dds and foo.png.
    png = Path('png') / game / rel.parent / (rel.name + '.png')
    thumb = Path('thumbs') / f'{ident}.png'
    try:
        if source.stat().st_size == 0:
            raise ValueError('Source file is empty (0 bytes)')
        with open_texture(source) as original:
            im = original.convert('RGBA')
            width, height = im.size
            alpha = im.getchannel('A').getextrema()
            (out / png).parent.mkdir(parents=True, exist_ok=True)
            im.save(out / png, compress_level=3)
            im.thumbnail((160, 140), Image.Resampling.LANCZOS)
            im.save(out / thumb, compress_level=3)
        return dict(id=ident, game=game, name=source.stem,
                    category=rel.parts[0] if len(rel.parts) > 1 else 'other',
                    relative_source=rel.as_posix(), source=str(source),
                    width=width, height=height, has_transparency=alpha[0] < 255,
                    png=png.as_posix(), thumbnail=thumb.as_posix()), None
    except Exception as exc:
        return None, dict(game=game, source=str(source), source_bytes=source.stat().st_size, error=str(exc))


def make_overview(assets, out):
    """Representative contact sheet, including icons and reusable UI pieces."""
    preferred = ['goods', 'pop', 'building', 'religion', 'generic', 'button', 'frame', 'background']
    picks = []
    for game in ('EU5', 'Victoria 3'):
        for term in preferred:
            candidates = [a for a in assets if a['game'] == game
                          and term in a['relative_source'].lower() and a not in picks]
            picks.extend(candidates[:3])
    cols, cw, ch = 8, 200, 185
    rows = (len(picks) + cols - 1) // cols
    canvas = Image.new('RGB', (cols*cw, rows*ch + 80), '#17212c')
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 13)
        title = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 28)
    except OSError:
        font = title = ImageFont.load_default()
    draw.text((24, 18), 'EU5 / VICTORIA 3 - UI ASSET LIBRARY', fill='#e9cb91', font=title)
    for i, asset in enumerate(picks):
        x, y = (i % cols)*cw, (i // cols)*ch + 80
        draw.rounded_rectangle((x+7, y+4, x+cw-7, y+ch-5), radius=8, fill='#263443')
        with Image.open(out / asset['thumbnail']) as thumb:
            canvas.paste(thumb, (x+(cw-thumb.width)//2, y+8), thumb)
        draw.text((x+14, y+148), asset['name'][:25], font=font, fill='#eef0f3')
        draw.text((x+14, y+165), asset['game'], font=font, fill='#adbdce')
    canvas.save(out / 'overview.jpg', quality=92)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--eu5', type=Path, default=Path('D:/Steam/steamapps/common/Europa Universalis V/game/main_menu/gfx/interface'))
    parser.add_argument('--vic3', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game/gfx/interface'))
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / '.local/game-ui-assets')
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    roots = {'EU5': args.eu5, 'Victoria 3': args.vic3}
    for root in roots.values():
        if not root.is_dir():
            parser.error(f'Interface directory missing: {root}')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'thumbs').mkdir(exist_ok=True)
    jobs = [(game, root, p, out) for game, root in roots.items()
            for p in sorted(root.rglob('*')) if p.suffix.lower() in {'.dds', '.png', '.jpg', '.jpeg', '.tga', '.bmp'}]
    print(f'Exporting {len(jobs)} images to {out}', flush=True)
    assets, errors = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(export_one, job) for job in jobs]
        for n, future in enumerate(as_completed(futures), 1):
            asset, error = future.result()
            if asset:
                assets.append(asset)
            else:
                errors.append(error)
            if n % 500 == 0 or n == len(jobs):
                print(f'{n}/{len(jobs)} processed; {len(errors)} errors', flush=True)
    write_catalog(assets, errors, roots, len(jobs), out)
    return 1 if errors else 0


def write_catalog(assets, errors, roots, discovered, out):
    assets.sort(key=lambda a: (a['game'], a['relative_source']))
    summary = dict(created_at=datetime.now(timezone.utc).isoformat(),
                   roots={g: str(r) for g, r in roots.items()}, discovered=discovered,
                   exported=len(assets), errors=errors,
                   by_game=dict(Counter(a['game'] for a in assets)),
                   by_category=dict(Counter(a['game']+'/'+a['category'] for a in assets)))
    (out / 'manifest.json').write_text(json.dumps(dict(summary=summary, assets=assets), ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'catalog-data.js').write_text('window.ASSETS = '+json.dumps(assets, ensure_ascii=False)+';\n', encoding='utf-8')
    (out / 'index.html').write_text(GALLERY, encoding='utf-8')
    make_overview(assets, out)
    (out / 'README.md').write_text(
        '# 游戏 UI 素材库\n\n'
        f'共导出 {len(assets):,} 张 PNG：'+ '，'.join(f'{g} {n:,} 张' for g, n in summary['by_game'].items())+'。\n\n'
        f'未能转换 {len(errors)} 个源文件，具体原因见 manifest.json 的 summary.errors。\n\n'
        '- 双击 index.html：离线搜索、按游戏和类别筛选、查看大图、下载素材。\n'
        '- png/：完整尺寸 RGBA PNG，保留透明度；沿用游戏目录分类。\n'
        '- thumbs/：仅用于浏览的缩略图，软件 UI 请引用 png/。\n'
        '- overview.jpg：代表性素材总览。\n'
        '- manifest.json：全部资源路径、尺寸、透明度与来源记录，以及失败明细。\n\n'
        '导出范围为两个游戏本体的 gfx/interface 目录；不包含 DLC 独立目录、3D 模型、地图地形和音频。'
        '多状态图集保留整张，未猜测裁切范围；有些按钮依赖九宫格、遮罩或游戏内着色，不能只靠一张图片完整还原。'
        'DDS 仅导出最高分辨率图层，不导出 mipmap。文件名保留原扩展名，如 gold.dds.png，以避免同名冲突。\n\n'
        '所有导出文件存放于项目已忽略的 .local 目录，游戏原文件保持不变。\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'by_category'}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
