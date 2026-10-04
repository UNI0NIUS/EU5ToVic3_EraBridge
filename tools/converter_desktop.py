"""Native Tk desktop workbench. No browser, webview, HTTP listener or JS bridge."""
import argparse
import base64
from copy import deepcopy
from datetime import datetime
import io
import os
from pathlib import Path
import queue
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
from PIL import Image, ImageTk
from converter_controller import App, ROOT
from converter_project import DEFAULTS, read, write, settings
from converter_export import export_candidate
from converter_pipeline import run_conversion
from converter_i18n import Translator, LANGUAGES, game_labels, diagnostic

BG='#edf1f4'; INK='#203342'; ACCENT='#176f68'
RISKS={'arable':'耕地不足','unemployment':'严重失业','food':'接入后缺粮','market_food':'市场缺粮','local_food':'本地缺粮'}
LAYERS={'国家归属':'country','州界与地块':'state','战略地区':'strategic_region','市场归属':'market','耕地提醒':'arable','失业风险':'unemployment','接入后食物缺口':'food','市场食物缺口':'market_food','地块本地食物缺口':'local_food'}
FILTERS={'全部提醒':'all','耕地不足':'arable','严重失业':'unemployment','食物不足':'food','全部地区':'every'}
STAGES={'C++ import audit':'读取存档并核对游戏与模组','Source politics':'提取国家与外交','Source population':'提取人口',
        'Source literacy':'提取识字率','Source economy':'提取经济','Source military':'提取陆军','Source navy':'提取舰队','Source wars':'提取战争',
        'Source territory and political base':'转换领土与国家','Population, cultures and literacy':'转换人口、文化与识字率',
        'Political evidence':'整理政治依据','Political rule evaluation':'计算政治规则','Laws and technology':'转换法律与科技',
        'Economic conversion':'转换经济','Economic capacity, administration and military':'计算经济容量、行政和军队',
        'Supply chain, land and opening wars':'计算供应链、耕地和战争','Startup script validation':'校验开局脚本','Output localization':'校验输出语言'}
PARAMS=[('population_multiplier','人口系数',False),('arable_multiplier','耕地系数',False),
        ('workforce_share','劳动力比例 %',True),('staffing','正式岗位招聘 %',True),
        ('food_wealth','食物消费生活水平',False),('small_arable','低耕地提醒 ≤',False),
        ('unemployment_threshold','严重失业缺口 ≥ %',True),('food_shortfall_threshold','食物缺口 ≥ %',True)]

def fmt(n):return '未知' if n is None else f'{n:,.0f}'
def pct(n):return '未知' if n is None else f'{n*100:.1f}%'

class Workbench:
    def __init__(self, root, workspace, autoload=True, language=None):
        self.root=root;self.app=App(workspace);self.events=queue.Queue();self.busy=False;self.closing=False
        self.cancel=threading.Event();self.operation='';self.selected=None;self.rows={};self.targets={}
        self.map=None;self.photo=None;self.overlay=None;self.box=None;self.marker=None;self.scale=1.;self.offset=[0.,0.]
        self.drag=None;self.picking=False;self.default=self.app.defaults();self.last_output=None;self.province_selection=set()
        self.preferences=self.app.workspace/'desktop.json';self.mutators=[];self.layer_cache={};self.map_pending=False
        pref=read(self.preferences) if self.preferences.exists() else {}
        self.set_translator(language or pref.get('language','zh-CN'))
        self.display_labels={}
        self.selection_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='map-selection')
        self.selection_generation=0;self.selection_future=None;self.selecting=False
        root.title(self.tr('EraBridge Beta · EU5 → Victoria 3 · 桌面转换器 0.12.2'));root.geometry('1380x900');root.minsize(1080,760)
        self.icon_dir=Path(__file__).with_name('converter_ui')/'icons'
        if os.name=='nt':root.iconbitmap(default=str(self.icon_dir/'erabridge-beta.ico'))
        else:
            self.window_icon=tk.PhotoImage(master=root,file=str(self.icon_dir/'erabridge-beta-256.png'))
            root.iconphoto(True,self.window_icon)
        root.configure(bg=BG);root.protocol('WM_DELETE_WINDOW',self.close)
        root.bind('<Escape>',lambda e:self.cancel_pick())
        root.report_callback_exception=self.callback_error
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10),background=BG,foreground=INK)
        style.configure('TButton',padding=(10,7));style.configure('TEntry',padding=5)
        style.configure('Accent.TButton',background=ACCENT,foreground='white')
        style.map('Accent.TButton',background=[('active','#225c57'),('disabled','#819c99')])
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',16,'bold'))
        style.configure('Treeview',rowheight=29,background='white',fieldbackground='white')
        style.configure('Treeview.Heading',font=('Microsoft YaHei UI',10,'bold'))
        self.build();self.poll_id=root.after(80,self.poll)
        root.bind('<Destroy>',self.destroyed,add='+')
        if autoload:root.after(200,self.startup)

    def set_translator(self,language):
        self.translator=Translator(language);self.tr=self.translator
        self.fmt=lambda n:self.tr(fmt(n));self.pct=lambda n:self.tr(pct(n))
        self.layers={self.tr(k):v for k,v in LAYERS.items()}
        self.filters={self.tr(k):v for k,v in FILTERS.items()}
        self.label_source=None

    def save_preferences(self,**values):
        prior=read(self.preferences) if self.preferences.exists() else {}
        write(self.preferences,{**prior,'language':self.translator.language,**values})

    def labels(self):
        return self.display_labels or getattr(self.app.world,'labels',{})

    def localize_row(self,row):
        result=dict(row)
        for key,name in [('state','state_name'),('country','country_name'),
                         ('market_owner','market_name'),('strategic_region','strategic_region_name')]:
            if key in row:result[name]=self.labels().get(row[key],row.get(name,row[key]))
        return result

    def change_language(self,event=None):
        language=next(k for k,v in LANGUAGES.items() if v['name']==self.language_choice.get())
        if self.busy or self.selecting or self.map_pending or self.closing:
            self.language_choice.set(LANGUAGES[self.translator.language]['name']);return
        if language==self.translator.language:return
        values={k:v.get() for k,v in self.params.items()}
        layer=self.layers[self.layer.get()];active_filter=self.filters[self.filter.get()]
        region=self.kind.get()!=self.tr('整个国家');query=self.search.get();target=self.targets.get(self.target.get())
        self.cancel_pick();self.set_translator(language);self.save_preferences()
        self.root.unbind('<MouseWheel>')
        for child in self.root.winfo_children():child.destroy()
        self.mutators=[];self.build()
        self.root.title(self.tr('EraBridge Beta · EU5 → Victoria 3 · 桌面转换器 0.12.2'))
        self.layer.set(next(k for k,v in self.layers.items() if v==layer))
        self.filter.set(next(k for k,v in self.filters.items() if v==active_filter))
        self.kind.set(self.tr('当前州内的地区') if region else self.tr('整个国家'))
        self.search.set(query)
        if self.app.preview:
            self.adopt()
            self.target.set(next((k for k,v in self.targets.items() if v==target),self.target.get()))
            self.load_layer()
        for k,v in values.items():self.params[k].set(v)
        self.draw()

    def button(self,parent,text,command,mutates=False,**kw):
        b=ttk.Button(parent,text=text,command=command,**kw)
        if mutates:self.mutators.append(b)
        return b

    def side_panel(self,parent,width):
        outer=ttk.Frame(parent);parent.add(outer,weight=0)
        canvas=tk.Canvas(outer,width=width,bg=BG,highlightthickness=0)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        frame=ttk.Frame(canvas,padding=10);item=canvas.create_window(0,0,window=frame,anchor='nw')
        frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        def wheel(event):
            widget=event.widget
            while widget is not None:
                if widget is outer:canvas.yview_scroll(-int(event.delta/120),'units');break
                widget=getattr(widget,'master',None)
        self.root.bind('<MouseWheel>',wheel,add='+')
        return frame

    def build(self):
        top=ttk.Frame(self.root,padding=12);top.pack(fill='x')
        self.brand_icon=tk.PhotoImage(master=self.root,file=str(self.icon_dir/'erabridge-beta-32.png'))
        ttk.Label(top,image=self.brand_icon).pack(side='left',padx=(0,8))
        ttk.Label(top,text='EU5 → VICTORIA 3',style='Title.TLabel').pack(side='left')
        actions=ttk.Frame(self.root,padding=(12,0,12,8));actions.pack(fill='x')
        for label,cmd in [(self.tr('退出'),self.close),(self.tr('打开输出目录'),self.open_output),(self.tr('导出模组'),self.export),(self.tr('打开项目 / 结果'),self.open_dialog),(self.tr('准备转换规则'),self.initialize_dialog),(self.tr('导入 EU5 存档'),self.convert_dialog)]:
            self.button(actions,label,cmd,mutates=label not in (self.tr('退出'),self.tr('打开输出目录'))).pack(side='right',padx=3)
        language_bar=ttk.Frame(self.root,padding=(16,0,16,4));language_bar.pack(fill='x')
        ttk.Label(language_bar,text='语言 / Language').pack(side='left')
        self.language_choice=tk.StringVar(value=LANGUAGES[self.translator.language]['name'])
        self.language_box=ttk.Combobox(language_bar,textvariable=self.language_choice,values=[v['name'] for v in LANGUAGES.values()],state='readonly',width=18)
        self.language_box.pack(side='left',padx=8);self.language_box.bind('<<ComboboxSelected>>',self.change_language)
        self.title=tk.StringVar(value=self.tr('选择存档开始转换，或打开已经生成的转换结果。'))
        ttk.Label(self.root,textvariable=self.title,padding=(16,0,16,8)).pack(fill='x')
        body=ttk.Panedwindow(self.root,orient='horizontal');body.pack(fill='both',expand=True,padx=12)
        left=self.side_panel(body,245)
        ttk.Label(left,text=self.tr('开局参数'),style='Title.TLabel').pack(anchor='w',pady=(0,10))
        self.params={}
        for i,(key,label,percent) in enumerate(PARAMS):
            if i==2:ttk.Separator(left).pack(fill='x',pady=12)
            row=ttk.Frame(left);row.pack(fill='x',pady=5)
            row.columnconfigure(0,weight=1)
            caption=ttk.Label(row,text=self.tr(label),wraplength=135);caption.grid(row=0,column=0,sticky='w')
            row.bind('<Configure>',lambda e,label=caption:label.configure(wraplength=max(70,e.width-85)))
            var=tk.StringVar(value=str(DEFAULTS[key]*(100 if percent else 1)));self.params[key]=var
            ttk.Entry(row,textvariable=var,width=7).grid(row=0,column=1,sticky='e',padx=(6,0))
        self.button(left,self.tr('应用参数并重新计算'),self.apply,True,style='Accent.TButton').pack(fill='x',pady=12)
        ttk.Label(left,text=self.tr('人口、耕地系数写入导出；\n其他参数用于风险估算。\n\n耕地 ≤ 3、失业与食物不足\n分别提醒，不自动强制合并。'),wraplength=215).pack(anchor='w')
        self.button(left,self.tr('计算依据与局限'),self.assumptions).pack(fill='x',pady=(12,3))
        self.button(left,self.tr('恢复初始方案'),self.restore,True).pack(fill='x',pady=3)
        self.button(left,self.tr('批量整合风险地区 / 州…'),self.bulk_dialog,True).pack(fill='x',pady=5)
        self.button(left,self.tr('削减人口 / 批量调节…'),self.population_dialog,True).pack(fill='x',pady=5)
        self.button(left,self.tr('批量为失业地区补耕地…'),self.arable_bulk_dialog,True).pack(fill='x',pady=5)
        center=ttk.Frame(body);body.add(center,weight=4)
        self.summary=tk.StringVar(value=self.tr('尚未载入世界'))
        summary_label=ttk.Label(center,textvariable=self.summary,padding=8,wraplength=500,font=('Microsoft YaHei UI',11,'bold'));summary_label.pack(fill='x')
        summary_label.bind('<Configure>',lambda e:summary_label.configure(wraplength=max(100,e.width-16)))
        controls=ttk.Frame(center);controls.pack(fill='x',pady=4)
        self.layer=tk.StringVar(value=self.tr('国家归属'))
        cb=ttk.Combobox(controls,textvariable=self.layer,values=list(self.layers),state='readonly',width=24);cb.pack(side='left');cb.bind('<<ComboboxSelected>>',lambda e:self.load_layer())
        ttk.Label(center,text=self.tr('  拖动平移 · 滚轮缩放 · 点击地区'),wraplength=400).pack(fill='x')
        for label,cmd in [('＋',lambda:self.zoom(1.4)),(self.tr('全图'),self.home),('－',lambda:self.zoom(1/1.4))]:self.button(controls,label,cmd,width=4).pack(side='right')
        self.legend=tk.StringVar(value=self.tr('国家颜色区分归属；点击地块查看地区数据。'))
        legend_label=ttk.Label(center,textvariable=self.legend,wraplength=700,padding=(0,3));legend_label.pack(fill='x')
        legend_label.bind('<Configure>',lambda e:legend_label.configure(wraplength=max(100,e.width)))
        split=ttk.Panedwindow(center,orient='vertical');split.pack(fill='both',expand=True)
        mf=ttk.Frame(split);split.add(mf,weight=3)
        self.canvas=tk.Canvas(mf,bg='#132531',highlightthickness=0,height=350);self.canvas.pack(fill='both',expand=True)
        self.canvas.create_text(260,150,text=self.tr('导入存档或打开转换结果后显示地图'),fill='white',font=('Microsoft YaHei UI',13))
        self.canvas.bind('<Configure>',lambda e:self.draw());self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<ButtonPress-1>',self.down);self.canvas.bind('<B1-Motion>',self.move);self.canvas.bind('<ButtonRelease-1>',self.up)
        bottom=ttk.Frame(split);split.add(bottom,weight=2)
        filters=ttk.Frame(bottom,padding=(0,8));filters.pack(fill='x')
        self.filter=tk.StringVar(value=self.tr('全部提醒'))
        cb=ttk.Combobox(filters,textvariable=self.filter,values=list(self.filters),state='readonly',width=18);cb.pack(side='left');cb.bind('<<ComboboxSelected>>',lambda e:self.filter_rows())
        self.search=tk.StringVar();self.search.trace_add('write',lambda *a:self.filter_rows())
        search_line=ttk.Frame(bottom);search_line.pack(fill='x',pady=(0,6))
        ttk.Label(search_line,text=self.tr('搜索国家 / 州 / TAG  ')).pack(side='left')
        ttk.Entry(search_line,textvariable=self.search,width=20).pack(side='left',fill='x',expand=True)
        tf=ttk.Frame(bottom);tf.pack(fill='both',expand=True)
        self.table=ttk.Treeview(tf,columns=('state','country','population','arable','jobs','food'),show='headings',selectmode='browse',height=7)
        heading_font=tkfont.Font(root=self.root,font=('Microsoft YaHei UI',10,'bold'))
        for key,name,width in [('state',self.tr('地区'),135),('country',self.tr('国家'),140),('population',self.tr('人口'),95),('arable',self.tr('耕地'),55),('jobs',self.tr('失业缺口'),80),('food',self.tr('接入后食物缺口'),100)]:
            heading_width=heading_font.measure(name)+20
            self.table.heading(key,text=name);self.table.column(key,width=max(width,heading_width),minwidth=heading_width,stretch=key in ('state','country'))
        sy=ttk.Scrollbar(tf,orient='vertical',command=self.table.yview);sx=ttk.Scrollbar(tf,orient='horizontal',command=self.table.xview)
        self.table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);tf.rowconfigure(0,weight=1);tf.columnconfigure(0,weight=1)
        self.table.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew')
        self.table.bind('<<TreeviewSelect>>',self.table_select)
        self.count=tk.StringVar();ttk.Label(bottom,textvariable=self.count).pack(anchor='w')
        right=self.side_panel(body,275)
        ttk.Label(right,text=self.tr('地区与合并'),style='Title.TLabel').pack(anchor='w')
        self.details=tk.StringVar(value=self.tr('点击地图或风险列表查看地区。'))
        ttk.Label(right,textvariable=self.details,wraplength=250,justify='left').pack(fill='x',pady=12)
        ttk.Separator(right).pack(fill='x',pady=6)
        ttk.Label(right,text=self.tr('合并范围')).pack(anchor='w');self.kind=tk.StringVar(value=self.tr('整个国家'))
        cb=ttk.Combobox(right,textvariable=self.kind,values=[self.tr('整个国家'),self.tr('当前州内的地区')],state='readonly');cb.pack(fill='x',pady=5);cb.bind('<<ComboboxSelected>>',lambda e:self.fill_targets())
        ttk.Label(right,text=self.tr('并入相邻国家')).pack(anchor='w');self.target=tk.StringVar()
        self.target_box=ttk.Combobox(right,textvariable=self.target,state='readonly');self.target_box.pack(fill='x',pady=5)
        self.pick_btn=self.button(right,self.tr('从地图点选目标'),self.pick);self.pick_btn.pack(fill='x',pady=5)
        self.button(right,self.tr('确认合并'),self.merge,True,style='Accent.TButton').pack(fill='x',pady=5)
        self.button(right,self.tr('编辑耕地 / 建筑 / 地块'),self.edit_dialog,True).pack(fill='x',pady=5)
        self.button(right,self.tr('撤销最近一次编辑'),self.undo,True).pack(fill='x',pady=5)
        self.history=tk.StringVar(value=self.tr('尚无合并决定'))
        ttk.Label(right,textvariable=self.history,wraplength=250).pack(fill='x',pady=10)
        ttk.Label(right,text=self.tr('合并不创造耕地、工作或粮食。\n外交、首都或建筑冲突会显示原因。'),wraplength=250).pack(fill='x')
        foot=ttk.Frame(self.root,padding=(12,8));foot.pack(fill='x',side='bottom',before=body)
        self.progress=ttk.Progressbar(foot,mode='indeterminate',length=100);self.progress.pack(side='left',padx=(0,10))
        self.status=tk.StringVar(value=self.tr('就绪 · 本机桌面程序'));status_label=ttk.Label(foot,textvariable=self.status,wraplength=950);status_label.pack(side='left',fill='x',expand=True)
        status_label.bind('<Configure>',lambda e:status_label.configure(wraplength=max(100,e.width)))

    def callback_error(self,kind,value,tb):
        self.error(self.tr('操作失败'),diagnostic(value),''.join(traceback.format_exception(kind,value,tb)))

    def destroyed(self,event):
        if event.widget is self.root:
            try:self.root.after_cancel(self.poll_id)
            except tk.TclError:pass
            self.selection_pool.shutdown(wait=False,cancel_futures=True)

    def error(self,title,detail,trace=''):
        log=self.app.workspace/'logs'/('desktop-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
        log.parent.mkdir(exist_ok=True);log.write_text(trace or str(detail),encoding='utf-8')
        detail=self.tr(detail)
        self.status.set(title+'：'+detail[:120]);messagebox.showerror(title,detail+self.tr('\n\n日志：')+str(log),parent=self.root)

    def submit(self,label,fn,done=None):
        if self.busy:return
        self.busy=True;self.operation=label;self.cancel.clear();self.status.set(label+'…');self.progress.start(12)
        for b in self.mutators:b.state(['disabled'])
        def work():
            try:self.events.put(('done',fn(),done))
            except Exception as e:self.events.put(('error',diagnostic(e),traceback.format_exc()))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event[0]
                if kind=='selection':
                    _,generation,done,result,error=event
                    if generation!=self.selection_generation:continue
                    self.selecting=False
                    if error:self.status.set(self.tr('地图定位失败，可重新选择：')+self.tr(error))
                    else:done(result)
                    continue
                if kind=='progress':self.status.set(self.tr(event[1]));continue
                self.busy=False;self.progress.stop()
                for b in self.mutators:b.state(['!disabled'])
                if self.closing:self.root.destroy();return
                if kind=='error':self.error(self.tr('操作失败'),event[1],event[2])
                else:
                    self.status.set(self.operation+self.tr('完成'))
                    if event[2]:event[2](event[1])
        except queue.Empty:pass
        except Exception as e:self.error(self.tr('更新界面失败'),diagnostic(e),traceback.format_exc())
        self.poll_id=self.root.after(80,self.poll)

    def startup(self):
        pref=read(self.preferences) if self.preferences.exists() else {}
        if pref.get('last_project') and (self.app.workspace/'projects'/pref['last_project']/'project.json').exists():self.load({'id':pref['last_project']})
        elif self.default['candidates']:
            c=self.default['candidates'][0];self.load(dict(package=c['path'],game=self.default['game'],name=c['name']))

    def load(self,body):
        self.cancel_pick();self.selection_generation+=1;self.selecting=False
        def work():
            self.app.load_project(body)
            return Image.open(io.BytesIO(self.app.image('country'))).copy()
        self.submit(self.tr('载入世界并计算风险'),work,self.loaded)

    def loaded(self,image):
        self.map=image;self.layer_cache={'country':image};self.layer.set(self.tr('国家归属'))
        self.selected=None;self.overlay=None;self.box=None;self.marker=None;self.picking=False
        self.pick_btn.configure(text=self.tr('从地图点选目标'));self.adopt();self.home()
        self.save_preferences(last_project=self.app.project['id'])

    def adopt(self):
        self.selection_generation+=1;self.selecting=False
        source=(id(self.app.world),self.translator.language)
        if source!=self.label_source:
            self.display_labels=game_labels(self.app.world.game,self.app.world.mod,self.translator.language) if hasattr(self.app.world,'game') else {}
            self.label_source=source
        previous=self.rows.get(self.selected);p=self.app.project;v=self.app.preview;self.display_preview=v;self.rows={r['id']:self.localize_row(r) for r in v['rows']}
        self.title.set(p['name']+' · '+v['source_date']+self.tr(' · 修订 ')+str(p['revision']))
        for key,_,percent in PARAMS:self.params[key].set(f"{p['settings'][key] * (100 if percent else 1):g}")
        s=v['summary'];self.summary.set(self.tr('{0} 国家 / {1} 地区    耕地 ≤ {2}：{3}    失业：{4}    食物：{5}', f"{s['countries']:,}", f"{s['regions']:,}", f"{p['settings']['small_arable']}", f"{s.get('arable_alerts', 0)}", f"{s.get('unemployment_alerts', 0)}", f"{s.get('food_alerts', 0)}"))
        self.history.set(self.tr('已保存 ')+str(len(p['merges']))+self.tr(' 次编辑\n')+'\n'.join(self.operation_label(o) for o in p['merges'][-3:]))
        if self.selected not in self.rows:
            self.selected=None;self.overlay=None;self.marker=None
            if previous and p['merges']:
                op=p['merges'][-1];target=op.get('target');state=op.get('target_state',previous['state'])
                if op['kind']=='bulk':target=next((m['target'] for m in op['transfers'] if m['state']==previous['state'] and m['source']==previous['country']),None)
                key=state+'|'+str(target)
                if key in self.rows:self.selected=key
        self.filter_rows();self.show_details()

    def require_project(self):
        if self.app.project:return True
        messagebox.showinfo(self.tr('尚未载入世界'),self.tr('请先导入存档，或打开已有转换结果。'),parent=self.root);return False

    def mutate(self,kind,extra=None):
        if self.busy or not self.require_project():return
        self.cancel_pick();self.selection_generation+=1;self.selecting=False
        body=dict(revision=self.app.project['revision'],**(extra or {}));layer=self.layers[self.layer.get()]
        def work():
            self.app.mutate(kind,body)
            return Image.open(io.BytesIO(self.app.image(layer))).copy()
        def done(image):
            self.map=image;self.layer_cache={layer:image};self.overlay=None;self.marker=None;self.adopt();self.draw()
            if self.selected:self.select(self.selected,False)
        self.submit(self.tr('保存方案并重算风险'),work,done)

    def apply(self):
        try:options=settings({key:float(self.params[key].get())/(100 if percent else 1) for key,_,percent in PARAMS})
        except (ValueError,TypeError) as e:messagebox.showerror(self.tr('参数无效'),self.tr(e),parent=self.root);return
        self.mutate('settings',{'settings':options})

    def restore(self):
        if self.require_project() and messagebox.askyesno(self.tr('恢复初始方案'),self.tr('恢复初始参数并清空合并决定？修订历史仍保留。'),parent=self.root):self.mutate('restore')
    def undo(self):self.mutate('undo')

    def filter_rows(self):
        if not self.rows:return
        query=self.search.get().strip().lower();f=self.filters[self.filter.get()]
        rows=[r for r in self.rows.values() if (f=='every' or f=='all' and r['risks'] or f in r['risks']) and query in ' '.join(str(r[k]) for k in ('state','country','state_name','country_name')).lower()]
        rows.sort(key=lambda r:(-len(r['risks']),-(r['food_shortfall'] or 0),r['id']))
        self.table.delete(*self.table.get_children())
        for r in rows:self.table.insert('', 'end',iid=r['id'],values=(r['state_name'],r['country_name']+' · '+r['country'],self.fmt(r['population']),self.fmt(r['arable']),self.pct(r['estimated_unemployment']),self.pct(r['food_shortfall'])))
        self.count.set(self.tr('当前 {0} 个地区 · 点击查看详情与合并选项', f'{len(rows):,}'))

    def table_select(self,event=None):
        keys=self.table.selection()
        if keys:self.select(keys[0],True)

    def select(self,key,focus=False):
        if key not in self.rows:return
        row=self.rows[key]
        if self.picking:
            choice=next((label for label,tag in self.targets.items() if tag==row['country']),None)
            self.cancel_pick()
            if choice:self.target.set(choice);self.status.set(self.tr('已选择合并目标：')+choice);return
            self.status.set(self.tr('已退出目标点选，正在查看所选地区'))
        if key!=self.selected:self.province_selection.clear()
        self.selected=key;self.show_details()
        def done(d):
            self.overlay=Image.open(io.BytesIO(base64.b64decode(d['image'].split(',',1)[1]))).copy();self.box=d['box'];self.marker=d['xy']
            if focus:
                x,y,w,h=d['focus'];cw,ch=self.canvas.winfo_width(),self.canvas.winfo_height()
                self.scale=max(self.fit(),min(3,cw/(w+160),ch/(h+160)));self.offset=[cw/2-(x+w/2)*self.scale,ch/2-(y+h/2)*self.scale]
            self.draw()
        self.selection_generation+=1;generation=self.selection_generation;self.selecting=True
        if self.selection_future:self.selection_future.cancel()
        selected=set(self.province_selection);preview=getattr(self,'display_preview',self.app.preview)
        def work():
            try:result=self.app.region(key,selected,preview);self.events.put(('selection',generation,done,result,None))
            except Exception as e:self.events.put(('selection',generation,done,None,diagnostic(e)))
        self.selection_future=self.selection_pool.submit(work)

    def show_details(self):
        r=self.rows.get(self.selected)
        if not r:self.details.set(self.tr('点击地图或风险列表查看地区。'));self.target.set('');self.targets={};self.target_box.configure(values=[]);return
        self.details.set(f"{r['state_name']}\n{r['country_name']} · {r['country']}\n"+'、'.join(self.tr(RISKS[k]) for k in r['risks'])+self.tr('\n人口：{0}\n耕地 / 地块：{1} / {2}\n岗位容量：{3}\n失业缺口：{4}\n市场：{5} · {6} 国\n预计接入：{7}\n本地食物缺口：{8}\n市场食物缺口：{9}\n有效食物缺口：{10}', f"{self.fmt(r['population'])}", f"{self.fmt(r['arable'])}", f"{self.fmt(r['province_count'])}", f"{self.fmt(r['job_capacity'])}", f"{self.pct(r['estimated_unemployment'])}", f"{r['market_name']}", f"{r['market_members']}", f"{self.pct(r['market_access_estimate'])}", f"{self.pct(r['local_food_shortfall'])}", f"{self.pct(r['market_food_shortfall'])}", f"{self.pct(r['food_shortfall'])}"))
        recommendation=r.get('arable_advice',{}).get('relief')
        if recommendation:
            self.details.set(self.details.get()+self.tr('\n\n耕地建议：')+(self.tr('整州调至 ')+self.fmt(recommendation['state_base'])+self.tr('（增加 ')+self.fmt(recommendation['added_base'])+self.tr('），可使本地区容量缺口低于严重失业阈值。') if recommendation['available'] else self.tr(recommendation['reason'])))
        elif r.get('arable_advice_error'):self.details.set(self.details.get()+self.tr('\n耕地建议：')+self.tr(r['arable_advice_error']))
        self.fill_targets()

    def fill_targets(self):
        r=self.rows.get(self.selected)
        if not r:return
        region=self.kind.get()!=self.tr('整个国家');parts=[r] if region else [v for v in self.rows.values() if v['country']==r['country']]
        adjacent={n for v in parts for n in v['neighbors']};targets={}
        for key in sorted(adjacent):
            v=self.rows.get(key)
            if v and v['country']!=r['country'] and (not region or v['state']==r['state']):targets[v['country_name']+' · '+v['country']]=v['country']
        self.targets=targets;self.target_box.configure(values=list(targets))
        if self.target.get() not in targets:self.target.set(next(iter(targets),self.tr('无可用的陆地相邻目标')))

    def pick(self):
        if not self.selected:self.status.set(self.tr('请先选择来源地区'));return
        self.picking=not self.picking;self.pick_btn.configure(text=self.tr('取消地图点选') if self.picking else self.tr('从地图点选目标'))
        self.status.set(self.tr('请在地图或列表中点击要并入的相邻国家') if self.picking else self.tr('已取消点选'))

    def cancel_pick(self):
        self.picking=False;self.pick_btn.configure(text=self.tr('从地图点选目标'))

    def merge(self):
        if not self.require_project():return
        r=self.rows.get(self.selected);target=self.targets.get(self.target.get())
        if not r or not target:messagebox.showinfo(self.tr('请选择地区'),self.tr('先选择来源地区和相邻目标国家。'),parent=self.root);return
        op=dict(kind='country' if self.kind.get()==self.tr('整个国家') else 'region',source=r['country'],target=target)
        if op['kind']=='region':op['state']=r['state']
        self.review_edit(op,self.tr('将 {0} 的{1}并入 {2}', f"{r['country_name']}", f'{self.kind.get()}', f'{self.target.get()}'))

    def operation_label(self,op):
        if op['kind']=='arable_bulk':return self.tr('批量补耕地 · ')+str(len(op['targets']))+self.tr(' 个州')
        if op['kind']=='bulk':return self.tr('批量整合 ')+str(len(op['transfers']))+self.tr(' 个地区')
        if op['kind']=='population':return self.tr('人口削减 · ')+str(len(op['targets']))+self.tr(' 个地区')
        if op['kind']=='arable':return op['state']+self.tr(' 耕地 → ')+str(op['value'])
        if op['kind']=='building':return op['state']+' / '+op['country']+self.tr(' 建筑调整')
        if op['kind']=='province':return str(len(op['provinces']))+self.tr(' 地块 → ')+op['target_state']+' / '+op['target']
        return op['source']+' → '+op['target']

    def bulk_dialog(self):
        if self.busy or not self.require_project():return
        d,f=self.dialog(self.tr('按州 / 战略地区批量整合'))
        scopes=[self.tr('全图：逐州整合风险地区'),self.tr('当前州：仅风险地区'),self.tr('当前州：全部分属地区'),
                self.tr('全图：逐战略地区整合风险地区'),self.tr('当前战略地区：仅风险地区'),self.tr('当前战略地区：全部分属地区')]
        scope=tk.StringVar(value=scopes[0]);ttk.Combobox(f,textvariable=scope,values=scopes,state='readonly',width=38).pack(fill='x',pady=8)
        conditions={k:tk.BooleanVar(value=k in ('market_food','unemployment')) for k in ('market_food','local_food','food','unemployment')}
        for k,label in [('market_food',self.tr('市场缺粮：共同市场整体供给不足')),('local_food',self.tr('本地缺粮：本地区生产不足（市场可能足够）')),('food',self.tr('接入后仍缺粮：结合本地和预计市场接入')),('unemployment',self.tr('严重失业'))]:
            ttk.Checkbutton(f,text=label,variable=conditions[k]).pack(anchor='w',pady=5)
        ttk.Label(f,text=self.tr('符合任一勾选条件即可；未知数据不自动选入。缺粮阈值沿用左侧参数。\n接收国为本州或整个战略地区内地块总数最多者，并列按 TAG 排序。\n战略地区整合允许跨州，可把某州地区交给原来不在该州的国家；不改变州界。\n整合不保证增加粮食供给。确认前列出筛选原因、政治调整和拆除选择；整批可撤销。'),wraplength=680).pack(anchor='w',pady=10)
        def prepare():
            from converter_edits import plan_bulk
            selected=self.rows.get(self.selected);idx=scopes.index(scope.get())
            if idx in (1,2,4,5) and not selected:messagebox.showinfo(self.tr('请选择地区'),self.tr('先关闭本窗口，在地图上选择范围内的一个地区。'),parent=d);return
            if idx in (4,5) and not selected.get('strategic_region'):messagebox.showinfo(self.tr('战略地区未知'),self.tr('当前州没有可用的战略地区定义，请改用州级整合。'),parent=d);return
            risks=[k for k,v in conditions.items() if v.get()] if idx not in (2,5) else []
            if idx not in (2,5) and not risks:messagebox.showinfo(self.tr('请选择风险'),self.tr('至少勾选一种风险。'),parent=d);return
            try:op=plan_bulk(list(self.rows.values()),'state' if idx in (2,5) else 'risk',
                selected['state'] if idx in (1,2) else None,risks,grouping='strategic_region' if idx>=3 else 'state',
                region=selected.get('strategic_region') if idx in (4,5) else None,food_threshold=self.app.project['settings']['food_shortfall_threshold'])
            except ValueError as e:messagebox.showinfo(self.tr('没有需要整合的地区'),self.tr(e),parent=d);return
            d.destroy();self.review_edit(op,scope.get()+'：'+str(len(op['transfers']))+self.tr(' 个地区'))
        ttk.Button(f,text=self.tr('预览一键整合'),command=prepare,style='Accent.TButton').pack(anchor='e',pady=8)

    def arable_bulk_dialog(self):
        if self.busy or not self.require_project():return
        d,f=self.dialog(self.tr('批量为严重失业地区补耕地'))
        ranges=[self.tr('全图'),self.tr('当前战略地区'),self.tr('当前国家'),self.tr('当前州')];scope=tk.StringVar(value=ranges[0])
        ttk.Combobox(f,textvariable=scope,values=ranges,state='readonly',width=44).pack(fill='x',pady=6)
        limit=tk.StringVar(value='2');line=ttk.Frame(f);line.pack(fill='x',pady=8)
        ttk.Label(line,text=self.tr('整州耕地最多增至操作前的几倍')).pack(side='left');ttk.Entry(line,textvariable=limit,width=8).pack(side='right')
        modes=[self.tr('降到严重失业阈值以下'),self.tr('岗位容量覆盖全部劳动力')];mode=tk.StringVar(value=modes[0])
        ttk.Combobox(f,textvariable=mode,values=modes,state='readonly',width=44).pack(fill='x',pady=6)
        ttk.Label(f,text=self.tr('只处理严重失业地区。同一州多国需要补地时取满足需求的最大值，只增加一次。\n倍率以上次操作后的整州基础耕地为基准；全局耕地系数另行计算。零耕地州需先手动补地。\n达到上限仍可能失业；预览会显示剩余缺口。新增耕地提供自给农业容量，不保证实际招聘或收入。'),wraplength=670).pack(anchor='w',pady=12)
        def prepare():
            from converter_arable_advice import plan_bulk
            selected=self.rows.get(self.selected);idx=ranges.index(scope.get())
            if idx and not selected:messagebox.showinfo(self.tr('请选择地区'),self.tr('先选择范围内的一个地区，或改用全图。'),parent=d);return
            if idx==1 and not selected.get('strategic_region'):messagebox.showinfo(self.tr('战略地区未知'),self.tr('请选择其他范围。'),parent=d);return
            try:factor=float(limit.get())
            except ValueError:messagebox.showinfo(self.tr('倍率无效'),self.tr('请输入大于 1 且不超过 100 的倍率。'),parent=d);return
            key={1:'strategic_region',2:'country',3:'state'}.get(idx)
            choices=[r['id'] for r in self.rows.values() if not key or r.get(key)==selected.get(key)]
            options=deepcopy(self.app.project['settings']);ops=deepcopy(self.app.project['merges']);goal='relief' if mode.get()==modes[0] else 'full'
            d.destroy()
            def work():
                try:return plan_bulk(self.app.world,options,ops,choices,factor,goal)
                except ValueError as e:return diagnostic(e)
            def done(op):
                if isinstance(op,str):messagebox.showinfo(self.tr('没有补地方案'),self.tr(op),parent=self.root);return
                self.review_edit(op,self.tr('批量补耕地 · ')+scope.get()+self.tr(' · 上限 ')+str(factor)+self.tr(' 倍'))
            self.submit(self.tr('计算批量补耕地方案'),work,done)
        ttk.Button(f,text=self.tr('预览批量补耕地'),command=prepare,style='Accent.TButton').pack(anchor='e')

    def population_dialog(self):
        if self.busy or not self.require_project():return
        d,f=self.dialog(self.tr('削减人口 / 批量调节'))
        ranges=[self.tr('当前所选地区'),self.tr('当前州'),self.tr('当前国家'),self.tr('当前战略地区'),self.tr('全图')]
        scope=tk.StringVar(value=ranges[0]);ttk.Combobox(f,textvariable=scope,values=ranges,state='readonly',width=44).pack(fill='x',pady=6)
        filters={self.tr('全部地区'):(), self.tr('严重失业'):('unemployment',),self.tr('市场缺粮'):('market_food',),self.tr('本地缺粮'):('local_food',),
                 self.tr('接入后缺粮'):('food',),self.tr('严重失业或接入后缺粮'):('unemployment','food')}
        condition=tk.StringVar(value=self.tr('严重失业'));ttk.Combobox(f,textvariable=condition,values=list(filters),state='readonly').pack(fill='x',pady=6)
        modes=[self.tr('按比例削减'),self.tr('按现有岗位容量削减（覆盖全部劳动力）')];mode=tk.StringVar(value=modes[0])
        ttk.Combobox(f,textvariable=mode,values=modes,state='readonly',width=44).pack(fill='x',pady=6)
        percent=tk.StringVar(value='10');line=ttk.Frame(f);line.pack(fill='x',pady=6)
        ttk.Label(line,text=self.tr('按比例模式：削减百分比')).pack(side='left');ttk.Entry(line,textvariable=percent,width=8).pack(side='right')
        ttk.Label(f,text=self.tr('这是玩家主动修改人口方案，并非游戏中的迁移。按原文化、宗教比例分配削减，每个有人地区至少保留 1 人。\n岗位模式按当前岗位容量估算；岗位未知的地区会跳过。不会自动拆建筑或缩编军队，劳动力和食物风险会重新计算。\n确认前列出实际减少人数和地区。整批可一次撤销；不改原始存档。'),wraplength=670).pack(anchor='w',pady=12)
        def prepare():
            from converter_edits import risk_reasons,plan_population
            selected=self.rows.get(self.selected);idx=ranges.index(scope.get())
            if idx!=4 and not selected:messagebox.showinfo(self.tr('请选择地区'),self.tr('先选择一个地区，或改用全图范围。'),parent=d);return
            if idx==3 and not selected.get('strategic_region'):messagebox.showinfo(self.tr('战略地区未知'),self.tr('当前州没有可用的战略地区定义，请改用其他范围。'),parent=d);return
            try:value=float(percent.get()) if mode.get()==modes[0] else 10
            except ValueError:messagebox.showinfo(self.tr('比例无效'),self.tr('请输入大于 0 且小于 100 的削减百分比。'),parent=d);return
            choices=[]
            for row in self.rows.values():
                if idx<4:
                    key=('id','state','country','strategic_region')[idx]
                    if row.get(key)!=selected.get(key):continue
                risks=filters[condition.get()]
                if risks and not risk_reasons(row,risks,self.app.project['settings']['food_shortfall_threshold']):continue
                choices.append(row['id'])
            chosen_mode='percent' if mode.get()==modes[0] else 'jobs'
            d.destroy();options=deepcopy(self.app.project['settings']);operations=deepcopy(self.app.project['merges'])
            def work():
                try:return plan_population(self.app.world,options,operations,choices,chosen_mode,value)
                except ValueError as e:return diagnostic(e)
            def done(op):
                if isinstance(op,str):messagebox.showinfo(self.tr('没有人口削减方案'),self.tr(op),parent=self.root);return
                self.review_edit(op,scope.get()+' · '+condition.get()+' · '+mode.get())
            self.submit(self.tr('计算人口削减范围'),work,done)
        ttk.Button(f,text=self.tr('预览人口削减'),command=prepare,style='Accent.TButton').pack(anchor='e')

    def review_edit(self,op,label):
        if self.busy:return
        self.cancel_pick()
        options=deepcopy(self.app.project['settings']);ops=deepcopy(self.app.project['merges'])+[op]
        prior=set(self.app.preview.get('adjustments',[]))
        def prepare():
            preview=self.app.world.preview(options,ops);variants=[(op,preview)]
            if op['kind']=='bulk' and preview['bulk_outcomes'][-1].get('conflicts') and not op.get('demolish'):
                automatic=dict(op,demolish=True)
                variants.append((automatic,self.app.world.preview(options,ops[:-1]+[automatic])))
            return variants
        def done(variants):
            d,f=self.dialog(self.tr('确认编辑及影响'));d.resizable(True,True)
            ttk.Label(f,text=label,wraplength=720).pack(anchor='w',pady=8)
            choice=tk.IntVar(value=0)
            if len(variants)>1:
                ttk.Label(f,text=self.tr('存在建筑兼容冲突，请选择处理方式。拆除清单及其他影响见下方。')).pack(anchor='w')
                ttk.Radiobutton(f,text=self.tr('保留建筑，跳过冲突地区'),variable=choice,value=0,command=lambda:render()).pack(anchor='w',pady=5)
                ttk.Radiobutton(f,text=self.tr('自动拆除冲突建筑后整合（整批可撤销）'),variable=choice,value=1,command=lambda:render()).pack(anchor='w',pady=5)
            area=ttk.Frame(f);area.pack(fill='both',expand=True)
            text=tk.Text(area,width=90,height=18,wrap='word',font=('Microsoft YaHei UI',10))
            scroll=ttk.Scrollbar(area,command=text.yview);text.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
            buttons=ttk.Frame(f);buttons.pack(fill='x',pady=10)
            def accept():
                chosen,preview=variants[choice.get()]
                if chosen['kind']=='bulk' and not preview['bulk_outcomes'][-1]['applied']:return
                d.destroy();self.mutate('edit',{'operation':chosen})
            apply=ttk.Button(buttons,text=self.tr('确认应用'),command=accept,style='Accent.TButton');apply.pack(side='right')
            ttk.Button(buttons,text=self.tr('取消'),command=d.destroy).pack(side='right',padx=8)
            def render():
                chosen,preview=variants[choice.get()]
                notes=[self.tr(n) for n in preview.get('adjustments',[]) if n not in prior]
                apply.state(['!disabled'])
                if chosen['kind']=='bulk':
                    outcome=preview['bulk_outcomes'][-1];skipped={(m['state'],m['source']) for m in outcome['skipped']}
                    conflicts=outcome.get('conflicts',[])
                    lines=[r['state']+' / '+r['source']+' → '+r['target']+'：'+self.labels().get(r['building'],r['building'])+' × '+str(r['levels'])+'；'+self.tr(r['reason']) for r in conflicts]
                    notes=[self.tr('将整合 ')+str(outcome['applied'])+self.tr(' 个地区；跳过 ')+str(len(skipped))+self.tr(' 个地区。'),
                        (self.tr('将拆除') if chosen.get('demolish') else self.tr('将保留'))+self.tr('以下冲突建筑，共 ')+str(sum(r['levels'] for r in conflicts))+self.tr(' 级：')]+lines+['']+notes+['',self.tr('整合层级：')+(self.tr('战略地区') if chosen.get('grouping')=='strategic_region' else self.tr('州')),self.tr('整合范围与筛选依据：')]+[m['state']+' / '+m['source']+' → '+m['target']+'；'+('、'.join(self.tr(RISKS[k]) for k in m.get('reasons',[])) or self.tr('整个范围'))+self.tr('（市场缺口 ')+self.pct(m.get('market_food_shortfall'))+self.tr(' / 本地缺口 ')+self.pct(m.get('local_food_shortfall'))+'）' for m in chosen['transfers'] if (m['state'],m['source']) not in skipped]
                    if not outcome['applied']:apply.state(['disabled']);notes.insert(1,self.tr('当前选择没有可应用的整合；可改选自动拆除或取消。'))
                if chosen['kind']=='arable_bulk':
                    before_rows={r['id']:self.localize_row(r) for r in self.app.preview['rows']};after_rows={r['id']:self.localize_row(r) for r in preview['rows']}
                    lines=[self.labels().get(i['state'],i['state'])+'：'+self.fmt(i['before'])+' → '+self.fmt(i['value'])+self.tr('（上限 ')+self.fmt(i['cap'])+'）' for i in chosen['targets']]
                    lines+=['',self.tr('所选地区失业容量缺口：')]+[before_rows[k]['state_name']+' / '+before_rows[k]['country_name']+'：'+self.pct(before_rows[k]['estimated_unemployment'])+' → '+self.pct(after_rows[k]['estimated_unemployment'])+(self.tr('；达到倍率上限，仍需其他措施') if k in chosen['limited'] else '') for k in chosen['regions']]
                    notes=lines+['',self.tr('跳过地区：')]+[i['region']+'：'+self.tr(i['reason']) for i in chosen['skipped']]+notes
                if chosen['kind']=='population':
                    before_rows={r['id']:self.localize_row(r) for r in self.app.preview['rows']};after_rows={r['id']:self.localize_row(r) for r in preview['rows']}
                    old=self.app.preview['summary']['population'];new=preview['summary']['population']
                    lines=[]
                    for item in chosen['targets']:
                        key=item['state']+'|'+item['country'];a,b=before_rows[key],after_rows[key]
                        lines.append(a['state_name']+' / '+a['country_name']+'：'+self.fmt(a['population'])+' → '+self.fmt(b['population'])+self.tr('（减少 ')+self.fmt(a['population']-b['population'])+self.tr('）；失业 ')+self.pct(a['estimated_unemployment'])+' → '+self.pct(b['estimated_unemployment'])+self.tr('，有效食物缺口 ')+self.pct(a['food_shortfall'])+' → '+self.pct(b['food_shortfall']))
                    notes=[self.tr('将削减 ')+str(len(chosen['targets']))+self.tr(' 个地区的人口。'),self.tr('世界总人口：')+self.fmt(old)+' → '+self.fmt(new)+self.tr('；实际减少 ')+self.fmt(old-new)+self.tr(' 人（已计入全局系数）。'),
                           self.tr('岗位未知而跳过的地区：')+str(len(chosen.get('skipped_unknown',[]))),
                           self.tr('现有建筑、军队不会自动缩减；减少人口也可能降低自给农业产出。'),'']+lines+['']+notes
                if any(r['overbuilt_arable'] for r in preview['rows']):notes.append(self.tr('农业建筑超过可用耕地的地区：')+str(sum(r['overbuilt_arable']>0 for r in preview['rows'])))
                text.configure(state='normal');text.delete('1.0','end');text.insert('1.0','\n'.join(notes) if notes else self.tr('已通过编辑检查。人口、地块与建筑将按预览写入独立导出，可撤销。'));text.configure(state='disabled')
            render()
        self.submit(self.tr('预览编辑影响'),prepare,done)

    def edit_dialog(self):
        if self.busy or not self.require_project():return
        row=self.rows.get(self.selected)
        if not row:messagebox.showinfo(self.tr('请选择地区'),self.tr('先点击地图或列表选择一个地区。'),parent=self.root);return
        d,f=self.dialog(self.tr('编辑 ')+row['state_name']);d.resizable(True,True);d.geometry('870x620')
        notebook=ttk.Notebook(f);notebook.pack(fill='both',expand=True)
        land=ttk.Frame(notebook,padding=16);buildings=ttk.Frame(notebook,padding=16);provinces=ttk.Frame(notebook,padding=16)
        notebook.add(land,text=self.tr('整州耕地'));notebook.add(buildings,text=self.tr('分属地区建筑'));notebook.add(provinces,text=self.tr('地图地块 / 州界'))
        ttk.Label(land,text=row['state_name']+' · '+row['state'],font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w',pady=10)
        ttk.Label(land,text=self.tr('设置整个州的基础耕地总量；导出时再乘左侧的全局耕地系数。\n州内各国家按地块比例分得耕地。'),wraplength=750).pack(anchor='w',pady=10)
        amount=tk.StringVar(value=str(row['state_arable']));ttk.Entry(land,textvariable=amount,width=18).pack(anchor='w',pady=10)
        def apply_land():
            try:n=int(amount.get())
            except ValueError:messagebox.showerror(self.tr('数值无效'),self.tr('耕地必须为整数。'),parent=d);return
            d.destroy();self.review_edit(dict(kind='arable',state=row['state'],value=n),self.tr('整州基础耕地 → ')+str(n))
        ttk.Button(land,text=self.tr('预览耕地调整'),command=apply_land).pack(anchor='w',pady=10)
        advice_text=tk.StringVar(value=self.tr('可计算增加多少整州耕地，能让当前所选地区退出严重失业提醒。'))
        ttk.Label(land,textvariable=advice_text,wraplength=750,justify='left').pack(anchor='w',pady=8)
        suggestions={};advice_buttons=ttk.Frame(land);advice_buttons.pack(fill='x',pady=6)
        def use_advice(key):
            result=suggestions.get(key)
            if result and result['available']:amount.set(str(result['state_base']))
        relief_button=ttk.Button(advice_buttons,text=self.tr('填入缓解失业建议值'),command=lambda:use_advice('relief'),state='disabled')
        full_button=ttk.Button(advice_buttons,text=self.tr('填入全部劳动力容量参考值'),command=lambda:use_advice('full'),state='disabled')
        def calculate_land():
            if self.busy:return
            from converter_arable_advice import advice
            options=deepcopy(self.app.project['settings']);operations=deepcopy(self.app.project['merges'])
            def work():
                try:return advice(self.app.world,options,operations,row['id'])
                except (ValueError,KeyError) as e:return diagnostic(e)
            def done(result):
                if not d.winfo_exists():return
                if isinstance(result,str):advice_text.set(self.tr('暂不能计算：')+result);return
                suggestions.update(result)
                lines=[row['country_name']+' / '+row['state_name']+self.tr(' · 当前失业容量缺口 ')+self.pct(result['unemployment']),
                    self.tr('每新增 1 单位本地区可用耕地，约提供 ')+self.fmt(result['jobs_per_arable'])+self.tr(' 个自给农业岗位。')]
                for key,label,button in [('relief',self.tr('降到 ')+self.pct(result['threshold'])+self.tr(' 严重失业阈值以下'),relief_button),('full',self.tr('岗位容量覆盖全部劳动力'),full_button)]:
                    value=result[key]
                    if not value['available']:lines.append(label+'：'+self.tr(value['reason']));continue
                    button.state(['!disabled'])
                    if value['already_satisfied']:lines.append(label+self.tr('：当前已满足，无需新增。'))
                    else:lines.append(label+self.tr('：整州基础耕地调至 ')+self.fmt(value['state_base'])+self.tr('（新增 ')+self.fmt(value['added_base'])+self.tr('）；本地区分得 ')+self.fmt(value['region_arable'])+self.tr('，预计缺口 ')+self.pct(value['unemployment'])+'。')
                lines+=[self.tr('已计入全局耕地系数 ')+str(result['arable_multiplier'])+self.tr('、州内地块分配及已有农业建筑占地。'),
                    self.tr('建议针对当前所选地区，不保证本州其他地区也退出提醒。新增耕地主要增加自给农业岗位容量，不等于实际招聘或收入改善；土地与食物需求也会随之改变。')]
                advice_text.set('\n'.join(lines))
            self.submit(self.tr('估算耕地与失业容量'),work,done)
        ttk.Button(advice_buttons,text=self.tr('计算所需耕地'),command=calculate_land).pack(side='left',padx=(0,5))
        relief_button.pack(side='left',padx=5);full_button.pack(side='left',padx=5)
        d.after_idle(calculate_land)
        parts={r['country_name']+' · '+r['country']:r for r in self.rows.values() if r['state']==row['state']}
        choice=tk.StringVar(value=next(k for k,v in parts.items() if v['id']==row['id']))
        cb=ttk.Combobox(buildings,textvariable=choice,values=list(parts),state='readonly',width=50);cb.pack(fill='x')
        ttk.Label(buildings,text=self.tr('切换本州所属国家，选择建筑并设置等级。0 为移除；自给建筑由剩余耕地自动产生。'),wraplength=750).pack(anchor='w',pady=8)
        area=ttk.Frame(buildings);area.pack(fill='both',expand=True)
        table=ttk.Treeview(area,columns=('name','level'),show='headings',selectmode='browse',height=11)
        table.heading('name',text=self.tr('建筑'));table.heading('level',text=self.tr('当前等级'));table.column('name',width=570);table.column('level',width=90)
        scroll=ttk.Scrollbar(area,orient='vertical',command=table.yview);table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)
        controls=ttk.Frame(buildings);controls.pack(fill='x',pady=10)
        query=tk.StringVar();ttk.Label(controls,text=self.tr('筛选')).pack(side='left');ttk.Entry(controls,textvariable=query,width=25).pack(side='left',padx=5)
        level=tk.StringVar(value='0');ttk.Label(controls,text=self.tr('等级')).pack(side='left');ttk.Entry(controls,textvariable=level,width=8).pack(side='left',padx=5)
        def fill(*args):
            r=parts[choice.get()];table.delete(*table.get_children());q=query.get().lower()
            keys=[k for k in self.app.world.target.buildings if not k.startswith('building_subsistence')]
            for k in sorted(keys,key=lambda k:(-r['buildings'].get(k,0),k)):
                name=self.labels().get(k,k)
                if q in (name+' '+k).lower():table.insert('','end',iid=k,values=(name+' · '+k,r['buildings'].get(k,0)))
        cb.bind('<<ComboboxSelected>>',fill);query.trace_add('write',fill);fill()
        table.bind('<<TreeviewSelect>>',lambda e:level.set(str(parts[choice.get()]['buildings'].get(table.selection()[0],0))) if table.selection() else None)
        def apply_building():
            if not table.selection():messagebox.showinfo(self.tr('请选择建筑'),self.tr('请选择要调整的建筑。'),parent=d);return
            try:n=int(level.get())
            except ValueError:messagebox.showerror(self.tr('数值无效'),self.tr('等级必须为整数。'),parent=d);return
            r=parts[choice.get()];k=table.selection()[0];d.destroy()
            self.review_edit(dict(kind='building',state=r['state'],country=r['country'],levels={k:n}),self.labels().get(k,k)+' → '+str(n))
        ttk.Button(controls,text=self.tr('预览建筑调整'),command=apply_building).pack(side='right')
        ttk.Label(provinces,text=self.tr('选择一个或多个地块（Ctrl / Shift 多选），并转入相邻地区。\n也可在主地图 Ctrl + 点击选取同一地区的地块，再打开本窗口。人口与建筑按地块比例随之分配。'),wraplength=760).pack(anchor='w',pady=8)
        area=ttk.Frame(provinces);area.pack(fill='both',expand=True)
        listing=tk.Listbox(area,selectmode='extended',exportselection=False,font=('Consolas',11))
        sy=ttk.Scrollbar(area,command=listing.yview);listing.configure(yscrollcommand=sy.set);sy.pack(side='right',fill='y');listing.pack(fill='both',expand=True)
        for i,p in enumerate(row['provinces']):
            listing.insert('end',p)
            if p in self.province_selection:listing.selection_set(i)
        targets={self.rows[k]['state_name']+' / '+self.rows[k]['country_name']+' · '+k:self.rows[k] for k in row['neighbors']}
        dest=tk.StringVar(value=next(iter(targets),''));ttk.Combobox(provinces,textvariable=dest,values=list(targets),state='readonly',width=80).pack(fill='x',pady=10)
        def apply_provinces():
            selected=[row['provinces'][i] for i in listing.curselection()];target=targets.get(dest.get())
            if not selected or not target:messagebox.showinfo(self.tr('请选择地块和目标'),self.tr('至少选择一个地块和相邻目标地区。'),parent=d);return
            d.destroy();self.review_edit(dict(kind='province',provinces=selected,target=target['country'],target_state=target['state']),str(len(selected))+self.tr(' 个地块转入 ')+dest.get())
        ttk.Button(provinces,text=self.tr('预览地块转移'),command=apply_provinces).pack(anchor='e')
        def supplement():
            selected=[row['provinces'][i] for i in listing.curselection()]
            if len(selected)!=1:messagebox.showinfo(self.tr('请选择一个地块'),self.tr('补建按整合后的单个地块估算，请只选择一个。'),parent=d);return
            d.destroy();self.supplement_dialog(selected[0])
        ttk.Button(provinces,text=self.tr('按所选单地块计算补建…'),command=supplement).pack(anchor='e',pady=6)

    def supplement_dialog(self,province):
        if self.busy:return
        row=next((r for r in self.rows.values() if province in r['provinces']),None)
        if row is None:return
        d,f=self.dialog(self.tr('整合后单地块补建估算'))
        ttk.Label(f,text=row['state_name']+' / '+row['country_name']+' · '+province+self.tr('\n按当前地区均分估算地块需求，建筑数量写入该地区。'),wraplength=700).pack(anchor='w',pady=8)
        names={self.labels().get(k,k)+' · '+k:k for k in sorted(self.app.world.target.buildings) if not k.startswith('building_subsistence')}
        preferred=next((k for k in ('building_fishing_wharf','building_rice_farm','building_wheat_farm','building_rye_farm','building_maize_farm','building_livestock_ranch','building_food_industry') if k in row['buildings']), 'building_fishing_wharf')
        kind=tk.StringVar(value=next((label for label,k in names.items() if k==preferred),next(iter(names))))
        ttk.Label(f,text=self.tr('用于补建的建筑（可输入名称筛选后选择）')).pack(anchor='w')
        query=tk.StringVar();ttk.Entry(f,textvariable=query).pack(fill='x',pady=4)
        box=ttk.Combobox(f,textvariable=kind,values=list(names),state='readonly',width=70);box.pack(fill='x',pady=6)
        def filter_names(*args):
            values=[k for k in names if query.get().lower() in k.lower()];box.configure(values=values)
            if kind.get() not in values:kind.set(values[0] if values else '')
        query.trace_add('write',filter_names)
        goals={self.tr('市场接入后的食物缺口'):'food',self.tr('失业岗位缺口'):'unemployment'}
        goal=tk.StringVar(value=next(iter(goals)));ttk.Combobox(f,textvariable=goal,values=list(goals),state='readonly',width=36).pack(fill='x',pady=6)
        maximum=tk.StringVar(value='100');line=ttk.Frame(f);line.pack(fill='x',pady=6)
        ttk.Label(line,text=self.tr('本次最多新增等级（1–1000）')).pack(side='left');ttk.Entry(line,textvariable=maximum,width=8).pack(side='right')
        def calculate():
            try:
                limit=int(maximum.get());building=names[kind.get()]
                if not 1<=limit<=1000:raise ValueError()
            except (ValueError,KeyError):messagebox.showinfo(self.tr('请检查输入'),self.tr('请选择建筑，并输入 1–1000 的整数上限。'),parent=d);return
            metric=goals[goal.get()]
            options=deepcopy(self.app.project['settings']);operations=deepcopy(self.app.project['merges']);d.destroy()
            from converter_supplement import proposal
            def work():
                try:return proposal(self.app.world,options,operations,province,building,metric,limit)
                except ValueError as e:return diagnostic(e)
            def done(result):
                if isinstance(result,str):messagebox.showinfo(self.tr('没有补建方案'),self.tr(result),parent=self.root);return
                popup,body=self.dialog(self.tr('补建计算结果'))
                before,after=result['before'],result['after'];unit=self.tr('食物价值单位') if metric=='food' else self.tr('个岗位')
                lines=[province+self.tr(' · 估算人口 ')+self.fmt(result['population_share']),
                    self.tr('该地块分摊缺口：')+self.fmt(result['need_share'])+' '+unit,
                    self.labels().get(building,building)+self.tr('：建议新增 ')+str(result['added'])+self.tr(' 级'),
                    self.tr('所属地区食物缺口：')+self.pct(before['food_shortfall'])+' → '+self.pct(after['food_shortfall']),
                    self.tr('所属地区失业缺口：')+self.pct(before['estimated_unemployment'])+' → '+self.pct(after['estimated_unemployment'])]
                if result['limited']:lines.append(self.tr('受容量或本次上限约束；估算需求为 ')+str(result['wanted'])+self.tr(' 级，当前仅建议 ')+str(result['added'])+self.tr(' 级。'))
                lines+=['']+[self.tr(n) for n in result['notes']]
                ttk.Label(body,text='\n'.join(lines),wraplength=700,justify='left').pack(anchor='w',pady=10)
                def accept():popup.destroy();self.mutate('edit',{'operation':result['operation']})
                ttk.Button(body,text=self.tr('确认补建'),command=accept,style='Accent.TButton').pack(side='right',padx=6)
                ttk.Button(body,text=self.tr('取消'),command=popup.destroy).pack(side='right')
            self.submit(self.tr('计算所选地块补建'),work,done)
        ttk.Button(f,text=self.tr('计算补建方案'),command=calculate,style='Accent.TButton').pack(anchor='e',pady=10)

    def fit(self):return min(max(1,self.canvas.winfo_width())/8192,max(1,self.canvas.winfo_height())/4096)
    def home(self):
        self.scale=self.fit();self.offset=[(self.canvas.winfo_width()-8192*self.scale)/2,(self.canvas.winfo_height()-4096*self.scale)/2];self.draw()
    def draw(self):
        if self.map is None:return
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        if w<2 or h<2:return
        # Transform just the viewport, never allocate a zoomed world-sized bitmap.
        ox,oy=self.offset;inv=1/self.scale
        frame=self.map.transform((w,h),Image.Transform.AFFINE,(inv/2,0,-ox*inv/2,0,inv/2,-oy*inv/2),resample=Image.Resampling.NEAREST,fillcolor='#132531').convert('RGBA')
        if self.overlay is not None and self.box:
            x,y,_,_=self.box
            overlay=self.overlay.transform((w,h),Image.Transform.AFFINE,(inv,0,-ox*inv-x,0,inv,-oy*inv-y),resample=Image.Resampling.NEAREST)
            frame.alpha_composite(overlay)
        self.photo=ImageTk.PhotoImage(frame,master=self.root);self.canvas.delete('all');self.canvas.create_image(0,0,image=self.photo,anchor='nw')
        if self.marker:
            x=ox+self.marker[0]*self.scale;y=oy+self.marker[1]*self.scale;self.canvas.create_oval(x-6,y-6,x+6,y+6,outline='#ffe8a2',width=2)
    def zoom(self,factor,x=None,y=None):
        if self.map is None:return
        x=self.canvas.winfo_width()/2 if x is None else x;y=self.canvas.winfo_height()/2 if y is None else y
        new=max(self.fit()*.65,min(12,self.scale*factor));self.offset=[x-(x-self.offset[0])*new/self.scale,y-(y-self.offset[1])*new/self.scale];self.scale=new;self.draw()
    def wheel(self,e):self.zoom(1.18 if e.delta>0 else 1/1.18,e.x,e.y)
    def down(self,e):self.drag=(e.x,e.y,*self.offset)
    def move(self,e):
        if self.drag:self.offset=[self.drag[2]+e.x-self.drag[0],self.drag[3]+e.y-self.drag[1]];self.draw()
    def up(self,e):
        drag=self.drag;self.drag=None
        if not drag or abs(e.x-drag[0])+abs(e.y-drag[1])>4 or not self.rows:return
        hit=self.app.hit(int((e.x-self.offset[0])/self.scale),int((e.y-self.offset[1])/self.scale),getattr(self,'display_preview',None))
        if hit['id']:
            if e.state&4:
                if self.selected!=hit['id']:self.province_selection.clear()
                p=hit['province']
                if p in self.province_selection:self.province_selection.remove(p)
                else:self.province_selection.add(p)
                selected=set(self.province_selection);self.select(hit['id']);self.province_selection=selected
                self.status.set(self.tr('已选 ')+str(len(selected))+self.tr(' 个地块；点击“编辑耕地 / 建筑 / 地块”转移'))
            else:self.select(hit['id'])

    def load_layer(self):
        if self.busy or not self.rows:return
        key=self.layers[self.layer.get()]
        descriptions={'market_food':self.tr('共同市场总体食物缺口；同一市场同色。'),
            'local_food':self.tr('各地块按所属分属地区的本地产出与需求着色，不计市场补给；并非独立地块级统计。'),
            'food':self.tr('预计市场接入后的有效食物缺口。'),
            'market':self.tr('颜色区分市场归属，不代表食物是否充足。'),
            'strategic_region':self.tr('颜色区分游戏战略地区；可在此层级跨州整合。')}
        self.legend.set(descriptions.get(key,self.tr('点击地块查看地区数据。'))+(self.tr(' 绿：无缺口 · 黄：低于提醒阈值 · 红：达到阈值 · 灰：未知') if key in ('market_food','local_food') else ''))
        if key in self.layer_cache:self.map=self.layer_cache[key];self.draw();return
        def done(image):self.layer_cache[key]=image;self.map=image;self.draw()
        self.submit(self.tr('绘制风险地图'),lambda:Image.open(io.BytesIO(self.app.image(key))).copy(),done)

    def dialog(self,title):
        d=tk.Toplevel(self.root);d.title(title);d.transient(self.root);d.grab_set();d.resizable(True,False)
        d.geometry('+%d+%d'%(self.root.winfo_rootx()+100,self.root.winfo_rooty()+80))
        frame=ttk.Frame(d,padding=18);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
        return d,frame

    def path_field(self,frame,row,label,value,kind='directory'):
        var=tk.StringVar(value=value);ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=7,padx=(0,12))
        ttk.Entry(frame,textvariable=var,width=65).grid(row=row,column=1,sticky='ew',pady=7)
        def browse():
            options=dict(parent=frame.winfo_toplevel(),title=label)
            current=Path(var.get()).expanduser()
            if current.exists():options['initialdir']=str(current if current.is_dir() else current.parent)
            if kind=='directory':path=filedialog.askdirectory(**options,mustexist=True)
            else:path=filedialog.askopenfilename(**options,filetypes=[(self.tr('EU5 存档'),'*.eu5'),(self.tr('所有文件'),'*.*')] if kind=='save' else [(self.tr('V3 开局存档'),'*.v3'),(self.tr('已解码文本'),'*.txt'),(self.tr('所有文件'),'*.*')] if kind=='baseline' else [(self.tr('JSON 文件'),'*.json'),(self.tr('所有文件'),'*.*')])
            if path:var.set(path)
        ttk.Button(frame,text=self.tr('浏览…'),command=browse).grid(row=row,column=2,padx=(8,0))
        return var

    def open_dialog(self):
        if self.busy:return
        d,f=self.dialog(self.tr('打开项目 / 转换结果'));defaults=self.app.defaults();projects=defaults['projects'];candidates=defaults['candidates']
        names=[self.tr('新建项目')]+[p['name']+' · '+p['id'][:6] for p in projects];choice=tk.StringVar(value=names[0])
        ttk.Label(f,text=self.tr('已保存项目')).grid(row=0,column=0,sticky='w');ttk.Combobox(f,textvariable=choice,values=names,state='readonly',width=62).grid(row=0,column=1,sticky='ew')
        labels=[c.get('date','')+' · '+c['name']+' · '+str(i+1) for i,c in enumerate(candidates)];candidate=tk.StringVar(value=labels[0] if labels else '')
        ttk.Label(f,text=self.tr('已生成的结果')).grid(row=1,column=0,sticky='w');cb=ttk.Combobox(f,textvariable=candidate,values=labels,state='readonly');cb.grid(row=1,column=1,sticky='ew',pady=8)
        package=self.path_field(f,2,self.tr('转换结果目录'),candidates[0]['path'] if candidates else '')
        game=self.path_field(f,3,'Victoria 3 / game',defaults['game'])
        cb.bind('<<ComboboxSelected>>',lambda e:package.set(candidates[labels.index(candidate.get())]['path']))
        ttk.Label(f,text=self.tr('结果目录应包含 package_report.json；EU5 原始存档请使用主窗口的“导入 EU5 存档”。'),wraplength=650).grid(row=4,column=0,columnspan=3,pady=10)
        def submit():
            idx=names.index(choice.get())
            if idx:body={'id':projects[idx-1]['id']}
            else:
                if not (Path(package.get())/'package_report.json').is_file():messagebox.showerror(self.tr('目录不正确'),self.tr('没有找到 package_report.json。请选择已生成的转换结果目录。'),parent=d);return
                body=dict(package=package.get(),game=game.get(),name=self.tr('转换世界 · ')+datetime.now().strftime('%m-%d %H:%M'))
            d.destroy();self.load(body)
        ttk.Button(f,text=self.tr('打开并计算风险'),command=submit,style='Accent.TButton').grid(row=5,column=1,sticky='e');ttk.Button(f,text=self.tr('取消'),command=d.destroy).grid(row=5,column=2,padx=8)

    def initialize_dialog(self):
        if self.busy:return
        d,f=self.dialog(self.tr('准备转换规则'))
        defaults=self.app.defaults()
        remembered=self.app.workspace/'conversion_inputs.json'
        prior=read(remembered) if remembered.exists() else {}
        eu5=self.path_field(f,0,self.tr('EU5 安装目录'),prior.get('eu5',defaults['eu5']))
        game=self.path_field(f,1,'Victoria 3 / game',prior.get('game',defaults['game']))
        baseline=self.path_field(f,2,self.tr('V3 原版开局存档'),prior.get('baseline',''),kind='baseline')
        ttk.Label(f,text=self.tr('首次使用时先准备规则。请在 Victoria 3 1.13.11 中禁用模组，新开 1836 年战役，暂停并立即保存。\n选择该 .v3 存档后，程序从本机游戏生成所需资源；原存档、游戏文件和已有规则保持不变。'),wraplength=700).grid(row=3,column=0,columnspan=3,sticky='w',pady=12)
        def submit():
            inputs=dict(eu5=eu5.get().strip(),game=game.get().strip(),baseline=baseline.get().strip())
            for key in ('eu5','game','baseline'):
                path=Path(inputs[key])
                if not inputs[key] or not (path.is_file() if key=='baseline' else path.is_dir()):
                    messagebox.showerror(self.tr('路径无效'),self.tr('请选择有效的游戏目录和基准存档。'),parent=d);return
            d.destroy()
            def work():
                from initialize_converter import initialize
                return initialize(ROOT,self.app.workspace,**inputs,progress=lambda msg:self.events.put(('progress',msg)))
            def done(result):
                write(remembered,{**prior,**inputs,'eu5':result['eu5'],'game':result['game'],'rules':result['rules']})
                self.status.set(self.tr('规则已准备好，可导入 EU5 存档。'))
                messagebox.showinfo(self.tr('规则准备完成'),self.tr('已生成并校验转换规则。现在可以导入 EU5 存档。'),parent=self.root)
            self.submit(self.tr('准备转换规则'),work,done)
        ttk.Button(f,text=self.tr('生成规则'),command=submit,style='Accent.TButton').grid(row=4,column=1,sticky='e')
        ttk.Button(f,text=self.tr('取消'),command=d.destroy).grid(row=4,column=2,padx=8)

    def convert_dialog(self):
        if self.busy:return
        d,f=self.dialog(self.tr('导入 EU5 存档'));defaults=self.app.defaults()
        remembered=self.app.workspace/'conversion_inputs.json';prior=read(remembered) if remembered.exists() else {}
        save=self.path_field(f,0,self.tr('EU5 存档'),prior.get('save',''),kind='save');eu5=self.path_field(f,1,self.tr('EU5 安装目录'),prior.get('eu5',defaults['eu5']))
        game=self.path_field(f,2,'Victoria 3 / game',prior.get('game',defaults['game']));rules=self.path_field(f,3,self.tr('转换规则 manifest.json'),prior.get('rules',str(self.app.workspace/'rules/manifest.json')),kind='json')
        ttk.Label(f,text=self.tr('存档使用的模组目录\n（每行一个）')).grid(row=4,column=0,sticky='nw',pady=8)
        mods=tk.Text(f,height=4,width=65,font=('Microsoft YaHei UI',10));mods.grid(row=4,column=1,sticky='ew',pady=8)
        mods.insert('1.0','\n'.join(prior.get('mods',[])))
        def add_mod():
            path=filedialog.askdirectory(parent=d,title=self.tr('添加 EU5 模组目录'),mustexist=True)
            if path:mods.insert('end',('\n' if mods.get('1.0','end').strip() else '')+path)
        ttk.Button(f,text=self.tr('添加目录…'),command=add_mod).grid(row=4,column=2,padx=8,sticky='n')
        ttk.Label(f,text=self.tr('模组目录留空时，按存档顺序自动匹配本机 Steam 创意工坊中的同名同版本模组。\n找不到或匹配不唯一时会明确提示；转换完成后自动载入地图。'),wraplength=700).grid(row=5,column=0,columnspan=3,pady=10)
        output_language=self.output_language_field(f,6,prior.get('output_language',self.translator.language))
        def submit():
            req=dict(output_language=output_language(),save=save.get().strip(),eu5=eu5.get().strip(),game=game.get().strip(),rules=rules.get().strip(),mods=[s.strip() for s in mods.get('1.0','end').splitlines() if s.strip()])
            for key,label in [('save',self.tr('EU5 存档')),('eu5',self.tr('EU5 安装目录')),('game',self.tr('Victoria 3 game 目录')),('rules',self.tr('转换规则'))]:
                p=Path(req[key]);valid=p.is_file() if key in ('save','rules') else p.is_dir()
                if not req[key] or not valid:messagebox.showerror(self.tr('路径无效'),self.tr('请选择有效的')+label,parent=d);return
            if any(not Path(p).is_dir() for p in req['mods']):messagebox.showerror(self.tr('路径无效'),self.tr('有模组目录不存在。'),parent=d);return
            write(remembered,req)
            d.destroy()
            def progress(msg):self.events.put(('progress',self.tr('转换中 · ')+self.tr(STAGES.get(msg,msg))))
            def done(result):self.last_output=Path(result['directory']);self.load(dict(package=result['directory'],game=req['game'],name=Path(req['save']).stem))
            self.submit(self.tr('转换存档'),lambda:run_conversion(ROOT,self.app.workspace,req,progress,self.cancel),done)
        ttk.Button(f,text=self.tr('开始转换'),command=submit,style='Accent.TButton').grid(row=7,column=1,sticky='e');ttk.Button(f,text=self.tr('取消'),command=d.destroy).grid(row=7,column=2,padx=8)

    def export(self):
        if self.busy or not self.require_project():return
        d,f=self.dialog(self.tr('导出模组'))
        value=tk.StringVar(value=self.app.project.get('mod_name',self.app.project['name']))
        ttk.Label(f,text=self.tr('模组名称')).grid(row=0,column=0,sticky='w',padx=(0,12))
        field=ttk.Entry(f,textvariable=value,width=54);field.grid(row=0,column=1,columnspan=2,sticky='ew',pady=8)
        field.focus_set();field.selection_range(0,'end')
        ttk.Label(f,text=self.tr('这是游戏启动器显示的名称，支持中文，最多 120 个字符。\n本项目会记住名称，下次导出仍可修改。'),wraplength=540).grid(row=1,column=0,columnspan=3,sticky='w',pady=10)
        output_language=self.output_language_field(f,2,self.app.project.get('output_language',self.translator.language))
        def start():
            from converter_project import mod_name
            if self.busy:return
            try:name=mod_name(value.get())
            except ValueError as e:messagebox.showerror(self.tr('名称无效'),self.tr(e),parent=d);return
            language=output_language();revision=self.app.project['revision'];out=self.app.workspace/'exports'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
            d.destroy()
            def work():
                project=self.app.configure_export_name(name,revision,language)
                return export_candidate(self.app.world,project,out)
            def done(result):
                self.last_output=out
                p=self.app.project;self.title.set(p['name']+' · '+self.app.preview['source_date']+self.tr(' · 修订 ')+str(p['revision']))
                messagebox.showinfo(self.tr('导出成功'),self.tr('已生成并校验模组「{0}」：\n{1}\n\n点击“打开输出目录”查看。',result['mod_name'],str(out)),parent=self.root)
            self.submit(self.tr('导出并校验模组'),work,done)
        ttk.Button(f,text=self.tr('开始导出'),command=start,style='Accent.TButton').grid(row=3,column=1,sticky='e',pady=8)
        ttk.Button(f,text=self.tr('取消'),command=d.destroy).grid(row=3,column=2,padx=8)
        d.bind('<Return>',lambda e:start())

    def output_language_field(self,parent,row,language):
        language=language if language in LANGUAGES else 'zh-CN'
        selected=tk.StringVar(value=LANGUAGES[language]['name'])
        ttk.Label(parent,text=self.tr('游戏显示语言')).grid(row=row,column=0,sticky='w',pady=8)
        ttk.Combobox(parent,textvariable=selected,values=[v['name'] for v in LANGUAGES.values()],state='readonly',width=24).grid(row=row,column=1,sticky='w',pady=8)
        return lambda:next(k for k,v in LANGUAGES.items() if v['name']==selected.get())

    def open_output(self):
        path=self.last_output or (Path(self.app.project['package']) if self.app.project else self.app.workspace)
        os.startfile(str(path))
    def assumptions(self):
        content=[self.tr(n) for n in self.app.preview['assumptions']] if self.app.preview else [self.tr('耕地提醒使用国家在该州分得的耕地，默认 3 及以下。'),self.tr('失业和食物不足为产能规划估算，不是游戏内实测失业率或饥荒事件。'),self.tr('合并不创造土地、工作或粮食。')]
        row=self.rows.get(self.selected)
        if row:
            evidence=row.get('market_evidence',[]) or [self.tr('市场由本国或其上级市场控制。')]
            blocs=[b['name']+'（'+(self.tr('共同市场') if b['customs_union'] else self.tr('未启用共同市场'))+'）' for b in row.get('power_blocs',[])]
            content=[self.tr('所选地区：')+row['state_name']+' / '+row['country']+self.tr('\n市场：')+row['market_name']+'\n'+'\n'.join(self.tr(n) for n in evidence)+self.tr('\n国家集团：')+('、'.join(blocs) if blocs else self.tr('无'))]+content
        messagebox.showinfo(self.tr('计算依据与局限'),'\n\n'.join(content),parent=self.root)
    def close(self):
        if self.busy:
            conversion=self.operation==self.tr('转换存档')
            prompt=self.tr('停止本次转换并退出？未完成的结果不会作为成功候选包。') if conversion else self.tr('当前操作正在保存或校验。完成后自动退出？')
            if not messagebox.askyesno(self.tr('退出转换器'),prompt,parent=self.root):return
            self.closing=True
            if conversion:self.cancel.set()
            self.status.set(self.tr('正在停止转换…') if conversion else self.tr('当前操作完成后自动退出…'));return
        self.selection_pool.shutdown(wait=False,cancel_futures=True);self.root.destroy()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,default=ROOT/'.local/converter');parser.add_argument('--no-autoload',action='store_true');parser.add_argument('--language',choices=list(LANGUAGES));args=parser.parse_args()
    if os.name=='nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('EraBridge.Converter.Beta')
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError,OSError):pass
    root=tk.Tk();Workbench(root,args.workspace,not args.no_autoload,args.language);root.mainloop()

if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc()
        try:messagebox.showerror('转换器启动失败 / Startup failed','无法启动桌面程序，请查看软件目录 data/startup.log。\n\nUnable to start the desktop application. See data/startup.log in the application folder.')
        except Exception:pass
        raise
