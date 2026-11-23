"""Make a compact contact sheet from the decoded review videos."""
from pathlib import Path
import cv2
from PIL import Image

root = Path(__file__).resolve().parent / "qa"
sheet = Image.new("RGB", (1920, 720), "#eeeeee")
for row, (name, start, end) in enumerate([
    ("head_touch", 0, 5.715),
    ("lift_and_land", 3.21, 5.28),
    ("body_touch_and_stretch", 3.04, 5.11),
]):
    capture = cv2.VideoCapture(str(root / "mp4" / (name + ".mp4")))
    fps = capture.get(cv2.CAP_PROP_FPS)
    last = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) - 1
    for column in range(6):
        position = min(last, round((start + (end - start) * column / 5) * fps))
        capture.set(cv2.CAP_PROP_POS_FRAMES, position)
        okay, frame = capture.read()
        if not okay:
            raise RuntimeError(f"Cannot decode {name}/{position}")
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        sheet.paste(image.resize((320, 240)), (column * 320, row * 240))
    capture.release()
sheet.save(root / "v14-decoded-review.png")
