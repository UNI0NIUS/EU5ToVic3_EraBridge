"""Shared local project model; independent of any GUI or HTTP transport."""
from copy import deepcopy
import io
from pathlib import Path
import secrets
import threading
import traceback
import uuid
import numpy as np
from PIL import Image
from converter_project import DEFAULTS, read, write, settings, resolve_merges
from converter_world import Candidate
ROOT=Path(__file__).resolve().parents[1]

class App:
    def __init__(self, workspace):
        self.workspace=Path(workspace).resolve();self.workspace.mkdir(parents=True,exist_ok=True)
        self.token=secrets.token_urlsafe(32);self.lock=threading.RLock()
        self.world=None;self.project=None;self.preview=None
        self.job=dict(status='idle',message='请选择候选包或新建转换任务');self.image_cache={}

    def projects(self):
        result=[]
        for path in sorted((self.workspace/'projects').glob('*/project.json'),reverse=True):
            d=read(path);result.append(dict(id=d['id'],name=d['name'],package=d['package'],revision=d['revision']))
        return result

    def defaults(self):
        local=self.workspace/'defaults.json'
        d=read(local) if local.exists() else {}
        candidates=[]
        paths=[Path(p) for p in d.get('candidate_paths',[])]+[ROOT/'.local/conversion/1337-20261002/complete']
        installed=ROOT/'.local/economy/installation-latest.json'
        if installed.exists():paths.append(Path(read(installed)['package']))
        for p in paths:
            if (p/'package_report.json').exists():
                r=read(p/'package_report.json');candidates.append(dict(path=str(p),name=r.get('mod_name',p.name),date=r.get('source_date','')))
        generated=[]
        for p in sorted((self.workspace/'runs').glob('*/complete/package_report.json'),reverse=True):
            r=read(p);generated.append(dict(path=str(p.parent),name=r.get('mod_name','通用流水线转换结果'),date=r.get('source_date','')))
        candidates=generated+candidates
        return dict(game=d.get('game',''),
                    eu5=d.get('eu5',''),
                    candidates=candidates,settings=DEFAULTS,projects=self.projects(),workspace=str(self.workspace))

    def save(self):
        path=self.workspace/'projects'/self.project['id']
        write(path/'history'/f"{self.project['revision']:06d}.json",self.project)
        write(path/'project.json',self.project)

    def snapshot(self):
        return dict(job=self.job,project=self.project,preview=self.preview)

    def check_revision(self, body):
        if self.job['status']=='running':raise RuntimeError('任务进行中，请等待完成')
        if not self.project:raise ValueError('请先载入项目')
        if body.get('revision')!=self.project['revision']:raise RuntimeError('项目已更新，请刷新后重试')

    def background(self,label,fn):
        with self.lock:
            if self.job['status']=='running':raise RuntimeError('已有任务运行中')
            job_id=uuid.uuid4().hex;self.job=dict(id=job_id,status='running',message=label)
        def run():
            try:
                result=fn()
                with self.lock:self.job=dict(id=job_id,status='done',message=label+'完成',result=result)
            except Exception as e:
                log=self.workspace/'logs'/(job_id+'.log');log.parent.mkdir(exist_ok=True)
                log.write_text(traceback.format_exc(),encoding='utf-8')
                with self.lock:self.job=dict(id=job_id,status='failed',message=str(e),log=str(log))
        threading.Thread(target=run,daemon=True).start()
        return dict(job=self.job)

    def load(self, body):
        return self.background('载入并计算地图',lambda:self.load_project(body))

    def load_project(self, body):
        if body.get('id'):
            if not isinstance(body['id'],str) or not all(c in '0123456789abcdef' for c in body['id']) or len(body['id'])!=32:raise ValueError('项目编号无效')
            project=read(self.workspace/'projects'/body['id']/'project.json')
        else:
            project=dict(schema=1,id=uuid.uuid4().hex,name=body.get('name') or 'EU5 → Victoria 3 转换项目',
                         package=str(Path(body['package']).resolve()),game=str(Path(body['game']).resolve()),
                         revision=0,settings=dict(DEFAULTS),merges=[])
        world=Candidate(project['package'],project['game'],self.workspace/'cache')
        if project.get('fingerprint') and project['fingerprint']!=world.fingerprint:raise ValueError('项目输入指纹已改变，不能自动复用旧合并决定')
        rules=self.workspace/'rules'
        if (rules/'identity_policy.json').exists():
            from converter_refresh import upgrade
            updated=upgrade(project['package'],project['game'],rules,self.workspace/'upgrades')
            if updated.resolve()!=Path(project['package']).resolve():
                previous=project['package'];world=Candidate(updated,project['game'],self.workspace/'cache')
                # Only publish the new project reference after every saved edit replays.
                world.preview(project['settings'],project['merges'])
                project['package']=str(updated.resolve());project['upgraded_from']=previous
                project['revision']+=1
        project['fingerprint']=world.fingerprint
        preview=world.preview(project['settings'],project['merges'])
        with self.lock:
            self.world=world;self.project=project;self.preview=preview;self.image_cache={};self.save()
        return dict(project=project['id'],regions=len(preview['rows']))

    def mutate(self,kind,body):
        with self.lock:
            self.check_revision(body);new=deepcopy(self.project)
            if kind=='settings':new['settings']=settings(body['settings'])
            elif kind in ('merge','edit'):
                new['merges'].append(body['operation'])
            elif kind=='undo':
                if not new['merges']:raise ValueError('没有可撤销的编辑')
                new['merges'].pop()
            elif kind=='restore':new['merges']=[];new['settings']=dict(DEFAULTS)
            else:raise ValueError('未知操作')
            preview=self.world.preview(new['settings'],new['merges'])
            new['revision']+=1;self.project=new;self.preview=preview;self.image_cache={};self.save()
            return self.snapshot()

    def configure_export_name(self,value,revision):
        from converter_project import mod_name
        with self.lock:
            self.check_revision(dict(revision=revision))
            value=mod_name(value)
            if self.project.get('mod_name')!=value:
                self.project=deepcopy(self.project);self.project['mod_name']=value
                self.project['revision']+=1;self.save()
            return deepcopy(self.project)

    def image(self,view):
        if not self.world:raise ValueError('请先载入地图')
        if view not in ('country','state','strategic_region','market','arable','unemployment','food','market_food','local_food'):raise ValueError('未知图层')
        if view in self.image_cache:return self.image_cache[view]
        lut=np.zeros((1<<24,3),dtype=np.uint8);lut[:]=[19,37,49]
        import hashlib
        for row in self.preview['rows']:
            seed=hashlib.sha256((row['strategic_region' if view=='strategic_region' else 'state' if view=='state' else 'market_owner' if view=='market' else 'country'] or row['state']).encode()).digest()
            color=[65+b%150 for b in seed[:3]]
            if view not in ('country','state','strategic_region','market'):
                color=[216,96,77] if view in row['risks'] else [55,107,105]
                if view=='unemployment' and row['estimated_unemployment'] is None:color=[110,110,116]
                if view=='food' and row['food_shortfall'] is None:color=[110,110,116]
                if view in ('market_food','local_food'):
                    field='market_food_shortfall' if view=='market_food' else 'local_food_shortfall';value=row[field]
                    color=([110,110,116] if value is None else [55,107,105] if value<=0 else
                           [216,96,77] if value+1e-12>=self.preview['settings']['food_shortfall_threshold'] else [205,167,79])
            for p in row['provinces']:lut[int(p[1:],16)]=color
        pixels=self.world.raster()[::2,::2];rgb=lut[pixels]
        borders=np.zeros(pixels.shape,dtype=bool)
        borders[:,1:]|=np.any(rgb[:,1:]!=rgb[:,:-1],axis=2);borders[1:,:]|=np.any(rgb[1:,:]!=rgb[:-1,:],axis=2)
        if view in ('state','local_food'):
            borders[:,1:]|=pixels[:,1:]!=pixels[:,:-1];borders[1:,:]|=pixels[1:,:]!=pixels[:-1,:]
        rgb[borders]=(rgb[borders]*.6).astype(np.uint8)
        buf=io.BytesIO();Image.fromarray(rgb).save(buf,format='PNG');data=buf.getvalue()
        self.image_cache[view]=data;return data

    def hit(self,x,y,preview=None):
        preview=preview or self.preview
        raster=self.world.raster()
        if not (0<=x<raster.shape[1] and 0<=y<raster.shape[0]):return dict(id=None)
        p='x'+f'{int(raster[y,x]):06X}'
        if getattr(self,'_hit_preview',None) is not preview:
            self._hit_index={p:r['id'] for r in preview['rows'] for p in r['provinces']};self._hit_preview=preview
        return dict(id=self._hit_index.get(p),province=p)

    def region(self,key,selected=None,preview=None):
        preview=preview or self.preview
        row=next((r for r in preview['rows'] if r['id']==key),None)
        if row is None:raise ValueError('地区不存在')
        provinces=sorted(set(selected or [])&set(row['provinces'])) or row['provinces']
        cache=getattr(self,'_region_cache',None)
        if cache is None:self._region_cache=cache={}
        signature=(self.world.fingerprint,tuple(provinces))
        if signature in cache:return cache[signature]
        mask=np.isin(self.world.raster(),[int(p[1:],16) for p in provinces]);yy,xx=np.where(mask)
        if not len(xx):raise ValueError('地图中缺少地区')
        x0,x1,y0,y1=int(xx.min()),int(xx.max())+1,int(yy.min()),int(yy.max())+1
        middle=len(xx)//2;xy=[int(xx[middle]),int(yy[middle])]
        # A seam-spanning region focuses on one actual land pixel, not an ocean centroid.
        focus=[x0,y0,x1-x0,y1-y0] if x1-x0<mask.shape[1]//2 else [xy[0]-120,y0,240,y1-y0]
        rgba=np.zeros((y1-y0,x1-x0,4),dtype=np.uint8);rgba[mask[y0:y1,x0:x1]]=[255,220,137,220]
        buf=io.BytesIO();Image.fromarray(rgba).save(buf,format='PNG')
        import base64
        result=dict(box=[x0,y0,x1-x0,y1-y0],focus=focus,xy=xy,image='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode())
        if len(cache)>=48:cache.pop(next(iter(cache)))
        cache[signature]=result;return result
