# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Project-owned code only; upstream drawing rights remain separate.
"""Direct interpolation of densely drawn, anatomically valid sleeping poses."""
from functools import lru_cache
import cv2
import numpy as np
from PIL import Image, ImageFilter
from continuous_morph import fields

X,Y=np.meshgrid(np.arange(512,dtype=np.float32),np.arange(512,dtype=np.float32))

@lru_cache(maxsize=24)
def motion(a_bytes,b_bytes):
    a=np.frombuffer(a_bytes,np.uint8).reshape(512,512,4).astype(np.float32)/255
    b=np.frombuffer(b_bytes,np.uint8).reshape(512,512,4).astype(np.float32)/255
    for p in (a,b): p[...,:3]*=p[...,3:4]
    def gray(p):
        return cv2.cvtColor(np.uint8(np.clip((p[...,:3]+(1-p[...,3:4])*.5)*255,0,255)),cv2.COLOR_RGB2GRAY)
    f,r=fields(gray(a).tobytes(),gray(b).tobytes())
    return a,b,f,r

def render(first,second,t):
    t=float(t)
    if t<=1e-6: return first.copy()
    if t>=1-1e-6: return second.copy()
    a,b,f,r=motion(first.tobytes(),second.tobytes())
    def warp(p,flow,amount):
        u,v=X.copy(),Y.copy()
        for _ in range(5):
            displacement=cv2.remap(flow,u,v,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            u=X-displacement[...,0]*amount; v=Y-displacement[...,1]*amount
        return cv2.remap(p,u,v,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
    a,b=warp(a,f,t),warp(b,r,1-t)
    # Exchange single-source textures across a narrow band instead of
    # blending two whole silhouettes or deforming mismatched paw anchors.
    threshold=.30+.40*(1-X/511)
    transfer=np.clip((t-threshold+.015)/.03,0,1)[...,None]
    transfer=transfer*transfer*(3-2*transfer)
    mixed=a*(1-transfer)+b*transfer; alpha=np.clip(mixed[...,3:4],0,1)
    rgba=np.concatenate((mixed[...,:3]/np.maximum(alpha,.001),alpha),axis=2)
    return Image.fromarray(np.uint8(np.clip(np.rint(rgba*255),0,255))).filter(
        ImageFilter.UnsharpMask(radius=.45,percent=45,threshold=2))
