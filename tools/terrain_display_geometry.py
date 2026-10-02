"""Display geometry from actual raster footprints, including seam-split islands."""
import numpy as np
from scipy.ndimage import label, find_objects
from build_location_workstation import packed, source_centers, wrapped_mean, wrapped_distances


def footprint(xs, ys, width):
    xs=np.asarray(xs,dtype=int);ys=np.asarray(ys,dtype=int)
    unique=np.unique(xs)
    gaps=np.diff(np.r_[unique,unique[0]+width])
    start=int(unique[(int(np.argmax(gaps))+1)%len(unique)])
    ux=(xs-start)%width; left,right=int(ux.min()),int(ux.max())
    top,bottom=int(ys.min()),int(ys.max())
    mask=np.zeros((bottom-top+1,right-left+1),dtype=bool)
    mask[ys-top,ux-left]=True
    labels,_=label(mask,np.ones((3,3),dtype=int));markers=[]
    for i,box in enumerate(find_objects(labels),1):
        if box is None:continue
        yy,xx=np.where(labels[box]==i);xx+=box[1].start;yy+=box[0].start
        near=int(np.argmin((xx-xx.mean())**2+(yy-yy.mean())**2))
        markers.append([int((xx[near]+left+start)%width),int(yy[near]+top)])
    near=int(np.argmin((ux-ux.mean())**2+(ys-ys.mean())**2))
    return dict(xy=[int(xs[near]),int(ys[near])],markers=markers,
                view_points=[[(start+left)%width,top],[(start+right)%width,bottom]],pixels=len(xs))


def refresh_geometry(data,image):
    width=image.width
    # The old cache averaged seam-split province pixels across the entire map.
    centers=source_centers(image,{p:int(p[1:],16) for p in data['targets']})
    for p,xy in centers.items():data['targets'][p]['xy']=[round(v*2,2) for v in xy]
    wanted={p for c in data['components'] for p in c['provinces']}
    ids=packed(image); lookup=np.zeros(1<<24,dtype=bool)
    for p in wanted:lookup[int(p[1:],16)]=True
    ys,xs=np.where(lookup[ids]);colors=ids[ys,xs]
    for p in sorted(wanted):
        keep=colors==int(p[1:],16)
        if not keep.any():raise ValueError('Missing target footprint: '+p)
        data['targets'][p].update(footprint(xs[keep],ys[keep],width))
    sources=data['sources'];targets=data['targets']
    anchors=[p for p,r in targets.items() if r['kind'] not in ('land_inferred','unresolved') and any(n in sources for n in r['sources'])]
    positions=np.array([targets[p]['xy'] for p in anchors])
    for c in data['components']:
        xy=wrapped_mean([targets[p]['xy'] for p in c['provinces']],width)
        near=[anchors[i] for i in np.argsort(wrapped_distances(positions,xy,width))[:10]]
        names=list(dict.fromkeys(n for p in near for n in targets[p]['sources'] if n in sources))[:24]
        c.update(xy=xy.tolist(),candidates=names,source_guess=wrapped_mean([sources[n]['xy'] for n in names],data['source_size'][0]).tolist())
    data['display_geometry_version']=2
    return data
