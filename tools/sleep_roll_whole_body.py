# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original project contributions; upstream character rights remain separate.
"""Interpolate reviewed whole-body drawings without independent paw relocation."""
from functools import lru_cache
import cv2
import numpy as np
from PIL import Image
from sleep_roll import X,Y,motion

@lru_cache(maxsize=48)
def bounded_motion(first,second):
    a,b,forward,backward=motion(first,second)
    result=[]
    for flow in (forward,backward):
        # Foreground occlusion is an appearance change, not a foot travelling
        # across the torso. Bound local displacement and regularize tiny folds.
        flow=cv2.GaussianBlur(flow,(0,0),.9)
        length=np.maximum(np.linalg.norm(flow,axis=2,keepdims=True),.001)
        result.append(flow*np.minimum(1,40/length))
    return a,b,*result

@lru_cache(maxsize=12)
def landmark_residual(first,second):
    from sleep_roll_landmarks import controls,placed
    from continuous_morph import fields
    a,b,*_=bounded_motion(first,second)
    a,b=placed(a,b,.5,controls(first,second))
    def gray(pixels):
        return cv2.cvtColor(np.uint8(np.clip((pixels[...,:3]+(1-pixels[...,3:4])*.5)*255,0,255)),cv2.COLOR_RGB2GRAY)
    f,r=fields(gray(a).tobytes(),gray(b).tobytes())
    return np.clip(f,-16,16),np.clip(r,-16,16)

def render(first,second,t):
    if t<=1e-7:return first.copy()
    if t>=1-1e-7:return second.copy()
    a,b,forward,backward=bounded_motion(first.tobytes(),second.tobytes())
    def warp(pixels,flow,amount):
        u,v=X.copy(),Y.copy()
        for _ in range(4):
            displacement=cv2.remap(flow,u,v,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            u=X-displacement[...,0]*amount;v=Y-displacement[...,1]*amount
        return cv2.remap(pixels,u,v,cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
    from sleep_roll_landmarks import controls,placed
    control=controls(first.tobytes(),second.tobytes())
    if control is None:
        a,b=warp(a,forward,t),warp(b,backward,1-t)
    else:
        a,b=placed(a,b,t,control)
        f,r=landmark_residual(first.tobytes(),second.tobytes())
        a,b=warp(a,f,t),warp(b,r,1-t)
    # A broad continuous local handoff avoids showing two whole silhouettes
    # at once while both anatomical surfaces continue to move every frame.
    threshold=.34+.32*(1-X/511)
    transfer=np.clip((t-threshold+.12)/.24,0,1)[...,None]
    transfer=transfer*transfer*(3-2*transfer)
    mixed=a*(1-transfer)+b*transfer
    alpha=np.clip(mixed[...,3:4],0,1)
    rgba=np.concatenate((mixed[...,:3]/np.maximum(alpha,.001),alpha),axis=2)
    return Image.fromarray(np.uint8(np.clip(np.rint(rgba*255),0,255)))
