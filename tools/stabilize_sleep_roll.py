# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Project-owned code only; upstream drawing rights remain separate.
"""Subpixel registration and motion-compensated filtering of final PNG frames."""
import hashlib
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

X,Y=np.meshgrid(np.arange(512,dtype=np.float32),np.arange(512,dtype=np.float32))

def premultiplied(image):
    p=np.asarray(image).astype(np.float32)/255
    p[...,:3]*=p[...,3:4]
    return p

def rgba(p):
    alpha=np.clip(p[...,3:4],0,1)
    pixels=np.concatenate((p[...,:3]/np.maximum(alpha,.001),alpha),axis=2)
    return Image.fromarray(np.uint8(np.clip(np.rint(pixels*255),0,255)))

def anchor(image):
    alpha=np.asarray(image)[...,3].astype(float)/255
    # Ignore moving feet and tail tips when measuring overall placement.
    weight=alpha.copy();weight[(X<180)|(X>390)|(Y<340)|(Y>490)]=0
    return [float((weight*X).sum()/weight.sum()),float((weight*Y).sum()/weight.sum())]

def shake(points):
    return float(np.sqrt(np.mean(np.diff(points,n=2,axis=0)**2)))

def stabilize(frames):
    first,last=frames[0],frames[-1]
    anchors=np.asarray([anchor(im) for im in frames],dtype=np.float32)
    smooth=cv2.GaussianBlur(anchors.reshape(1,-1,2),(0,0),sigmaX=4,sigmaY=0).reshape(-1,2)
    correction=np.clip(smooth-anchors,-4,4)
    for i in range(1,len(frames)-1):
        fade=min(1,i/12,(len(frames)-1-i)/12)
        dx,dy=map(float,correction[i]*fade)
        if abs(dx)+abs(dy)>.005:
            frames[i]=rgba(cv2.remap(premultiplied(frames[i]),X-dx,Y-dy,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT))
    # Neighbours are registered to the current frame before filtering, so
    # this removes line flicker without leaving a trailing double silhouette.
    def gray(p):
        return cv2.cvtColor(np.uint8(np.clip((p[...,:3]+(1-p[...,3:4])*.5)*255,0,255)),cv2.COLOR_RGB2GRAY)
    previous=premultiplied(first)
    for i in range(1,len(frames)-1):
        current=premultiplied(frames[i]);following=premultiplied(frames[i+1])
        cg=gray(current);filtered=current*.6
        for neighbour in (previous,following):
            flow=cv2.calcOpticalFlowFarneback(cg,gray(neighbour),None,.5,2,13,3,5,1.1,0)
            flow=np.clip(flow,-3,3)
            registered=cv2.remap(neighbour,X+flow[...,0],Y+flow[...,1],cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
            filtered+=registered*.2
        frames[i]=rgba(filtered);previous=current
    frames[0]=first;frames[-1]=last
    after=np.asarray([anchor(im) for im in frames])
    return {'frame_count':len(frames),'unique_pixel_frames':len({hashlib.sha256(im.tobytes()).digest() for im in frames}),
            'anchor_acceleration_rms_before':shake(anchors),'anchor_acceleration_rms_after':shake(after),
            'max_registration_pixels':float(np.max(np.abs(correction))),
            'exact_sleep_endpoints_preserved':True,'temporal_filter':'3-frame motion compensated'}
