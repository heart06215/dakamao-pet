"""Check the packaged picture-style sprite sequence and write a small QA report."""

from hashlib import sha256
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image
from head_palette import NAMES as HEAD_PALETTE_NAMES, OUT as HEAD_PALETTE_OUT, TARGET, samples
from build_fluid_frames import TOUCH_EYE_BOXES


ROOT = Path(__file__).resolve().parents[1]
PET = ROOT / "DakamaoPet/PetMod/pet/dakamao"
INFO = PET / "info.lps"
KEYS = ROOT / "tools/keyframes/picture_style"
OUT = ROOT / "tools/qa/frame-validation-v22.json"


def main() -> None:
    registered = set(re.findall(r"\|path#([^:]+):", INFO.read_text(encoding="utf-8")))
    folders = sorted({str(path.parent.relative_to(PET)).replace("\\", "/")
                      for path in PET.rglob("frame_*.png")})
    issues = []
    counts = {}
    combined = sha256()
    keyframes = sorted(KEYS.glob("*.png"))
    palette_names = (
        "front_neutral", "tilt_early_left", "tilt_soft_left",
        "tilt_middle_left", "tilt_far_left", "tilt_early_right",
        "tilt_soft_right", "tilt_middle_right", "tilt_far_right",
        "touch_smile_right",
    )
    palette = {}
    calibrated_palette = {}
    for name in sorted(HEAD_PALETTE_NAMES):
        original = np.asarray(Image.open(KEYS / f"{name}.png").convert("RGBA"))
        calibrated = np.asarray(Image.open(HEAD_PALETTE_OUT / f"{name}.png").convert("RGBA"))
        _, masks = samples(original)
        colors = [np.median(calibrated[mask, :3], axis=0) for mask in masks]
        calibrated_palette[name] = [color.tolist() for color in colors]
        if np.max(np.abs(np.asarray(colors) - TARGET)) > 2:
            issues.append(f"Calibrated fur/ink palette drift: {name}")
        if not np.array_equal(original[..., 3], calibrated[..., 3]):
            issues.append(f"Calibration changed alpha geometry: {name}")
    for name in palette_names:
        pixels = np.asarray(Image.open(KEYS / f"{name}.png").convert("RGBA"))
        neutral = (pixels[:, :, 3] > 240) & (pixels[:, :, 0] > 180) & \
            (pixels[:, :, 1] > 170) & (pixels[:, :, 2] > 170)
        palette[name] = np.median(pixels[neutral, :3], axis=0).round().astype(int).tolist()
    reference = palette["front_neutral"]
    for name, color in palette.items():
        if max(abs(channel - master) for channel, master in zip(color, reference)) > 5:
            issues.append(f"Touch palette drift: {name} {color} vs {reference}")
    for path in keyframes:
        with Image.open(path) as keyframe:
            if keyframe.convert("RGBA").getpixel((0, 0))[3] != 0:
                issues.append(f"Opaque keyframe corner: {path.name}")
    for folder in folders:
        paths = sorted((PET / folder).glob("frame_*.png"))
        counts[folder] = len(paths)
        digits = 3 if len(paths) >= 100 else 2
        expected = [f"frame_{number:0{digits}}.png" for number in range(1, len(paths) + 1)]
        if len(paths) * 512 > 60000:
            issues.append(f"Atlas exceeds engine width limit: {folder}")
        if [path.name for path in paths] != expected:
            issues.append(f"Nonconsecutive frames: {folder}")
        for path in paths:
            with Image.open(path) as frame:
                if frame.size != (512, 512) or frame.mode != "RGBA":
                    issues.append(f"Invalid format: {path.relative_to(PET)}")
                if frame.getpixel((0, 0))[3] != 0:
                    issues.append(f"Opaque corner: {path.relative_to(PET)}")
                if frame.getchannel("A").getbbox() is None:
                    issues.append(f"Empty image: {path.relative_to(PET)}")
            combined.update(str(path.relative_to(PET)).encode("utf-8"))
            combined.update(path.read_bytes())
    if set(folders) != registered:
        issues.append(f"Registration mismatch: {sorted(set(folders) ^ registered)}")
    transition_pairs = [
        ("idel/blink_a", "idel/blink_b"),
        ("idel/blink_b", "idel/blink_c"),
        ("idel/doze_a", "idel/doze_b"),
        ("idel/doze_b", "idel/doze_c"),
        ("raised_static/hold_a", "raised_static/hold_b"),
        ("raised_static/hold_b", "raised_static/hold_c"),
        ("touch_body/touch_a", "touch_body/touch_b"),
        ("touch_body/touch_b", "touch_body/touch_c"),
        ("touch_head/touch_a", "touch_head/touch_b"),
        ("touch_head/touch_b", "touch_head/touch_c"),
        ("touch_head/purr_a", "touch_head/purr_b"),
        ("touch_head/purr_b", "touch_head/purr_c"),
        ("sleep/curled_a", "sleep/curled_b"),
        ("sleep/curled_b", "sleep/curled_c"),
        ("sleep/curled_b", "sleep/curled_touch_single"),
        ("sleep/curled_touch_single", "sleep/curled_b"),
        ("sleep/belly_a", "sleep/belly_b"),
        ("sleep/belly_b", "sleep/belly_c"),
        ("sleep/belly_b", "sleep/belly_touch_single"),
        ("sleep/belly_touch_single", "sleep/belly_b"),
        ("sleep/curled_b", "sleep/flip_to_belly_single"),
        ("sleep/flip_to_belly_single", "sleep/belly_b"),
        ("sleep/belly_b", "sleep/flip_to_curled_single"),
        ("sleep/flip_to_curled_single", "sleep/curled_b"),
        ("walk/west_a", "walk/west_b"),
        ("walk/west_b", "walk/west_c"),
        ("walk/east_a", "walk/east_b"),
        ("walk/east_b", "walk/east_c"),
        ("walk/west_b", "walk/west_blink_single"),
        ("walk/west_blink_single", "walk/west_b"),
        ("walk/east_b", "walk/east_blink_single"),
        ("walk/east_blink_single", "walk/east_b"),
        ("sleep/curled_c", "touch_head/touch_a"),
        ("sleep/curled_c", "touch_head/purr_a"),
        ("touch_head/touch_c", "sleep/curled_a"),
        ("touch_head/purr_c", "sleep/curled_a"),
    ]
    for before, after in transition_pairs:
        last = sorted((PET / before).glob("frame_*.png"))[-1]
        first = sorted((PET / after).glob("frame_*.png"))[0]
        with Image.open(last) as old, Image.open(first) as new:
            old_pixels = np.asarray(old.convert("RGBA"))
            new_pixels = np.asarray(new.convert("RGBA"))
            visible = (old_pixels[:, :, 3] > 0) | (new_pixels[:, :, 3] > 0)
            color_delta = np.abs(old_pixels[:, :, :3].astype(np.int16) -
                                 new_pixels[:, :, :3].astype(np.int16))
            if np.any(old_pixels[:, :, 3] != new_pixels[:, :, 3]) or \
                    np.any(color_delta[visible] > 1):
                issues.append(f"Discontinuous animation seam: {before} -> {after}")
    forward_roll = sorted((PET / "sleep/flip_to_belly_single").glob("frame_*.png"))
    reverse_roll = sorted((PET / "sleep/flip_to_curled_single").glob("frame_*.png"))
    if len(forward_roll) != 97 or any(a.read_bytes() != b.read_bytes() for a,b in zip(forward_roll,reversed(reverse_roll))):
        issues.append("Sleep flips do not share the exact 97-frame reversed trajectory")
    neutral = (PET / "default/breathe_b/frame_01.png").read_bytes()
    idle_singles = [
        "idel/groom_single", "idel/look_around_single",
        "idel/sleep_single", "idel/stretch_single",
        "idel/tail_swish_single", "idel/yawn_single",
    ]
    for folder in idle_singles:
        paths = sorted((PET / folder).glob("frame_*.png"))
        if paths[0].read_bytes() != neutral or paths[-1].read_bytes() != neutral:
            issues.append(f"Idle action does not meet neutral at both ends: {folder}")
    stationary_sleep_loops = ["sleep/zzz_b", "sleep/curled_b", "sleep/belly_b"]
    for folder in stationary_sleep_loops:
        paths = sorted((PET / folder).glob("frame_*.png"))
        first = paths[0].read_bytes()
        if any(path.read_bytes() != first for path in paths[1:]):
            issues.append(f"Sleep hold moves the sprite: {folder}")
    blink_paths = [path for folder in ("idel/blink_a", "idel/blink_b", "idel/blink_c")
                   for path in sorted((PET / folder).glob("frame_*.png"))]
    neutral_pixels = np.asarray(Image.open(PET / "default/breathe_b/frame_01.png"))
    fixed = np.ones((512, 512), dtype=bool)
    for left, top, right, bottom in [(85, 129, 129, 169), (128, 129, 172, 169)]:
        fixed[top * 2:bottom * 2 + 1, left * 2:right * 2 + 1] = False
    for path in blink_paths:
        pixels = np.asarray(Image.open(path))
        if np.any(pixels[fixed] != neutral_pixels[fixed]):
            issues.append(f"Blink moves outside the eye area: {path.relative_to(PET)}")
    closed_pixels = np.asarray(Image.open(PET / "idel/blink_b/frame_01.png")).astype(int)
    eye_pixels = closed_pixels[270:330, 178:337, :3]
    blue_iris = (eye_pixels[:, :, 2] > eye_pixels[:, :, 0] + 25) & \
        (eye_pixels[:, :, 2] > eye_pixels[:, :, 1] + 8)
    if np.any(blue_iris):
        issues.append("Blink closed pose leaves blue iris pixels visible")
    timing = json.loads((ROOT / "tools/animation_timing.json").read_text(encoding="utf-8"))
    for line in INFO.read_text(encoding="utf-8").splitlines():
        match = re.search(r"pnganimation#([^:]+):\|path#([^:]+):\|graph#[^:]+:\|animat#([^:]+):", line)
        if match:
            name, folder, phase = match.groups()
            durations = timing["frame_ms"].get(name + "/" + phase, [])
            if len(durations) != counts[folder] or any(t <= 0 for t in durations):
                issues.append(f"Invalid per-frame timing: {folder}")
    blink_ms = timing["name_ms"]["idel_blink"]
    scene_blinks = [
        ("walk/west_blink_single", "walk_left_blink/Single", 0, [(79,277,119,318)]),
        ("walk/east_blink_single", "walk_right_blink/Single", 0, [(395,289,426,327)]),
        ("raised_static/hold_b", "raised_static_hold/B_Loop", 0, [(189,143,241,183),(265,148,314,189)]),
        ("sleep/curled_touch_single", "sleep_curled_touch/Single", 18, [(119,350,160,388),(179,348,224,386)]),
        ("sleep/belly_touch_single", "sleep_belly_touch/Single", 12, [(176,298,211,333),(139,320,175,359)]),
    ]
    for folder, timing_key, start, boxes in scene_blinks:
        paths = sorted((PET / folder).glob("frame_*.png"))[start:start + 26]
        pixels = [np.asarray(Image.open(path)) for path in paths]
        outside = np.ones((512, 512), dtype=bool)
        for left, top, right, bottom in boxes:
            outside[top:bottom + 1, left:right + 1] = False
        if len(pixels) != 26 or any(not np.array_equal(p[outside], pixels[0][outside]) for p in pixels):
            issues.append(f"Scene blink moves outside eyes: {folder}")
        if timing["frame_ms"].get(timing_key, [])[start:start + 26] != [10] * 26:
            issues.append(f"Scene blink timing incorrect: {folder}")
    fixed_mouth_body = np.ones((512, 512), dtype=bool)
    fixed_mouth_body[325:360, 240:290] = False
    all_mouth_paths = sorted((PET / "touch_head/purr_b").glob("frame_*.png"))
    all_mouth_pixels = [np.asarray(Image.open(path)) for path in all_mouth_paths]
    mouth_paths, mouth_pixels = [], []
    for start in range(len(all_mouth_pixels) - 12):
        candidate = all_mouth_pixels[start:start + 13]
        if (all(np.array_equal(p[fixed_mouth_body], candidate[0][fixed_mouth_body]) for p in candidate)
                and len({p[325:360, 240:290].tobytes() for p in candidate}) >= 7):
            mouth_paths = all_mouth_paths[start:start + 13]
            mouth_pixels = candidate
            break
    if not mouth_pixels:
        raise ValueError("Missing complete 13-frame mouth cycle in head-touch B")
    for path, pixels in zip(mouth_paths, mouth_pixels):
        if not np.array_equal(pixels[fixed_mouth_body], mouth_pixels[0][fixed_mouth_body]):
            issues.append(f"Mouth animation changes face/body outside ROI: {path.name}")
    mouth_unique = len({pixels[325:360, 240:290].tobytes() for pixels in mouth_pixels})
    if mouth_unique < 7:
        issues.append(f"Too few distinct mouth transitions: {mouth_unique}")
    closed_eye_frames = {}
    for folder, side, base_index in [("touch_b", "left", 6), ("purr_b", "right", 7)]:
        opened = np.asarray(Image.open(ROOT / f"tools/base_frames/touch_head/{folder}/frame_03.png"))
        if side == "right":
            opened = np.asarray(Image.open(ROOT / f"tools/base_frames/touch_head/{folder}/frame_04.png"))
        closed = np.asarray(Image.open(ROOT / f"tools/base_frames/touch_head/{folder}/frame_{base_index:02}.png"))
        outside = np.ones((512, 512), dtype=bool)
        for left, top, right, bottom in TOUCH_EYE_BOXES[side]:
            outside[top:bottom + 1, left:right + 1] = False
        if not np.array_equal(opened[outside], closed[outside]):
            issues.append(f"Touch eyelids change body/hair: {side}")
        eye = closed[~outside, :3].astype(int)
        if np.any((eye[:, 2] > eye[:, 0] + 25) & (eye[:, 2] > eye[:, 1] + 8)):
            issues.append(f"Touch closed eyes retain blue iris: {side}")
        matches = [path.name for path in sorted((PET / f"touch_head/{folder}").glob("frame_*.png"))
                   if np.array_equal(np.asarray(Image.open(path)), closed)]
        closed_eye_frames[side] = matches
        if len(matches) < 4:
            issues.append(f"Touch closed-eye hold missing: {side}")
    body_expression = np.asarray(Image.open(PET / "touch_body/touch_b/frame_01.png"))
    body_neutral = np.asarray(Image.open(ROOT / "tools/base_frames/touch_body/touch_a/frame_06.png"))
    body_fixed = np.ones((512, 512), dtype=bool)
    body_fixed[317:382, 102:230] = False
    if not np.array_equal(body_expression[body_fixed], body_neutral[body_fixed]):
        issues.append("Body-touch expression changes paws/body outside face ROI")
    eyes = body_expression[328:354, 110:220, :3].astype(int)
    if np.any((eyes[:, :, 2] > eyes[:, :, 0] + 25) & (eyes[:, :, 2] > eyes[:, :, 1] + 8)):
        issues.append("Body-touch closed eyes retain a blue iris")
    neutral_alpha = neutral_pixels[:, :, 3] >= 128
    touch_rows, touch_columns = np.nonzero(neutral_alpha)
    touch_bounds = [int(touch_columns.min()), int(touch_rows.min()),
                    int(touch_columns.max()) + 1, int(touch_rows.max()) + 1]
    report = {
        "registered_folders": len(registered),
        "picture_style_keyframes": len(keyframes),
        "total_frames": sum(counts.values()),
        "frame_resolution": 512,
        "blink_frames": len(blink_paths),
        "blink_frame_ms": blink_ms,
        "blink_fps": round(1000 / blink_ms, 2),
        "blink_duration_ms": len(blink_paths) * blink_ms,
        "blink_body_fixed": True,
        "scene_blink_folders": [entry[0] for entry in scene_blinks],
        "mouth_cycle_frames": len(mouth_paths),
        "mouth_unique_frames": mouth_unique,
        "mouth_face_body_fixed": True,
        "touch_closed_eye_frames": closed_eye_frames,
        "touch_mouth_open_cycles": {"touch": 0, "purr": 1},
        "body_touch_face_only": True,
        "body_touch_closed_eyes": True,
        "front_touch_bounds": touch_bounds,
        "front_touch_split_y": (touch_bounds[1] + touch_bounds[3]) / 2,
        "sleep_direct_switch_seams": 4,
        "sleep_flip_frames": len(forward_roll),
        "sleep_flip_exact_reverse": True,
        "folder_frames": counts,
        "matched_transition_seams": len(transition_pairs),
        "neutral_idle_actions": len(idle_singles),
        "stationary_sleep_loops": len(stationary_sleep_loops),
        "touch_palette_medians": palette,
        "touch_material_palette": calibrated_palette,
        "sha256": combined.hexdigest(),
        "issues": issues,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"folders={len(registered)} frames={report['total_frames']} issues={len(issues)}")
    if issues:
        raise SystemExit("\n".join(issues))


if __name__ == "__main__":
    main()
