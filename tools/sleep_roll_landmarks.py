# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original project contributions; upstream character rights remain separate.
"""Local silhouette correspondence for five reviewed large pose changes."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import cv2
import numpy as np
from sleep_roll import X,Y

PATH=Path(__file__).parent/'sequence_sources/sleep_roll_v26/landmarks.json'

@lru_cache(maxsize=48)
def controls(a_bytes,b_bytes):
    data=json.loads(PATH.read_text())
    a,b=[hashlib.sha256(v).hexdigest() for v in (a_bytes,b_bytes)]
    if [a,b] not in data['pairs']:return None
    pa,pb=[np.float32(data['poses'][key]) for key in (a,b)]
    boundary=np.float32([(0,0),(511,0),(511,511),(0,511),(256,0),(511,256),(256,511),(0,256)])
    pa,pb=[np.concatenate((p,boundary)) for p in (pa,pb)]
    mean=(pa+pb)/2;subdiv=cv2.Subdiv2D((0,0,512,512))
    for point in mean:subdiv.insert(tuple(map(float,point)))
    triangles=[]
    for tri in subdiv.getTriangleList().reshape(-1,3,2):
        ids=[int(np.argmin(np.linalg.norm(mean-p,axis=1))) for p in tri]
        if all(np.linalg.norm(mean[i]-p)<1 for i,p in zip(ids,tri)):triangles.append(ids)
    return pa,pb,triangles

def warp(pixels,source,target,triangles):
    u,v=X.copy(),Y.copy()
    for ids in triangles:
        destination=target[ids]
        x0,y0=np.maximum(0,np.floor(destination.min(axis=0)).astype(int))
        x1,y1=np.minimum(512,np.ceil(destination.max(axis=0)).astype(int)+1)
        if x1<=x0 or y1<=y0:continue
        matrix=cv2.getAffineTransform(destination.astype(np.float32),source[ids].astype(np.float32))
        mask=np.zeros((y1-y0,x1-x0),np.uint8)
        cv2.fillConvexPoly(mask,np.rint(destination-[x0,y0]).astype(np.int32),1)
        inside=mask.astype(bool);xx=X[y0:y1,x0:x1];yy=Y[y0:y1,x0:x1]
        u[y0:y1,x0:x1][inside]=(matrix[0,0]*xx+matrix[0,1]*yy+matrix[0,2])[inside]
        v[y0:y1,x0:x1][inside]=(matrix[1,0]*xx+matrix[1,1]*yy+matrix[1,2])[inside]
    return cv2.remap(pixels,u,v,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)

def placed(a,b,t,control):
    pa,pb,triangles=control;target=pa*(1-t)+pb*t
    result=[warp(a,pa,target,triangles),warp(b,pb,target,triangles)]
    # Preserve each moving paw as a compact surface. A single center point
    # otherwise stretches the pad across adjoining torso triangles.
    for index,rx,ry in [(9,25,23),(10,27,21),(17,34,35)]:
        if np.linalg.norm(pa[index]-pb[index])<20:continue
        cx,cy=target[index]
        q=np.sqrt(((X-cx)/rx)**2+((Y-cy)/ry)**2)
        weight=np.clip((1.25-q)/.35,0,1)[...,None]
        weight=weight*weight*(3-2*weight)
        for i,(pixels,points) in enumerate(((a,pa),(b,pb))):
            u=X-cx+points[index,0];v=Y-cy+points[index,1]
            rigid=cv2.remap(pixels,u,v,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
            effective=weight*np.clip((rigid[...,3:4]-.3)/.5,0,1)
            result[i]=result[i]*(1-effective)+rigid*effective
    return tuple(result)
