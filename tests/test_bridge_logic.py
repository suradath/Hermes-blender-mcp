#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_bridge_logic.py — ทดสอบตรรกะของ blender_bridge.py บนเครื่องที่ไม่มี Blender

ใช้ ``tests/fake_bpy.py`` ฉีดเป็นโมดูล ``bpy`` ก่อน import bridge
สิ่งที่ทดสอบได้: การอ่านฉาก · การสร้างรูปทรง · การแก้ transform · ด่านความปลอดภัย
สิ่งที่ทดสอบไม่ได้ (ต้องมี Blender จริง): การเรนเดอร์ · UI · bpy.app.timers
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

import fake_bpy  # noqa: E402  (ต้อง import fake ก่อนสร้าง sys.modules)

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


def call(tool: str, **args):
    """เรียกผ่าน handle_message เหมือนที่ MCP server เรียกจริง"""
    return br.handle_message({"id": 1, "method": "call_tool",
                              "params": {"name": tool, "arguments": args}})


def ok(tool: str, **args):
    r = call(tool, **args)
    assert r["ok"], f"{tool} ล้มเหลว: {r.get('error')}"
    return r["result"]


def err(tool: str, **args) -> dict:
    r = call(tool, **args)
    return r


# ===========================================================================
section("[1] get_scene_hierarchy — อ่านฉาก")
fake_bpy.reset()
h = ok("get_scene_hierarchy")

check("คืนผลเป็น dict ที่ JSON ส่งได้", isinstance(h, dict) and json.dumps(h, ensure_ascii=False))
check("มีส่วน scene", "scene" in h and h["scene"]["name"] == "Scene")
check("บอก engine ที่ใช้เรนเดอร์", h["scene"]["engine"] == "BLENDER_EEVEE_NEXT", str(h["scene"]))
check("บอกเวอร์ชัน Blender", h["blender_version"] == "5.2.0", h["blender_version"])
check("เห็นวัตถุครบ 4 ชิ้น",
      sorted(o["name"] for o in h["objects"]) == ["Camera", "Cube", "Light", "tree_a"],
      str([o["name"] for o in h["objects"]]))
check("นับตามชนิดถูก", h["counts_by_type"] == {"CAMERA": 1, "LIGHT": 1, "MESH": 2},
      str(h["counts_by_type"]))
check("totals ตรงกับของจริง", h["totals"]["objects"] == len(fake_bpy.data.objects) == 4)

names = [c["name"] for c in h["collections"]]
check("มี Scene Collection เป็นราก", names[0] == "Scene Collection" and h["collections"][0].get("is_root"),
      str(names))
check("มีคอลเลกชัน Props", "Props" in names, str(names))
props = next(c for c in h["collections"] if c["name"] == "Props")
check("เส้นทางคอลเลกชันซ้อนถูก", props["path"] == "Scene Collection/Props", props["path"])
check("Props มี tree_a อยู่ข้างใน", props["objects"] == ["tree_a"], str(props["objects"]))

cube = next(o for o in h["objects"] if o["name"] == "Cube")
check("บอกจำนวนจุดยอดของ mesh", cube.get("vertices") == 8 and cube.get("polygons") == 6, str(cube))
tree = next(o for o in h["objects"] if o["name"] == "tree_a")
check("บอกวัตถุแม่", tree.get("parent") == "Cube", str(tree.get("parent")))

r = ok("get_scene_hierarchy", name_filter="cube")
check("กรองชื่อได้ (ไม่สนตัวพิมพ์)",
      [o["name"] for o in r["objects"]] == ["Cube"], str([o["name"] for o in r["objects"]]))

fake_bpy.data.objects["Light"].hidden = True
r = ok("get_scene_hierarchy", include_hidden=False)
check("ซ่อนวัตถุที่มองไม่เห็นเมื่อสั่ง",
      "Light" not in [o["name"] for o in r["objects"]], str([o["name"] for o in r["objects"]]))
r = ok("get_scene_hierarchy", include_hidden=True)
check("ยังเห็นได้ถ้าสั่งให้รวม", "Light" in [o["name"] for o in r["objects"]])
fake_bpy.data.objects["Light"].hidden = False

r = ok("get_scene_hierarchy", max_objects=2)
check("เตือนเมื่อมีวัตถุมากกว่าที่แสดง", r["totals"]["not_shown"] == 2 and "note" in r,
      str(r["totals"]))

# ===========================================================================
section("[2] add_primitive_mesh — สร้างรูปทรง")
fake_bpy.reset()
before = len(fake_bpy.data.objects)
res = ok("add_primitive_mesh", primitive="cube", name="กล่องทดสอบ",
         location=[1, 2, 3], rotation=[90, 0, 0], scale=[2, 2, 2])
check("สร้างวัตถุใหม่จริง", len(fake_bpy.data.objects) == before + 1)
check("ตั้งชื่อตามที่สั่ง", res["created"] == "กล่องทดสอบ", res["created"])
check("ตำแหน่งถูก", res["location"] == [1.0, 2.0, 3.0], str(res["location"]))
check("ขนาดถูก", res["scale"] == [2.0, 2.0, 2.0], str(res["scale"]))

op_calls = [c for c in fake_bpy.ops.calls if c[0] == "mesh.primitive_cube_add"]
check("เรียก operator ของ Blender จริง", len(op_calls) == 1, str(fake_bpy.ops.calls))
kw = op_calls[0][1]
check("⚠️ แปลงองศาเป็น 'เรเดียน' ก่อนส่ง (บั๊กคลาสสิก)",
      abs(kw["rotation"][0] - math.pi / 2) < 1e-9, str(kw["rotation"]))
check("ส่ง location แบบ float", kw["location"] == (1.0, 2.0, 3.0), str(kw["location"]))
obj = fake_bpy.data.objects["กล่องทดสอบ"]
check("ชื่อ mesh data ตรงกับวัตถุ", obj.data.name == "กล่องทดสอบ", obj.data.name)

res = ok("add_primitive_mesh", primitive="sphere", name="ลูกบอล", radius=2.5)
sp = [c for c in fake_bpy.ops.calls if c[0] == "mesh.primitive_uv_sphere_add"][-1][1]
check("ส่ง radius ให้ทรงกลม", sp.get("radius") == 2.5, str(sp))
res = ok("add_primitive_mesh", primitive="torus", name="โดนัท")
to = [c for c in fake_bpy.ops.calls if c[0] == "mesh.primitive_torus_add"][-1][1]
check("torus ส่ง major/minor radius (ชื่อพารามิเตอร์ต่างจากทรงอื่น)",
      "major_radius" in to and "minor_radius" in to, str(to))
res = ok("add_primitive_mesh", primitive="cylinder", name="กระบอก", radius=1.0, size=4.0)
cy = [c for c in fake_bpy.ops.calls if c[0] == "mesh.primitive_cylinder_add"][-1][1]
check("cylinder ใช้ depth ไม่ใช่ size", cy.get("depth") == 4.0, str(cy))

res = ok("add_primitive_mesh", primitive="cube", name="ย้ายคอลเลกชัน", collection="Props")
check("ย้ายเข้าคอลเลกชันที่สั่งได้", res["collection"] == "Props", res["collection"])
check("วัตถุอยู่ในคอลเลกชันจริง",
      fake_bpy.data.objects["ย้ายคอลเลกชัน"] in fake_bpy.data.scenes[0].collection.children[0].objects)

r = err("add_primitive_mesh", primitive="กล้วย")
check("รูปทรงที่ไม่รู้จัก → ปฏิเสธพร้อมบอกตัวเลือก",
      r["ok"] is False and "cube" in r["error"] and "cylinder" in r["error"], r.get("error"))

r = err("add_primitive_mesh", primitive="cube", bogus_param=1)
check("พารามิเตอร์เกิน → error_type='arguments'", r.get("error_type") == "arguments", str(r))

# ===========================================================================
section("[3] modify_object_transform — ขยับวัตถุ")
fake_bpy.reset()
res = ok("modify_object_transform", name="Cube", location=[5, 0, 0])
check("ย้ายแบบสัมบูรณ์", res["location"] == [5.0, 0.0, 0.0], str(res["location"]))
check("รายงานค่าเดิมไว้เทียบ", res["before"]["location"] == [0.0, 0.0, 0.0], str(res["before"]))

res = ok("modify_object_transform", name="Cube", location=[1, 2, 3], relative=True)
check("ย้ายแบบสัมพัทธ์ (บวกเพิ่ม)", res["location"] == [6.0, 2.0, 3.0], str(res["location"]))

res = ok("modify_object_transform", name="Cube", rotation=[45, 0, 180])
check("หมุน: รับองศา คืนองศา", abs(res["rotation_euler_deg"][0] - 45) < 1e-6,
      str(res["rotation_euler_deg"]))
check("⚠️ เก็บเป็นเรเดียนจริง",
      abs(fake_bpy.data.objects["Cube"].rotation_euler[0] - math.radians(45)) < 1e-9,
      str(fake_bpy.data.objects["Cube"].rotation_euler))

res = ok("modify_object_transform", name="Cube", scale=[3, 1, 1])
check("แก้ขนาดได้", res["scale"] == [3.0, 1.0, 1.0], str(res["scale"]))
res = ok("modify_object_transform", name="Cube", scale=[2, 1, 1], relative=True)
check("ขนาดแบบสัมพัทธ์ = คูณ", res["scale"] == [6.0, 1.0, 1.0], str(res["scale"]))

res = ok("modify_object_transform", name="tree_a", location=[0, 0, 10])
check("ไม่แตะค่าที่ไม่ได้สั่งแก้",
      fake_bpy.data.objects["tree_a"].scale == [1.0, 1.0, 1.0], "scale ควรคงเดิม")

r = err("modify_object_transform", name="Cube")
check("ไม่ได้สั่งแก้อะไร → บอกให้ระบุอย่างน้อยหนึ่งอย่าง",
      r["ok"] is False and "location" in r["error"], r.get("error"))

r = err("modify_object_transform", name="ลูกบาศก์ที่ไม่มีอยู่")
check("หาวัตถุไม่เจอ → แจ้งพร้อมชื่อใกล้เคียง",
      r["ok"] is False and "ไม่พบวัตถุ" in r["error"], r.get("error"))

r = err("modify_object_transform", name="Cube", rotation=[10, 0, 0], rotation_mode="ABC")
check("rotation_mode ผิด → ปฏิเสธ", r["ok"] is False and "rotation_mode" in r["error"], r.get("error"))

# ===========================================================================
section("[4] delete_object / set_object_material / save_blend_file")
fake_bpy.reset()
r = ok("delete_object", name="tree_a")
check("มีสลักกันลบพลาด (ยังไม่ลบถ้าไม่ยืนยัน)",
      r["deleted"] is False and "tree_a" in fake_bpy.data.objects, str(r))
r = ok("delete_object", name="tree_a", confirm=True)
check("ยืนยันแล้วลบจริง", r["deleted"] is True and "tree_a" not in fake_bpy.data.objects, str(r))

res = ok("set_object_material", name="Cube", color=[0.9, 0.1, 0.2], metallic=0.5)
check("สร้างวัสดุใหม่สำเร็จ", res["material"].startswith("LPM_"), res["material"])
mat = fake_bpy.data.materials[res["material"]]
bsdf = mat.node_tree.nodes.get("Principled BSDF")
check("ตั้งสีที่ Base Color", bsdf.inputs["Base Color"].default_value[:3] == [0.9, 0.1, 0.2],
      str(bsdf.inputs["Base Color"].default_value))
check("ตั้งค่า metallic", bsdf.inputs["Metallic"].default_value == 0.5)
check("ผูกวัสดุเข้ากับ mesh", fake_bpy.data.objects["Cube"].data.materials[0] is mat)

r = err("set_object_material", name="Camera", color=[1, 0, 0])
check("วัตถุที่ไม่ใช่ mesh → ปฏิเสธอย่างสุภาพ",
      r["ok"] is False and "MESH" in r["error"], r.get("error"))

r = err("save_blend_file")
check("ไฟล์ที่ยังไม่เคยบันทึก → บอกให้ส่ง filepath",
      r["ok"] is False and "filepath" in r["error"], r.get("error"))
res = ok("save_blend_file", filepath="C:/งาน/scene_test")
check("เติม .blend ให้เองถ้าไม่ได้ใส่", res["filepath"].endswith(".blend"), res["filepath"])

# ===========================================================================
section("[5] get_object_details / get_file_metadata")
fake_bpy.reset()
d = ok("get_object_details", name="tree_a")
check("บอกโมดิฟายเออร์", d["modifiers"][0]["name"] == "Subdivision", str(d["modifiers"]))
check("บอกเมทริกซ์โลก 4x4", len(d["matrix_world"]) == 4 and len(d["matrix_world"][0]) == 4)
check("บอกชนิดการหมุน", d["rotation_mode"] == "XYZ")
check("บอก custom properties ได้", isinstance(d["custom_properties"], dict))

fake_bpy.data.filepath = "C:/งาน/โรงเรียน.blend"
m = br.handle_message({"id": 1, "method": "file_metadata"})["result"]
check("metadata: ส่งผ่านคำสั่ง 'file_metadata' (ใช้เป็น MCP Resource ไม่ใช่ tool)",
      isinstance(m, dict) and "filepath" in m, str(m)[:120])
check("metadata: มีที่อยู่ไฟล์", m["filepath"].endswith("โรงเรียน.blend"), m["filepath"])
check("metadata: มีชื่อไฟล์แยก", m["filename"] == "โรงเรียน.blend", m["filename"])
check("metadata: มีเฟรมปัจจุบัน", m["frame"]["current"] == 1, str(m["frame"]))
check("metadata: มี engine", m["render_engine"] == "BLENDER_EEVEE_NEXT")
check("metadata: มีความละเอียดภาพ", m["resolution"]["x"] == 1920, str(m["resolution"]))
check("metadata: นับของในไฟล์ครบ",
      m["counts"]["objects"] == 4 and "meshes" in m["counts"], str(m["counts"]))
check("metadata: บอกว่ายังไม่บันทึกการแก้ไข", m["is_dirty"] is False)

# ===========================================================================
section("[6] execute_blender_script — รันโค้ด + ด่านความปลอดภัย")
fake_bpy.reset()
r = ok("execute_blender_script", code="result = 6 * 7\nprint('สวัสดีจาก Blender')")
check("รันโค้ดสำเร็จ", r["ok"] is True)
check("คืนค่าจากตัวแปร result", r["result"] == 42, str(r.get("result")))
check("เก็บ stdout ที่พิมพ์ออกมาได้", "สวัสดีจาก Blender" in r["stdout"], r["stdout"])

r = ok("execute_blender_script",
       code="import bpy\nresult = [o.name for o in bpy.data.objects]")
check("เข้าถึง bpy ได้", "Cube" in r["result"], str(r.get("result")))

r = ok("execute_blender_script",
       code="import math\nresult = round(math.degrees(math.pi/2), 1)")
check("ใช้ math ได้ (จำเป็นสำหรับงาน 3D)", r["result"] == 90.0, str(r.get("result")))

r = ok("execute_blender_script", code="result = 1/0")
check("โค้ดพัง → คืน error ไม่ทำให้ Blender ตาย", r["ok"] is False and "ZeroDivision" in r["error"],
      str(r.get("error")))
check("มี traceback ให้ตามแก้", "traceback" in r and "ZeroDivisionError" in r["traceback"])
check("Blender ยังอยู่ (ฉากยังอ่านได้)", ok("get_scene_hierarchy")["totals"]["objects"] == 4)

r = ok("execute_blender_script", code="result = undefined_name")
check("ใช้ชื่อที่ไม่มี → จับ error ได้", r["ok"] is False and "NameError" in r["error"], str(r.get("error")))

# --- ด่านความปลอดภัย ---
guards = [
    ("import os\nresult = os.listdir('.')", "ห้าม import 'os'", "อ่านไฟล์ทั้งเครื่อง"),
    ("import subprocess\nresult = 1", "ห้าม import 'subprocess'", "เรียกโปรแกรมอื่น"),
    ("result = open('secret.txt').read()", "ห้ามเรียก 'open()'", "อ่านไฟล์"),
    ("result = eval('1+1')", "ห้ามเรียก 'eval()'", "รันโค้ดที่ซ่อนมา"),
    ("result = (1).__class__.__bases__", "attribute พิเศษ", "ทางหลบหนี sandbox"),
    ("bpy.ops.wm.quit_blender()", "quit_blender", "ปิด Blender ทิ้งงานที่ทำอยู่"),
    ("import sys\nresult = sys.exit(0)", "ห้าม import 'sys'", "ปิดโปรเซส"),
]
for code, expect, why in guards:
    # โค้ดที่ฝ่าด่านจะถูก "ปฏิเสธ" → handle_message คืน ok=False (ไม่ใช่ ok=True)
    r = call("execute_blender_script", code=code)
    check(f"ด่านกันได้: {why}", r["ok"] is False and expect in r["error"],
          f"คาดว่าเจอ '{expect}' แต่ได้: {str(r.get('error'))[:120]}")

r = ok("execute_blender_script", code="result = 40 + 2")
check("งานที่ปลอดภัยยังผ่านได้ตามปกติ", r["ok"] is True and r["result"] == 42)

g = br.scan_code("import os")
check("scan_code แยก 'ละเมิด' ออกจาก 'เตือน'", len(g.violations) == 1 and isinstance(g.warnings, list))
g = br.scan_code("bpy.ops.wm.save_mainfile()")
check("งานที่แค่ 'น่าสงสัย' → เตือน ไม่บล็อก",
      not g.violations and any("บันทึกทับ" in w for w in g.warnings), str(g.warnings))
g = br.scan_code("result = = 1")
check("ไวยากรณ์ผิด → รายงานบรรทัด", g.violations and "ไวยากรณ์" in g.violations[0], str(g.violations))
g = br.scan_code("")
check("โค้ดว่าง → ปฏิเสธ", g.violations == ["โค้ดว่าง"], str(g.violations))

r = ok("execute_blender_script", code="import os\nresult = os.getcwd()", allow_unsafe=True)
check("allow_unsafe=true ข้ามด่านได้ (ตามที่ผู้ใช้สั่ง)",
      r["ok"] is True and r.get("warnings"), str(r.get("warnings")))

# ===========================================================================
section("[7] โปรโตคอล — handle_message")
r = br.handle_message({"id": 7, "method": "ping"})
check("ping → pong + เลขโปรโตคอล", r["ok"] and r["result"]["pong"] and r["result"]["protocol"] == 1,
      str(r))
r = br.handle_message({"id": 8, "method": "hello"})
check("hello → บอกเวอร์ชัน Blender", r["ok"] and r["result"]["blender"] == "5.2.0", str(r))
check("hello → บอกว่ารันแบบ background", r["result"]["background"] is True)

r = br.handle_message({"id": 9, "method": "list_tools"})
names = [t["name"] for t in r["result"]]
check("list_tools → 8 เครื่องมือ", len(names) == 8, str(names))
for want in ("get_scene_hierarchy", "add_primitive_mesh", "modify_object_transform",
             "execute_blender_script"):
    check(f"มีเครื่องมือบังคับ: {want}", want in names)
check("ทุกเครื่องมือมีคำอธิบายให้ AI อ่าน",
      all(len(t["description"]) > 30 for t in r["result"]))

r = br.handle_message({"id": 10, "method": "ไม่มีคำสั่งนี้"})
check("คำสั่งที่ไม่รู้จัก → error ชัดเจน", r["ok"] is False and "ไม่รู้จักคำสั่ง" in r["error"])
r = br.handle_message({"id": 11, "method": "call_tool", "params": {"name": "มั่ว"}})
check("เครื่องมือที่ไม่รู้จัก → บอกว่ามีอะไรบ้าง",
      r["ok"] is False and "get_scene_hierarchy" in r["error"], r.get("error"))
r = br.handle_message({"id": 12, "method": "call_tool",
                       "params": {"name": "get_scene_hierarchy", "arguments": "ไม่ใช่ dict"}})
check("arguments ผิดชนิด → error_type='arguments'", r.get("error_type") == "arguments", str(r))
check("ทุกคำตอบมี id กลับมาด้วย", all(br.handle_message({"id": i, "method": "ping"})["id"] == i
                                    for i in (1, 99, "x")))

# ===========================================================================
section("[8] ความทนทาน — bridge ต้องไม่ทำให้ Blender ตาย")
fake_bpy.reset()
r = br.handle_message({"id": 1, "method": "call_tool",
                       "params": {"name": "get_object_details", "arguments": {"name": "ไม่มี"}}})
check("เรียกเครื่องมือกับวัตถุที่ไม่มี → error ไม่ใช่ crash", r["ok"] is False)
r = br.handle_message({"id": 2, "method": "call_tool",
                       "params": {"name": "get_scene_hierarchy", "arguments": {}}})
check("เรียกซ้ำหลัง error ยังทำงานปกติ", r["ok"] is True, str(r)[:120])
check("จำนวนเครื่องมือคงที่ ไม่สะสมซ้ำ",
      len(br.handle_message({"id": 3, "method": "list_tools"})["result"]) == 8)

r = br.handle_message({"id": 4, "method": "call_tool",
                       "params": {"name": "get_scene_hierarchy",
                                  "arguments": {"max_objects": "ไม่ใช่ตัวเลข"}}})
check("ส่งชนิดข้อมูลผิด → จับได้ ไม่ล้มทั้ง bridge",
      r["ok"] is False or isinstance(r.get("result"), dict), str(r)[:160])

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
