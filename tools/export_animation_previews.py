# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Original contributions only; upstream character rights are not relicensed.
"""Export review MP4s at the same frame durations configured in PetWindow."""

from pathlib import Path
import json
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PET = ROOT / "DakamaoPet/PetMod/pet/dakamao"
OUT = ROOT / "tools/qa/mp4"
FPS = 60
TIMING = json.loads((ROOT / "tools/animation_timing.json").read_text(encoding="utf-8"))
SMOOTH_ROOT = ROOT / "DakamaoPet/PetMod/fluid"
SMOOTH = json.loads((SMOOTH_ROOT / "manifest.json").read_text(encoding="utf-8")) if (SMOOTH_ROOT / "manifest.json").exists() else {}
REGISTRATION = {
    path: (name, graph, phase)
    for name, path, graph, phase in re.findall(
        r"pnganimation#([^:]+):\|path#([^:]+):\|graph#([^:]+):\|animat#([^:]+):",
        (PET / "info.lps").read_text(encoding="utf-8"))
}
CLIPS = {
    "blink": ["idel/blink_a", "idel/blink_b", "idel/blink_c"],
    "turn": ["idel/look_around_single", "raised_dynamic/wiggle_single",
             "idel/tail_swish_single"],
    "lift_and_land": ["raised_static/hold_a", "raised_static/hold_b",
                      "common/falling_single", "common/fall_single"],
    "head_touch": ["touch_head/touch_a", "touch_head/touch_b",
                   "touch_head/touch_c", "touch_head/purr_a",
                   "touch_head/purr_b", "touch_head/purr_c"],
    "body_touch_and_stretch": ["touch_body/touch_a", "touch_body/touch_b",
                               "touch_body/touch_c", "idel/stretch_single"],
    "sleep": ["idel/sleep_single"],
    "sleep_loop": ["sleep/zzz_b"],
    "sleep_pose_switch": ["sleep/curled_b", "sleep/flip_to_belly_single",
                          "sleep/belly_b", "sleep/flip_to_curled_single", "sleep/curled_b"],
    "sleep_curled_touch": ["sleep/curled_a", "sleep/curled_b",
                            "sleep/curled_touch_single", "sleep/curled_b",
                            "sleep/curled_c"],
    "sleep_belly_up": ["sleep/curled_a", "sleep/flip_to_belly_single", "sleep/belly_b",
                        "sleep/belly_touch_single", "sleep/belly_b",
                        "sleep/flip_to_curled_single", "sleep/curled_c"],
    "sleep_to_head_touch": ["sleep/belly_b", "sleep/flip_to_curled_single", "sleep/curled_c",
                            "touch_head/touch_a", "touch_head/touch_b", "touch_head/touch_c",
                            "sleep/curled_a", "sleep/curled_b"],
    "yawn": ["idel/yawn_single"],
    "walk": ["walk/west_a", "walk/west_b", "walk/west_b", "walk/west_c",
             "walk/east_a", "walk/east_b", "walk/east_b", "walk/east_c"],
    "blink_scenes": ["idel/doze_a", "idel/doze_b", "idel/doze_c", "walk/west_blink_single", "walk/east_blink_single", "raised_static/hold_b", "sleep/curled_touch_single", "sleep/belly_touch_single"],
}


def frame_duration(folder: str) -> int:
    name, graph, phase = REGISTRATION[folder]
    if phase in TIMING.get("phase_ms", {}).get(name, {}):
        return TIMING["phase_ms"][name][phase]
    return TIMING["name_ms"].get(name,
           TIMING["graph_type_ms"].get(graph, TIMING["default_ms"]))


def timeline(sequences: list[str], fps: int = FPS) -> list[tuple[str, Path, int, int, int]]:
    """Round cumulative presentation time so sub-frame errors do not build up."""
    result = []
    elapsed_ms = 0
    written = 0
    for folder in sequences:
        milliseconds = frame_duration(folder)
        frames = sorted((PET / folder).glob("frame_*.png"))
        if not frames:
            raise FileNotFoundError(folder)
        name, graph, phase = REGISTRATION[folder]
        custom_times = TIMING.get("frame_ms", {}).get(name + "/" + phase)
        dense = SMOOTH.get(name + "/" + phase)
        if dense:
            source = PET if dense.get("source") == "pet" else SMOOTH_ROOT
            frames = sorted((source / dense["path"]).glob("frame_*.png"))
            custom_times = dense.get("frame_durations") or [min(dense["frame_ms"], max(0, dense["duration_ms"] - i * dense["frame_ms"])) for i in range(len(frames))]
        for index, path in enumerate(frames):
            milliseconds = custom_times[index] if custom_times else frame_duration(folder)
            if milliseconds <= 0: continue
            elapsed_ms += milliseconds
            next_written = round(elapsed_ms * fps / 1000)
            count = max(1, next_written - written)
            result.append((folder, path, milliseconds, count, written))
            written += count
    return result


def render_frame(path: Path, label: str) -> np.ndarray:
    frame = Image.open(path).convert("RGBA").resize((384, 384), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (640, 480), "#e5e5e5")
    canvas.alpha_composite(frame, (128, 56))
    rgb = cv2.cvtColor(np.asarray(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)
    cv2.putText(rgb, label, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                (35, 35, 35), 2, cv2.LINE_AA)
    return rgb


def export(name: str, sequences: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{name}.mp4"
    # 125fps exactly represents the 8ms sidecar cadence without adding a
    # forced video frame and stealing time from the next static sleep stage.
    fps = 125 if name in {"blink", "head_touch", "walk", "lift_and_land", "sleep_curled_touch", "sleep_belly_up", "blink_scenes", "sleep_pose_switch", "sleep_to_head_touch"} else FPS
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 480))
    if not writer.isOpened():
        raise RuntimeError("OpenCV cannot open MP4 writer")
    entries = timeline(sequences, fps)
    for folder, path, milliseconds, count, _ in entries:
        image = render_frame(path, f"{folder} / {path.stem} / {milliseconds}ms")
        for _ in range(count):
            writer.write(image)
    writer.release()
    capture = cv2.VideoCapture(str(target))
    if not capture.isOpened() or int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 0:
        raise RuntimeError(f"MP4 verification failed: {target}")
    print(f"{target.name}: {int(capture.get(cv2.CAP_PROP_FRAME_COUNT))} frames")
    capture.release()

    # Review the actual encoded/decoded MP4, not just the source PNGs.
    capture = cv2.VideoCapture(str(target))
    samples = []
    review_entries=[]
    for folder in sequences:
        group=[entry for entry in entries if entry[0]==folder]
        for index in np.unique(np.linspace(0,len(group)-1,min(8,len(group))).astype(int)):
            review_entries.append(group[index])
    for folder, path, _, count, position in review_entries:
        capture.set(cv2.CAP_PROP_POS_FRAMES, position + count // 2)
        okay, decoded = capture.read()
        if not okay:
            raise RuntimeError(f"Cannot decode frame {position} from {target}")
        samples.append((folder, path.stem, Image.fromarray(cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB))))
    capture.release()
    columns = 5
    cell_width, cell_height = 320, 264
    rows = (len(samples) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#f0f0f0")
    draw = ImageDraw.Draw(sheet)
    for index, (folder, stem, frame) in enumerate(samples):
        x, y = index % columns * cell_width, index // columns * cell_height
        sheet.paste(frame.resize((320, 240), Image.Resampling.LANCZOS), (x, y))
        draw.text((x + 8, y + 244), f"{folder} / {stem}", fill="#222222")
    sheet.save(OUT / f"{name}-review.png")


if __name__ == "__main__":
    for clip, parts in CLIPS.items():
        export(clip, parts)
