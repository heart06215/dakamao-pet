"""Verify rendered frames and record truthful image-generation provenance."""

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PET = ROOT / "DakamaoPet/PetMod/pet/dakamao"
PLAN = ROOT / "tools/generation-plan.json"
KEYFRAMES = ROOT / "tools/keyframes/core"
DIRECT = {
    "default/breathe_b/frame_01.png": "open",
    "touch_head/touch_a/frame_03.png": "head_center",
    "touch_head/touch_a/frame_04.png": "head_left",
    "touch_head/touch_b/frame_03.png": "head_right",
    "touch_body/touch_a/frame_02.png": "body_intro",
    "touch_body/touch_a/frame_03.png": "body_arch",
    "raised_static/hold_a/frame_01.png": "hold",
    "raised_static/hold_c/frame_01.png": "lowered",
    "raised_dynamic/wiggle_single/frame_01.png": "wiggle_left",
    "raised_dynamic/wiggle_single/frame_02.png": "wiggle_right",
    "common/fall_single/frame_03.png": "impact",
    "common/fall_single/frame_04.png": "rebound",
    "idel/blink_a/frame_01.png": "half",
    "idel/blink_a/frame_02.png": "nearly_closed",
    "idel/blink_b/frame_01.png": "closed",
    "idel/yawn_single/frame_01.png": "yawn",
    "idel/look_around_single/frame_01.png": "look_left",
    "idel/look_around_single/frame_02.png": "look_right",
    "idel/groom_single/frame_01.png": "groom_lick",
    "idel/groom_single/frame_02.png": "groom_wash",
    "idel/tail_swish_single/frame_01.png": "tail_left",
    "idel/tail_swish_single/frame_02.png": "tail_right",
    "idel/stretch_single/frame_01.png": "stretch",
    "sleep/zzz_b/frame_01.png": "sleep",
    "shutdown/bye_single/frame_01.png": "wave",
    "say/talk_b/frame_01.png": "talk",
    "work/work_b/frame_01.png": "work",
    "switch_up/up_single/frame_01.png": "happy_jump",
    "switch_down/down_single/frame_01.png": "sad",
    "switch_hunger/hungry_single/frame_01.png": "hungry",
    "switch_thirsty/thirsty_single/frame_01.png": "thirsty",
}


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    prompts = {}
    for line in (ROOT / "Codex制作指南.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("- `") and "/frame_" in line and "` — " in line:
            path, prompt = line[3:].split("` — ", 1)
            prompts[path] = prompt
    assert len(prompts) == 84, len(prompts)
    plan["source_document"] = "Codex制作指南.md"
    plan["workflow_document"] = "关键帧制作流程.md"
    plan["common_prompt"] = (
        "外观以 tools/reference.png 为准；动作截图仅参考姿态与表情。"
        "生成单只完整角色、真实透明背景、无手与其他物体、无文字；"
        "保持金角、蓝色饰物、白色长毛及统一比例。"
    )
    assert len(plan["frames"]) == 84
    targets = {frame["target"] for frame in plan["frames"]}
    files = {str(path.relative_to(ROOT)).replace("\\", "/")
             for path in PET.rglob("frame_*.png")}
    assert targets == files, (sorted(targets - files), sorted(files - targets))
    seen_hashes: dict[str, str] = {}
    counts = {"imagegen_keyframe": 0, "derived_inbetween": 0, "approved_copy": 0}
    for frame in plan["frames"]:
        path = ROOT / frame["target"]
        relative = str(path.relative_to(PET)).replace("\\", "/")
        frame["prompt"] = prompts[relative]
        with Image.open(path) as image:
            assert image.format == "PNG" and image.size == (256, 256)
            assert image.mode == "RGBA" and image.getpixel((0, 0))[3] == 0
            assert image.getchannel("A").getextrema() == (0, 255)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if relative in DIRECT:
            pose = DIRECT[relative]
            assert (KEYFRAMES / f"{pose}.png").exists(), pose
            frame["status"] = "imagegen_keyframe"
            frame["source_keyframe"] = f"tools/keyframes/core/{pose}.png"
        elif digest in seen_hashes:
            frame["status"] = "approved_copy"
            frame["source_frame"] = seen_hashes[digest]
        else:
            frame["status"] = "derived_inbetween"
        frame["current_asset_kind"] = frame["status"]
        frame["current_sha256"] = digest
        counts[frame["status"]] += 1
        seen_hashes.setdefault(digest, frame["target"])

    plan["approved_generated_frames"] = counts["imagegen_keyframe"]
    plan["approved_delivery_frames"] = 84
    plan["generation_route"] = "built_in_imagegen"
    plan["last_tool_error"] = None
    plan["completed_date"] = "2026-09-29"
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "date": "2026-09-29",
        "target_count": 84,
        "counts": counts,
        "format": "256x256 RGBA PNG",
        "contact_sheets": [
            "tools/qa/blink-contact.png",
            "tools/qa/touch-head-contact.png",
            "tools/qa/touch-body-contact.png",
            "tools/qa/raised-fall-contact.png",
            "tools/qa/idle-actions-contact.png",
            "tools/qa/other-actions-contact.png",
        ],
    }
    (ROOT / "tools/qa/frame-validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
