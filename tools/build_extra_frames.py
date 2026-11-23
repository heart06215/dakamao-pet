"""Build the remaining desktop-pet action frames from generated key poses."""

from pathlib import Path
from shutil import copy2

from PIL import Image, ImageDraw

from build_core_frames import GENERATED, KEYFRAMES, PET, ROOT, fit, save


SOURCES = {
    "closed": "exec-31a58d66-c13e-4c82-84df-d91f0291c81c.png",
    "nearly_closed": "exec-e9f8505f-7ae1-422b-ba92-fd1a64b944d4.png",
    "yawn": "exec-ca746319-304e-4fbb-8242-6179d2d4e192.png",
    "look_left": "exec-1dd674fa-9db2-4a81-b66d-e72889f7ad3c.png",
    "look_right": "exec-82176558-2cbb-4559-9115-5f78a63a9986.png",
    "sleep": "exec-a762bb1f-db0d-4a3e-9a12-916b1c08ea1b.png",
    "groom_lick": "exec-32c49623-6c4a-4c56-be9d-f8890f0fa62d.png",
    "groom_wash": "exec-9bc85bbf-1edc-479f-ba80-7a9cb1ffc6f3.png",
    "stretch": "exec-9604181c-6ab3-4c10-899f-1cf3d21e794f.png",
    "wave": "exec-b57aebc1-51b6-48f6-b5e3-87de2e3bc187.png",
    "tail_left": "exec-d42ce2a6-00d4-4fbc-a87e-3ceb168ca574.png",
    "tail_right": "exec-552b5c1b-cd91-47d5-9184-2f94b5b9c229.png",
    "talk": "exec-7e8bcacc-1939-4406-bfcc-359924f62eb0.png",
    "work": "exec-a408e0e5-744c-47bd-abef-782a6b70cd00.png",
    "happy_jump": "exec-ac7849c5-0c62-46fd-88b9-28a0c4e3ab9f.png",
    "sad": "exec-c624ef9e-2783-4652-8999-7d91a25aa61c.png",
    "hungry": "exec-1c100d45-6c98-4d8c-a714-406564b8c13e.png",
    "thirsty": "exec-b38feca9-3d6c-4bfb-ae66-738308b1f1c6.png",
}


def contact(name: str, folders: list[str]) -> None:
    paths = [path for folder in folders for path in sorted((PET / folder).glob("*.png"))]
    sheet = Image.new("RGB", (256 * 6, 290 * ((len(paths) + 5) // 6)), "#888888")
    label = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        frame = Image.open(path).convert("RGBA")
        x, y = index % 6 * 256, index // 6 * 290
        sheet.paste(frame, (x, y), frame.getchannel("A"))
        label.text((x + 4, y + 260), f"{path.parent.name}/{path.name}", fill="white")
    sheet.save(ROOT / "tools/qa" / f"{name}-contact.png")


def main() -> None:
    KEYFRAMES.mkdir(parents=True, exist_ok=True)
    for pose, filename in SOURCES.items():
        saved = KEYFRAMES / f"{pose}.png"
        if not saved.exists():
            copy2(GENERATED / filename, saved)

    stand = ("open", 150, 198, 248, 0)
    closed = ("closed", 150, 198, 248, 0)
    sleeping = ("sleep", 190, 126, 248, 0)

    save("idel/yawn_single", [("yawn", 150, 198, 248, 0),
                              ("half", 150, 198, 248, 0)])
    save("idel/look_around_single", [("look_left", 150, 198, 248, 0),
                                    ("look_right", 150, 198, 248, 0), stand])
    save("idel/groom_single", [("groom_lick", 150, 198, 248, 0),
                              ("groom_wash", 150, 198, 248, 0), stand])
    save("idel/tail_swish_single", [("tail_left", 175, 198, 248, 0),
                                   ("tail_right", 175, 198, 248, 0)])
    save("idel/stretch_single", [("stretch", 190, 172, 248, 0), stand])

    save("idel/doze_a", [("half", 150, 198, 248, 0), closed])
    save("idel/doze_b", [closed, ("closed", 150, 198, 247, 0)])
    save("idel/doze_c", [("open", 150, 198, 247, 0), stand])
    save("sleep/zzz_b", [sleeping, ("sleep", 190, 127, 248, 0),
                         ("sleep", 190, 129, 248, 0), sleeping])

    save("startup/boot_single", [sleeping, stand])
    save("shutdown/bye_single", [("wave", 165, 198, 248, 0), sleeping])
    save("say/talk_b", [("talk", 150, 198, 248, 0), stand])
    save("work/work_b", [("work", 150, 198, 248, -1),
                         ("work", 150, 198, 248, 1)])

    save("switch_up/up_single", [("happy_jump", 170, 182, 224, 0),
                                 ("head_center", 150, 192, 248, 0)])
    save("switch_down/down_single", [("sad", 150, 198, 248, 0),
                                     ("sad", 150, 192, 248, 0)])
    save("switch_hunger/hungry_single", [("hungry", 155, 198, 248, 0),
                                         ("hungry", 155, 198, 248, 2)])
    save("switch_thirsty/thirsty_single", [("thirsty", 150, 198, 248, 0),
                                           ("thirsty", 150, 198, 248, 2)])

    contact("idle-actions", ["idel/yawn_single", "idel/look_around_single",
                             "idel/groom_single", "idel/tail_swish_single",
                             "idel/stretch_single", "idel/doze_a", "idel/doze_b",
                             "idel/doze_c"])
    contact("other-actions", ["sleep/zzz_b", "startup/boot_single",
                              "shutdown/bye_single", "say/talk_b", "work/work_b",
                              "switch_up/up_single", "switch_down/down_single",
                              "switch_hunger/hungry_single", "switch_thirsty/thirsty_single"])


if __name__ == "__main__":
    main()
