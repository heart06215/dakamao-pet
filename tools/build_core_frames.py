"""Fit generated action key poses and derive the 40 core desktop-pet frames."""

from pathlib import Path
from shutil import copy2

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
GENERATED = Path.home() / ".codex/generated_images/01a0eb59-c50f-7951-bc74-3963cc0d6d38"
KEYFRAMES = ROOT / "tools/keyframes/core"
PET = ROOT / "DakamaoPet/PetMod/pet/dakamao"
SOURCES = {
    "open": "exec-5bd2a103-548f-445c-b39a-d691f42e3601.png",
    "half": "exec-4e992ad1-dfa1-4332-bb3b-ae2dbd9ea563.png",
    "head_center": "exec-2848402f-c7f9-4939-a6d4-e74893468989.png",
    "head_left": "exec-fb5b9101-e0b2-42de-a080-6d1cf35333ba.png",
    "head_right": "exec-dd36c0e9-e0f8-4bd5-914e-37010bde9f8a.png",
    "body_intro": "exec-f3db4874-6058-4534-aba5-2ed9d1981103.png",
    "body_arch": "exec-3d7d055d-a0ca-4d0e-b1e1-1889f785aa7e.png",
    "hold": "exec-c0c593fe-ab9a-4293-903f-4c9e3c2e4f61.png",
    "lowered": "exec-da45097e-5ac9-4ad0-92f6-0dd934ababb2.png",
    "wiggle_left": "exec-e4d4a8a7-e2a9-455b-8a18-de78ebfe6cd9.png",
    "wiggle_right": "exec-3b45fc18-31b6-4316-88b4-a0dc0d3e67c8.png",
    "impact": "exec-83afaf62-1363-4c7b-8db5-124a6293e92b.png",
    "rebound": "exec-8e7e835f-bafd-4f77-a7e7-157b96a074e7.png",
}


def fit(pose: str, width: int, height: int, bottom: int, dx: int = 0) -> Image.Image:
    image = Image.open(KEYFRAMES / f"{pose}.png").convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 240 else 0).getbbox()
    if bbox is None:
        raise ValueError(f"No opaque pixels: {pose}")
    # Remove semitransparent generator specks beyond the character silhouette.
    bbox = tuple(max(0, edge - 3) if i < 2 else min(image.size[i - 2], edge + 3)
                 for i, edge in enumerate(bbox))
    image = image.crop(bbox)
    scale = min(width / image.width, height / image.height)
    size = (round(image.width * scale), round(image.height * scale))
    image = image.resize(size, Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (256, 256))
    output.alpha_composite(image, ((256 - size[0]) // 2 + dx, bottom - size[1]))
    return output


def save(folder: str, poses: list[tuple[str, int, int, int, int]]) -> None:
    destination = PET / folder
    destination.mkdir(parents=True, exist_ok=True)
    for index, (pose, width, height, bottom, dx) in enumerate(poses, start=1):
        fit(pose, width, height, bottom, dx).save(destination / f"frame_{index:02}.png")


def main() -> None:
    KEYFRAMES.mkdir(parents=True, exist_ok=True)
    for pose, filename in SOURCES.items():
        saved = KEYFRAMES / f"{pose}.png"
        if not saved.exists():
            copy2(GENERATED / filename, saved)

    stand = ("open", 150, 198, 248, 0)
    smile = ("head_center", 150, 198, 248, 0)
    left = ("head_left", 155, 198, 248, 0)
    right = ("head_right", 155, 198, 248, 0)
    intro = ("body_intro", 155, 198, 248, 0)
    arch = ("body_arch", 188, 187, 248, 0)
    hold = ("hold", 150, 180, 217, 0)
    lowered = ("lowered", 150, 185, 239, 0)
    impact = ("impact", 190, 128, 248, 0)

    save("touch_head/touch_a", [stand, stand, smile, left])
    save("touch_head/touch_b", [left, smile, right, left])
    save("touch_head/touch_c", [("half", 150, 198, 248, 0), stand])

    save("touch_body/touch_a", [stand, intro, arch, arch])
    save("touch_body/touch_b", [("body_arch", 188, 187, 248, -2), arch,
                                ("body_arch", 188, 187, 248, 2),
                                ("body_arch", 188, 187, 248, -2)])
    save("touch_body/touch_c", [intro, stand])

    save("raised_static/hold_a", [hold, ("hold", 150, 180, 219, 0)])
    save("raised_static/hold_b", [("hold", 150, 180, 219, -2),
                                  ("hold", 150, 180, 219, 2)])
    save("raised_static/hold_c", [lowered, impact])

    save("raised_dynamic/wiggle_single", [
        ("wiggle_left", 175, 180, 222, 0),
        ("wiggle_right", 175, 180, 222, 0),
    ])
    save("common/fall_single", [
        ("wiggle_left", 165, 175, 190, 0),
        ("hold", 150, 180, 225, 0),
        impact,
        ("rebound", 165, 165, 233, 0),
        ("impact", 175, 116, 248, 0),
        stand,
    ])

    groups = {
        "touch-head": ["touch_head/touch_a", "touch_head/touch_b", "touch_head/touch_c"],
        "touch-body": ["touch_body/touch_a", "touch_body/touch_b", "touch_body/touch_c"],
        "raised-fall": ["raised_static/hold_a", "raised_static/hold_b",
                        "raised_static/hold_c", "raised_dynamic/wiggle_single",
                        "common/fall_single"],
    }
    qa = ROOT / "tools/qa"
    qa.mkdir(exist_ok=True)
    for name, folders in groups.items():
        paths = [path for folder in folders for path in sorted((PET / folder).glob("*.png"))]
        sheet = Image.new("RGB", (256 * 6, 290 * ((len(paths) + 5) // 6)), "#888888")
        label = ImageDraw.Draw(sheet)
        for index, path in enumerate(paths):
            frame = Image.open(path).convert("RGBA")
            x, y = index % 6 * 256, index // 6 * 290
            sheet.paste(frame, (x, y), frame.getchannel("A"))
            label.text((x + 4, y + 260), f"{path.parent.name}/{path.name}", fill="white")
        sheet.save(qa / f"{name}-contact.png")


if __name__ == "__main__":
    main()
