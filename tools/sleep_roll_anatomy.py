# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Project-owned code only; upstream drawing rights remain separate.
"""Constrain each paw's inverse map to its own anatomical track."""
import cv2
import numpy as np
from functools import lru_cache
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageFilter
from sleep_roll import motion, X, Y

@lru_cache(maxsize=40)
def head_rig(a_bytes,b_bytes):
    pictures=[np.frombuffer(v,np.uint8).reshape(512,512,4) for v in (a_bytes,b_bytes)]
    gray=[cv2.cvtColor(p[...,:3],cv2.COLOR_RGB2GRAY) for p in pictures]
    mask=np.uint8((X>40)&(X<275)&(Y>205)&(Y<425))*255
    points=cv2.goodFeaturesToTrack(gray[0],100,.02,6,mask=mask)
    matrix=np.float32([[1,0,0],[0,1,0]])
    if points is not None and len(points)>=6:
        target,status,_=cv2.calcOpticalFlowPyrLK(gray[0],gray[1],points,None,winSize=(31,31),maxLevel=3)
        if target is not None:
            back,back_status,_=cv2.calcOpticalFlowPyrLK(gray[1],gray[0],target,None,winSize=(31,31),maxLevel=3)
            valid=(status.ravel()>0)&(back_status.ravel()>0)&(np.linalg.norm(back-points,axis=2).ravel()<1.5)
            if valid.sum()>=6:
                fit,_=cv2.estimateAffinePartial2D(points[valid],target[valid],method=cv2.RANSAC,ransacReprojThreshold=2)
                # Rollover changes the projected head size. Rejecting this
                # modest scale change left an identity transform and doubled
                # the face when the two textures were blended.
                if fit is not None and .80<np.linalg.det(fit[:,:2])<1.25:matrix=fit.astype(np.float32)
    landmark_path=Path(__file__).parent/'sequence_sources/sleep_roll_v25/head_landmarks.json'
    landmarks=json.loads(landmark_path.read_text()) if landmark_path.exists() else {}
    anchors=[landmarks.get(hashlib.sha256(v).hexdigest()) for v in (a_bytes,b_bytes)]
    if all(v is not None for v in anchors):
        fit,_=cv2.estimateAffinePartial2D(np.float32(anchors[0]),np.float32(anchors[1]),method=cv2.LMEDS)
        if fit is not None:matrix=fit.astype(np.float32)
    centres=[]
    for p in pictures:
        rgb=p[...,:3].astype(int)
        gold=(rgb[...,0]>rgb[...,1]+18)&(rgb[...,1]>rgb[...,2]+25)&(p[...,3]>240)&(X<230)&(Y<400)
        ys,xs=np.nonzero(gold)
        centres.append((float(np.median(xs))+30,float(np.median(ys))+45) if len(xs) else (160,370))
    return matrix,centres

def placed(first,second,t,first_paws,second_paws):
    t=float(t)
    if t<=1e-6:return first.copy()
    if t>=1-1e-6:return second.copy()
    a,b,f,r=motion(first.tobytes(),second.tobytes())
    def inverse(flow,amount):
        u,v=X.copy(),Y.copy()
        for _ in range(5):
            d=cv2.remap(flow,u,v,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            u=X-d[...,0]*amount;v=Y-d[...,1]*amount
        return u,v
    ua,va=inverse(f,t);ub,vb=inverse(r,1-t)
    # A rigid head transform protects the face, eyelids and horn from the
    # large local flow that was previously stretching them during rollover.
    head,centres=head_rig(first.tobytes(),second.tobytes())
    centre=np.asarray(centres[0])*(1-t)+np.asarray(centres[1])*t
    q=np.sqrt(((X-centre[0])/130)**2+((Y-centre[1])/115)**2)
    head_weight=np.clip((1.35-q)/.45,0,1).astype(np.float32)
    head_weight=head_weight*head_weight*(3-2*head_weight)
    # At the last head roll the visible ear changes occlusion. A single
    # rigid fit cannot map the ear and muzzle together; retain dense local
    # correspondence for this reviewed pair instead.
    landmark_path=Path(__file__).parent/'sequence_sources/sleep_roll_v25/head_landmarks.json'
    reviewed=json.loads(landmark_path.read_text()) if landmark_path.exists() else {}
    final_head_roll=all(hashlib.sha256(im.tobytes()).hexdigest() in reviewed for im in (first,second))
    if final_head_roll:head_weight[:]=0
    identity=np.float32([[1,0,0],[0,1,0]])
    for transform,amount,u,v in [(head,t,ua,va),(cv2.invertAffineTransform(head),1-t,ub,vb)]:
        inv=cv2.invertAffineTransform(identity*(1-amount)+transform*amount)
        hx=inv[0,0]*X+inv[0,1]*Y+inv[0,2];hy=inv[1,0]*X+inv[1,1]*Y+inv[1,2]
        u[:]=u*(1-head_weight)+hx*head_weight;v[:]=v*(1-head_weight)+hy*head_weight
    # front-near, front-far, hind-near, hind-far retain their identities.
    # Around a paw, replace unconstrained flow with a local rigid placement;
    # the algorithm cannot pair a hind foot with the neck or another limb.
    weights=[]; maps_a=[]; maps_b=[]
    for pa,pb in zip(first_paws,second_paws):
        pa=np.asarray(pa,dtype=np.float32);pb=np.asarray(pb,dtype=np.float32)
        target=pa*(1-t)+pb*t
        cx,cy,rx,ry=target
        if rx<1 or ry<1:continue
        q=np.sqrt(((X-cx)/(rx+4))**2+((Y-cy)/(ry+4))**2)
        w=np.clip((1.7-q)/1.2,0,1);w=w*w*(3-2*w)
        # Keep occluded feet under the haunch until the drawings expose them.
        if min(pa[2],pb[2])<1:continue
        weights.append(w)
        maps_a.append((pa[0]+(X-cx)*pa[2]/rx,pa[1]+(Y-cy)*pa[3]/ry))
        maps_b.append((pb[0]+(X-cx)*pb[2]/rx,pb[1]+(Y-cy)*pb[3]/ry))
    if weights:
        weights=np.asarray(weights); total=weights.sum(axis=0)
        cover=np.minimum(total,1);den=np.maximum(total,.001)
        for maps,u,v in [(maps_a,ua,va),(maps_b,ub,vb)]:
            rigid_x=sum(w*m[0] for w,m in zip(weights,maps))/den
            rigid_y=sum(w*m[1] for w,m in zip(weights,maps))/den
            u[:]=u*(1-cover)+rigid_x*cover;v[:]=v*(1-cover)+rigid_y*cover
    # Forepaws pass close to the cheek. Their feathered influence must never
    # pull the eyelids or mouth into a paw; keep the face on its rigid rig.
    face_centre=centre+np.asarray([13,28])
    face_q=np.sqrt(((X-face_centre[0])/72)**2+((Y-face_centre[1])/35)**2)
    protect=np.clip((1.1-face_q)/.15,0,1).astype(np.float32)
    if final_head_roll:protect[:]=0
    for transform,amount,u,v in [(head,t,ua,va),(cv2.invertAffineTransform(head),1-t,ub,vb)]:
        inv=cv2.invertAffineTransform(identity*(1-amount)+transform*amount)
        hx=inv[0,0]*X+inv[0,1]*Y+inv[0,2];hy=inv[1,0]*X+inv[1,1]*Y+inv[1,2]
        u[:]=u*(1-protect)+hx*protect;v[:]=v*(1-protect)+hy*protect
    original_a,original_b=a,b
    a=cv2.remap(a,ua,va,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
    b=cv2.remap(b,ub,vb,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
    if final_head_roll:
        # Only the reviewed changing head silhouette uses landmark triangles;
        # legs and torso retain their separate anatomical maps above.
        from continuous_morph import mesh_warp
        path=Path(__file__).parent/'sequence_sources/sleep_roll_v25/head_landmarks.json'
        mapping=json.loads(path.read_text())
        points=[mapping[hashlib.sha256(im.tobytes()).hexdigest()] for im in (first,second)]
        boundary=[(0,0),(511,0),(511,511),(0,511),(0,256),(256,0),(511,256),(256,511)]
        pa,pb=[np.float32(v+boundary) for v in points]
        target=pa*(1-t)+pb*t
        subdiv=cv2.Subdiv2D((0,0,512,512))
        for point in (pa+pb)/2:subdiv.insert(tuple(map(float,point)))
        triangles=[];mean=(pa+pb)/2
        for tri in subdiv.getTriangleList().reshape(-1,3,2):
            ids=[int(np.argmin(np.linalg.norm(mean-p,axis=1))) for p in tri]
            if all(np.linalg.norm(mean[i]-p)<1 for i,p in zip(ids,tri)):triangles.append(ids)
        blend=np.clip((245-X)/35,0,1)[...,None]
        a=a*(1-blend)+mesh_warp(original_a,pa,target,triangles)*blend
        b=b*(1-blend)+mesh_warp(original_b,pb,target,triangles)*blend
    return a,b

@lru_cache(maxsize=48)
def texture_residual(first_bytes,second_bytes,paws_a,paws_b):
    first=Image.fromarray(np.frombuffer(first_bytes,np.uint8).reshape(512,512,4))
    second=Image.fromarray(np.frombuffer(second_bytes,np.uint8).reshape(512,512,4))
    a,b=placed(first,second,.5,paws_a,paws_b)
    def gray(p):
        rgb=p[...,:3]+(1-p[...,3:4])*.5
        return cv2.cvtColor(np.uint8(np.clip(rgb*255,0,255)),cv2.COLOR_RGB2GRAY)
    from continuous_morph import fields
    forward,backward=fields(gray(a).tobytes(),gray(b).tobytes())
    # Only align remaining ink and fur details. Anatomy has already been
    # registered, so residual flow cannot exchange different limbs.
    return np.clip(forward,-8,8),np.clip(backward,-8,8)

def render(first,second,t,first_paws,second_paws):
    t=float(t)
    if t<=1e-6:return first.copy()
    if t>=1-1e-6:return second.copy()
    a,b=placed(first,second,t,first_paws,second_paws)
    f,r=texture_residual(first.tobytes(),second.tobytes(),
        tuple(tuple(p) for p in first_paws),tuple(tuple(p) for p in second_paws))
    def refine(p,flow,amount):
        u,v=X.copy(),Y.copy()
        for _ in range(3):
            d=cv2.remap(flow,u,v,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            u=X-d[...,0]*amount;v=Y-d[...,1]*amount
        return cv2.remap(p,u,v,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
    a,b=refine(a,f,t),refine(b,r,1-t)
    # Registered textures change continuously; no half-interval source cut.
    transfer=t*t*(3-2*t)
    mixed=a*(1-transfer)+b*transfer
    alpha=np.clip(mixed[...,3:4],0,1)
    rgba=np.concatenate((mixed[...,:3]/np.maximum(alpha,.001),alpha),axis=2)
    result=Image.fromarray(np.uint8(np.clip(np.rint(rgba*255),0,255)))
    sharpened=result.convert('RGB').filter(ImageFilter.UnsharpMask(radius=.5,percent=60,threshold=2))
    sharpened.putalpha(result.getchannel('A'))
    return sharpened
