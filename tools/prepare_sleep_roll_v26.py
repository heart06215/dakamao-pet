# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original project contributions; upstream character rights remain separate.
"""Prepare replacement whole-body poses without stretching their proportions."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools/sequence_sources/sleep_roll_v26'

def cells(name):
    sheet=Image.open(SOURCE/f'{name}_sheet.png').convert('RGBA')
    w,h=sheet.size
    return [sheet.crop((i%3*w//3,i//3*h//2,(i%3+1)*w//3,(i//3+1)*h//2)) for i in range(6)]

def normalize(image):
    pixels=np.asarray(image).copy()
    _,labels,stats,_=cv2.connectedComponentsWithStats(np.uint8(pixels[...,3]>150),8)
    mask=np.uint8(labels==1+np.argmax(stats[1:,4]))
    mask=cv2.dilate(mask,np.ones((3,3),np.uint8))
    pixels[...,3]=np.where(mask,np.clip(pixels[...,3].astype(float)*255/253,0,255),0).astype(np.uint8)
    pixels[pixels[...,3]<40,3]=0
    image=Image.fromarray(pixels)
    box=image.getchannel('A').point(lambda a:255 if a>150 else 0).getbbox()
    # One uniform scale per drawing. Never stretch height to fit a pose box.
    width=420;scale=width/(box[2]-box[0]);height=round((box[3]-box[1])*scale)
    crop=image.crop(box).resize((width,height),Image.Resampling.LANCZOS)
    result=Image.new('RGBA',(512,512));result.alpha_composite(crop,(47,502-height))
    return result

def build_keys():
    master,side,back=[cells(name) for name in ('master','side','back')]
    old=ROOT/'tools/sequence_sources/sleep_roll_v25'
    poses=[Image.open(old/'key_00.png').convert('RGBA')]
    poses += [normalize(im) for im in master[:2]+side+[master[2]]+back+master[3:]]
    poses += [Image.open(old/'key_40.png').convert('RGBA')]
    hip,head=[cells(name) for name in ('hip','head')]
    # Hip cell 4 retains a tucked rear toe in addition to two raised soles:
    # reject that drawing instead of propagating an extra limb into frames.
    insert={4:[normalize(hip[i]) for i in (0,1,2,3,5)],12:[normalize(im) for im in head]}
    expanded=[];origins=[]
    for i,im in enumerate(poses):
        expanded.append(im);origins.append({'base':i})
        for j,extra in enumerate(insert.get(i,[])):
            expanded.append(extra);origins.append({'between':[i,i+1],'fraction':(j+1)/(len(insert[i])+1)})
    poses=expanded
    hide,settle=[cells(name) for name in ('hide','settle')]
    last=[];final_origins=[]
    for i,im in enumerate(poses):
        last.append(im);final_origins.append(origins[i])
        group={8:hide,27:settle}.get(i,[])
        for j,extra in enumerate(group):
            last.append(normalize(extra));final_origins.append({'sheet':'hide' if i==8 else 'settle','cell':j})
    poses=last
    (SOURCE/'pose_order.json').write_text(json.dumps(final_origins,indent=2)+'\n')
    for i,im in enumerate(poses):im.save(SOURCE/f'key_{i:02}.png')
    grid=Image.new('RGB',(1280,((len(poses)+4)//5)*180),'#35343b');draw=ImageDraw.Draw(grid)
    for i,im in enumerate(poses):
        crop=im.crop((25,205,490,512));crop.thumbnail((250,160),Image.Resampling.LANCZOS)
        x=i%5*256;y=i//5*180;grid.paste(crop,(x,y+20),crop);draw.text((x+8,y+2),str(i),fill='white')
    grid.save(ROOT/'tools/qa/roll-v26-keys.jpg',quality=95)
    return poses

if __name__=='__main__':print('Whole-body replacement poses:',len(build_keys()))
