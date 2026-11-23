"""Build a consistent animated sprite set from the supplied front-view artwork.

This is a deterministic fallback for environments without image generation. It
keeps the original drawing intact and animates it with small pose transforms.
Run explicitly with --replace to overwrite the existing placeholder frames.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "example" / "ChatGPT 图像 2026年9月29日 10_43_04.png"
DESTINATION = ROOT / "DakamaoPet" / "PetMod" / "pet" / "dakamao"
SIZE = 256


def original_sprite() -> Image.Image:
    image = Image.open(SOURCE).convert("RGBA")
    # The supplied sheet has three views. The front view occupies this box.
    sprite = image.crop((0, 210, 485, 875))
    alpha = sprite.getchannel("A")
    # Remove the detached tip of the adjacent side-view horn.
    ImageDraw.Draw(alpha).rectangle((460, 0, 484, 150), fill=0)
    sprite.putalpha(alpha)
    sprite.thumbnail((208, 205), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE))
    canvas.alpha_composite(sprite, ((SIZE - sprite.width) // 2, 248 - sprite.height))
    return canvas


def expression(sprite: Image.Image, face: str) -> Image.Image:
    if face == "normal":
        return sprite
    data = np.array(sprite)
    rgb = cv2.cvtColor(data[:, :, :3], cv2.COLOR_RGB2BGR)
    mask = np.zeros((SIZE, SIZE), dtype=np.uint8)
    if face in {"closed", "half"}:
        for x in (108, 148):
            cv2.ellipse(mask, (x, 134), (19, 20), 0, 0, 360, 255, -1)
    if face in {"talk", "yawn"}:
        cv2.ellipse(mask, (128, 153), (9, 7), 0, 0, 360, 255, -1)
    if mask.any():
        rgb = cv2.inpaint(rgb, mask, 9, cv2.INPAINT_TELEA)
    result = Image.fromarray(
        np.dstack((cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB), data[:, :, 3]))
    )
    draw = ImageDraw.Draw(result)
    if face in {"closed", "half"}:
        for x in (108, 148):
            if face == "closed":
                draw.arc((x - 13, 127, x + 13, 139), 185, 355, fill=(86, 45, 55, 255), width=2)
            else:
                draw.arc((x - 12, 128, x + 12, 139), 190, 350, fill=(99, 61, 69, 255), width=2)
                draw.arc((x - 9, 130, x + 9, 140), 15, 165, fill=(75, 134, 184, 255), width=2)
    if face in {"talk", "yawn"}:
        box = (123, 148, 133, 160) if face == "talk" else (120, 145, 136, 167)
        draw.ellipse(box, fill=(125, 48, 62, 255), outline=(105, 61, 67, 255), width=1)
        draw.arc((box[0] + 2, box[1] + 6, box[2] - 2, box[3] - 1), 0, 180,
                 fill=(239, 130, 151, 255), width=2)
    return result


def frame(base: Image.Image, *, scale_x=1.0, scale_y=1.0, angle=0.0,
          offset_x=0, offset_y=0, face="normal") -> Image.Image:
    sprite = expression(base, face)
    bbox = sprite.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("The source view is empty")
    sprite = sprite.crop(bbox)
    sprite = sprite.resize(
        (max(1, round(sprite.width * scale_x)), max(1, round(sprite.height * scale_y))),
        Image.Resampling.LANCZOS,
    )
    if angle:
        sprite = sprite.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    output = Image.new("RGBA", (SIZE, SIZE))
    x = (SIZE - sprite.width) // 2 + offset_x
    y = 248 - sprite.height + offset_y
    # Rotation increases the bounding box; keep the gold horn in view.
    x = min(max(x, 1), SIZE - sprite.width - 1)
    y = max(y, 1)
    output.alpha_composite(sprite, (x, y))
    return output


# Each list corresponds exactly to the numbered frame files in the VPet pack.
# Sizes, tilts and positions are intentionally restrained to avoid style drift.
ANIMATIONS = {
    "default/breathe_b": [
        dict(scale_y=.985), dict(scale_y=1.0), dict(scale_y=1.018, offset_y=-1),
        dict(scale_y=1.018, offset_y=-1), dict(scale_y=1.0), dict(scale_y=.985),
    ],
    "touch_head/touch_a": [
        dict(angle=-2, face="half"), dict(angle=-3, offset_y=-2, face="half"),
        dict(angle=-4, offset_y=-4, face="closed"), dict(angle=-5, offset_y=-5, face="closed"),
    ],
    "touch_head/touch_b": [
        dict(angle=-6, offset_x=-2, offset_y=-5, face="closed"),
        dict(angle=0, offset_y=-6, face="closed"),
        dict(angle=6, offset_x=2, offset_y=-5, face="closed"),
        dict(angle=-6, offset_x=-2, offset_y=-5, face="closed"),
    ],
    "touch_head/touch_c": [dict(angle=-2, offset_y=-2, face="half"), dict()],
    "touch_body/touch_a": [
        dict(scale_x=.99, scale_y=1.01), dict(scale_x=1.02, scale_y=.98),
        dict(scale_x=1.04, scale_y=.96, face="half"),
        dict(scale_x=1.06, scale_y=.94, face="closed"),
    ],
    "touch_body/touch_b": [
        dict(scale_x=1.06, scale_y=.94, angle=-3, face="closed"),
        dict(scale_x=1.06, scale_y=.94, face="closed"),
        dict(scale_x=1.06, scale_y=.94, angle=3, face="closed"),
        dict(scale_x=1.06, scale_y=.94, angle=-3, face="closed"),
    ],
    "touch_body/touch_c": [dict(scale_x=1.02, scale_y=.98, face="half"), dict()],
    "raised_static/hold_a": [
        dict(scale_x=.96, scale_y=1.07, offset_y=-22),
        dict(scale_x=.96, scale_y=1.04, offset_y=-32, angle=-2),
    ],
    "raised_static/hold_b": [
        dict(scale_x=.96, scale_y=1.04, offset_y=-34, angle=-4),
        dict(scale_x=.96, scale_y=1.04, offset_y=-34, angle=4),
    ],
    "raised_static/hold_c": [
        dict(scale_x=.97, scale_y=1.02, offset_y=-12),
        dict(scale_x=1.10, scale_y=.82),
    ],
    "raised_dynamic/wiggle_single": [
        dict(scale_x=.95, scale_y=1.07, angle=13, offset_x=-7, offset_y=-8),
        dict(scale_x=.95, scale_y=1.07, angle=-13, offset_x=7, offset_y=-8),
    ],
    "common/fall_single": [
        dict(scale_x=.96, scale_y=1.07, offset_y=-20, angle=-5),
        dict(scale_x=.97, scale_y=1.05, offset_y=-10, angle=4),
        dict(scale_x=1.25, scale_y=.62),
        dict(scale_x=.94, scale_y=1.10, offset_y=-15),
        dict(scale_x=1.10, scale_y=.84), dict(),
    ],
    "idel/blink_a": [dict(face="half"), dict(face="closed")],
    "idel/blink_b": [dict(face="closed"), dict(face="half")],
    "idel/blink_c": [dict(face="half"), dict()],
    "idel/yawn_single": [dict(face="yawn", angle=-2), dict(face="half")],
    "idel/look_around_single": [dict(angle=5), dict(angle=-5), dict()],
    "idel/groom_single": [
        dict(angle=-7, scale_y=.96, face="half"),
        dict(angle=5, scale_y=.94, face="closed"), dict(),
    ],
    "idel/tail_swish_single": [dict(angle=-3), dict(angle=3)],
    "idel/stretch_single": [dict(scale_x=1.14, scale_y=.84, face="half"), dict()],
    "idel/doze_a": [dict(angle=-2, face="half"), dict(angle=-5, face="closed")],
    "idel/doze_b": [dict(angle=-6, face="closed"), dict(angle=-3, face="closed")],
    "idel/doze_c": [dict(angle=4), dict()],
    "sleep/zzz_b": [
        dict(scale_x=1.20, scale_y=.72, face="closed"),
        dict(scale_x=1.19, scale_y=.74, face="closed"),
        dict(scale_x=1.18, scale_y=.76, face="closed"),
        dict(scale_x=1.20, scale_y=.72, face="closed"),
    ],
    "startup/boot_single": [dict(scale_x=1.17, scale_y=.75, face="closed"), dict()],
    "shutdown/bye_single": [dict(angle=7, face="half"), dict(scale_x=1.17, scale_y=.75, face="closed")],
    "say/talk_b": [dict(face="talk"), dict()],
    "work/work_b": [dict(angle=-3, face="half"), dict(angle=2, face="half")],
    "switch_up/up_single": [dict(offset_y=-20, face="talk"), dict(scale_x=1.08, scale_y=.88, face="closed")],
    "switch_down/down_single": [dict(angle=-5, scale_y=.96, face="half"), dict(angle=-7, scale_y=.93, face="closed")],
    "switch_hunger/hungry_single": [dict(scale_y=.96, face="half"), dict(angle=-3, scale_y=.95, face="half")],
    "switch_thirsty/thirsty_single": [dict(face="talk"), dict(scale_y=1.01, face="talk")],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="overwrite matching frame files")
    args = parser.parse_args()
    base = original_sprite()
    expected = sum(len(specs) for specs in ANIMATIONS.values())
    if expected != 84:
        raise ValueError(f"Expected 84 frames, found {expected}")
    if not args.replace:
        print("Ready to build 84 frames; pass --replace to write them.")
        return
    for folder, specs in ANIMATIONS.items():
        target = DESTINATION / folder
        target.mkdir(parents=True, exist_ok=True)
        for index, spec in enumerate(specs, 1):
            frame(base, **spec).save(target / f"frame_{index:02d}.png")
        print(f"[done] {folder} {len(specs)} frames")


if __name__ == "__main__":
    main()
