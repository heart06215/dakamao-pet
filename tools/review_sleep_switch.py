"""Inspect both directions using frames decoded from the exported MP4."""
from pathlib import Path
import cv2
from PIL import Image

qa = Path(__file__).resolve().parent / "qa"
capture = cv2.VideoCapture(str(qa / "mp4/sleep_pose_switch.mp4"))
fps = capture.get(cv2.CAP_PROP_FPS)
sheet = Image.new("RGB", (1792, 512), "#eeeeee")
for row, start in enumerate((0.288, 1.908)):
    for column in range(7):
        time = start + column * 6 * 0.036 + 0.018
        capture.set(cv2.CAP_PROP_POS_FRAMES, round(time * fps))
        okay, frame = capture.read()
        if not okay:
            raise RuntimeError(f"Cannot decode sleep switch at {time}")
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image = image.crop((128, 56, 512, 440)).resize((256, 256))
        sheet.paste(image, (column * 256, row * 256))
capture.release()
sheet.save(qa / "v16-sleep-switch-decoded.png")
