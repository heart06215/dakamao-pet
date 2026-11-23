# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Project-owned code only; upstream image rights remain separate.
"""Use the same original-PNG renderer for static and animated states."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PET=ROOT/'DakamaoPet/PetMod/pet/dakamao'
MANIFEST=ROOT/'DakamaoPet/PetMod/fluid/manifest.json'

def build():
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    timing=json.loads((ROOT/'tools/animation_timing.json').read_text(encoding='utf-8'))
    records=re.findall(r'pnganimation#([^:]+):\|path#([^:]+):\|graph#([^:]+):\|animat#([^:]+):',
                       (PET/'info.lps').read_text(encoding='utf-8'))
    for name,folder,graph,phase in records:
        key=name+'/'+phase
        if key in manifest and manifest[key].get('source')!='pet': continue
        count=len(list((PET/folder).glob('frame_*.png')))
        durations=timing['frame_ms'][key]
        if len(durations)!=count: raise ValueError(key)
        manifest[key]={'source':'pet','path':folder,'count':count,'frame_ms':durations[0],
                       'duration_ms':sum(durations),'frame_durations':durations}
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Unified original-PNG renderer: {len(manifest)} sequences',flush=True)

if __name__=='__main__': build()
