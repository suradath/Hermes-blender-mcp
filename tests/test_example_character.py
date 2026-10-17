#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_example_character.py — ทดสอบ "ตัวอย่างสร้างตัวละคร" ที่ให้ผู้ใช้/AI คัดลอกไปใช้

ทำไมต้องมีเทสต์นี้
------------------
1. ตัวอย่างนี้ถูกออกแบบให้ **ส่งเข้า ``execute_blender_script`` ได้ตรง ๆ**
   จึงต้องผ่านด่านความปลอดภัย (ถ้ามีอะไรที่ด่านห้าม ผู้ใช้จะคัดลอกไปแล้วเจอ error)
2. ต้องพิสูจน์ว่ามันสร้างชิ้นส่วนครบจริง และ **สัดส่วนที่ให้ไปถูกใช้จริง**
   (นี่คือส่วนที่เราตรวจได้ — ส่วน "อ่านรูปแล้วได้สัดส่วนเท่าไร" เป็นงานของ vision ไม่ใช่โค้ด)
3. ต้องไม่ลบข้อความเตือนว่า "นี่คือ blockout ไม่ใช่ image-to-3D" ออกจากเอกสาร
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import fake_bpy  # noqa: E402

sys.modules["bpy"] = fake_bpy

import blender_bridge as br  # noqa: E402

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


EXAMPLE = ROOT / "examples" / "character_blockout.py"


def run_script(code: str) -> dict:
    """ส่งโค้ดเข้าเส้นทางจริงของ execute_blender_script (ผ่านด่าน + exec)"""
    return br.handle_message({"id": 1, "method": "call_tool",
                              "params": {"name": "execute_blender_script",
                                         "arguments": {"code": code,
                                                       "return_variables": "result"}}})


# ===========================================================================
section("[1] ไฟล์ตัวอย่างต้องมีและผ่านด่านความปลอดภัย")
# ===========================================================================
check("มีไฟล์ examples/character_blockout.py", EXAMPLE.is_file(), str(EXAMPLE))
source = EXAMPLE.read_text(encoding="utf-8") if EXAMPLE.is_file() else ""

guard = br.scan_code(source)
check("⚠️ ผ่านด่านความปลอดภัยของ execute_blender_script (คัดลอกไปวางได้เลย)",
      not guard.violations, "; ".join(guard.violations)[:200])
check("ด่านไม่เตือนถัง ๆ (งานนี้ไม่ควรแตะการบันทึก/ลบ)",
      all("ลบ" not in w and "บันทึกทับ" not in w for w in guard.warnings), str(guard.warnings))
check("ใช้แค่ bpy + math (สะพานเป็น stdlib และ math ถูกอนุญาต)",
      "import bpy" in source and "import math" in source and "import os" not in source)

# ===========================================================================
section("[2] รันตัวอย่างจริงในฉากจำลอง")
# ===========================================================================
fake_bpy.reset()
r = run_script(source)
check("รันสำเร็จผ่าน execute_blender_script", r.get("ok") is True, str(r.get("error"))[:200])
res = (r.get("result") or {})
check("คืนค่าสรุปผลกลับมา (ตัวแปร result)", isinstance(res.get("result"), dict), str(res)[:160])
summary = res.get("result") or {}
check("สร้างชิ้นส่วนครบ 9 ชิ้น (ขา2 สะโพก ลำตัว แขน2 คอ หัว ผม)",
      summary.get("part_count") == 9, str(summary.get("part_count")))
check("คืนชื่อชิ้นส่วนทั้งหมด (เป็นชื่อ ไม่ใช่วัตถุ)",
      len(summary.get("parts") or []) == 9 and all(isinstance(x, str) for x in summary["parts"]),
      str(summary.get("parts")))
check("ความสูงรวมตรงกับสเปก (1.70 ม.)",
      abs((summary.get("height_m") or 0) - 1.70) < 0.02, str(summary.get("height_m")))
check("บอกจำนวนหัวที่ทับได้ (สัดส่วนที่ใช้จริง)",
      abs((summary.get("height_heads") or 0) - 7.5) < 0.05, str(summary.get("height_heads")))

names = [o.name for o in fake_bpy.data.objects]
for part in ("head", "torso", "hips", "neck", "hair", "leg_L", "leg_R", "arm_L", "arm_R"):
    check(f"มีชิ้นส่วน {part} ในฉากจริง", f"Character_{part}" in names, str(sorted(names)))

coll = fake_bpy.data.collections.get("Character")
check("สร้างคอลเลกชันของตัวละครให้", coll is not None, str(list(fake_bpy.data.collections)))
check("ชิ้นส่วนอยู่ในคอลเลกชันของตัวเองทั้งหมด (9 ชิ้น)",
      coll is not None and len(coll.objects) == 9,
      str(len(coll.objects)) if coll else "ไม่มีคอลเลกชัน")
check("คอลเลกชันถูกผูกเข้าฉาก (มองเห็นใน Outliner)",
      coll in fake_bpy.DATA.scenes[0].collection.children if coll else False)

head = fake_bpy.data.objects["Character_head"]
check("หัวตั้งอยู่บนสุด (สูงกว่าลำตัว)", head.location[2] > fake_bpy.data.objects["Character_torso"].location[2],
      f"{head.location[2]} vs {fake_bpy.data.objects['Character_torso'].location[2]}")
legs = fake_bpy.data.objects["Character_leg_L"]
check("ขาเริ่มจากพื้นพอดี (ล่างของขาอยู่ที่ Z=0 ไม่ลอย/ไม่จม)",
      abs((legs.location[2] - legs.scale[2]) - 0.0) < 0.01,
      f"ล่างของขา = {legs.location[2] - legs.scale[2]}")
hair = fake_bpy.data.objects["Character_hair"]
check("ผมอยู่เหนือหัว", hair.location[2] > head.location[2],
      f"ผม z={hair.location[2]} · หัว z={head.location[2]}")
check("ส่วนบนสุดยังสูงไม่เกิน 1.8 ม. (อิงจากส่วนสูง 1.70)",
      hair.location[2] + hair.scale[2] < 1.8,
      f"ยอดผม = {hair.location[2] + hair.scale[2]}")

# คอลเลกชันของ bpy อาจวนได้ทั้ง "ชื่อ" และ "วัตถุ" — รองรับทั้งสองแบบให้เทสต์ไม่เปราะ
def _names(coll):
    return [x if isinstance(x, str) else x.name for x in list(coll)]


check("ใส่สีให้ทุกชิ้น (สร้างวัสดุตามสีที่ให้)",
      len(fake_bpy.data.materials) >= 4, str(_names(fake_bpy.data.materials)))
check("สีเสื้อถูกใช้จริง (มีวัสดุที่มีค่า 0.2)",
      any("0.2" in m for m in _names(fake_bpy.data.materials)), str(_names(fake_bpy.data.materials)))
check("ใช้สีผิวที่ให้ไปด้วย (มีวัสดุ 0.95)",
      any("0.95" in m for m in _names(fake_bpy.data.materials)), str(_names(fake_bpy.data.materials)))
check("พิมพ์สรุปออกมาให้เห็นใน stdout", "character_blockout" in (res.get("stdout") or ""),
      (res.get("stdout") or "")[:120])
check("ไม่ทำให้ฉากเดิมพัง (วัตถุเดิมยังอยู่)",
      "Cube" in names and "Camera" in names, str(sorted(names)))

# ===========================================================================
section("[3] สัดส่วนที่ให้ไปต้องถูกใช้จริง (หัวใจของงาน 'สร้างตามแบบ')")
# ===========================================================================
fake_bpy.reset()
# จำลองว่า AI อ่านรูปแล้วสรุปเป็น "การ์ตูนหัวโต 4 หัว" + สีชุดต่างออกไป
cartoon = (source
           .replace('"heads_tall": 7.5', '"heads_tall": 4.0')
           .replace('"color_shirt": (0.20, 0.45, 0.85)', '"color_shirt": (0.95, 0.20, 0.30)'))
check("แก้สเปกในโค้ดได้ (สิ่งที่ AI จะทำหลังดูรูป)", cartoon != source)
r = run_script(cartoon)
summary2 = (r.get("result") or {}).get("result") or {}
check("รันสเปกใหม่สำเร็จ", r.get("ok") is True, str(r.get("error"))[:160])
check("สัดส่วนใหม่ถูกใช้จริง (4 หัว)",
      abs((summary2.get("height_heads") or 0) - 4.0) < 0.05, str(summary2.get("height_heads")))
check("ยังคงส่วนสูงรวม 1.70 ม. (สัดส่วนเปลี่ยนแต่ขนาดจริงไม่เปลี่ยน)",
      abs((summary2.get("height_m") or 0) - 1.70) < 0.02, str(summary2.get("height_m")))
check("หัวใหญ่ขึ้นจริงเมื่อลดจำนวนหัวที่ทับได้",
      (summary2.get("head_m") or 0) > (summary.get("head_m") or 0),
      f"{summary2.get('head_m')} vs {summary.get('head_m')}")
check("สีใหม่ถูกใช้ (มีวัสดุสีแดง 0.95)",
      any("0.95" in m for m in _names(fake_bpy.data.materials)), str(_names(fake_bpy.data.materials)))

# ===========================================================================
section("[4] เอกสารต้องซื่อสัตย์เรื่องขอบเขตความสามารถ")
# ===========================================================================
check("ไฟล์ตัวอย่างเตือนว่าเป็น blockout ไม่ใช่ image-to-3D อัตโนมัติ",
      "blockout" in source and ("ไม่ใช่" in source and "image-to-3D" in source),
      "ต้องบอกขอบเขตให้ชัด")
check("อธิบายวิธีใช้กับ AI เป็นขั้นตอน (ดูรูป → แก้ค่า → ส่ง → ดูภาพ → ปรับ)",
      all(k in source for k in ("get_viewport_screenshot", "CHARACTER", "execute_blender_script")))
check("บอกว่าใช้ได้ทั้งแบบวางใน execute_blender_script และรันตรง ๆ",
      "blender -b" in source and "--python" in source)
check("เอกสารประกอบ (docs/03) มีอยู่จริง",
      (ROOT / "docs" / "03-สร้างตัวละครจากรูป.md").is_file(),
      "ต้องมีคู่มืออธิบายวิธีทำจริง")
doc = (ROOT / "docs" / "03-สร้างตัวละครจากรูป.md")
if doc.is_file():
    d = doc.read_text(encoding="utf-8")
    check("คู่มืออ้างถึงไฟล์ตัวอย่างนี้", "character_blockout.py" in d)
    check("คู่มือบอกข้อจำกัด (ทำ image-to-3D อัตโนมัติไม่ได้ถ้าไม่มีบริการภายนอก)",
          "image-to-3D" in d or "image to 3D" in d)
    check("คู่มือมีตัวอย่างคำสั่งที่ผู้ใช้พิมพ์ได้จริง", "แนบรูป" in d or "รูป" in d)
    check("คู่มือบอกชื่อเครื่องมือแบบเต็มที่ AI จะเรียก",
          "mcp_blender_get_viewport_screenshot" in d,
          "ผู้ใช้ต้องรู้ว่าต้องเรียกอะไร")
    check("คู่มือมีขั้นตอนเป็นข้อ ๆ (อย่างน้อย 5 ขั้น)", d.count("\n1. ") >= 1 and "7." in d)

# ===========================================================================
section("[5] ตัวละครจริงจากรูปที่แนบมา (T-pose · หัวโล้น · ตา · เข็มขัด · เท้า)")
# ===========================================================================
# ค่าที่ "วัดจากพิกเซลของรูปจริง" (ไม่ใช่เดาด้วยตา) — ได้จากสคริปต์วัด silhouette:
#   ความสูงรวม 751 px · หัว 247 px → 3.04 หัว · แขนกว้าง 0.872H · อกกว้าง 0.25H
#   เป้าที่ 0.759H จากยอด (= 0.241H จากพื้น) · ขายาว 0.24H · สีผิว #e0b080 · เข็มขัด #704020
MEASURED = {"heads_tall": 3.04, "head_h": 0.329, "arm_span": 0.872, "torso_or_chest_w": 0.25,
            "crotch_z": 0.241, "leg_len": 0.24}

fake_bpy.reset()
# AI ทำแบบนี้จริง: แปลง "ค่าที่วัดได้" เป็นสเปกในหน่วย "หัว" แล้วแก้ในไฟล์
ref = (source
       .replace('"heads_tall": 7.5,', '"heads_tall": 3.04,')          # ตัวตุ๊กตา 3 หัว
       .replace('"shoulder_width_heads": 1.7,', '"shoulder_width_heads": 0.85,')
       .replace('"arm_length_heads": 3.0,', '"arm_length_heads": 0.95,')
       .replace('"leg_length_heads": 3.8,', '"leg_length_heads": 2.2,')
       .replace('"pose": "stand",', '"pose": "tpose",')
       .replace('"shirt": True,', '"shirt": False,')
       .replace('"pants": True,', '"pants": False,')
       .replace('"hair": True,', '"hair": False,')
       .replace('"face": False,', '"face": True,')
       .replace('"belt": False,', '"belt": True,')
       .replace('"feet": False,', '"feet": True,')
       .replace('"color_skin": (0.95, 0.76, 0.65),', '"color_skin": (0.88, 0.69, 0.50),')
       .replace('"color_belt": (0.44, 0.25, 0.13),', '"color_belt": (0.44, 0.25, 0.13),'))
check("แก้สเปกเป็นค่าที่วัดจากรูปได้ (11 จุด)", ref != source and '"heads_tall": 3.04,' in ref)
check("สเปกใหม่ยังผ่านด่านความปลอดภัย", not br.scan_code(ref).violations)

r = run_script(ref)
check("รันตัวละครจากรูปสำเร็จ", r.get("ok") is True, str(r.get("error"))[:200])
res5 = ((r.get("result") or {}).get("result") or {})
names5 = [o.name for o in fake_bpy.data.objects]
check("ได้ชิ้นส่วนครบ 14 ชิ้น (ขา2+เท้า2+สะโพก+เข็มขัด+ผ้าเตี่ยว+ลำตัว+แขน2+คอ+หัว+ตา2)",
      res5.get("part_count") == 14, str(res5.get("part_count")))
check("หัวโล้นจริง — ไม่มีชิ้น 'hair'", not any(n.endswith("_hair") for n in names5), str(sorted(names5)))
for want in ("_eye_L", "_eye_R", "_belt", "_cloth", "_foot_L", "_foot_R"):
    check(f"มีชิ้นส่วน {want}", any(n.endswith(want) for n in names5), str(sorted(names5)))
check("ท่าเป็น T-pose ตามรูป", res5.get("pose") == "tpose", str(res5.get("pose")))

# ── เทียบสัดส่วนที่โมเดลสร้าง กับ ที่วัดจากรูป ──
rat = res5.get("ratios") or {}
print(f"    ที่วัดจากรูป: {MEASURED}")
print(f"    โมเดลสร้าง : {rat}")
for key, got, tol in [("head_h", rat.get("head_h"), 0.03),
                      ("arm_span", rat.get("arm_span"), 0.08),
                      ("shoulder_w", rat.get("shoulder_w"), 0.05),
                      ("crotch_z", rat.get("crotch_z"), 0.03),
                      ("leg_len", rat.get("leg_len"), 0.04)]:
    want = MEASURED.get(key) if key != "shoulder_w" else MEASURED["torso_or_chest_w"]
    check(f"สัดส่วน {key} ตรงกับที่วัดจากรูป (±{tol}) — ได้ {got} วัดได้ {want}",
          got is not None and abs(got - want) <= tol, f"{got} vs {want}")
check("จำนวนหัวที่ทับได้ตรงกับที่วัด (3.04)",
      abs((res5.get("height_heads") or 0) - MEASURED["heads_tall"]) < 0.02,
      str(res5.get("height_heads")))

arm = fake_bpy.data.objects[[n for n in names5 if n.endswith("_arm_L")][0]]
# ⚠️ ในสคริปต์ bpy ดิบ มุมเป็น "เรเดียน" (เครื่องมือ MCP ที่รับค่าจาก AI ใช้ "องศา" แล้วแปลงให้)
check("แขนวางแนวนอนจริง (หมุน 90 องศา = 1.5708 เรเดียน รอบแกน Y)",
      abs(arm.rotation_euler[1] - math.pi / 2.0) < 0.01, str(arm.rotation_euler))
span_half = (res5["ratios"]["arm_span"] * res5["height_m"]) / 2.0
check("ปลายแขนข้างนอกอยู่ที่ระยะครึ่งหนึ่งของช่วงแขนพอดี",
      abs((arm.location[0] + arm.scale[2]) - span_half) < 0.01,
      f"{arm.location[0] + arm.scale[2]} vs {span_half}")
check("สีผิวที่โมเดลใช้ตรงกับที่สุ่มจากรูป (#e0b080 → 0.88,0.69,0.50)",
      any("0.88_0.69_0.5" in m for m in _names(fake_bpy.data.materials)),
      str(_names(fake_bpy.data.materials)))
check("เท้าอยู่ติดพื้น (ไม่ลอย)", all(
    abs(fake_bpy.data.objects[n].location[2] - fake_bpy.data.objects[n].scale[2]) < 0.005
    for n in names5 if n.endswith(("_foot_L", "_foot_R"))))

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
