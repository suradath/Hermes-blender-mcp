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

# ── บทเรียนจาก Blender จริง 5.2.2 ────────────────────────────────────────────
# get_scene_hierarchy เคยพังบน Blender จริงด้วย
#   AttributeError: 'Collection' object has no attribute 'parent'
# เพราะ bpy.types.Collection ไม่มี .parent (ความสัมพันธ์เก็บที่ parent.children)
# และ fake_bpy เคย "ประดิษฐ์" .parent ให้ → เทสต์ผ่านทั้งที่โค้ดพังจริง
props_coll = fake_bpy.data.collections["Props"]
check("คอลเลกชันไม่มี .parent (เหมือน Blender จริง)",
      not hasattr(props_coll, "parent"),
      "fake ต้องไม่เติม .parent — ของจริงไม่มี attribute นี้")
trees_coll = fake_bpy.FakeSceneCollection("trees", parent=props_coll)
fake_bpy.data.collections.add(trees_coll)
h2 = ok("get_scene_hierarchy")
trees = next(c for c in h2["collections"] if c["name"] == "trees")
check("เส้นทางคอลเลกชันซ้อน 2 ชั้นถูก",
      trees["path"] == "Scene Collection/Props/trees", trees["path"])
fake_bpy.data.scenes[0].collection.children.link(trees_coll)   # DAG: อยู่ใต้ 2 ที่
h3 = ok("get_scene_hierarchy")
trees = next(c for c in h3["collections"] if c["name"] == "trees")
check("คอลเลกชันที่ถูก link ใต้ 2 ที่ ไม่ทำให้ค้าง/พัง",
      trees["path"] in ("Scene Collection/trees", "Scene Collection/Props/trees"),
      trees["path"])
fake_bpy.data.scenes[0].collection.children.unlink(trees_coll)
props_coll.children.unlink(trees_coll)
fake_bpy.data.collections.remove(trees_coll)

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
check("list_tools → 12 เครื่องมือ", len(names) == 12, str(names))
for want in ("get_scene_hierarchy", "add_primitive_mesh", "modify_object_transform",
             "execute_blender_script", "get_viewport_screenshot",
             "search_polyhaven", "get_polyhaven_info", "download_polyhaven_asset"):
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
      len(br.handle_message({"id": 3, "method": "list_tools"})["result"]) == 12)

r = br.handle_message({"id": 4, "method": "call_tool",
                       "params": {"name": "get_scene_hierarchy",
                                  "arguments": {"max_objects": "ไม่ใช่ตัวเลข"}}})
check("ส่งชนิดข้อมูลผิด → จับได้ ไม่ล้มทั้ง bridge",
      r["ok"] is False or isinstance(r.get("result"), dict), str(r)[:160])

# ===========================================================================
section("[9] get_viewport_screenshot — ให้ AI 'เห็น' ฉากได้")
# ===========================================================================
import pathlib as _pl  # noqa: E402

fake_bpy.reset()
r = ok("get_viewport_screenshot")
shot = _pl.Path(r["filepath"])
check("คืนที่อยู่ไฟล์รูป", shot.suffix == ".png" and shot.is_file(), r["filepath"])
check("เป็น PNG จริง (ตรวจหัวไฟล์)",
      shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", str(shot.read_bytes()[:8]))
check("โหมด -b เลือก 'render' ให้เอง (ไม่ใช่ viewport ที่ต้องมีหน้าต่าง)",
      r["mode"] == "render", r["mode"])
check("บอกกล้องที่ใช้จริง", r["camera"] == "Camera", str(r["camera"]))
check("บอกขนาดไฟล์/ความละเอียด/เวลา",
      r["bytes"] > 0 and r["resolution"] == [1920, 1080] and "seconds" in r, str(r)[:150])
check("เขียนไฟล์ลงโฟลเดอร์ชั่วคราว (ไม่ทับไฟล์ผู้ใช้)", "view-" in shot.name, shot.name)

sc = fake_bpy.DATA.scenes[0].render
check("⚠️ คืนค่าตั้งการเรนเดอร์เดิมหลังถ่ายภาพ (resolution)",
      sc.resolution_x == 1920 and sc.resolution_y == 1080, f"{sc.resolution_x}x{sc.resolution_y}")
check("⚠️ คืนค่า filepath เดิม (ไม่ทิ้งร่องรอย)", sc.filepath == "", repr(sc.filepath))
check("คืนเปอร์เซ็นต์ความละเอียดเดิม", sc.resolution_percentage == 100)

r = ok("get_viewport_screenshot", width=800, height=600)
check("กำหนดความละเอียดเองได้", r["resolution"] == [800, 600], str(r["resolution"]))
check("รายงานค่าที่ใช้จริง ไม่ใช่ค่าเดิมหลังคืนค่า",
      r["resolution"] != [1920, 1080], "บั๊กที่เคยเกิด: อ่านค่าหลัง restore")

r = ok("get_viewport_screenshot", filepath="/tmp/lpm-test-shot")
check("Blender เติมนามสกุลให้เอง → ตามหาไฟล์เจอ", r["filepath"].endswith(".png"), r["filepath"])
check("ไฟล์ที่ Blender เขียนจริงมีอยู่", _pl.Path(r["filepath"]).is_file())

r = call("get_viewport_screenshot", mode="ไม่ถูกต้อง")
check("mode ที่ไม่รู้จัก → ปฏิเสธแบบ argument error",
      r["ok"] is False and r.get("error_type") == "arguments", str(r)[:150])

r = call("get_viewport_screenshot", mode="viewport")
check("สั่ง viewport ในโหมด -b → บอกให้ชัดว่าทำไม่ได้ พร้อมทางออก",
      r["ok"] is False and "render" in r["error"] and "หน้าต่าง" in r["error"], str(r["error"])[:160])

r = call("get_viewport_screenshot", camera="Light")
check("ระบุวัตถุที่ไม่ใช่กล้อง → ปฏิเสธอย่างสุภาพ",
      r["ok"] is False and "ไม่ใช่กล้อง" in r["error"], str(r)[:160])
check("เรียกซ้ำได้ (ไม่ค้างสถานะ)", ok("get_viewport_screenshot")["bytes"] > 0)

# ไม่มีกล้องในฉาก → ต้องบอกวิธีสร้างกล้อง
fake_bpy.reset()
fake_bpy.DATA.scenes[0].camera = None
fake_bpy.DATA.objects.pop("Camera", None)
r = call("get_viewport_screenshot")
check("ฉากไม่มีกล้อง → บอกว่าต้องมีกล้องก่อน",
      r["ok"] is False and "ไม่มีกล้อง" in r["error"], str(r["error"])[:160])
check("ข้อความแนะนำวิธีสร้างกล้อง", "camera_add" in r["error"], str(r["error"])[:200])

# ===========================================================================
section("[10] คลังฟรี Poly Haven (CC0 · ไม่ต้องใช้คีย์)")
# ===========================================================================
import tempfile as _tf  # noqa: E402

CALLED: list[str] = []
DOWNLOADED: list[tuple[str, str]] = []

FAKE_MODELS = {
    "Chair_A": {"name": "Chair A", "categories": ["furniture"], "tags": ["wood", "chair"],
                "authors": {"Jane D": "All"}, "polycount": 1000, "max_resolution": [4096, 4096]},
    "Barrel_B": {"name": "Barrel B", "categories": ["props"], "tags": ["metal", "barrel"],
                 "authors": {"Som C": "All"}, "polycount": 300},
    "Tree_C": {"name": "Tree C", "categories": ["nature"], "tags": ["tree", "leafy"],
               "authors": {"Ann E": "All"}, "polycount": 5000},
}


def fake_json(url, timeout=30.0):  # noqa: ARG001
    CALLED.append(url)
    if url.endswith("/assets?t=models"):
        return FAKE_MODELS
    if url.endswith("/assets?t=hdris"):
        return {"sky_1": {"name": "Sky One", "categories": ["outdoor"], "tags": ["sky"],
                          "authors": {"Sky Author": "All"}, "max_resolution": [8192, 4096]}}
    if url.endswith("/info/Chair_A"):
        return {"name": "Chair A", "categories": ["furniture"], "authors": {"Jane D": "All"},
                "polycount": 1000, "dimensions": [0.8, 0.8, 1.0]}
    if url.endswith("/files/Chair_A"):
        return {"gltf": {"1k": {"gltf": {"url": "https://dl.example/Chair_A.gltf", "size": 1000,
                                         "include": {"textures/chair_diffuse.jpg":
                                                     {"url": "https://dl.example/cd.jpg", "size": 10}}}}},
                "Diffuse": {"1k": {"jpg": {"url": "https://dl.example/chair_d.jpg", "size": 20,
                                           "include": {"textures/d.jpg":
                                                       {"url": "https://dl.example/d.jpg", "size": 5}}}}},
                "blend": {"1k": {"blend": {"url": "https://dl.example/x.blend", "size": 900,
                                           "include": {}}}}}
    if url.endswith("/files/sky_1"):
        return {"hdri": {"1k": {"hdr": {"url": "https://dl.example/sky_1_1k.hdr",
                                        "size": 500, "md5": "abc"},
                                 "exr": {"url": "https://dl.example/sky_1_1k.exr",
                                         "size": 900, "md5": "def"}},
                         "16k": {"hdr": {"url": "https://dl.example/sky_16k.hdr",
                                         "size": 377_000_000, "md5": "ghi"}}}}
    raise AssertionError("เครื่องมือเรียก URL ที่ไม่คาดคิด: " + url)


def fake_download(url, dest, max_bytes):
    if max_bytes < 100:
        raise br.ToolError("ไฟล์ใหญ่ 999 MB เกินเพดาน 0 MB")
    if dest.is_file():
        return dest.stat().st_size, False          # แคช
    DOWNLOADED.append((url, str(dest)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"x" * 20)
    return 20, True


_REAL_HTTP_JSON, _REAL_HTTP_DL = br._http_json, br._http_download   # เก็บของจริงไว้
br._http_json = fake_json
br._http_download = fake_download
br._PH_LIST_CACHE.clear()
fake_bpy.reset()

r = ok("search_polyhaven", query="chair")
check("ค้นเจอเฉพาะที่ตรงคำ", [a["id"] for a in r["assets"]] == ["Chair_A"], str(r["assets"]))
check("ค้นแบบไม่สนตัวพิมพ์ใหญ่เล็ก",
      [a["id"] for a in ok("search_polyhaven", query="CHAIR")["assets"]] == ["Chair_A"])
check("ค้นเจอจาก tag ได้ด้วย",
      [a["id"] for a in ok("search_polyhaven", query="leafy")["assets"]] == ["Tree_C"])
check("บอกจำนวนที่ตรงทั้งหมด", r["total_matching"] == 1, str(r["total_matching"]))
check("บอกสัญญาอนุญาต CC0 ชัดเจน", "CC0" in r["licence"], r["licence"])

r = ok("search_polyhaven")
check("ไม่ใส่คำค้น → ได้ทั้งหมด", r["total_matching"] == 3, str(r["total_matching"]))
check("เรียงชิ้นที่โพลีน้อยก่อน (ไฟล์เบาก่อน)",
      [a["id"] for a in r["assets"]][:2] == ["Barrel_B", "Chair_A"],
      str([a["id"] for a in r["assets"]]))
check("limit ทำงาน", len(ok("search_polyhaven", limit=2)["assets"]) == 2)
check("กรองตามหมวดได้",
      [a["id"] for a in ok("search_polyhaven", categories="nature")["assets"]] == ["Tree_C"])
check("ค้นชนิดอื่นได้ (hdris)", ok("search_polyhaven", asset_type="hdris")["asset_type"] == "hdris")
r = call("search_polyhaven", asset_type="ไม่รู้จัก")
check("ชนิดที่ไม่รู้จัก → ปฏิเสธพร้อมบอกค่าที่ใช้ได้",
      r["ok"] is False and "hdris" in r["error"], str(r["error"])[:140])
check("แคชรายการไว้ (เรียก /assets?t=models ครั้งเดียวเท่านั้น)",
      sum(1 for u in CALLED if u.endswith("/assets?t=models")) == 1,
      str([u for u in CALLED if "assets" in u]))

r = ok("get_polyhaven_info", asset_id="Chair_A")
check("info: บอกชื่อ/หมวด/ผู้สร้าง", r["name"] == "Chair A" and r["authors"] == ["Jane D"],
      str(r)[:120])
check("info: บอกจำนวนโพลีโกนและขนาด", r["polycount"] == 1000 and r["dimensions"] is not None)
check("info: บอกความละเอียดที่มีให้เลือก", "1k" in r["available"]["gltf"],
      str(list(r["available"]["gltf"])))
check("info: บอกรูปแบบทั้งหมดที่มี", {"gltf", "blend", "Diffuse"} <= set(r["available"]),
      str(list(r["available"])))
check("info: บอกขนาดไฟล์ให้ตัดสินใจได้ (ไม่ต้องดาวน์โหลดก่อน)",
      r["available"]["gltf"]["1k"].get("gltf") == 1000, str(r["available"]["gltf"]))

with _tf.TemporaryDirectory() as td:
    DOWNLOADED.clear()
    r = ok("download_polyhaven_asset", asset_id="Chair_A", kind="gltf", resolution="1k",
           target_dir=td, apply=True)
    check("ดาวน์โหลดไฟล์หลัก", any("Chair_A.gltf" in u for u, _ in DOWNLOADED), str(DOWNLOADED))
    check("⚠️ ดึงไฟล์เท็กซ์เจอร์ที่ต้องใช้คู่กันด้วย (include)",
          any("cd.jpg" in u for u, _ in DOWNLOADED), str(DOWNLOADED))
    check("วางไฟล์เท็กซ์เจอร์ตามพาธสัมพัทธ์เดิม (ให้โมเดลอ้างถึงได้)",
          pathlib.Path(td, "textures", "chair_diffuse.jpg").is_file(),
          str(sorted(str(x) for x in pathlib.Path(td).rglob("*"))))
    check("นำเข้าโมเดลเข้าฉากจริง + บอกชื่อวัตถุใหม่",
          r["applied"] == "imported" and r["object_count"] == 2, str(r)[:160])
    check("บอกสัญญาอนุญาต CC0", "CC0" in r["licence"])
    check("เรียกซ้ำใช้แคช (ไม่ดาวน์โหลดซ้ำ)",
          ok("download_polyhaven_asset", asset_id="Chair_A", kind="gltf",
             target_dir=td)["reused_from_cache"] >= 1)

    DOWNLOADED.clear()
    r = ok("download_polyhaven_asset", asset_id="Chair_A", kind="Diffuse", resolution="1k",
           target_dir=td, apply=True, texture_map="diffuse")
    check("เท็กซ์เจอร์ → สร้างวัสดุและผูก Base Color",
          r["applied"] == "material" and r["material"].startswith("PH_Chair_A"), str(r)[:160])
    check("เลือกแผนที่ตามชื่อที่สั่ง", "d.jpg" in r["map_used"], r["map_used"])
    mat = fake_bpy.DATA.materials[r["material"]]
    check("เชื่อมโหนดรูปเข้ากับ Base Color จริง (1 เส้น)",
          len(mat.node_tree.links.connections) == 1, str(mat.node_tree.links.connections))

    r = ok("download_polyhaven_asset", asset_id="sky_1", kind="hdri", resolution="1k",
           target_dir=td, apply=True)
    check("HDRI → ตั้งเป็น world ให้ฉาก", r["applied"] == "world", str(r)[:150])
    check("เลือก .hdr เป็นปริยาย (ไฟล์เล็กกว่า exr)", r["main_file"].endswith(".hdr"), r["main_file"])
    world = fake_bpy.DATA.scenes[0].world
    check("world เปิด use_nodes และต่อ Environment Texture → Background",
          world.use_nodes and len(world.node_tree.links.connections) == 1,
          str(world.node_tree.links.connections))

    r = call("download_polyhaven_asset", asset_id="sky_1", kind="hdri", resolution="16k",
             target_dir=td, max_mb=10)
    check("ความละเอียดใหญ่เกินเพดาน → ปฏิเสธพร้อมบอกขนาดจริง (377 MB)",
          r["ok"] is False and "377" in r["error"], str(r["error"])[:160])

    r = call("download_polyhaven_asset", asset_id="Chair_A", kind="fbx", target_dir=td)
    check("kind ที่ asset ไม่มี → บอกว่ามีอะไรให้เลือก",
          r["ok"] is False and "gltf" in r["error"], str(r["error"])[:160])

r = call("download_polyhaven_asset", asset_id="", kind="gltf")
check("ไม่ระบุ asset_id → ปฏิเสธ", r["ok"] is False and "asset_id" in r["error"], str(r)[:120])

section("[11] ทดสอบกับ Poly Haven จริง (ข้ามอัตโนมัติถ้าเครือข่ายไม่พร้อม)")
# คืนฟังก์ชันเครือข่ายตัวจริงกลับก่อน (section [10] จำลองไว้)
br._http_json, br._http_download = _REAL_HTTP_JSON, _REAL_HTTP_DL
br._PH_LIST_CACHE.clear()
try:
    real = br._http_json(f"{br.POLYHAVEN_API}/types")
    check("เข้าถึง API จริงได้", "models" in (real or []), str(real)[:120])
    live = ok("search_polyhaven", query="chair", asset_type="models", limit=3)
    check("ค้นของจริงได้ผล", live["total_matching"] > 10, str(live["total_matching"]))
    check("ของจริงมีข้อมูลหมวดติดมาด้วย",
          bool(live["assets"][0].get("categories")), str(live["assets"][0])[:140])
except br.ToolError as exc:
    print(f"    ⏭️  ข้ามการทดสอบออนไลน์: {str(exc)[:110]}")

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
