# -*- coding: utf-8 -*-
"""
character_blockout.py — สร้างตัวละครสามมิติแบบ blockout จาก "สเปก" ที่ AI อ่านจากรูป
====================================================================================

ใช้ได้ 2 ทาง
------------
1. ให้ AI คัดลอกไปส่งในเครื่องมือ ``execute_blender_script`` (ผ่านด่านความปลอดภัยได้
   — เทสต์ของโปรเจกต์ตรวจไว้แล้วว่าโค้ดนี้ไม่มีอะไรที่ด่านห้าม)
2. รันตรง ๆ กับ Blender::

       blender -b ไฟล์.blend --python examples/character_blockout.py

⚠️ ความจริงที่ต้องเข้าใจก่อนใช้
------------------------------
นี่คือ **blockout** = ร่างด้วยรูปทรงพื้นฐาน (กล่อง/ทรงกระบอก) ตามสัดส่วนที่วัดจากรูป
**ไม่ใช่** การปั้นโมเดลละเอียดจากรูปอัตโนมัติ (แบบนั้นต้องใช้บริการ image-to-3D ภายนอก)
แต่ blockout ใช้ตั้งต้นงานได้จริง และเป็นวิธีที่คนทำ 3D ใช้กันก่อนลงรายละเอียด

วิธีที่ AI ควรใช้
----------------
1. ดูรูปที่ผู้ใช้แนบ → ประเมิน **สัดส่วน** (สูงกี่หัว · ไหล่กว้างกี่เท่าหัว · ขายาวเท่าไร)
   และ **สีหลัก** (ผิว/เสื้อ/กางเกง/ผม)
2. แก้ค่าใน ``CHARACTER`` ข้างล่างให้ตรงกับที่อ่านได้
3. ส่งสคริปต์นี้เข้า ``execute_blender_script``
4. เรียก ``get_viewport_screenshot`` เพื่อดูผล เทียบกับรูปต้นแบบ ปรับค่า แล้วทำซ้ำ

**รับประกันเรื่องสัดส่วน:** ส่วนสูงรวมที่ได้จะเท่ากับ ``height_m`` **เสมอ** ไม่ว่า
``heads_tall`` จะเป็นเท่าไร (ค่าความยาวของแต่ละชิ้นเป็น "น้ำหนักสัมพัทธ์" แล้วถูกปรับ
ให้รวมได้พอดี) — ลด ``heads_tall`` = หัวโตขึ้น ดูการ์ตูนขึ้น โดยส่วนสูงไม่เปลี่ยน
"""

import bpy
import math

# ---------------------------------------------------------------------------
# 1) สเปกตัวละคร — AI แก้ค่าตรงนี้ตามรูปต้นแบบ
# ---------------------------------------------------------------------------
CHARACTER = {
    "name": "Character",
    "height_m": 1.70,          # ส่วนสูงจริง (เมตร) — ใช้กำหนดขนาดรวม
    # สัดส่วน: จำนวน "หัว" ที่ทับกันได้ทั้งตัว · 7.5 = มนุษย์จริง · 5 = การ์ตูน · 3 = ตุ๊กตา
    "heads_tall": 7.5,
    "shoulder_width_heads": 1.7,    # ความกว้างไหล่ = กี่เท่าของความสูงหัว
    "arm_length_heads": 3.0,
    "leg_length_heads": 3.8,
    "body_depth_heads": 0.8,        # ความหนาลำตัว
    # สีหลักที่อ่านจากรูป (r,g,b ตั้งแต่ 0..1)
    "color_skin": (0.95, 0.76, 0.65),
    "color_shirt": (0.20, 0.45, 0.85),
    "color_pants": (0.15, 0.15, 0.20),
    "color_hair": (0.10, 0.08, 0.07),
    "collection": "Character",
}

# ---------------------------------------------------------------------------
# 2) คำนวณขนาดชิ้นส่วนจากสัดส่วน
# ---------------------------------------------------------------------------
# หลักคิด: ความสูง = "หัว" 1 หัว + "ลำตัวที่เหลือ" (ขา+สะโพก+ลำตัว+คอ)
#   · HEAD มาจาก heads_tall ตรง ๆ → จำนวนหัวที่ทับได้ตรงตามที่สั่งเสมอ
#   · ที่เหลือแบ่งตาม "ส่วนแบ่ง" ข้างล่าง → ผลรวม = ส่วนสูงที่สั่งเสมอ (ไม่คลาดเคลื่อน)
HEAD = CHARACTER["height_m"] / CHARACTER["heads_tall"]        # ความสูงหัว (เมตร)
BODY = CHARACTER["height_m"] - HEAD                           # ความสูงช่วงลำตัวที่เหลือ
SHARE = {"leg": CHARACTER["leg_length_heads"],                # ส่วนแบ่งของแต่ละช่วงลำตัว
         "hip": 1.0, "torso": 2.6, "neck": 0.3}
SHARE_SUM = SHARE["leg"] + SHARE["hip"] + SHARE["torso"] + SHARE["neck"]
LEN = {name: BODY * w / SHARE_SUM for name, w in SHARE.items()}   # ความยาวจริงแต่ละช่วง

WIDTH = {
    "shoulder": CHARACTER["shoulder_width_heads"] * HEAD,
    "depth": CHARACTER["body_depth_heads"] * HEAD,
    "arm": CHARACTER["arm_length_heads"] * HEAD,
    "limb": HEAD * 0.7,          # ความหนาแขน/ขา
    "arm_thick": HEAD * 0.45,
    "neck_thick": HEAD * 0.45,
}
# หมายเหตุ: ความกว้างอิงกับ HEAD (ความสูงหัวจริง) → ตัวการ์ตูนหัวโตจะได้ไหล่/แขนสมส่วน


# ---------------------------------------------------------------------------
# 3) เครื่องมือย่อย (ไม่ใช้ฟีเจอร์ที่ด่านความปลอดภัยห้าม)
# ---------------------------------------------------------------------------
def ensure_collection(name):
    """สร้าง/หาคอลเลกชันสำหรับเก็บชิ้นส่วนตัวละคร"""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def paint(obj, color, collection):
    """ใส่สี + ย้ายเข้าคอลเลกชัน · คืนชื่อวัสดุ"""
    mat_name = "MAT_" + "_".join(str(round(c, 2)) for c in color)
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
            bsdf.inputs["Roughness"].default_value = 0.6
    if obj.data is not None and len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    for coll in list(obj.users_collection):
        if coll is not collection:
            coll.objects.unlink(obj)
    if obj not in collection.objects:
        collection.objects.link(obj)
    return mat.name


def grab_last(name, size_xyz, color, collection):
    """หยิบวัตถุที่ Blender เพิ่งสร้างให้ แล้วตั้งชื่อ/ย่อขนาด/ใส่สี · คืนชื่อวัตถุ"""
    obj = list(bpy.context.scene.collection.objects)[-1]
    obj.name = name
    obj.scale = [s / 2.0 for s in size_xyz]     # primitive size=1 → scale = ครึ่งของขนาด
    paint(obj, color, collection)
    return obj.name


def add_box(name, size_xyz, location, color, collection):
    """ส่วนที่เป็นกล่อง (สะโพก/ลำตัว/คอ/หัว/ผม)"""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location,
                                    rotation=(0.0, 0.0, 0.0), align="WORLD")
    return grab_last(name, size_xyz, color, collection)


def add_round(name, size_xyz, location, color, collection, sides=16):
    """ส่วนที่เป็นทรงกระบอก (แขน/ขา)"""
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=0.5, depth=1.0,
                                        location=location, rotation=(0.0, 0.0, 0.0),
                                        align="WORLD")
    return grab_last(name, size_xyz, color, collection)


# ---------------------------------------------------------------------------
# 4) ประกอบตัวละคร (วัดจากพื้นขึ้นบน เป็นเมตร)
# ---------------------------------------------------------------------------
coll = ensure_collection(CHARACTER["collection"])
made = []
NM = CHARACTER["name"]

# --- ขา 2 ข้าง ยืนตรง ห่างกันเล็กน้อย ---
leg_z = LEN["leg"] / 2.0
side = WIDTH["shoulder"] * 0.22
made.append(add_round(NM + "_leg_L", (WIDTH["limb"], WIDTH["limb"], LEN["leg"]),
                      (side, 0.0, leg_z), CHARACTER["color_pants"], coll))
made.append(add_round(NM + "_leg_R", (WIDTH["limb"], WIDTH["limb"], LEN["leg"]),
                      (-side, 0.0, leg_z), CHARACTER["color_pants"], coll))

# --- สะโพก ---
made.append(add_box(NM + "_hips", (WIDTH["shoulder"] * 0.85, WIDTH["depth"], LEN["hip"]),
                    (0.0, 0.0, LEN["leg"] + LEN["hip"] / 2.0),
                    CHARACTER["color_pants"], coll))

# --- ลำตัว (เสื้อ) ---
torso_z = LEN["leg"] + LEN["hip"] + LEN["torso"] / 2.0
made.append(add_box(NM + "_torso", (WIDTH["shoulder"], WIDTH["depth"], LEN["torso"]),
                    (0.0, 0.0, torso_z), CHARACTER["color_shirt"], coll))

# --- แขน 2 ข้าง ห้อยข้างลำตัว ---
arm_top = torso_z + LEN["torso"] * 0.32
arm_x = WIDTH["shoulder"] / 2.0 + WIDTH["arm_thick"] * 0.5
made.append(add_round(NM + "_arm_L", (WIDTH["arm_thick"], WIDTH["arm_thick"], WIDTH["arm"]),
                      (arm_x, 0.0, arm_top - WIDTH["arm"] / 2.0), CHARACTER["color_skin"], coll))
made.append(add_round(NM + "_arm_R", (WIDTH["arm_thick"], WIDTH["arm_thick"], WIDTH["arm"]),
                      (-arm_x, 0.0, arm_top - WIDTH["arm"] / 2.0), CHARACTER["color_skin"], coll))

# --- คอ ---
neck_z = LEN["leg"] + LEN["hip"] + LEN["torso"] + LEN["neck"] / 2.0
made.append(add_box(NM + "_neck", (WIDTH["neck_thick"], WIDTH["neck_thick"], LEN["neck"]),
                    (0.0, 0.0, neck_z), CHARACTER["color_skin"], coll))

# --- หัว + ผม ---
head_z = LEN["leg"] + LEN["hip"] + LEN["torso"] + LEN["neck"] + HEAD / 2.0
made.append(add_box(NM + "_head", (HEAD * 0.8, HEAD * 0.8, HEAD),
                    (0.0, 0.0, head_z), CHARACTER["color_skin"], coll))
made.append(add_box(NM + "_hair", (HEAD * 0.86, HEAD * 0.86, HEAD * 0.35),
                    (0.0, 0.0, head_z + HEAD * 0.35), CHARACTER["color_hair"], coll))

# ---------------------------------------------------------------------------
# 5) สรุปผล — ให้ AI ตรวจสอบได้เองโดยไม่ต้องเดา
# ---------------------------------------------------------------------------
total_height = LEN["leg"] + LEN["hip"] + LEN["torso"] + LEN["neck"] + HEAD
result = {
    "name": NM,
    "collection": coll.name,
    "parts": made,
    "part_count": len(made),
    "height_m": round(total_height, 4),
    "height_heads": round(total_height / HEAD, 2),
    "head_m": round(HEAD, 4),
    "note": "blockout จากสัดส่วน — ขั้นต่อไปปรับรายละเอียดหรือปั้นต่อได้",
}
print("[character_blockout] สร้างแล้ว", result["part_count"], "ชิ้น · สูง",
      result["height_m"], "ม. ·", result["height_heads"], "หัว · หัวสูง", result["head_m"], "ม.")
