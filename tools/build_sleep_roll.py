# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Project-owned code only; upstream drawing rights remain separate.
"""Bake the corrected 41-key roll once, preserving exact sleep endpoints."""
from pathlib import Path
import json
import bisect
import cv2
import numpy as np
from PIL import Image
from sleep_roll import render

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'tools/base_frames/sleep/flip_to_belly_single'
SOURCE=ROOT/'tools/sequence_sources/sleep_roll_v24'
FLUID=ROOT/'DakamaoPet/PetMod/fluid'
POSITIONS=[0,1,1.2,1.4,1.6,1.8,2,3,4,5,5.2,5.4,5.6,5.8,6]
PHASES=[0,.10,.16,.22,.28,.34,.40,.49,.58,.67,.73,.79,.85,.91,1]

def prepare_sheet(sheet,first,last,label):
    pixels=np.asarray(Image.open(sheet).convert('RGBA'))
    h,w=pixels.shape[:2]; results=[]
    for i in range(4):
        p=pixels[i//2*(h//2):(i//2+1)*(h//2),i%2*(w//2):(i%2+1)*(w//2)].copy()
        _,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(p[...,3]>150),8)
        selected=1+int(np.argmax(stats[1:,4])); mask=np.uint8(labels==selected)
        mask=cv2.dilate(mask,np.ones((3,3),np.uint8))
        p[...,3]=np.where(mask,np.minimum(255,np.rint(p[...,3].astype(float)*255/253)),0).astype(np.uint8)
        image=Image.fromarray(p); bounds=image.getchannel('A').point(lambda a:255 if a>150 else 0).getbbox()
        a,b=[im.getchannel('A').point(lambda a:255 if a>240 else 0).getbbox() for im in (first,last)]
        t=(i+1)/5; target=tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))
        crop=image.crop(bounds).resize((target[2]-target[0],target[3]-target[1]),Image.Resampling.LANCZOS)
        rgb=np.asarray(crop).copy(); values=rgb[...,:3].astype(float)
        neutral=(np.max(values,axis=2)-np.min(values,axis=2)<22)&(values.mean(axis=2)>140)&(rgb[...,3]>245)
        ref=np.asarray(first); reference=ref[...,:3].astype(float)
        ref_mask=(reference.max(axis=2)-reference.min(axis=2)<22)&(reference.mean(axis=2)>140)&(ref[...,3]>245)
        delta=np.clip(np.median(reference[ref_mask],axis=0)-np.median(values[neutral],axis=0),-12,12)
        rgb[neutral,:3]=np.uint8(np.clip(np.rint(values[neutral]+delta),0,255)); crop=Image.fromarray(rgb)
        frame=Image.new('RGBA',(512,512));frame.alpha_composite(crop,target[:2])
        frame.save(SOURCE/f'{label}_{i+1:02}.png');results.append(frame)
    return results

def build():
    if (ROOT/'tools/sequence_sources/sleep_roll_v26/settle_sheet.png').exists():
        from build_sleep_roll_v26 import build as build_whole_body
        return build_whole_body()
    SOURCE.mkdir(parents=True,exist_ok=True)
    original=[Image.open(p).convert('RGBA') for p in sorted(BASE.glob('frame_*.png'))]
    early=prepare_sheet(SOURCE/'early_sheet.png',original[1],original[2],'early')
    late=prepare_sheet(SOURCE/'late_sheet.png',original[5],original[6],'late')
    keys=original[:2]+early+original[2:6]+late+original[6:]
    tracks=None
    positions=POSITIONS;phases=PHASES
    if (ROOT/'tools/sequence_sources/sleep_roll_v25/pads_sheet.png').exists():
        from prepare_sleep_roll_v25 import build_keys
        keys,tracks=build_keys()
        positions=list(range(len(keys)))
        tracked=np.asarray(tracks,dtype=float)
        distance=np.linalg.norm(np.diff(tracked[:,:,:2],axis=0),axis=2)
        visible=(tracked[:-1,:,2]>0)&(tracked[1:,:,2]>0)
        distance=np.where(visible,distance,0).max(axis=1)
        weights=8+distance
        phases=np.concatenate(([0],np.cumsum(weights)/weights.sum()))
    if tracks is None:
        for i,im in enumerate(keys):im.save(SOURCE/f'key_{i:02}.png')
    manifest=json.loads((FLUID/'manifest.json').read_text(encoding='utf-8'))
    total=4400 if tracks is not None else 3200;cadence=8
    frames=[]
    for timestamp in list(range(0,total,cadence))+[total]:
        u=min(timestamp/total,1)
        position=float(np.interp(.5-.5*np.cos(np.pi*u),phases,positions))
        pair=min(len(keys)-2,max(0,bisect.bisect_right(positions,position)-1))
        t=(position-positions[pair])/(positions[pair+1]-positions[pair])
        if tracks is not None:
            from sleep_roll_anatomy import render as render_anatomy
            frame=render_anatomy(keys[pair],keys[pair+1],t,tracks[pair],tracks[pair+1])
        else:frame=render(keys[pair],keys[pair+1],t)
        frames.append(frame)
    frames[0]=original[0];frames[-1]=original[-1]
    if tracks is not None:
        from stabilize_sleep_roll import stabilize
        report=stabilize(frames)
        (ROOT/'tools/qa/roll-stabilization-v25.json').write_text(json.dumps(report,indent=2)+chr(10),encoding='utf-8')
        print('Sequence stabilization: '+json.dumps(report),flush=True)
    for name,folder,sequence in [('sleep_roll_to_belly/Single','sleep/flip_to_belly_single',frames),
                                 ('sleep_roll_to_curled/Single','sleep/flip_to_curled_single',list(reversed(frames)))]:
        destination=FLUID/folder;destination.mkdir(parents=True,exist_ok=True)
        for stale in destination.glob('frame_*.png'):stale.unlink()
        for i,image in enumerate(sequence):image.save(destination/f'frame_{i+1:04}.png')
        manifest[name]={'path':folder,'count':len(sequence),'frame_ms':cadence,'duration_ms':total}
    # Replace the legacy atlas fallback too. It must never retain the old
    # mismatched paw mesh; keep 97 tiles to respect the engine's width limit.
    atlas=[frames[round(i*(len(frames)-1)/96)] for i in range(97)]
    timing_path=ROOT/'tools/animation_timing.json'
    timing=json.loads(timing_path.read_text(encoding='utf-8'))
    for name,folder,sequence in [('sleep_roll_to_belly/Single','sleep/flip_to_belly_single',atlas),
                                 ('sleep_roll_to_curled/Single','sleep/flip_to_curled_single',list(reversed(atlas)))]:
        destination=ROOT/'DakamaoPet/PetMod/pet/dakamao'/folder
        for i,image in enumerate(sequence):image.save(destination/f'frame_{i+1:02}.png')
        timing['frame_ms'][name]=[round((i+1)*total/97)-round(i*total/97) for i in range(97)]
    timing_path.write_text(json.dumps(timing,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')
    (FLUID/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+chr(10),encoding='utf-8')
    print(f'Corrected roll: {len(keys)} keys, {len(frames)} frames, exact reverse',flush=True)

if __name__=='__main__':build()
