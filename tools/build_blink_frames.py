"""Build the approved blink and matching idle loop from generated key poses."""

from pathlib import Path
from shutil import copy2

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
GENERATED = Path.home() / ".codex/generated_images/01a0eb59-c50f-7951-bc74-3963cc0d6d38"
KEYFRAMES = ROOT / "tools/keyframes/blink"
PET = ROOT / "DakamaoPet/PetMod/pet/dakamao"
SOURCES = {
    "closed": "exec-31a58d66-c13e-4c82-84df-d91f0291c81c.png",
    "open": "exec-5bd2a103-548f-445c-b39a-d691f42e3601.png",
    "half": "exec-4e992ad1-dfa1-4332-bb3b-ae2dbd9ea563.png",
    "nearly_closed": "exec-e9f8505f-7ae1-422b-ba92-fd1a64b944d4.png",
}


def fitted_frame(path: Path) -> Image.Image:
    # Identical crop for all key poses keeps the horn, fur and paws still.
    source = Image.open(path).convert("RGBA").crop((190, 20, 1070, 1185))
    source = source.resize((150, 198), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (256, 256))
    frame.alpha_composite(source, (53, 50))
    return frame


def breathe(frame: Image.Image, height_delta: int) -> Image.Image:
    if not height_delta:
        return frame.copy()
    # Keep the paws planted as the fur rises subtly with the breath.
    raised = frame.crop((53, 50, 203, 248)).resize(
        (150, 198 + height_delta), Image.Resampling.LANCZOS
    )
    output = Image.new("RGBA", (256, 256))
    output.alpha_composite(raised, (53, 50 - height_delta))
    return output


def save(relative: str, frame: Image.Image) -> None:
    destination = PET / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.save(destination)


def main() -> None:
    KEYFRAMES.mkdir(parents=True, exist_ok=True)
    for pose, filename in SOURCES.items():
        saved = KEYFRAMES / f"{pose}.png"
        if not saved.exists():
            copy2(GENERATED / filename, saved)
    frames = {pose: fitted_frame(KEYFRAMES / f"{pose}.png") for pose in SOURCES}

    for number, height in enumerate((0, 1, 2, 2, 1, 0), start=1):
        save(f"default/breathe_b/frame_{number:02}.png", breathe(frames["open"], height))

    blink = (
        ("idel/blink_a/frame_01.png", "half"),
        ("idel/blink_a/frame_02.png", "nearly_closed"),
        ("idel/blink_b/frame_01.png", "closed"),
        ("idel/blink_b/frame_02.png", "half"),
        ("idel/blink_c/frame_01.png", "half"),
        ("idel/blink_c/frame_02.png", "open"),
    )
    for relative, pose in blink:
        save(relative, frames[pose])


if __name__ == "__main__":
    main()
