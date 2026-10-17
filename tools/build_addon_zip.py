#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_addon_zip.py — สร้างไฟล์ .zip สำหรับติดตั้ง add-on เข้า Blender

ทำไมต้องมี
----------
Blender ติดตั้ง add-on ได้จาก `Edit > Preferences > Add-ons > Install...` ซึ่งรับ
ไฟล์ .zip ที่ **ข้างในมีโฟลเดอร์ชื่อ add-on** และมี `__init__.py` อยู่ข้างในนั้น
แต่ในรีโปซอร์สโค้ดมี `blender_addon/__init__.py` + `blender_bridge.py` แยกกัน
ถ้าให้ผู้ใช้คัดลอกเองก็พลาดง่าย (ลืมไฟล์ใดไฟล์หนึ่ง → add-on หาสะพานไม่เจอ)

สคริปต์นี้จึงประกอบเป็น zip ที่พร้อมติดตั้ง และ **ตรวจซ้ำว่าโครงสร้างถูกต้อง**

ใช้:
    python tools/build_addon_zip.py                 # ได้ dist/blender_mcp_bridge-<ver>.zip
    python tools/build_addon_zip.py --out /tmp      # ระบุที่เก็บเอง
    python tools/build_addon_zip.py --list-only     # ดูของที่จะใส่ ไม่ต้องสร้าง
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDON_NAME = "blender_mcp_bridge"          # ชื่อโฟลเดอร์ที่ Blender จะเห็น
SOURCE_INIT = ROOT / "blender_addon" / "__init__.py"
SOURCE_BRIDGE = ROOT / "blender_bridge.py"
LICENSE = ROOT / "LICENSE"

# ไฟล์ที่ต้องมีใน zip: (ไฟล์ต้นทาง, ชื่อในไฟล์ zip)
MEMBERS = [
    (SOURCE_INIT, f"{ADDON_NAME}/__init__.py"),
    (SOURCE_BRIDGE, f"{ADDON_NAME}/blender_bridge.py"),
]


def read_version(path: pathlib.Path | None = None) -> str:
    """อ่านเลขเวอร์ชันจาก bl_info ในไฟล์ add-on (ไม่ import เพราะต้องมี bpy)"""
    src = (path or SOURCE_INIT).read_text(encoding="utf-8")
    m = re.search(r"^bl_info\s*=\s*(\{.*?\n\})", src, re.S | re.M)
    if not m:
        raise ValueError(f"หา bl_info ใน {path or SOURCE_INIT} ไม่เจอ")
    info = ast.literal_eval(m.group(1))
    version = info.get("version")
    if not isinstance(version, tuple) or len(version) < 2:
        raise ValueError(f"bl_info['version'] ต้องเป็น tuple — ได้ {version!r}")
    return ".".join(str(v) for v in version)


def check_sources() -> None:
    """ตรวจก่อนสร้าง — บอกให้ชัดว่าขาดอะไร ไม่ปล่อยให้ได้ zip ที่ติดตั้งแล้วพัง"""
    missing = [str(p) for p, _ in MEMBERS if not p.is_file()]
    if missing:
        raise FileNotFoundError("ไม่พบไฟล์ต้นทาง:\n  - " + "\n  - ".join(missing))
    # add-on ต้องมี register/unregister และ bl_info (Blender บังคับ)
    src = SOURCE_INIT.read_text(encoding="utf-8")
    for need, why in (("def register()", "Blender ต้องมี register()"),
                      ("def unregister()", "Blender ต้องมี unregister()"),
                      ("bl_info", "Blender ต้องมี bl_info")):
        if need not in src:
            raise ValueError(f"add-on ไม่ครบ: ไม่มี {need} — {why}")
    if "load_bridge" not in src or "blender_bridge.py" not in src:
        raise ValueError("add-on ไม่ได้อ้างถึง blender_bridge.py — "
                         "ติดตั้งแล้วจะหาสะพานไม่เจอ")


def build(out_dir: pathlib.Path, version: str | None = None) -> pathlib.Path:
    check_sources()
    ver = version or read_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{ADDON_NAME}-{ver}.zip"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in MEMBERS:
            z.write(src, arc)
        if LICENSE.is_file():
            z.write(LICENSE, f"{ADDON_NAME}/LICENSE")

    verify(target)
    return target


def verify(zip_path: pathlib.Path) -> list[str]:
    """เปิด zip กลับมาอ่าน — กันกรณีสร้างเสร็จแต่โครงสร้างผิด"""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        bad = z.testzip()
        if bad:
            raise ValueError(f"ไฟล์ใน zip เสียหาย: {bad}")
        need = [arc for _, arc in MEMBERS]
        for arc in need:
            if arc not in names:
                raise ValueError(f"zip ไม่มี {arc} (มี: {names})")
        # `bl_info` ต้องอ่านได้จากข้างใน zip จริง ๆ
        init = z.read(f"{ADDON_NAME}/__init__.py").decode("utf-8")
        m = re.search(r"^bl_info\s*=\s*(\{.*?\n\})", init, re.S | re.M)
        if not m:
            raise ValueError("zip นี้ติดตั้งแล้ว Blender จะไม่เห็น add-on (ไม่มี bl_info)")
        # ต้องไม่มีไฟล์แปลกปลอมหลุดเข้ามา (เช่น __pycache__)
        junk = [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
        if junk:
            raise ValueError(f"มีไฟล์ที่ไม่ควรอยู่ใน zip: {junk}")
    return names


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="สร้าง zip สำหรับติดตั้ง add-on เข้า Blender")
    p.add_argument("--out", default=str(ROOT / "dist"), help="โฟลเดอร์ปลายทาง (ค่าปริยาย dist/)")
    p.add_argument("--version", default="", help="กำหนดเลขเวอร์ชันเอง (ค่าปริยายอ่านจาก bl_info)")
    p.add_argument("--list-only", action="store_true", help="แสดงของที่จะใส่แล้วจบ")
    args = p.parse_args(argv)

    if args.list_only:
        print(f"add-on: {ADDON_NAME} · เวอร์ชัน {read_version()}")
        for src, arc in MEMBERS:
            print(f"  {'✓' if src.is_file() else '✗'} {src.relative_to(ROOT)} → {arc}")
        if LICENSE.is_file():
            print(f"  ✓ LICENSE → {ADDON_NAME}/LICENSE")
        return 0

    try:
        target = build(pathlib.Path(args.out), args.version or None)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ สร้างไม่สำเร็จ: {exc}", file=sys.stderr)
        return 1

    names = verify(target)
    print(f"✅ สร้างแล้ว: {target}")
    print(f"   ขนาด {target.stat().st_size:,} ไบต์ · {len(names)} ไฟล์")
    for n in names:
        print(f"     • {n}")
    print("\nวิธีติดตั้ง:")
    print("  Blender → Edit > Preferences > Add-ons > ▼ (มุมขวาบน) > Install from Disk...")
    print(f"  เลือกไฟล์ {target.name} แล้วติ๊กถูกที่ 'LPM Blender MCP Bridge'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
