"""Rebuild the pet sequences from approved picture-style keyframes."""

from pathlib import Path
from shutil import copy2
from functools import lru_cache
import re
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from build_blink_frames import fitted_frame
from head_palette import normalize as normalize_head_palette
from continuous_morph import morph as continuous_morph, ROLL_POINTS


ROOT = Path(__file__).resolve().parents[1]
PET = ROOT / "DakamaoPet/PetMod/pet/dakamao"
BASE = ROOT / "tools/base_frames"
SEQUENCE_SOURCE = ROOT / "tools/sequence_sources"
KEYS = ROOT / "tools/keyframes/upgrade"
PICTURE_STYLE = ROOT / "tools/keyframes/picture_style"
FRAME_SCALE = 2
FRAME_SIZE = 256 * FRAME_SCALE
TOUCH_EYE_BOXES = {
    "left": [(180, 289, 239, 327), (263, 308, 319, 351)],
    "right": [(173, 308, 244, 356), (269, 287, 322, 331)],
}


def touch_eye_cycle(opened: Image.Image, edited: Image.Image, side: str) -> list[Image.Image]:
    mask = Image.new("L", opened.size)
    for box in TOUCH_EYE_BOXES[side]:
        ImageDraw.Draw(mask).rectangle(box, fill=255)
    closed = Image.composite(edited, opened, mask)

    def closing(fraction: float) -> Image.Image:
        # Compress the existing round iris into its lid rather than fading
        # two unrelated eyes. Every pixel outside these two patches is fixed.
        result = closed.copy()
        for left, top, right, bottom in TOUCH_EYE_BOXES[side]:
            patch = opened.crop((left, top, right, bottom))
            pixels = np.asarray(closed.crop((left, top, right, bottom)))
            rows = np.nonzero(pixels[..., :3].mean(axis=2) < 120)[0]
            lid = top + (float(np.median(rows)) if rows.size else (bottom - top) / 2)
            height = max(1, round((bottom - top) * (1 - fraction)))
            center = (top + bottom) / 2 * (1 - fraction) + lid * fraction
            y = round(center - height / 2)
            result.paste(patch.resize((right - left, height), Image.Resampling.LANCZOS), (left, y))
        return result

    third, two_thirds = closing(1 / 3), closing(2 / 3)
    return [opened, third, two_thirds, closed, closed, two_thirds, third, opened]


def pose_blink(opened: Image.Image, boxes: list[tuple[int, int, int, int]]) -> list[Image.Image]:
    """Reuse the 11-close/4-hold/11-open cadence with a stationary pose."""
    closed = opened.copy()
    for left, top, right, bottom in boxes:
        patch = np.asarray(opened.crop((left, top, right, bottom))).astype(int)
        fur = (patch[..., 0] > 220) & (patch[..., 1] > 210) & (patch[..., 2] > 210)
        skin = tuple(np.median(patch[fur, :3], axis=0).round().astype(int)) + (255,)
        ink = (patch[..., 0] > patch[..., 1] + 10) & (patch[..., 1] < 115)
        line = tuple(np.median(patch[ink, :3], axis=0).round().astype(int)) + (255,) if ink.any() else (83, 55, 62, 255)
        draw = ImageDraw.Draw(closed)
        draw.rectangle((left, top, right - 1, bottom - 1), fill=skin)
        y = (top + bottom) // 2
        draw.line([(left + 3, y - 1), ((left + right) // 2, y + 1), (right - 3, y - 1)], fill=line, width=3)

    def closing(fraction: float) -> Image.Image:
        if fraction == 0: return opened
        if fraction == 1: return closed
        result = closed.copy()
        for left, top, right, bottom in boxes:
            height = max(1, round((bottom - top) * (1 - fraction)))
            patch = opened.crop((left, top, right, bottom)).resize((right - left, height), Image.Resampling.LANCZOS)
            result.paste(patch, (left, round((top + bottom - height) / 2)))
        return result
    closing_frames = [closing(step / 10) for step in range(11)]
    return closing_frames + [closed] * 4 + list(reversed(closing_frames))
GENERATED = Path.home() / ".codex/generated_images/01a0eb59-c50f-7951-bc74-3963cc0d6d38"
SOURCES = {
    "hold_full_size": "exec-27116c8f-59bc-485f-bc11-24fc97ae418b.png",
    "look_half_left": "exec-66da8c97-63ad-4161-9255-209c9acb3b21.png",
    "fall_descent": "exec-b187e07b-c4c0-43e8-998b-5e460607d2bb.png",
    "fall_tuck": "exec-f9b6a82c-d8d6-4bba-904b-8ca40beb102e.png",
    "fall_impact": "exec-b362b5e1-633a-450a-9f20-ac944c888ee0.png",
    "fall_rebound": "exec-d98d6087-3f02-44ca-8c35-c44816bc7398.png",
    "fall_recover": "exec-530ea1d6-7a3e-41f0-92cd-281f75f7723c.png",
    "fall_settle": "exec-114be574-a3a0-4298-ac58-6e76fc582c11.png",
}


def snapshot_originals() -> None:
    if list(BASE.rglob("frame_*.png")):
        return
    for path in PET.rglob("frame_*.png"):
        destination = BASE / path.relative_to(PET)
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy2(path, destination)


def fit_key(name: str, width: int, height: int, bottom: int = 248) -> Image.Image:
    image = Image.open(KEYS / f"{name}.png").convert("RGBA")
    bbox = image.getchannel("A").point(lambda value: 255 if value > 240 else 0).getbbox()
    if bbox is None:
        raise ValueError(f"Empty keyframe: {name}")
    image = image.crop(bbox)
    scale = min(width / image.width, height / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)),
                         Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (256, 256))
    output.alpha_composite(image, ((256 - image.width) // 2, bottom - image.height))
    return output


def save_base(folder: str, poses: list[Image.Image]) -> None:
    destination = BASE / folder
    destination.mkdir(parents=True, exist_ok=True)
    for stale in destination.glob("frame_*.png"):
        stale.unlink()
    for index, pose in enumerate(poses, start=1):
        pose.save(destination / f"frame_{index:02}.png")


def build_picture_style_base() -> None:
    """Build every animation from the approved face and fuller side silhouettes."""
    def pose(name: str, width: int = 150, height: int = 198,
             bottom: int = 248) -> Image.Image:
        image = Image.open(PICTURE_STYLE / f"{name}.png").convert("RGBA")
        image = normalize_head_palette(image, name)
        bbox = image.getchannel("A").point(lambda value: 255 if value > 240 else 0).getbbox()
        if bbox is None:
            raise ValueError(f"Empty picture-style keyframe: {name}")
        image = image.crop(bbox)
        scale = min(width * FRAME_SCALE / image.width,
                    height * FRAME_SCALE / image.height)
        image = image.resize((round(image.width * scale), round(image.height * scale)),
                             Image.Resampling.LANCZOS)
        result = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE))
        result.alpha_composite(image, ((FRAME_SIZE - image.width) // 2,
                                      bottom * FRAME_SCALE - image.height))
        return result

    def moved(source: Image.Image, dx: int = 0, dy: int = 0) -> Image.Image:
        result = Image.new("RGBA", (FRAME_SIZE, FRAME_SIZE))
        result.alpha_composite(source, (dx * FRAME_SCALE, dy * FRAME_SCALE))
        return result

    front = pose("front_neutral")
    talk = pose("front_talk")
    yawn_start = pose("yawn_start")
    yawn_mid = pose("yawn_mid")
    yawn_peak = pose("yawn_peak")
    eighth = pose("blink_eighth")
    quarter = pose("blink_quarter")
    half = pose("blink_half")
    three_quarter_blink = pose("blink_three_quarter")
    closed = pose("blink_closed")
    # Keep the accepted body and hair perfectly still. Existing imagegen keys
    # supply the eyelids; interpolation changes only these two eye regions.
    eye_mask = Image.new("L", (FRAME_SIZE, FRAME_SIZE))
    eye_draw = ImageDraw.Draw(eye_mask)
    for box in [(89, 133, 125, 165), (132, 133, 168, 165)]:
        eye_draw.rectangle(tuple(value * FRAME_SCALE for value in box), fill=255)
    eye_mask = eye_mask.filter(ImageFilter.GaussianBlur(0.65 * FRAME_SCALE))
    blink_keys = [front] + [Image.composite(key, front, eye_mask)
                            for key in (eighth, quarter, half,
                                        three_quarter_blink, closed)]
    eighth, quarter, half, three_quarter_blink, closed = blink_keys[1:]
    blink_close = []
    for first, second in zip(blink_keys, blink_keys[1:]):
        between = Image.composite(midpoint(first, second), front, eye_mask)
        blink_close.extend((first, between))
    blink_close.append(closed)
    left_three = pose("three_quarter_left", 192, 185)
    left_start = pose("turn_start_left", 156, 194)
    left_entry = pose("turn_15_left", 162, 192)
    left_early = pose("turn_25_left", 169, 190)
    left_middle = pose("turn_38_left", 181, 187)
    left_almost_side = pose("turn_65_left", 195, 182)
    left_late = pose("turn_75_left", 197, 183)
    left_side = pose("side_left", 198, 180)
    left_step_a = pose("walk_left_a", 198, 180)
    left_step_b = pose("walk_left_b", 198, 180)
    right_three = pose("three_quarter_right", 192, 185)
    right_start = pose("turn_start_right", 156, 194)
    right_entry = pose("turn_15_right", 162, 192)
    right_early = pose("turn_25_right", 169, 190)
    right_middle = pose("turn_38_right", 181, 187)
    right_almost_side = pose("turn_65_right", 195, 182)
    right_late = pose("turn_75_right", 197, 183)
    right_side = pose("side_right", 198, 180)
    right_step_a = pose("walk_right_a", 198, 180)
    right_step_b = pose("walk_right_b", 198, 180)
    tilt_left_early = pose("tilt_early_left")
    tilt_left = pose("tilt_soft_left")
    tilt_left_middle = pose("tilt_middle_left")
    tilt_left_far = pose("tilt_far_left")
    tilt_right_early = pose("tilt_early_right")
    tilt_right = pose("tilt_soft_right")
    tilt_right_middle = pose("tilt_middle_right")
    tilt_right_far = pose("tilt_far_right")
    touch_smile_right = pose("touch_smile_right")
    mouth_mask = Image.new("L", (FRAME_SIZE, FRAME_SIZE))
    ImageDraw.Draw(mouth_mask).rectangle((248, 330, 282, 354), fill=255)
    mouth_mask = mouth_mask.filter(ImageFilter.GaussianBlur(0.6))
    mouth_closed, mouth_quarter, mouth_half = [
        Image.composite(pose("touch_mouth_" + stage), touch_smile_right, mouth_mask)
        for stage in ("closed", "quarter", "half")
    ]
    mouth_cycle = [mouth_closed, mouth_quarter, mouth_half, touch_smile_right,
                   mouth_half, mouth_quarter, mouth_closed]
    left_eye_cycle = touch_eye_cycle(tilt_left, pose("touch_closed_left"), "left")
    right_eye_cycle = touch_eye_cycle(tilt_right, pose("touch_closed_right"), "right")
    # B loops end with the continuous warp back toward their first pose.
    # Use that exact image to start C, so ending a touch does not jump.
    touch_loop_exit = continuous_morph(tilt_left_middle, tilt_left_far, 0.8)
    purr_loop_exit = continuous_morph(tilt_right_middle, tilt_right_far, 0.8)
    down_early = pose("down_early", 153, 195)
    down_transition = pose("down_transition", 169, 185)
    down_mid = pose("down_mid", 182, 177)
    sleep_bridge = pose("sleep_bridge", 188, 169)
    sleep_turn = pose("sleep_turn", 200, 161)
    sleep_drowsy = pose("sleep_drowsy", 208, 157)
    sleep_closed = pose("sleep_closed", 208, 157)
    sleep_head_half = pose("sleep_head_half", 208, 190)
    sleep_head_up = pose("sleep_head_up", 208, 190)
    sleep_roll_early = pose("sleep_roll_early", 208, 170)
    sleep_roll_side = pose("sleep_roll_side", 208, 170)
    sleep_roll_mid = pose("sleep_roll_mid", 208, 170)
    sleep_roll_between_side_mid = pose("sleep_roll_between_side_mid", 208, 170)
    sleep_roll_between_mid_back = pose("sleep_roll_between_mid_back", 208, 170)
    sleep_belly_up = pose("sleep_belly_up", 208, 170)
    sleep_belly_head_half = pose("sleep_belly_head_half", 208, 170)
    sleep_belly_head_up = pose("sleep_belly_head_up", 208, 170)
    rise_entry = pose("rise_entry", 191, 169)
    rise_low = pose("rise_low", 194, 166)
    body_face_mask = Image.new("L", (FRAME_SIZE, FRAME_SIZE))
    ImageDraw.Draw(body_face_mask).rectangle((108, 322, 224, 376), fill=255)
    body_face_mask = body_face_mask.filter(ImageFilter.GaussianBlur(1))
    body_content = Image.composite(pose("body_content", 194, 166), rise_low, body_face_mask)
    rise_half = pose("rise_half", 194, 177)
    rise_push = pose("rise_push", 191, 181)
    rise_sit = pose("rise_sit", 183, 190)
    rise_exit = pose("rise_exit", 158, 195)
    hold = pose("hold", 154, 218, 230)
    descent = pose("fall_descent", 164, 195, 224)
    fall_pancake = pose("fall_impact", 194, 144)
    fall_impact_front = pose("fall_impact_front", 168, 177)

    curled_entry = [front, down_early, down_transition, down_mid,
                    sleep_bridge, sleep_turn, sleep_drowsy, sleep_closed]
    curled_exit = [sleep_closed, sleep_drowsy, sleep_turn, sleep_bridge,
                   down_mid, rise_entry, rise_low, rise_half, rise_push,
                   rise_sit, rise_exit, front]
    roll_to_back = [sleep_closed, sleep_roll_early, sleep_roll_side,
                    sleep_roll_between_side_mid, sleep_roll_mid,
                    sleep_roll_between_mid_back, sleep_belly_up]

    frames = {
        "default/breathe_b": [front, moved(front, 0, 1), moved(front, 0, 2),
                              moved(front, 0, 1), front, moved(front, 0, -1)],
        "idel/blink_a": blink_close,
        "idel/blink_b": [closed] * 4,
        "idel/blink_c": list(reversed(blink_close)),
        "idel/doze_a": blink_close,
        "idel/doze_b": [closed] * 4,
        "idel/doze_c": list(reversed(blink_close)),
        "idel/groom_single": [front, tilt_left, tilt_right, front],
        "idel/look_around_single": [front, left_start, left_entry, left_early, left_middle,
                                    left_three, left_almost_side, left_late,
                                    left_side, moved(left_step_a, -3),
                                    moved(left_side, -5), moved(left_step_b, -8),
                                    moved(left_side, -10), moved(left_late, -9),
                                    moved(left_almost_side, -8), moved(left_three, -6),
                                    moved(left_middle, -4), moved(left_early, -2),
                                    left_entry, left_start, front, right_start,
                                    right_entry, right_early,
                                    right_middle, right_three, right_almost_side,
                                    right_late, right_side, moved(right_step_a, 3),
                                    moved(right_side, 5), moved(right_step_b, 8),
                                    moved(right_side, 10), moved(right_late, 9),
                                    moved(right_almost_side, 8), moved(right_three, 6),
                                    moved(right_middle, 4), moved(right_early, 2),
                                    right_entry, right_start, front],
        "walk/west_a": [front, left_start, left_entry, left_early, left_middle,
                         left_three, left_almost_side, left_late, left_side],
        "walk/west_b": [left_side, left_step_a, left_side, left_step_b, left_side],
        "walk/west_c": [left_side, left_late, left_almost_side, left_three,
                         left_middle, left_early, left_entry, left_start, front],
        "walk/east_a": [front, right_start, right_entry, right_early, right_middle,
                         right_three, right_almost_side, right_late, right_side],
        "walk/east_b": [right_side, right_step_a, right_side, right_step_b, right_side],
        "walk/east_c": [right_side, right_late, right_almost_side, right_three,
                         right_middle, right_early, right_entry, right_start, front],
        "walk/west_blink_single": pose_blink(left_side, [(79, 277, 119, 318)]),
        "walk/east_blink_single": pose_blink(right_side, [(395, 289, 426, 327)]),
        "idel/sleep_single": curled_entry + [sleep_closed] * 10 + curled_exit,
        "idel/stretch_single": [front, down_early, down_transition, down_mid,
                                rise_entry, rise_low,
                                rise_half, rise_push, rise_sit, rise_exit, front],
        "idel/tail_swish_single": [front, left_start, left_entry, left_early,
                                    left_middle, left_three,
                                    left_almost_side, left_late, left_side,
                                    moved(left_side, 0, 1), left_side,
                                    left_late, left_almost_side, left_three,
                                    left_middle, left_early, left_entry, left_start, front],
        "idel/yawn_single": [front, yawn_start, yawn_mid,
                              yawn_peak, yawn_peak, yawn_peak,
                              yawn_mid, yawn_start, front],
        "raised_dynamic/wiggle_single": [moved(hold, -2, 1), hold,
                                          moved(hold, 2, 1), hold],
        "raised_static/hold_a": [hold, moved(hold, 0, 1), hold],
        "raised_static/hold_b": [hold, moved(hold, -2), hold,
                                  moved(hold, 2), hold],
        "raised_static/hold_c": [hold, descent],
        "common/falling_single": [descent, moved(descent, 0, 3), descent],
        "common/fall_single": [fall_pancake, fall_pancake,
                               down_mid, rise_entry, rise_low,
                               rise_half, rise_push, rise_sit, rise_exit, front],
        "say/talk_b": [front, talk],
        "shutdown/bye_single": blink_close,
        # Sleep holds never translate the entire sprite: paws, tail and body
        # remain pixel-identical, including the loop boundary.
        "sleep/zzz_b": [sleep_closed] * 8,
        "sleep/curled_a": curled_entry,
        "sleep/curled_b": [sleep_closed] * 8,
        "sleep/curled_c": curled_exit,
        "sleep/curled_touch_single": [sleep_closed, sleep_drowsy,
                                       sleep_head_half, sleep_head_up,
                                       sleep_head_up, sleep_head_up,
                                       sleep_head_half, sleep_drowsy, sleep_closed],
        "sleep/belly_a": curled_entry + roll_to_back[1:],
        "sleep/belly_b": [sleep_belly_up] * 8,
        "sleep/flip_to_belly_single": roll_to_back,
        "sleep/flip_to_curled_single": list(reversed(roll_to_back)),
        "sleep/belly_c": list(reversed(roll_to_back))[:-1] + curled_exit,
        "sleep/belly_touch_single": [sleep_belly_up, sleep_belly_head_half,
                                      sleep_belly_head_up, sleep_belly_head_up,
                                      sleep_belly_head_up, sleep_belly_head_half,
                                      sleep_belly_up],
        "startup/boot_single": list(reversed(blink_close)),
        "switch_down/down_single": [front, tilt_left, front],
        "switch_hunger/hungry_single": [front, talk, front],
        "switch_thirsty/thirsty_single": [front, talk, front],
        "switch_up/up_single": [front, tilt_right, front],
        "touch_body/touch_a": [front, down_early, down_transition, down_mid,
                               rise_entry, rise_low, body_content],
        "touch_body/touch_b": [body_content, moved(body_content, -2), body_content,
                               moved(body_content, 2), body_content],
        "touch_body/touch_c": [body_content, rise_low, rise_half, rise_push, rise_sit,
                               rise_exit, front],
        "touch_head/touch_a": [front, tilt_left_early,
                                tilt_left, tilt_left_middle, tilt_left_far],
        "touch_head/touch_b": [tilt_left_far, tilt_left_middle, left_eye_cycle,
                                tilt_left_early, front,
                                tilt_right_early, tilt_right, mouth_closed,
                                tilt_right_middle, tilt_right_far,
                                tilt_right_middle, mouth_closed,
                                tilt_right_early, front, tilt_left_early,
                                tilt_left, tilt_left_middle],
        "touch_head/touch_c": [touch_loop_exit, tilt_left_middle, tilt_left,
                                tilt_left_early, front],
        "touch_head/purr_a": [front, tilt_right_early,
                               mouth_closed,
                               tilt_right_middle, tilt_right_far],
        "touch_head/purr_b": [tilt_right_far, tilt_right_middle,
                               mouth_closed, right_eye_cycle, tilt_right_early,
                               front, tilt_left_early, tilt_left,
                               tilt_left_middle, tilt_left_far,
                               tilt_left_middle, tilt_left,
                               tilt_left_early, front,
                               touch_smile_right, tilt_right_middle],
        "touch_head/purr_c": [purr_loop_exit, tilt_right_middle, tilt_right,
                               tilt_right_early, front],
        "work/work_b": [front, talk],
    }
    expected = set(re.findall(r"\|path#([^:]+):",
                              (PET / "info.lps").read_text(encoding="utf-8")))
    if set(frames) != expected:
        raise ValueError(f"Picture-style animation coverage mismatch: {expected ^ set(frames)}")
    for folder, sequence in frames.items():
        if folder.startswith("touch_head/"):
            # Separate the mouth opening from the pose change, keeping the
            # eyes, brows and hair identical throughout the seven mouth keys.
            sequence = [stage for key in sequence for stage in
                        (key if isinstance(key, list) else
                         mouth_cycle if key is touch_smile_right else [key])]
        save_base(folder, sequence)


def build_new_base() -> None:
    KEYS.mkdir(parents=True, exist_ok=True)
    for name, filename in SOURCES.items():
        saved = KEYS / f"{name}.png"
        if not saved.exists():
            copy2(GENERATED / filename, saved)

    for folder, count in (("touch_body/touch_a", 4), ("touch_body/touch_c", 2),
                          ("idel/stretch_single", 2)):
        for index in range(1, count + 1):
            path = BASE / folder / f"frame_{index:02}.png"
            saved = SEQUENCE_SOURCE / folder / path.name
            if not saved.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                copy2(path, saved)

    stand = Image.open(BASE / "default/breathe_b/frame_01.png").convert("RGBA")
    for folder, index in (("idel/blink_a", 1), ("idel/blink_b", 1)):
        original = BASE / folder / f"frame_{index:02}.png"
        saved = SEQUENCE_SOURCE / folder / original.name
        if not saved.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            copy2(original, saved)
    blink_quarter = fitted_frame(KEYS / "blink_quarter.png")
    blink_half = Image.open(SEQUENCE_SOURCE / "idel/blink_a/frame_01.png").convert("RGBA")
    blink_nearly = fitted_frame(ROOT / "tools/keyframes/blink/nearly_closed.png")
    blink_closed = Image.open(SEQUENCE_SOURCE / "idel/blink_b/frame_01.png").convert("RGBA")
    save_base("idel/blink_a", [stand, blink_quarter, blink_half, blink_nearly, blink_closed])
    save_base("idel/blink_b", [blink_closed, blink_closed])
    save_base("idel/blink_c", [blink_nearly, blink_half, blink_quarter, stand])
    hold = fit_key("hold_full_size", 150, 220, 236)
    def shift(pose: Image.Image, dx: int, dy: int = 0) -> Image.Image:
        output = Image.new("RGBA", (256, 256))
        output.alpha_composite(pose, (dx, dy))
        return output

    save_base("raised_static/hold_a", [shift(hold, 0, 2), hold, shift(hold, 0, -1)])
    save_base("raised_static/hold_b", [shift(hold, -2), hold, shift(hold, 2), hold])
    save_base("raised_dynamic/wiggle_single",
              [hold, shift(hold, -2, 1), hold, shift(hold, 2, 1), hold])

    half_left = fit_key("look_half_left", 150, 198)
    half_right = Image.Image.transpose(half_left, Image.Transpose.FLIP_LEFT_RIGHT)
    for direction in ("look_left", "look_right"):
        target = KEYS / f"{direction}.png"
        if not target.exists():
            copy2(ROOT / "tools/keyframes/core" / target.name, target)
    left = fit_key("look_left", 150, 198)
    right = fit_key("look_right", 150, 198)
    save_base("idel/look_around_single",
              [stand, half_left, left, half_left, stand,
               half_right, right, half_right, stand])
    descent = fit_key("fall_descent", 155, 185)
    tuck = fit_key("fall_tuck", 150, 181)
    impact = fit_key("fall_impact", 188, 138)
    recover = fit_key("fall_recover", 180, 166)
    rebound = fit_key("fall_rebound", 165, 180, 233)
    settle = fit_key("fall_settle", 165, 188)
    raised_release = Image.open(BASE / "raised_static/hold_c/frame_01.png").convert("RGBA")
    save_base("raised_static/hold_c", [raised_release, descent])
    save_base("common/falling_single", [descent, tuck, descent, tuck])
    save_base("common/fall_single", [impact, impact, recover, rebound, settle, stand])

    # Use the reference-matched round-eyed neutral pose between head tilts.
    # The former closed-eye center made both touch sequences abruptly switch faces.
    center = stand
    soft_left = fit_key("tilt_soft_left", 150, 198)
    far_left = fit_key("tilt_far_left", 150, 198)
    soft_right = fit_key("tilt_soft_right", 150, 198)
    far_right = fit_key("tilt_far_right", 150, 198)
    save_base("touch_head/touch_a", [stand, soft_left, far_left])
    save_base("touch_head/touch_b", [far_left, soft_left, center, soft_right,
                                     far_right, soft_right, center, soft_left])
    save_base("touch_head/touch_c", [soft_left, stand])
    save_base("touch_head/purr_a", [stand, soft_right, far_right])
    save_base("touch_head/purr_b", [far_right, soft_right, center, soft_left,
                                    far_left, soft_left, center, soft_right])
    save_base("touch_head/purr_c", [soft_right, stand])

    half_rise = fit_key("stretch_half_rise", 190, 180)
    def source_frame(folder: str, index: int) -> Image.Image:
        return Image.open(SEQUENCE_SOURCE / folder / f"frame_{index:02}.png").convert("RGBA")

    low_rise = fit_key("rise_low", 190, 180)
    sitting_rise = fit_key("rise_to_sit", 190, 185)
    save_base("idel/stretch_single", [source_frame("idel/stretch_single", 1), low_rise,
                                      half_rise, sitting_rise, stand])
    save_base("touch_body/touch_a", [source_frame("touch_body/touch_a", 1),
                                    source_frame("touch_body/touch_a", 2), half_rise,
                                    source_frame("touch_body/touch_a", 3),
                                    source_frame("touch_body/touch_a", 4)])
    save_base("touch_body/touch_c", [source_frame("touch_body/touch_a", 4), half_rise,
                                    source_frame("touch_body/touch_c", 1),
                                    source_frame("touch_body/touch_c", 2)])


def premultiplied(frame: np.ndarray) -> np.ndarray:
    result = frame.astype(np.float32) / 255.0
    result[:, :, :3] *= result[:, :, 3:4]
    return result


def head_tip_x(frame: np.ndarray) -> float:
    mask = frame[:, :, 3] > 240
    rows = np.flatnonzero(mask.any(axis=1))
    if len(rows) == 0:
        return frame.shape[1] / 2
    tip = mask[rows[0]:rows[0] + round(12 * frame.shape[0] / 256)]
    return float(np.flatnonzero(tip.any(axis=0)).mean())


@lru_cache(maxsize=2)
def motion_fields(first_gray: bytes, second_gray: bytes) -> tuple[np.ndarray, np.ndarray]:
    first = np.frombuffer(first_gray, dtype=np.uint8).reshape(256, 256)
    second = np.frombuffer(second_gray, dtype=np.uint8).reshape(256, 256)
    forward = cv2.calcOpticalFlowFarneback(first, second, None, 0.5, 3, 21, 5, 7, 1.5, 0)
    backward = cv2.calcOpticalFlowFarneback(second, first, None, 0.5, 3, 21, 5, 7, 1.5, 0)
    return forward, backward


def head_anchor(source: Image.Image) -> float:
    pixels = np.asarray(source).astype(np.int16)
    gold = (pixels[:, :, 0] > pixels[:, :, 1] + 15) & (pixels[:, :, 1] > pixels[:, :, 2] + 30) & (pixels[:, :, 3] > 240)
    rows = np.nonzero(gold)[0]
    return float(np.median(rows)) if rows.size else source.height / 2


def midpoint(first: Image.Image, second: Image.Image, head: bool = False,
             fraction: float = 0.5, single_texture: bool = False) -> Image.Image:
    # Large crouch/stand changes exceed local optical-flow search distance.
    # First align the silhouettes to their intermediate extent; otherwise the
    # two crowns and faces remain separated and produce a visible double cat.
    original_a, original_b = first, second
    bounds_a = first.getchannel("A").point(lambda value: 255 if value > 240 else 0).getbbox()
    bounds_b = second.getchannel("A").point(lambda value: 255 if value > 240 else 0).getbbox()
    large_change = bool(bounds_a and bounds_b and (
        max(abs(a - b) for a, b in zip(bounds_a, bounds_b)) > 24 or
        abs(head_anchor(first) - head_anchor(second)) > 24))
    if large_change:
        target = tuple(round(a * (1 - fraction) + b * fraction)
                       for a, b in zip(bounds_a, bounds_b))

        def align(source: Image.Image, bounds: tuple[int, int, int, int]) -> Image.Image:
            aligned = Image.new("RGBA", source.size)
            crop = source.crop(bounds).resize((target[2] - target[0], target[3] - target[1]),
                                               Image.Resampling.LANCZOS)
            aligned.alpha_composite(crop, target[:2])
            return aligned

        first, second = align(first, bounds_a), align(second, bounds_b)
    a = np.asarray(first.convert("RGBA"))
    b = np.asarray(second.convert("RGBA"))
    gray_a = cv2.cvtColor(cv2.addWeighted(a[:, :, :3], 0.9,
                                          np.full_like(a[:, :, :3], 128), 0.1, 0),
                          cv2.COLOR_RGB2GRAY)
    gray_b = cv2.cvtColor(cv2.addWeighted(b[:, :, :3], 0.9,
                                          np.full_like(b[:, :, :3], 128), 0.1, 0),
                          cv2.COLOR_RGB2GRAY)
    height, width = gray_a.shape
    scale = width / 256
    # Compute motion in logical coordinates, then remap the original high
    # resolution pixels; no intermediate frame is reduced to 256 pixels.
    small_a = cv2.resize(gray_a, (256, 256), interpolation=cv2.INTER_AREA)
    small_b = cv2.resize(gray_b, (256, 256), interpolation=cv2.INTER_AREA)
    flow_small, reverse_small = motion_fields(small_a.tobytes(), small_b.tobytes())
    flow_ab = cv2.resize(flow_small, (width, height), interpolation=cv2.INTER_LINEAR) * scale
    flow_ba = cv2.resize(reverse_small, (width, height), interpolation=cv2.INTER_LINEAR) * scale
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32),
                                 np.arange(height, dtype=np.float32))

    def warp(frame: np.ndarray, flow: np.ndarray, amount: float) -> np.ndarray:
        return cv2.remap(premultiplied(frame), grid_x - flow[:, :, 0] * amount,
                         grid_y - flow[:, :, 1] * amount,
                         cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    # Align both endpoints before blending, so the last intermediate approaches
    # the next key rather than resetting from a halfway warped previous key.
    if single_texture:
        # One source drawing supplies every pixel: outlines, eyes and paws
        # never become two transparent silhouettes when motion fails to align.
        moved = warp(a, flow_ab, fraction) if fraction < 0.5 else warp(b, flow_ba, 1 - fraction)
    else:
        moved = warp(a, flow_ab, fraction) * (1 - fraction) + warp(b, flow_ba, 1 - fraction) * fraction
    if large_change:
        # Keep a single opaque silhouette during major posture changes. Align
        # the gold horn (head anchor) and planted paws instead of crossfading
        # unrelated face and tail positions.
        anchor_a, anchor_b = head_anchor(original_a), head_anchor(original_b)
        target_anchor = anchor_a * (1 - fraction) + anchor_b * fraction
        source = original_a if fraction < 0.5 else original_b
        source_anchor = anchor_a if fraction < 0.5 else anchor_b
        source_bounds = bounds_a if fraction < 0.5 else bounds_b
        target_bottom = bounds_a[3] * (1 - fraction) + bounds_b[3] * fraction
        map_y = np.interp(grid_y, [0, target_anchor, target_bottom, height],
                          [0, source_anchor, source_bounds[3], height]).astype(np.float32)
        moved = cv2.remap(premultiplied(np.asarray(source)), grid_x, map_y,
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    if head:
        # Shear the crown halfway toward its next position while the planted
        # paws remain fixed. Optical flow alone barely moves large head tilts.
        delta = np.clip(head_tip_x(b) - head_tip_x(a), -32 * scale, 32 * scale) * fraction
        weight = np.clip((248 * scale - grid_y) / (198 * scale), 0, 1)
        moved = cv2.remap(moved, grid_x - delta * weight, grid_y,
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    alpha = moved[:, :, 3:4]
    rgb = np.divide(moved[:, :, :3], np.maximum(alpha, 0.001))
    result = np.concatenate((rgb, alpha), axis=2)
    return Image.fromarray(np.uint8(np.clip(result * 255, 0, 255)))


def expand_all(prefixes: tuple[str, ...] | None = None) -> dict[str, int]:
    counts = {}
    timing_path = ROOT / "tools/animation_timing.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    frame_times = timing.setdefault("frame_ms", {})
    registration = {path: (name, graph, phase) for name, path, graph, phase in re.findall(
        r"pnganimation#([^:]+):\|path#([^:]+):\|graph#([^:]+):\|animat#([^:]+):", (PET / "info.lps").read_text(encoding="utf-8"))}
    for folder in sorted({p.parent for p in BASE.rglob("frame_*.png")}):
        originals = [Image.open(path).convert("RGBA") for path in sorted(folder.glob("frame_*.png"))]
        if len(originals) < 2:
            continue
        relative = folder.relative_to(BASE)
        sequence_name = str(relative).replace("\\", "/")
        if prefixes and not sequence_name.startswith(prefixes):
            continue;
        crisp_keys = relative.parts[0] in {"sleep", "walk"} or sequence_name in {
            "idel/doze_a", "idel/doze_b", "idel/doze_c", "startup/boot_single", "shutdown/bye_single",
            "idel/blink_a", "idel/blink_b", "idel/blink_c",
            "idel/look_around_single",
            "idel/sleep_single", "idel/yawn_single", "sleep/zzz_b",
            "idel/tail_swish_single",
            "idel/stretch_single", "touch_body/touch_a", "touch_body/touch_c",
            "raised_static/hold_a",
            "raised_static/hold_b", "raised_dynamic/wiggle_single",
        }
        is_loop = folder.name.endswith("_b") or folder.name == "breathe_b" \
            or folder.name == "falling_single"
        result = []
        overrides = {}
        dense = (relative.parts[0] in {"touch_head", "touch_body", "walk"} and "blink" not in sequence_name) or sequence_name in {
            "default/breathe_b", "idel/groom_single", "idel/yawn_single", "idel/tail_swish_single",
            "idel/look_around_single", "raised_static/hold_a", "raised_static/hold_b", "raised_dynamic/wiggle_single",
            "idel/stretch_single", "idel/sleep_single", "common/fall_single",
            "common/falling_single", "raised_static/hold_c",
            "sleep/curled_a", "sleep/curled_c", "sleep/belly_a", "sleep/belly_c",
            "sleep/curled_touch_single", "sleep/belly_touch_single",
            "sleep/flip_to_belly_single", "sleep/flip_to_curled_single",
            "walk/west_b", "walk/east_b",
        }
        roll_keys = [Image.open(path).convert("RGBA") for path in sorted((BASE / "sleep/flip_to_belly_single").glob("frame_*.png"))]
        roll_lookup = {key.tobytes(): points for key, points in zip(roll_keys, ROLL_POINTS)}
        # Flip trajectories are built once below with their own global easing.
        if dense and sequence_name not in {"sleep/flip_to_belly_single", "sleep/flip_to_curled_single"}:
            divisions = (16 if sequence_name in {"sleep/flip_to_belly_single", "sleep/flip_to_curled_single"} else
                         3 if sequence_name == "idel/sleep_single" else
                         2 if sequence_name == "idel/look_around_single" else
                         8 if sequence_name == "idel/groom_single" else
                         4 if sequence_name in {"default/breathe_b", "idel/yawn_single", "idel/tail_swish_single"} else
                         (10 if is_loop else 4) if relative.parts[0] == "walk" else
                         6 if relative.parts[0] == "sleep" else 5)
            pairs = list(zip(originals, originals[1:]))
            closed_walk_loop = relative.parts[0] == "walk" and is_loop and originals[0].tobytes() == originals[-1].tobytes()
            if is_loop and not closed_walk_loop:
                pairs.append((originals[-1], originals[0]))
            for first, second in pairs:
                result.append(first)
                local_divisions = divisions
                mouth_only = False
                eyes_only = False
                if relative.parts[0] == "touch_head":
                    a, b = np.asarray(first), np.asarray(second)
                    outside = np.ones(a.shape[:2], dtype=bool)
                    outside[325:360, 240:290] = False
                    mouth_only = np.array_equal(a[outside], b[outside]) and not np.array_equal(a, b)
                    if mouth_only:
                        local_divisions = 2
                    else:
                        eye_outside = np.ones(a.shape[:2], dtype=bool)
                        for boxes in TOUCH_EYE_BOXES.values():
                            for left, top, right, bottom in boxes:
                                eye_outside[top:bottom + 1, left:right + 1] = False
                        eyes_only = np.array_equal(a[eye_outside], b[eye_outside])
                        if eyes_only:
                            local_divisions = 3
                            overrides[len(result) - 1] = 40 if np.array_equal(a, b) else 10
                for step in range(1, local_divisions):
                    points = (roll_lookup[first.tobytes()], roll_lookup[second.tobytes()]) if first.tobytes() in roll_lookup and second.tobytes() in roll_lookup else None
                    if first.tobytes() == second.tobytes():
                        frame = first
                    elif relative.parts[0] == "sleep" or sequence_name == "idel/sleep_single" or (relative.parts[0] == "touch_head" and not mouth_only and not eyes_only):
                        frame = continuous_morph(first, second, step / local_divisions, points)
                    else:
                        frame = midpoint(first, second, fraction=step / local_divisions, single_texture=True)
                    if mouth_only:
                        # Optical flow is evaluated on the full frame, but only
                        # its mouth pixels enter the animation.
                        pixels = np.asarray(first).copy()
                        pixels[325:360, 240:290] = np.asarray(frame)[325:360, 240:290]
                        frame = Image.fromarray(pixels)
                    elif eyes_only:
                        pixels = np.asarray(first).copy()
                        pixels[~eye_outside] = np.asarray(frame)[~eye_outside]
                        frame = Image.fromarray(pixels)
                    result.append(frame)
                    if eyes_only:
                        overrides[len(result) - 1] = 40 if np.array_equal(a, b) else 10
            if not is_loop or closed_walk_loop:
                result.append(originals[-1])
        elif crisp_keys:
            result = originals
        elif relative.parts[0] == "touch_head":
            for index in range(len(originals) - 1):
                result.extend((originals[index], midpoint(originals[index], originals[index + 1])
                               .filter(ImageFilter.UnsharpMask(radius=0.8, percent=160,
                                                               threshold=1))))
            result.append(originals[-1])
            if is_loop:
                result.append(midpoint(originals[-1], originals[0]).filter(
                    ImageFilter.UnsharpMask(radius=0.8, percent=160, threshold=1)))
        else:
            for index in range(len(originals) - 1):
                result.extend((originals[index], midpoint(originals[index], originals[index + 1],
                                                          relative.parts[0] == "touch_head")))
            result.append(originals[-1])
            if is_loop:
                result.append(midpoint(originals[-1], originals[0],
                                       relative.parts[0] == "touch_head"))
        destination = PET / relative
        if sequence_name == "sleep/flip_to_belly_single":
            result = []
            for index in range(97):
                position = (0.5 - 0.5 * np.cos(np.pi * index / 96)) * 6
                pair = min(5, int(position))
                result.append(continuous_morph(roll_keys[pair], roll_keys[pair + 1], position - pair,
                    (ROLL_POINTS[pair], ROLL_POINTS[pair + 1])))
        elif sequence_name == "sleep/flip_to_curled_single":
            # Identical trajectory in reverse, including its gradual start/stop.
            result = [Image.open(path).convert("RGBA") for path in reversed(sorted(
                (PET / "sleep/flip_to_belly_single").glob("frame_*.png")))]
        blink_pose = None
        boxes = []
        if sequence_name == "raised_static/hold_b":
            blink_pose, boxes = originals[0], [(189, 143, 241, 183), (265, 148, 314, 189)]
        elif sequence_name == "sleep/curled_touch_single":
            blink_pose, boxes = originals[3], [(119, 350, 160, 388), (179, 348, 224, 386)]
        elif sequence_name == "sleep/belly_touch_single":
            blink_pose, boxes = originals[2], [(176, 298, 211, 333), (139, 320, 175, 359)]
        name, graph, phase = registration[sequence_name]
        default_ms = timing.get("phase_ms", {}).get(name, {}).get(phase,
            timing["name_ms"].get(name, timing["graph_type_ms"].get(graph, timing["default_ms"])))
        times = [overrides.get(index, default_ms) for index in range(len(result))]
        if blink_pose is not None:
            insertion = next(i for i, frame in enumerate(result) if frame.tobytes() == blink_pose.tobytes())
            cycle = pose_blink(blink_pose, boxes)
            result[insertion:insertion + 1] = cycle
            times[insertion:insertion + 1] = [10] * len(cycle)
        if len(result) > 117:
            raise ValueError(f"Atlas frame limit exceeded: {sequence_name}: {len(result)}")
        frame_times[name + "/" + phase] = times
        destination.mkdir(parents=True, exist_ok=True)
        for stale in destination.glob("frame_*.png"):
            stale.unlink()
        for index, frame in enumerate(result, start=1):
            digits = 3 if len(result) >= 100 else 2
            frame.save(destination / f"frame_{index:0{digits}}.png")
        counts[str(relative).replace("\\", "/")] = len(result)
    timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return counts


def contact(name: str, folders: list[str]) -> None:
    paths = [path for folder in folders for path in sorted((PET / folder).glob("frame_*.png"))]
    cols = 8
    sheet = Image.new("RGB", (256 * cols, 280 * ((len(paths) + cols - 1) // cols)), "#888888")
    labels = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        frame = Image.open(path).convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
        x, y = index % cols * 256, index // cols * 280
        sheet.paste(frame, (x, y), frame.getchannel("A"))
        labels.text((x + 4, y + 258), f"{path.parent.name}/{path.stem}", fill="white")
    destination = ROOT / "tools/qa" / f"v2-{name}.png"
    destination.parent.mkdir(exist_ok=True)
    sheet.save(destination)


def main() -> None:
    snapshot_originals()
    build_picture_style_base()
    counts = expand_all()
    contact("blink", ["idel/blink_a", "idel/blink_b", "idel/blink_c"])
    contact("fall", ["common/falling_single", "common/fall_single"])
    contact("head", ["touch_head/touch_a", "touch_head/touch_b",
                     "touch_head/touch_c", "touch_head/purr_a",
                     "touch_head/purr_b", "touch_head/purr_c"])
    contact("sleep", ["idel/sleep_single", "sleep/zzz_b"])
    contact("sleep-touch", ["sleep/curled_touch_single", "sleep/belly_touch_single"])
    contact("sleep-belly", ["sleep/belly_a", "sleep/belly_b", "sleep/belly_c"])
    contact("yawn", ["idel/yawn_single"])
    print(f"folders={len(counts)} frames={sum(counts.values())}")


if __name__ == "__main__":
    main()
