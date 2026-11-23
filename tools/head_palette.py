"""Fixed material-aware color calibration for the head-touch sprite builder.

Keep source geometry/alpha and saturated eye, ornament, horn and mouth colors.
Original imagegen keyframes are retained; only derived animation sources use
the same neutral fur/ink reference curve.
"""
from pathlib import Path
import json

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
KEYS = ROOT / "tools/keyframes/picture_style"
OUT = ROOT / "tools/sequence_sources/head_palette"
NAMES = {
    "tilt_early_left", "tilt_soft_left", "tilt_middle_left", "tilt_far_left",
    "tilt_early_right", "tilt_soft_right", "tilt_middle_right", "tilt_far_right",
    "touch_smile_right", "touch_mouth_closed", "touch_mouth_quarter", "touch_mouth_half",
    "touch_closed_left", "touch_closed_right",
}
BANDS = ((65, 150), (150, 210), (210, 245), (245, 256))


def material(rgb: np.ndarray) -> np.ndarray:
    return ((np.abs(rgb[..., 1] - rgb[..., 2]) < 9)
            & (rgb[..., 0] - rgb[..., 1] < 17)
            & (rgb[..., 0] - rgb[..., 1] > -6))


def samples(pixels: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    rgb = pixels[..., :3].astype(np.float32)
    luminance = rgb.mean(axis=2)
    neutral = (pixels[..., 3] > 250) & material(rgb)
    masks = [neutral & (luminance >= lo) & (luminance < hi) for lo, hi in BANDS]
    return [np.median(rgb[mask], axis=0) for mask in masks], masks


REFERENCE = np.asarray(Image.open(KEYS / "front_neutral.png").convert("RGBA"))
TARGET, _ = samples(REFERENCE)
REPORT = {}


def normalize(image: Image.Image, name: str) -> Image.Image:
    if name not in NAMES:
        return image
    pixels = np.asarray(image.convert("RGBA")).copy()
    rgb = pixels[..., :3].astype(np.float32)
    source, masks = samples(pixels)
    reference_rgb = REFERENCE[..., :3].astype(np.float32)
    _, reference_masks = samples(REFERENCE)
    knots, adjustments = [0., 40.], [np.zeros(3), np.zeros(3)]
    # Match the distribution inside each material band, not just its median.
    # This also matches highlight/shadow contrast on differently tilted heads.
    for mask, target_mask in zip(masks, reference_masks):
        source_values = rgb[mask]
        target_values = reference_rgb[target_mask]
        order = np.argsort(source_values.mean(axis=1))
        target_order = np.argsort(target_values.mean(axis=1))
        for quantile in (0.1, 0.25, 0.5, 0.75, 0.9):
            index = round((len(order)-1)*quantile)
            target_index = round((len(target_order)-1)*quantile)
            width = max(2, len(order)//100)
            target_width = max(2, len(target_order)//100)
            color = np.median(source_values[order[max(0,index-width):index+width+1]],axis=0)
            target_color = np.median(target_values[target_order[max(0,target_index-target_width):target_index+target_width+1]],axis=0)
            knots.append(max(knots[-1]+0.001,float(color.mean())))
            adjustments.append(np.clip(target_color-color,-25,25))
    knots.append(255.)
    adjustments.append(np.zeros(3))
    offsets = np.asarray(adjustments)
    # Fully protect non-neutral colors; feather only along the neutral boundary.
    saturation = (rgb.max(axis=2) - rgb.min(axis=2)) / np.maximum(rgb.max(axis=2), 1)
    weight = np.clip((0.17 - saturation) / 0.04, 0, 1)
    weight *= np.clip((12 - np.abs(rgb[..., 1] - rgb[..., 2])) / 3, 0, 1)
    weight *= np.clip((20 - (rgb[..., 0] - rgb[..., 1])) / 3, 0, 1)
    weight *= np.clip(((rgb[..., 0] - rgb[..., 1]) + 9) / 3, 0, 1)
    weight *= pixels[..., 3] > 0
    brightness = rgb.mean(axis=2)
    for channel in range(3):
        delta = np.interp(brightness, knots, offsets[:, channel])
        pixels[..., channel] = np.clip(np.rint(rgb[..., channel] + delta * weight), 0, 255)
    # Brown outline ink was excluded by the neutral-color mask. Calibrate its
    # color separately, protecting saturated blue/gold/pink and mouth colors.
    def ink_mask(colors, alpha):
        return ((alpha > 250) & (colors[...,1] < 135)
                & (colors[...,0]-colors[...,1] > 8)
                & (colors[...,0]-colors[...,1] < 48)
                & (np.abs(colors[...,2]-colors[...,1]) < 22))
    ink = ink_mask(rgb,pixels[...,3])
    reference_ink = ink_mask(reference_rgb,REFERENCE[...,3])
    ink_delta = np.clip(np.median(reference_rgb[reference_ink],axis=0)-np.median(rgb[ink],axis=0),-20,20)
    pixels[ink,:3] = np.uint8(np.clip(np.rint(rgb[ink]+ink_delta),0,255))
    # Keep the established median-color gate as well as the finer distribution.
    # The small residual corrects feathered boundaries without editing accents.
    for _ in range(3):
        measured = np.asarray([np.median(pixels[mask,:3],axis=0) for mask in masks])
        residual = np.asarray(TARGET)-measured
        if np.max(np.abs(residual)) <= 1: break
        levels = [0,40]+[float(c.mean()) for c in measured]+[255]
        corrections = np.concatenate((np.zeros((2,3)),residual,np.zeros((1,3))),axis=0)
        luminance = pixels[...,:3].astype(float).mean(axis=2)
        for channel in range(3):
            shift = np.interp(luminance,levels,corrections[:,channel])*weight
            pixels[...,channel] = np.uint8(np.clip(np.rint(pixels[...,channel]+shift),0,255))
    corrected = [np.median(pixels[mask, :3], axis=0).tolist() for mask in masks]
    REPORT[name] = {
        "before": [color.tolist() for color in source], "after": corrected,
        "reference": [color.tolist() for color in TARGET],
        "alpha_unchanged": bool(np.array_equal(pixels[..., 3], np.asarray(image)[..., 3])),
        "accent_pixels_unchanged": bool(np.array_equal(pixels[(weight == 0) & ~ink], np.asarray(image)[(weight == 0) & ~ink])),
        "ink_delta": ink_delta.tolist(),
    }
    result = Image.fromarray(pixels)
    OUT.mkdir(parents=True, exist_ok=True)
    result.save(OUT / f"{name}.png")
    (OUT / "calibration.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
