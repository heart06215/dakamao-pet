# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original contributions only; upstream character rights are not relicensed.
"""Bake dense sidecar frames outside VPet's bounded-width atlases."""
import bisect
import json
from pathlib import Path
import re

import cv2
import numpy as np
from PIL import Image

from build_fluid_frames import midpoint, premultiplied

ROOT=Path(__file__).resolve().parents[1]
PET=ROOT/"DakamaoPet/PetMod/pet/dakamao"
OUT=ROOT/"DakamaoPet/PetMod/fluid"


def ear_bounce(image: Image.Image, amount: float) -> Image.Image:
    if abs(amount)<0.001: return image
    pixels=np.asarray(image)
    rgb=pixels[...,:3].astype(int)
    y,x=np.mgrid[:512,:512]
    pink=(pixels[...,3]>200)&(rgb[...,0]>180)&(rgb[...,0]-rgb[...,1]>25)&(rgb[...,0]-rgb[...,1]<90)&(np.abs(rgb[...,1]-rgb[...,2])<28)&(y<260)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(pink.astype(np.uint8),8)
    candidates=[i for i in range(1,count) if stats[i,4]>30 and stats[i,1]>120]
    candidates=sorted(candidates,key=lambda i:stats[i,4],reverse=True)[:2]
    displacement=np.zeros((512,512),np.float32)
    for i in candidates:
        left,top,width,height,_=stats[i]
        center=centers[i,0]
        base=top+height+16
        horizontal=np.maximum(0,1-((x-center)/(width/2+16))**2)**2
        vertical=np.clip((base-y)/(height+12),0,1)
        vertical*=np.clip((y-(top-18))/12,0,1)
        displacement=np.maximum(displacement,(horizontal*vertical).astype(np.float32))
    warped=cv2.remap(premultiplied(pixels),x.astype(np.float32),y.astype(np.float32)+displacement*amount,
        cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    alpha=warped[...,3:4]
    rgba=np.concatenate((warped[...,:3]/np.maximum(alpha,0.001),alpha),axis=2)
    result=np.uint8(np.clip(np.rint(rgba*255),0,255))
    # Preserve all pixels outside the ear deformation exactly.
    result[displacement==0]=pixels[displacement==0]
    return Image.fromarray(result)


def reduce_idle_float() -> None:
    paths=sorted((PET/"default/breathe_b").glob("frame_*.png"))
    reference=Image.open(paths[0]).convert("RGBA")
    # Smaller continuous translation; retain the exact neutral at both ends.
    x,y=np.meshgrid(np.arange(512,dtype=np.float32),np.arange(512,dtype=np.float32))
    for index,path in enumerate(paths):
        phase=index/(len(paths)-1)
        offset=1.3*np.sin(2*np.pi*phase)*(1-np.cos(2*np.pi*phase))
        if index in (0,len(paths)-1): frame=reference
        else:
            moved=cv2.remap(premultiplied(np.asarray(reference)),x,y-np.float32(offset),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            alpha=moved[...,3:4]
            rgba=np.concatenate((moved[...,:3]/np.maximum(alpha,0.001),alpha),axis=2)
            frame=Image.fromarray(np.uint8(np.clip(np.rint(rgba*255),0,255)))
        frame.save(path)


def build() -> None:
    timing=json.loads((ROOT/"tools/animation_timing.json").read_text(encoding="utf-8"))
    registrations=re.findall(r"pnganimation#([^:]+):\|path#([^:]+):\|graph#([^:]+):\|animat#([^:]+):",(PET/"info.lps").read_text(encoding="utf-8"))
    reduce_idle_float()
    manifest={}
    for name,folder,graph,phase in registrations:
        selected=(folder.startswith(("touch_head/","touch_body/")) or folder in {
            "default/breathe_b","sleep/curled_a","sleep/curled_c",
            "sleep/flip_to_belly_single","sleep/flip_to_curled_single",
            "sleep/curled_touch_single","sleep/belly_touch_single",
            "idel/stretch_single","idel/sleep_single","common/fall_single",
            "idel/blink_a","idel/blink_b","idel/blink_c",
            "idel/doze_a","idel/doze_b","idel/doze_c"})
        if not selected: continue
        paths=sorted((PET/folder).glob("frame_*.png"))
        frames=[Image.open(p).convert("RGBA") for p in paths]
        durations=timing["frame_ms"][name+"/"+phase]
        starts=[0]
        for duration in durations: starts.append(starts[-1]+duration)
        total=starts[-1]
        cadence=8 if "flip_to" in folder or (graph=="touch_head" and phase=="A_Start") or "blink" in folder or "doze" in folder else 16
        destination=OUT/folder
        destination.mkdir(parents=True,exist_ok=True)
        for stale in destination.glob("frame_*.png"): stale.unlink()
        output_count=0
        for timestamp in list(range(0,total,cadence))+[total]:
            index=min(len(frames)-1,bisect.bisect_right(starts,timestamp)-1)
            fraction=(timestamp-starts[index])/durations[index]
            first=frames[index]
            second=frames[min(index+1,len(frames)-1)]
            if timestamp==total: image=frames[-1]
            elif fraction<0.001 or first.tobytes()==second.tobytes(): image=first
            else:
                image=midpoint(first,second,fraction=fraction,single_texture=False)
                a,b=np.asarray(first),np.asarray(second)
                changed=np.any(a!=b,axis=2)
                rows,columns=np.nonzero(changed)
                # Eye/mouth-only phases never warp the paws or surrounding hair.
                if rows.size and rows.max()-rows.min()<95:
                    top=max(0,int(rows.min())-2); bottom=min(512,int(rows.max())+3)
                    left=max(0,int(columns.min())-2); right=min(512,int(columns.max())+3)
                    pixels=a.copy(); pixels[top:bottom,left:right]=np.asarray(image)[top:bottom,left:right]
                    image=Image.fromarray(pixels)
            if graph=="touch_head" and phase=="A_Start":
                u=timestamp/total
                amount=7*np.sin(np.pi*u)**2*(1+0.3*np.sin(6*np.pi*u))
                image=ear_bounce(image,float(amount))
            output_count+=1
            image.save(destination/f"frame_{output_count:04}.png")
        manifest[name+"/"+phase]={"path":folder,"frame_ms":cadence,"duration_ms":total,"count":output_count}
        print(f"{folder}: {len(frames)} -> {output_count} ({cadence}ms)",flush=True)
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"smooth_sequences={len(manifest)} frames={sum(v['count'] for v in manifest.values())}",flush=True)
    from build_render_manifest import build as build_render_manifest
    build_render_manifest()
    if (ROOT/"tools/sequence_sources/sleep_roll_v24/early_sheet.png").exists():
        from build_sleep_roll import build as build_sleep_roll
        build_sleep_roll()


if __name__=="__main__": build()
