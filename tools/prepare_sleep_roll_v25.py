# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Project-owned code only; upstream drawing rights remain separate.
"""Prepare 41 drawings and four separately identified paw tracks."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools/sequence_sources/sleep_roll_v25'
OLD=ROOT/'tools/sequence_sources/sleep_roll_v24'

def sheet(name,first,last,columns=3,rows=2):
    image=Image.open(SOURCE/(name+'_sheet.png')).convert('RGBA');w,h=image.size
    bounds=[im.getchannel('A').point(lambda a:255 if a>240 else 0).getbbox() for im in (first,last)]
    output=[]
    for i in range(columns*rows):
        p=np.asarray(image.crop((i%columns*(w//columns),i//columns*(h//rows),(i%columns+1)*(w//columns),(i//columns+1)*(h//rows)))).copy()
        _,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(p[...,3]>150),8)
        mask=np.uint8(labels==1+np.argmax(stats[1:,4]));mask=cv2.dilate(mask,np.ones((3,3),np.uint8))
        p[...,3]=np.uint8(np.where(mask,np.minimum(255,p[...,3].astype(float)*255/253),0))
        im=Image.fromarray(p);box=im.getchannel('A').point(lambda a:255 if a>150 else 0).getbbox()
        t=(i+1)/(columns*rows+1);target=tuple(round(a*(1-t)+b*t) for a,b in zip(*bounds))
        im=im.crop(box).resize((target[2]-target[0],target[3]-target[1]),Image.Resampling.LANCZOS)
        frame=Image.new('RGBA',(512,512));frame.alpha_composite(im,target[:2]);output.append(frame)
    return output

def build_keys():
    base=[Image.open(p).convert('RGBA') for p in sorted((ROOT/'tools/base_frames/sleep/flip_to_belly_single').glob('*.png'))]
    initial=[base[0]]+sheet('entry',base[0],base[1])+[base[1]]
    initial += [Image.open(OLD/f'early_{i:02}.png').convert('RGBA') for i in range(1,5)]+[base[2]]
    initial += sheet('middle',base[2],base[5])+[base[5]]
    initial += [Image.open(OLD/f'late_{i:02}.png').convert('RGBA') for i in range(1,5)]+[base[6]]
    prior=json.loads((SOURCE/'base_paw_tracks.json').read_text())['keys']
    keys=[];tracks=[]
    for i,image in enumerate(initial):
        keys.append(image);tracks.append(prior[i])
        if i in (8,9):
            extra=sheet('curl' if i==8 else 'pads',image,initial[i+1])
            for j,pose in enumerate(extra):
                t=(j+1)/7
                keys.append(pose);tracks.append((np.asarray(prior[i])*(1-t)+np.asarray(prior[i+1])*t).tolist())
    # These points have been checked against the drawings. Automatic pink
    # component detection confuses cheeks, pads and paw shadows and must not
    # silently rewrite the identities of the manually labelled limbs.
    tracks=json.loads((SOURCE/'manual_paw_tracks.json').read_text())['keys']
    occlusion=sheet('occlusion',keys[12],keys[13],columns=2)
    extra=[]
    for i in range(4):
        t=(i+1)/5
        row=(np.asarray(tracks[12])*(1-t)+np.asarray(tracks[13])*t).tolist()
        row[0][:2]=[(208,422),(208,424),(211,422),(216,411)][i]
        row[1]=[(151,447,25,23),(185,430,0,0),(225,408,0,0),(252,386,24,18)][i]
        extra.append(row)
    keys=keys[:13]+occlusion+keys[13:]
    tracks=tracks[:13]+extra+tracks[13:]
    for path in SOURCE.glob('key_*.png'):path.unlink()
    for i,image in enumerate(keys):image.save(SOURCE/f'key_{i:02}.png')
    (SOURCE/'paw_tracks.json').write_text(json.dumps({'order':['front_near','front_far','hind_near','hind_far'],'keys':tracks},indent=2)+chr(10))
    return keys,tracks

if __name__=='__main__':
    keys,_=build_keys();print('Prepared anatomy keys:',len(keys))
