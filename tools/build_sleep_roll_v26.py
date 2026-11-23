# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original project contributions; upstream character rights remain separate.
"""Replace the dislocated torso/hip rollover using reviewed whole-body poses."""
from pathlib import Path
import hashlib
import json
import shutil
import cv2
import numpy as np
from PIL import Image,ImageDraw
from prepare_sleep_roll_v26 import build_keys
from sleep_roll_whole_body import bounded_motion,render
from stabilize_sleep_roll import stabilize

ROOT=Path(__file__).resolve().parents[1]
FLUID=ROOT/'DakamaoPet/PetMod/fluid'
SOURCE=ROOT/'tools/sequence_sources/sleep_roll_v26'

def build():
    cv2.setNumThreads(1)
    keys=build_keys();assert len(keys)==43
    weights=[]
    for a,b in zip(keys,keys[1:]):
        pa,pb,f,r=bounded_motion(a.tobytes(),b.tobytes())
        visible=(pa[...,3]>.9)&(pb[...,3]>.9)
        # Give larger whole-body moves more time, rather than spending the
        # same duration on near-duplicate drawings and large physical rolls.
        amount=float(np.mean(np.linalg.norm(f,axis=2)[visible]))
        weights.append(8+4*min(amount,18))
    phases=np.concatenate(([0],np.cumsum(weights)/sum(weights)))
    total=4400;cadence=8;frames=[]
    for i,timestamp in enumerate(range(0,total+1,cadence)):
        u=timestamp/total;progress=.5-.5*np.cos(np.pi*u)
        position=float(np.interp(progress,phases,np.arange(len(keys))))
        pair=min(len(keys)-2,int(position));t=position-pair
        frames.append(render(keys[pair],keys[pair+1],t))
        if i%100==0:print(f'Whole-body sequence {i+1}/551, pose {pair}->{pair+1}',flush=True)
    frames[0]=keys[0];frames[-1]=keys[-1]
    report=stabilize(frames)
    report.update({'revision':'v26_whole_body','key_count':len(keys),'duration_ms':total})
    (ROOT/'tools/qa/roll-stabilization-v26.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest=json.loads((FLUID/'manifest.json').read_text(encoding='utf-8'))
    for name,folder,sequence in [('sleep_roll_to_belly/Single','sleep/flip_to_belly_single',frames),
                                  ('sleep_roll_to_curled/Single','sleep/flip_to_curled_single',frames[::-1])]:
        destination=FLUID/folder;staging=destination.with_name(destination.name+'_v26_stage')
        staging.mkdir(parents=True,exist_ok=True)
        for i,im in enumerate(sequence):im.save(staging/f'frame_{i+1:04}.png',compress_level=3)
        for stale in destination.glob('frame_*.png'):stale.unlink()
        for frame in staging.glob('frame_*.png'):frame.replace(destination/frame.name)
        staging.rmdir()
        manifest[name]={'path':folder,'count':len(sequence),'frame_ms':cadence,'duration_ms':total}
    atlas=[frames[round(i*(len(frames)-1)/96)] for i in range(97)]
    timing_path=ROOT/'tools/animation_timing.json'
    timing=json.loads(timing_path.read_text(encoding='utf-8'))
    for name,folder,sequence in [('sleep_roll_to_belly/Single','sleep/flip_to_belly_single',atlas),
                                  ('sleep_roll_to_curled/Single','sleep/flip_to_curled_single',atlas[::-1])]:
        destination=ROOT/'DakamaoPet/PetMod/pet/dakamao'/folder
        for i,im in enumerate(sequence):im.save(destination/f'frame_{i+1:02}.png')
        timing['frame_ms'][name]=[round((i+1)*total/97)-round(i*total/97) for i in range(97)]
    timing_path.write_text(json.dumps(timing,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (FLUID/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    provenance={'revision':'v26_whole_body','key_count':len(keys),'source':'tools/sequence_sources/sleep_roll_v26',
        'whole_body_source_hashes':[hashlib.sha256(im.tobytes()).hexdigest() for im in keys],
        'stabilization_report':'tools/qa/roll-stabilization-v26.json',
        'far_hind_leg_hidden_keys':[9,10,11],'rejected_sheet_cells':{'hip':[4]},
        'legacy_fallback_count':97,'duration_ms':total}
    (FLUID/'sleep-roll-source.json').write_text(json.dumps(provenance,indent=2)+'\n')
    grid=Image.new('RGB',(1280,4*180),'#34343b');draw=ImageDraw.Draw(grid)
    for slot,i in enumerate(np.linspace(0,len(frames)-1,20).astype(int)):
        im=frames[i].crop((25,205,490,512));im.thumbnail((250,160));x=slot%5*256;y=slot//5*180
        grid.paste(im,(x,y+20),im);draw.text((x+8,y+2),f'{i+1:04} {i*cadence/1000:.2f}s',fill='white')
    grid.save(ROOT/'tools/qa/roll-v26-final-sequence.jpg',quality=95)
    print('Whole-body replacement complete: '+json.dumps(report),flush=True)

if __name__=='__main__':build()
