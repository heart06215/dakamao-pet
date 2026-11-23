# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original project contributions only; see 项目开发文档 for scope.
"""Check runtime sidecars and their seams against the registered drawings."""
import json
import hashlib
from pathlib import Path
import re

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
PET=ROOT/"DakamaoPet/PetMod/pet/dakamao"
FLUID=ROOT/"DakamaoPet/PetMod/fluid"


def main():
    manifest=json.loads((FLUID/"manifest.json").read_text(encoding="utf-8"))
    registration={name+"/"+phase:folder for name,folder,phase in re.findall(
        r"pnganimation#([^:]+):\|path#([^:]+):\|graph#[^:]+:\|animat#([^:]+):",(PET/"info.lps").read_text(encoding="utf-8"))}
    issues=[]
    for key,config in manifest.items():
        source=PET if config.get("source")=="pet" else FLUID
        files=sorted((source/config["path"]).glob("frame_*.png"))
        valid_timing=(len(config["frame_durations"])==config["count"] and sum(config["frame_durations"])==config["duration_ms"]) if config.get("source")=="pet" else config["count"]==len(range(0,config["duration_ms"],config["frame_ms"]))+1
        if len(files)!=config["count"] or not valid_timing:
            issues.append("Invalid timing/count: "+key)
        if config.get("source")!="pet" and [p.name for p in files]!=[f"frame_{i+1:04}.png" for i in range(len(files))]: issues.append("Invalid numbering: "+key)
        original=sorted((PET/registration[key]).glob("frame_*.png"))
        for a,b in [(files[0],original[0]),(files[-1],original[-1])]:
            if not np.array_equal(np.asarray(Image.open(a)),np.asarray(Image.open(b))): issues.append("Endpoint mismatch: "+key)
        for file in files:
            with Image.open(file) as frame:
                if frame.mode!="RGBA" or frame.size!=(512,512) or frame.getpixel((0,0))[3]!=0: issues.append("Invalid frame: "+str(file))
    forward=sorted((FLUID/manifest["sleep_roll_to_belly/Single"]["path"]).glob("frame_*.png"))
    reverse=sorted((FLUID/manifest["sleep_roll_to_curled/Single"]["path"]).glob("frame_*.png"))
    if any(a.read_bytes()!=b.read_bytes() for a,b in zip(forward,reversed(reverse))): issues.append("Roll reverse mismatch")
    if set(manifest)!=set(registration): issues.append("Static/animated renderer coverage mismatch")
    provenance_path=FLUID/'sleep-roll-source.json'
    provenance=json.loads(provenance_path.read_text()) if provenance_path.exists() else {}
    is_v26=provenance.get('revision')=='v26_whole_body'
    version='v26' if is_v26 else 'v25'
    stabilization=json.loads((ROOT/f'tools/qa/roll-stabilization-{version}.json').read_text(encoding='utf-8'))
    if stabilization['unique_pixel_frames']!=len(forward):issues.append('Duplicated padding frames in roll sequence')
    if stabilization['anchor_acceleration_rms_after']>=stabilization['anchor_acceleration_rms_before']:issues.append('Sequence registration did not reduce measured shake')
    anatomy_path=ROOT/'tools/sequence_sources/sleep_roll_v25/paw_tracks.json'
    anatomical_keys=0
    if is_v26:
        key_files=sorted((ROOT/provenance['source']).glob('key_*.png'))
        anatomical_keys=len(key_files)
        if anatomical_keys!=43 or provenance['key_count']!=43:issues.append('Incomplete replacement whole-body poses')
        hashes=[hashlib.sha256(Image.open(file).convert('RGBA').tobytes()).hexdigest() for file in key_files]
        if hashes!=provenance['whole_body_source_hashes']:issues.append('Replacement source provenance mismatch')
        old_hashes={hashlib.sha256(Image.open(file).convert('RGBA').tobytes()).hexdigest() for file in (ROOT/'tools/sequence_sources/sleep_roll_v25').glob('key_*.png')}
        if any(key in old_hashes for key in hashes[1:-1]):issues.append('Old malformed intermediate pose retained')
        if provenance['far_hind_leg_hidden_keys']!=[9,10,11] or provenance['rejected_sheet_cells']!={'hip':[4]}:issues.append('Reviewed occlusion/rejected drawing changed')
    elif anatomy_path.exists():
        anatomy=json.loads(anatomy_path.read_text(encoding='utf-8'))
        expected=['front_near','front_far','hind_near','hind_far']
        if anatomy['order']!=expected:issues.append('Paw identity order changed')
        tracks=np.asarray(anatomy['keys']);anatomical_keys=len(tracks)
        if tracks.shape!=(41,4,4):issues.append('Incomplete anatomical key tracks')
        if not np.all(tracks[:,:2,0]<282) or not np.all(tracks[:,2:,0]>260):issues.append('Front/hind paw identity crossed')
    report={"sequences":len(manifest),"dense_frames":sum(v["count"] for v in manifest.values() if v.get("source")!="pet"),
        "all_registered_states_use_original_png_renderer":set(manifest)==set(registration),
        "roll_is_exact_reverse":not any("reverse" in issue for issue in issues),
        "flip_frames":manifest["sleep_roll_to_belly/Single"]["count"],
        "ear_bounce_frames":manifest["touch_head_touch/A_Start"]["count"],
        "anatomical_drawings":anatomical_keys,
        "unique_roll_frames":stabilization['unique_pixel_frames'],
        "anchor_shake_reduction":1-stabilization['anchor_acceleration_rms_after']/stabilization['anchor_acceleration_rms_before'],
        "issues":issues}
    report['pose_revision']=provenance.get('revision','v25')
    (ROOT/f"tools/qa/smooth-validation-{version}.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if issues: raise SystemExit(1)


if __name__=="__main__":main()
