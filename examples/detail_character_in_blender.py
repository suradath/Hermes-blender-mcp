# -*- coding: utf-8 -*-
"""
detail_character_in_blender.py — นำเข้าโมเดลที่สร้างจาก tools/character_builder.py
แล้วแต่งให้ "เนียนแบบ organic low-poly" ด้วย modifier ของ Blender
==============================================================================
ตัวสร้างของเรา (``character_builder.py``) ทำ **รูปทรง** ให้ถูกสัดส่วนและลบมุมแล้ว
แต่ยังเป็นเหลี่ยมแข็ง · สคริปต์นี้คือขั้นตอนที่เปลี่ยนให้ใกล้รูปเรนเดอร์ต้นแบบที่สุด:

  1. Bevel  — เพิ่มเหลี่ยมเล็ก ๆ ที่ทุกขอบ (เหมือนงาน low-poly ที่มือทำ)
  2. Subdivision (ไม่บังคับ) — เพิ่มความเนียนของผิว
  3. Shade Smooth — ให้แสงไล่เนียน (ถ้าอยากได้ลุคเหลี่ยมดิบให้ปิด)

ใช้ได้ 2 ทาง
------------
1. ผ่าน Hermes/เครื่องมือ ``execute_blender_script`` (ผ่านด่านความปลอดภัยแล้ว):
   แก้ ``OBJ_PATH`` ให้ชี้ไปที่ไฟล์ .obj บนเครื่องคุณ แล้วส่งทั้งไฟล์นี้เข้าไป
2. รันตรง ๆ::

       blender -b --python examples/detail_character_in_blender.py

   (แก้ค่าที่หัวไฟล์ก่อน — สคริปต์นี้ตั้งใจไม่รับ argument เพื่อให้วางในแชทได้)
"""

import bpy

# ── แก้ค่าตรงนี้ ────────────────────────────────────────────────────────────
OBJ_PATH = "out/character.obj"     # ไฟล์ที่ได้จาก tools/character_builder.py
BEVEL_WIDTH = 0.010                # ความกว้างรอยลบขอบ (เมตร) · 0 = ไม่ทำ
BEVEL_SEGMENTS = 2                 # 2 = เหลี่ยมกำลังดี · 3-4 = เนียนขึ้นแต่หน้าถี่ขึ้น
SUBDIV_LEVELS = 0                  # 0 = ไม่แบ่ง · 1 = เนียนขึ้น (หน้าคูณ ~4)
SHADE_SMOOTH = False               # False = คงลุคเหลี่ยม low-poly (ตรงต้นแบบกว่า)
JOIN_OBJECTS = False               # True = รวมทุกชิ้นเป็นวัตถุเดียว
# ────────────────────────────────────────────────────────────────────────────

bpy.ops.wm.obj_import(filepath=OBJ_PATH)
imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
if not imported:
    raise RuntimeError("นำเข้าไม่สำเร็จ: ไม่พบวัตถุชนิด MESH — ตรวจ OBJ_PATH อีกครั้ง")

for obj in imported:
    bpy.context.view_layer.objects.active = obj
    if BEVEL_WIDTH > 0:
        mod = obj.modifiers.new("Chamfer", "BEVEL")
        mod.width = BEVEL_WIDTH
        mod.segments = BEVEL_SEGMENTS
        mod.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if SUBDIV_LEVELS > 0:
        sub = obj.modifiers.new("Smooth", "SUBSURF")
        sub.levels = SUBDIV_LEVELS
        sub.render_levels = SUBDIV_LEVELS
        bpy.ops.object.modifier_apply(modifier=sub.name)
    if SHADE_SMOOTH:
        bpy.ops.object.shade_smooth()
    else:
        bpy.ops.object.shade_flat()          # คงลุคเหลี่ยมแบบงาน low-poly

if JOIN_OBJECTS and len(imported) > 1:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.join()
    imported = [bpy.context.view_layer.objects.active]

total_v = sum(len(o.data.vertices) for o in imported)
total_f = sum(len(o.data.polygons) for o in imported)
print("[detail_character] นำเข้า", len(imported), "วัตถุ ·", total_v, "จุด ·", total_f, "หน้า",
      "· bevel", BEVEL_WIDTH, "· subdiv", SUBDIV_LEVELS, "· smooth", SHADE_SMOOTH)
