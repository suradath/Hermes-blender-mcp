#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_addon_structure.py — ตรวจไฟล์ add-on ของ Blender แบบไม่ต้องมี Blender

ตรวจสิ่งที่ "พังเงียบ ๆ" ได้บ่อยที่สุด
  - bl_info ครบตามที่ Blender ต้องการ (ขาดคีย์เดียว add-on ไม่ขึ้นในเมนู)
  - มี register() / unregister() จริง
  - จุดสำคัญเชิงสถาปัตยกรรม: ลงทะเบียน timer บน main thread และใช้ TimerPump
    (ถ้าเอา bpy ไปเรียกใน thread แยก Blender จะ crash — ไม่ใช่ exception)
  - เส้นทางการหา blender_bridge.py และคู่มือการติดตั้งตรงกัน
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDON = ROOT / "blender_addon" / "__init__.py"

passed = 0
failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed
    if cond:
        passed += 1
    else:
        failed.append(f"{name} — {detail}" if detail else name)


def section(t: str) -> None:
    print(f"\n{'=' * 70}\n{t}\n{'=' * 70}")


src = ADDON.read_text(encoding="utf-8") if ADDON.is_file() else ""

# ===========================================================================
section("[1] ไฟล์และ bl_info (Blender อ่านส่วนนี้ตอนติดตั้ง)")
# ===========================================================================
check("มีไฟล์ blender_addon/__init__.py", ADDON.is_file(), str(ADDON))

bl_info = {}
m = re.search(r"^bl_info\s*=\s*(\{.*?\n\})", src, re.S | re.M)
check("มี bl_info เป็น dict ที่ระดับบนสุด", m is not None)
if m:
    try:
        bl_info = ast.literal_eval(m.group(1))
    except Exception as exc:  # noqa: BLE001
        check("bl_info อ่านค่าได้", False, str(exc))
for key in ("name", "author", "version", "blender", "location", "description", "category"):
    check(f"bl_info มีคีย์ {key}", key in bl_info, str(sorted(bl_info)))
check("version เป็น tuple ของเลข 3 ตัว",
      isinstance(bl_info.get("version"), tuple) and len(bl_info["version"]) == 3,
      str(bl_info.get("version")))
check("blender ระบุเวอร์ชันขั้นต่ำ",
      isinstance(bl_info.get("blender"), tuple) and bl_info["blender"][0] >= 4,
      str(bl_info.get("blender")))
check("หมวดหมู่เป็นค่าที่ Blender รู้จัก",
      bl_info.get("category") in ("Development", "Add Mesh", "Object", "System",
                                  "Animation", "3D View", "Scene", "Render"),
      str(bl_info.get("category")))

# ===========================================================================
section("[2] โครงสร้าง add-on ที่ Blender ต้องการ")
# ===========================================================================
tree = None
try:
    tree = ast.parse(src)
    check("ไวยากรณ์ Python ถูกต้อง", True)
except SyntaxError as exc:
    check("ไวยากรณ์ Python ถูกต้อง", False, f"บรรทัด {exc.lineno}: {exc.msg}")

top_funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)] if tree else []
check("มีฟังก์ชัน register()", "register" in top_funcs, str(top_funcs[:12]))
check("มีฟังก์ชัน unregister()", "unregister" in top_funcs)

classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)] if tree else []
check("มีคลาส Panel (แผงใน Sidebar)", any("PT_" in c or "Panel" in c for c in classes),
      str(classes))
check("มี Operator เริ่มสะพาน", any("start_bridge" in c for c in classes), str(classes))
check("มี Operator หยุดสะพาน", any("stop_bridge" in c for c in classes), str(classes))
check("มีคลาสเก็บค่าตั้ง (PropertyGroup)", any("Settings" in c for c in classes), str(classes))
check("ลงทะเบียนคลาสครบผ่านลูป (ไม่ลืมตัวใดตัวหนึ่ง)",
      re.search(r"for cls in (reversed\()?CLASSES", src) is not None)
check("unregister ลบ property ของ Scene ด้วย", "del bpy.types.Scene.lpm_bridge" in src)

# ===========================================================================
section("[3] หัวใจสถาปัตยกรรม: bpy ต้องอยู่บน main thread")
# ===========================================================================
check("ใช้ TimerPump ของสะพาน (คิวงานไป main thread)",
      "TimerPump" in src and "pump.drain" in src)
check("ลงทะเบียน bpy.app.timers.register()",
      "bpy.app.timers.register(" in src,
      "ถ้าไม่มี timer งานจาก thread แยกจะไปแตะ bpy → Blender crash")
check("ยกเลิก timer ตอนหยุด", "bpy.app.timers.unregister(" in src)
check("โหลดสะพานผ่านสเปกไฟล์ (ไม่พึ่ง sys.path)",
      "importlib.util.spec_from_file_location" in src)
check("หา blender_bridge.py หลายที่ (โฟลเดอร์ add-on / แม่ / BLENDER_MCP_DIR)",
      "BLENDER_MCP_DIR" in src and "_bridge_candidates" in src)
check("โหลดสะพานไม่สำเร็จ → บอกผู้ใช้ชัดเจน ไม่พังเงียบ",
      "หา blender_bridge.py ไม่เจอ" in src)
check("ไม่เรียก bpy จากใน thread ของสะพานโดยตรง",
      "threading.Thread" not in src,
      "ให้ TimerPump เป็นเจ้าของ thread แทน")
check("มี token กันโปรเซสอื่นในเครื่องมาใช้",
      "token" in src.lower() and "secrets.token_urlsafe" in src)
check("บอกบรรทัดคำสั่งที่ต้องใส่ใน config ของ Hermes",
      "--attach" in src)

# ===========================================================================
section("[4] คู่มือการติดตั้งกับความจริงตรงกัน")
# ===========================================================================
check("เอกสารบอกโฟลเดอร์ addons ของ Blender",
      "scripts/addons/blender_mcp_bridge" in src or "addons\\blender_mcp_bridge" in src)
check("บอกว่าต้องมี blender_bridge.py อยู่ด้วยกัน",
      "blender_bridge.py" in src and "โฟลเดอร์เดียวกัน" in src)
check("สคริปต์สะพานมีอยู่จริงในโปรเจกต์", (ROOT / "blender_bridge.py").is_file())
check("สคริปต์สะพานบอกวิธีรันแบบ headless ในเอกสารตัวเอง",
      "blender -b" in (ROOT / "blender_bridge.py").read_text(encoding="utf-8"))

# ===========================================================================
section("[5] ตัวสร้างไฟล์ .zip สำหรับติดตั้ง (Install from Disk)")
# ===========================================================================
sys.path.insert(0, str(ROOT / "tools"))
bz = None
try:
    import build_addon_zip as bz  # noqa: E402
    check("มีสคริปต์ tools/build_addon_zip.py", True)
except Exception as exc:  # noqa: BLE001
    check("มีสคริปต์ tools/build_addon_zip.py", False, str(exc))

if bz is not None:
    import tempfile  # noqa: E402
    import zipfile  # noqa: E402

    want_ver = ".".join(str(v) for v in bl_info.get("version", ()))
    check("อ่านเลขเวอร์ชันจาก bl_info ได้", bz.read_version() == want_ver,
          f"{bz.read_version()} ≠ {want_ver}")
    check("ชื่อโฟลเดอร์ add-on ใช้ชื่อที่เอกสารบอก",
          bz.ADDON_NAME == "blender_mcp_bridge", bz.ADDON_NAME)

    with tempfile.TemporaryDirectory() as td:
        target = bz.build(pathlib.Path(td))
        check("ตั้งชื่อไฟล์มีเลขเวอร์ชัน",
              target.name == f"{bz.ADDON_NAME}-{want_ver}.zip", target.name)
        with zipfile.ZipFile(target) as z:
            names = z.namelist()
            check("zip มี __init__.py ของ add-on",
                  f"{bz.ADDON_NAME}/__init__.py" in names, str(names))
            check("⚠️ zip มี blender_bridge.py อยู่ข้างในด้วย "
                  "(ลืมเมื่อไร add-on หาสะพานไม่เจอทันที)",
                  f"{bz.ADDON_NAME}/blender_bridge.py" in names, str(names))
            check("แนบ LICENSE ไปด้วยถ้ามี", any(n.endswith("LICENSE") for n in names), str(names))
            check("ไม่มีไฟล์ขยะปน (__pycache__/.pyc)",
                  not any("__pycache__" in n or n.endswith(".pyc") for n in names), str(names))
            check("zip ผ่านการทดสอบความสมบูรณ์ของตัวเอง", z.testzip() is None)
            init_in_zip = z.read(f"{bz.ADDON_NAME}/__init__.py").decode("utf-8")
            check("bl_info อ่านได้จากข้างใน zip จริง",
                  re.search(r"^bl_info\s*=\s*\{", init_in_zip, re.M) is not None)
            check("add-on หา blender_bridge.py จากโฟลเดอร์ตัวเองได้ (สำคัญ: ใน zip อยู่ด้วยกัน)",
                  "ADDON_DIR" in init_in_zip, "ต้องค้นจากโฟลเดอร์ของ add-on")

    # ต้องไม่ปล่อยผ่านถ้าไฟล์ต้นทางขาด
    saved = bz.MEMBERS
    try:
        bz.MEMBERS = [(pathlib.Path("/ไม่มีไฟล์นี้.py"), "x/__init__.py")]
        try:
            bz.check_sources()
            check("ไฟล์ต้นทางขาด → ต้องไม่ปล่อยผ่าน", False, "ไม่เกิดข้อผิดพลาด")
        except FileNotFoundError:
            check("ไฟล์ต้นทางขาด → แจ้งชัดเจนไม่ปล่อยผ่าน", True)
    finally:
        bz.MEMBERS = saved

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
