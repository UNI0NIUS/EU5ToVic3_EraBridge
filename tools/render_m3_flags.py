"""Approximate local COA preview using installed texture masks, not engine capture."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def render(run, game):
    report = json.loads((run/'conversion_report.json').read_text(encoding='utf-8'))
    assets = game/'gfx/coat_of_arms'
    mod=run/'eu5_economy_test/gfx/coat_of_arms'
    def asset(folder,name):
        return (mod/folder/name) if (mod/folder/name).is_file() else (assets/folder/name)
    selected = [f for f in report['flags'] if f.get('design')]
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 13)
    title = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 25)
    w,h = 240,160
    def paint(texture, color1, color2, color3=None):
        data=np.asarray(Image.open(texture).convert('RGBA'),dtype=float)
        mask=data[:,:,1:2]/255
        rgb=np.array(color1)*(1-mask)+np.array(color2)*mask
        if color3 is not None:
            # V3 jomini colored-emblem shader: green -> color2, red ->
            # color3; blue is an overlay, NOT a third flat-color mask.
            red=data[:,:,0:1]/255
            rgb=rgb*(1-red)+np.array(color3)*red
            blue=data[:,:,2:3]/255;normal=rgb/255
            rgb=np.where(blue<.5,2*normal*blue,1-2*(1-normal)*(1-blue))*255
        return Image.fromarray(np.dstack((rgb,data[:,:,3])).clip(0,255).astype('uint8'),'RGBA')
    cards=[]
    for f in selected:
        d=f['design']
        image=paint(asset('patterns',d['pattern']),d['field'],d['metal']).resize((w,h))
        for layer in d.get('layers',[]):
            art=paint(asset('colored_emblems',layer['emblem']),layer['color'],layer.get('color2',layer['color']),layer.get('color3',layer['color']))
            art=art.resize((round(w*layer['scale'][0]),round(h*layer['scale'][1])),Image.Resampling.LANCZOS)
            x,y=layer['position'];image.alpha_composite(art,(round(w*x-art.width/2),round(h*y-art.height/2)))
        if d.get('emblem'):
            emblem=paint(asset('colored_emblems',d['emblem']),d.get('charge_color',d['metal']),d.get('charge_color',d['field']))
            emblem=emblem.resize((round(w*d['scale'][0]),round(h*d['scale'][1])),Image.Resampling.LANCZOS)
            for x,y in d['positions']:
                image.alpha_composite(emblem,(round(w*x-emblem.width/2),round(h*y-emblem.height/2)))
        if d['colonial']:
            draw=ImageDraw.Draw(image)
            draw.rectangle((0,0,w*.4,h*.4),fill='#d3d7dc',outline='#596778',width=2)
            draw.text((10,18),'宗主旗',font=small,fill='#223344')
        card=Image.new('RGB',(270,218),'#152534'); card.paste(image,(15,8))
        draw=ImageDraw.Draw(card)
        name=report['countries'][f['tag']]['name_simp_chinese']
        draw.text((15,176),name[:13],font=font,fill='#edf0f3')
        draw.text((15,199),f['tag']+(' · 殖民旗' if d['colonial'] else ''),font=small,fill='#a0b5c9')
        cards.append(card)
    # Full catalogue, plus a compact selection for review.
    highlighted=['E8R','E8S','E7B','E1C','E1L','E1M','E1N','E5M']
    preview=[cards[next(i for i,f in enumerate(selected) if f['tag']==tag)] for tag in highlighted if any(f['tag']==tag for f in selected)]
    preview += [c for c,f in zip(cards,selected) if f['design']['colonial']][:8]
    for filename,items in [('flag-catalogue.png',cards),('flag-preview.png',preview)]:
        cols=4; rows=(len(items)+cols-1)//cols
        sheet=Image.new('RGB',(cols*270,rows*218+100),'#101c28')
        draw=ImageDraw.Draw(sheet)
        draw.text((20,16),'生成旗帜 · 地方身份与文化图案',font=title,fill='white')
        draw.text((20,57),'按原版材质近似绘制，非游戏截图；灰色角标在游戏中由宗主旗替换。',font=font,fill='#b7cadb')
        for n,card in enumerate(items):sheet.paste(card,((n%cols)*270,100+(n//cols)*218))
        sheet.save(run/filename)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path)
    p.add_argument('--game',type=Path,default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    a=p.parse_args();render(a.run,a.game)
