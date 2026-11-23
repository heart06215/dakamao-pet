"""Export 84 delivery frames with generated key poses and transition guidance."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
document = ROOT / "Codex制作指南.md"
rows = re.findall(r"^- `([^`]+frame_\d+\.png)` — (.+)$", document.read_text(encoding="utf-8"), re.M)
if len(rows) != 84:
    raise ValueError(f"Expected 84 documented prompts, found {len(rows)}")

common = (
    "第一张参考图 tools/reference.png 是角色造型、比例、毛发、饰物、配色和画风的唯一依据。"
    "第二张截图如有，仅参考动作和神态，不画截图中的人物、手、背景、UI。"
    "生成单张1024×1024透明PNG，真实透明背景、单一完整角色，无阴影、道具、文字、水印。"
    "固定角色比例和脚底基线，提起/甩动/下落按该帧要求偏移。"
    "先用生图真正绘制动作关键姿态，再从通过验收的关键图制作过渡序列帧。"
    "闭眼必须先得到真正闭合眼睑的关键图，不用覆盖眼睛或整体旋转拉伸代替。"
    "保留角尖、耳朵、脚掌和毛发边缘。"
)

def screenshot_for(path):
    if path.startswith("touch_head/"):
        return "223646" if "touch_a/frame_01" in path else "223842"
    if path.startswith("touch_body/"):
        return "223646" if "touch_a/frame_01" in path else "224028"
    if path.startswith("common/fall") or path.startswith("raised_"):
        return "223646"
    if path.startswith("idel/yawn") or path.startswith("say/"):
        return "224202"
    if path.startswith(("idel/doze", "sleep/", "startup/", "shutdown/")):
        return "223804"
    if path.startswith(("work/", "switch_down/")):
        return "223824"
    if path.startswith("switch_up/"):
        return "224028"
    return None

copies = {
    "default/breathe_b/frame_06.png": "default/breathe_b/frame_01.png",
    "touch_head/touch_b/frame_04.png": "touch_head/touch_b/frame_01.png",
    "touch_body/touch_b/frame_04.png": "touch_body/touch_b/frame_01.png",
    "idel/blink_c/frame_02.png": "default/breathe_b/frame_03.png",
    "sleep/zzz_b/frame_04.png": "sleep/zzz_b/frame_01.png",
}
frames = []
for path, prompt in rows:
    target = "DakamaoPet/PetMod/pet/dakamao/" + path
    reference = screenshot_for(path)
    refs = ["tools/reference.png"]
    if reference:
        refs.append(f"picture/Screenshot 2026-09-28 {reference}.jpg")
    frames.append({
        "target": target,
        "original": "tools/originals/" + path,
        "priority": "core" if path.split("/")[0] in
            {"default", "touch_head", "touch_body", "raised_static", "raised_dynamic", "common"} else "secondary",
        "status": "pending_image_generation",
        "current_asset_kind": "reference_transform_preview",
        "current_sha256": hashlib.sha256((ROOT / target).read_bytes()).hexdigest(),
        "reference_images": refs,
        "prompt": prompt,
        "copy_after_source_approved": copies.get(path),
    })

plan = {
    "source_document": document.name,
    "date": "2026-09-29",
    "total_frames": len(frames),
    "approved_generated_frames": 0,
    "generation_route": "built_in_imagegen_in_enabled_environment",
    "production_strategy": "generated_key_poses_then_reviewed_inbetweens",
    "workflow_document": "关键帧制作流程.md",
    "environment_diagnostic": "tools/qa/imagegen-environment.json",
    "last_tool_error": "403 permission_error: Image generation is not enabled for this group",
    "common_prompt": common,
    "resume_rules": [
        "Do not treat existing file counts as evidence that generation is complete.",
        "Generate each required action endpoint with imagegen before constructing transition frames.",
        "For blinking, first generate a genuine closed-eye pose, then make open-to-closed and closed-to-open inbetweens.",
        "Use tools/reference.png and the listed action reference; preserve character identity and alpha.",
        "If eye interpolation produces residual irises or doubled eyelids, generate a half-closed key pose and split the transition.",
        "Track generated key poses separately from derived transition frames; 84 delivery frames do not require 84 independent generations.",
        "Save generated originals before mechanical resizing; preserve genuine alpha and white fur.",
        "Review each action contact sheet and transitions, then update that frame's status and sha256.",
        "Keep frame_NN.png paths; VPet metadata and frame duration are configured by the host.",
        "Publish with tools/publish.ps1 after importing approved art.",
    ],
    "frames": frames,
}
output = ROOT / "tools" / "generation-plan.json"
if output.exists():
    existing = json.loads(output.read_text(encoding="utf-8"))
    if any(f.get("status") != "pending_image_generation" for f in existing.get("frames", [])):
        raise RuntimeError("The plan contains generation progress; do not reset it.")
output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Prepared {len(frames)} prompts; none marked generated.")
