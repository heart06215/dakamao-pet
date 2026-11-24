# SPDX-License-Identifier: CC-BY-NC-SA-4.0
"""Build a content-deduplicated PetMod tree for single-file publishing.

The repository keeps the readable, one-frame-per-file layout so the art
pipeline and the QA scripts keep working unchanged.  The published EXE does
not need duplicate bytes: many sequences reuse identical frames (idle holds,
reversed roll frames, slow loops).  This script writes:

    <out>/shared/<sha256><ext>       one blob per unique file content
    <out>/layout.json                logical path -> blob path

The host materialises the logical tree into
%LOCALAPPDATA%\\DakamaoPet\\assets\\<layout-hash> on first run, using hard
links when the volume allows it and copies otherwise.  No image is decoded or
re-encoded here, so every byte (and therefore every QA pixel comparison) is
preserved exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "DakamaoPet" / "PetMod"
DEFAULT_OUT = ROOT / "DakamaoPet" / "obj" / "petmod-dedup"


def iter_files(source: Path):
    for path in sorted(source.rglob("*")):
        if path.is_file():
            yield path


def build(source: Path, out: Path, verify: bool = False) -> dict:
    if not source.is_dir():
        raise SystemExit(f"PetMod 目录不存在：{source}")
    source = source.resolve()
    out = out.resolve()
    try:
        out.relative_to(source)
    except ValueError:
        pass
    else:
        raise SystemExit("输出目录不能位于 PetMod 内部。")

    started = time.perf_counter()
    files = list(iter_files(source))
    groups: dict[str, list[Path]] = {}
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        groups.setdefault(digest, []).append(path)

    if out.exists():
        shutil.rmtree(out)
    shared = out / "shared"
    shared.mkdir(parents=True)

    layout: dict[str, str] = {}
    linked = copied = 0
    for digest, paths in groups.items():
        suffix = paths[0].suffix.lower()
        blob_name = digest + suffix
        blob = shared / blob_name
        try:
            os.link(paths[0], blob)
            linked += 1
        except OSError:
            shutil.copyfile(paths[0], blob)
            copied += 1
        for path in paths:
            layout[path.relative_to(source).as_posix()] = f"shared/{blob_name}"

    layout_path = out / "layout.json"
    layout_path.write_text(
        json.dumps(layout, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if verify:
        for logical, blob in layout.items():
            original = source / logical.replace("/", os.sep)
            stored = out / blob.replace("/", os.sep)
            if hashlib.sha256(original.read_bytes()).digest() != hashlib.sha256(stored.read_bytes()).digest():
                raise SystemExit(f"去重校验失败：{logical}")

    total = sum(path.stat().st_size for path in files)
    unique = sum((shared / (digest + groups[digest][0].suffix.lower())).stat().st_size for digest in groups)
    report = {
        "files": len(files),
        "unique_files": len(groups),
        "duplicate_files": len(files) - len(groups),
        "total_bytes": total,
        "unique_bytes": unique,
        "saved_bytes": total - unique,
        "saved_percent": round((total - unique) / total * 100, 1) if total else 0,
        "linked_blobs": linked,
        "copied_blobs": copied,
        "seconds": round(time.perf_counter() - started, 2),
        "source": str(source),
        "out": str(out),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="生成去重后的 PetMod 发布素材")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="只统计，不写文件")
    parser.add_argument("--verify", action="store_true", help="写入后逐文件校验字节一致")
    args = parser.parse_args()

    if args.check:
        files = list(iter_files(args.source))
        groups: dict[str, int] = {}
        total = 0
        for path in files:
            size = path.stat().st_size
            total += size
            groups[hashlib.sha256(path.read_bytes()).hexdigest()] = size
        unique = sum(groups.values())
        print(json.dumps({
            "files": len(files),
            "unique_files": len(groups),
            "total_bytes": total,
            "unique_bytes": unique,
            "saved_bytes": total - unique,
            "saved_percent": round((total - unique) / total * 100, 1) if total else 0,
        }, ensure_ascii=False))
        return 0

    report = build(args.source, args.out, args.verify)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
