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
1. ดูรูปที่ผู้ใช้แนบ → วัด **สัดส่วน** (สูงกี่หัว · ไหล่กว้างกี่เท่าหัว · แขน/ขายาวเท่าไร)
   และ **สีหลัก** (ผิว/เสื้อ/กางเกง/ผม)
   💡 วัดจากพิกเซลได้แม่นกว่าเดาด้วยตา: หา "ความสูงรวม" → หา "คอ" (แถวที่แคบสุดช่วงบน)
   → ได้จำนวนหัว = ความสูงรวม ÷ ความสูงหัว · หา "เป้า" จากแถวที่ภาพแยกเป็น 2 ช่วง
2. แก้ค่าใน ``CHARACTER`` ข้างล่างให้ตรงกับที่วัดได้ (ตัวอย่างสเปกจริงอยู่ใน ``docs/03``)
3. ส่งสคริปต์นี้เข้า ``execute_blender_script``
4. เรียก ``get_viewport_screenshot`` เพื่อดูผล เทียบกับรูปต้นแบบ ปรับค่า แล้วทำซ้ำ

**รับประกันเรื่องสัดส่วน:** ส่วนสูงรวมที่ได้จะเท่ากับ ``height_m`` **เสมอ** ไม่ว่า
``heads_tall`` จะเป็นเท่าไร และจำนวนหัวที่ทับได้จะตรงกับ ``heads_tall`` **เสมอ**
(หัวมาจากการหารตรง ๆ ส่วนที่เหลือแบ่งตามส่วนแบ่ง) — ลด ``heads_tall`` = หัวโตขึ้น
โดยส่วนสูงไม่เปลี่ยน

สวิตช์เปิด/ปิดชิ้นส่วน (ทำตัวละครได้ทั้งแบบมนุษย์ ใส่ชุดเต็ม และแบบตุ๊กตาหัวโล้น):
``pose`` (stand/tpose) · ``shirt`` · ``pants`` · ``hair`` · ``face`` (ตา) · ``belt``
(เข็มขัด+ผ้าเตี่ยว) · ``feet`` (เท้า)
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
    "arm_length_heads": 3.0,        # ความยาวแขน = กี่เท่าของความสูงหัว
    "leg_length_heads": 3.8,        # ส่วนแบ่งความยาวขา (ยิ่งมาก = ขายิ่งยาว)
    "body_depth_heads": 0.8,        # ความหนาลำตัว
    # ท่า: "stand" = แขนห้อยข้างลำตัว · "tpose" = แขนกางตรงแนวนอน (เหมือนรูปเรนเดอร์ 3D)
    "pose": "stand",
    # ใส่เสื้อ/กางเกงไหม (ปิด = ใช้สีผิว → ตัวเปลือยแบบรูปเรนเดอร์)
    "shirt": True,
    "pants": True,
    # ชิ้นส่วนเสริม (เปิดเท่าที่รูปมี — ปิดไว้ = ไม่สร้าง ไม่กินโพลี)
    "hair": True,              # ผมบนหัว (ปิด = หัวโล้น)
    "face": False,             # ตา 2 ข้าง (กล่องดำเล็ก ๆ บนใบหน้า)
    "belt": False,             # เข็มขัด + ผ้าเตี่ยว
    "feet": False,             # เท้า (ทรงลิ่ม)
    # สีหลักที่อ่านจากรูป (r,g,b ตั้งแต่ 0..1)
    "color_skin": (0.95, 0.76, 0.65),
    "color_shirt": (0.20, 0.45, 0.85),
    "color_pants": (0.15, 0.15, 0.20),
    "color_hair": (0.10, 0.08, 0.07),
    "color_eye": (0.10, 0.08, 0.07),
    "color_belt": (0.44, 0.25, 0.13),
    "color_cloth": (0.49, 0.32, 0.16),
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
TORSO_C = CHARACTER["color_shirt"] if CHARACTER["shirt"] else CHARACTER["color_skin"]
LEG_C = CHARACTER["color_pants"] if CHARACTER["pants"] else CHARACTER["color_skin"]


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


def add_box(name, size_xyz, location, color, collection, rotate=None):
    """ส่วนที่เป็นกล่อง (สะโพก/ลำตัว/คอ/หัว/ผม/ตา/เข็มขัด/เท้า)"""
    rot = [math.radians(r) for r in (rotate or (0.0, 0.0, 0.0))]
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rot, align="WORLD")
    return grab_last(name, size_xyz, color, collection)


def add_round(name, size_xyz, location, color, collection, rotate=None, sides=16):
    """ส่วนที่เป็นทรงกระบอก (แขน/ขา) · rotate=(0,90,0) = วางแนวนอน (ท่า T)"""
    rot = [math.radians(r) for r in (rotate or (0.0, 0.0, 0.0))]
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=0.5, depth=1.0,
                                        location=location, rotation=rot, align="WORLD")
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
                      (side, 0.0, leg_z), LEG_C, coll))
made.append(add_round(NM + "_leg_R", (WIDTH["limb"], WIDTH["limb"], LEN["leg"]),
                      (-side, 0.0, leg_z), LEG_C, coll))

# --- เท้า (ทรงลิ่ม ยื่นไปข้างหน้า) ---
if CHARACTER["feet"]:
    foot_h = LEN["leg"] * 0.09
    made.append(add_box(NM + "_foot_L", (WIDTH["limb"] * 1.15, HEAD * 0.75, foot_h),
                        (side, -HEAD * 0.18, foot_h / 2.0), LEG_C, coll))
    made.append(add_box(NM + "_foot_R", (WIDTH["limb"] * 1.15, HEAD * 0.75, foot_h),
                        (-side, -HEAD * 0.18, foot_h / 2.0), LEG_C, coll))

# --- สะโพก ---
made.append(add_box(NM + "_hips", (WIDTH["shoulder"] * 0.85, WIDTH["depth"], LEN["hip"]),
                    (0.0, 0.0, LEN["leg"] + LEN["hip"] / 2.0), LEG_C, coll))

# --- เข็มขัด + ผ้าเตี่ยว ---
if CHARACTER["belt"]:
    made.append(add_box(NM + "_belt", (WIDTH["shoulder"] * 0.9, WIDTH["depth"] * 1.1, LEN["hip"] * 0.4),
                        (0.0, 0.0, LEN["leg"] + LEN["hip"] * 0.72), CHARACTER["color_belt"], coll))
    made.append(add_box(NM + "_cloth", (WIDTH["shoulder"] * 0.55, WIDTH["depth"] * 0.3, LEN["hip"] * 1.25),
                        (0.0, -WIDTH["depth"] * 0.55, LEN["leg"] + LEN["hip"] * 0.42),
                        CHARACTER["color_cloth"], coll))

# --- ลำตัว (เสื้อ หรือผิวเปลือย) ---
torso_z = LEN["leg"] + LEN["hip"] + LEN["torso"] / 2.0
made.append(add_box(NM + "_torso", (WIDTH["shoulder"], WIDTH["depth"], LEN["torso"]),
                    (0.0, 0.0, torso_z), TORSO_C, coll))

# --- แขน 2 ข้าง (ห้อยข้างลำตัว หรือกางตรงแนวนอนตามท่า) ---
arm_top = torso_z + LEN["torso"] * 0.32
if CHARACTER["pose"] == "tpose":
    arm_x = WIDTH["shoulder"] / 2.0 + WIDTH["arm"] / 2.0
    arm_rot = (0.0, 90.0, 0.0)                      # หมุนให้ยาวตามแกน X
    arm_z = arm_top
else:
    arm_x = WIDTH["shoulder"] / 2.0 + WIDTH["arm_thick"] * 0.5
    arm_rot = None
    arm_z = arm_top - WIDTH["arm"] / 2.0
made.append(add_round(NM + "_arm_L", (WIDTH["arm_thick"], WIDTH["arm_thick"], WIDTH["arm"]),
                      (arm_x, 0.0, arm_z), CHARACTER["color_skin"], coll, rotate=arm_rot))
made.append(add_round(NM + "_arm_R", (WIDTH["arm_thick"], WIDTH["arm_thick"], WIDTH["arm"]),
                      (-arm_x, 0.0, arm_z), CHARACTER["color_skin"], coll, rotate=arm_rot))

# --- คอ ---
neck_z = LEN["leg"] + LEN["hip"] + LEN["torso"] + LEN["neck"] / 2.0
made.append(add_box(NM + "_neck", (WIDTH["neck_thick"], WIDTH["neck_thick"], LEN["neck"]),
                    (0.0, 0.0, neck_z), CHARACTER["color_skin"], coll))

# --- หัว (+ ผม + ตา) ---
head_z = LEN["leg"] + LEN["hip"] + LEN["torso"] + LEN["neck"] + HEAD / 2.0
made.append(add_box(NM + "_head", (HEAD * 0.8, HEAD * 0.8, HEAD),
                    (0.0, 0.0, head_z), CHARACTER["color_skin"], coll))
if CHARACTER["hair"]:
    made.append(add_box(NM + "_hair", (HEAD * 0.86, HEAD * 0.86, HEAD * 0.35),
                        (0.0, 0.0, head_z + HEAD * 0.35), CHARACTER["color_hair"], coll))
if CHARACTER["face"]:
    eye = (HEAD * 0.16, HEAD * 0.06, HEAD * 0.09)          # กว้าง/ลึก/สูง
    eye_z = head_z + HEAD * 0.12
    eye_y = -HEAD * 0.40                                    # -Y = ด้านหน้า
    made.append(add_box(NM + "_eye_L", eye, (HEAD * 0.19, eye_y, eye_z),
                        CHARACTER["color_eye"], coll))
    made.append(add_box(NM + "_eye_R", eye, (-HEAD * 0.19, eye_y, eye_z),
                        CHARACTER["color_eye"], coll))

# ---------------------------------------------------------------------------
# 5) สรุปผล — ให้ AI ตรวจสอบได้เองโดยไม่ต้องเดา
# ---------------------------------------------------------------------------
total_height = LEN["leg"] + LEN["hip"] + LEN["torso"] + LEN["neck"] + HEAD
arm_span_m = (WIDTH["shoulder"] + 2.0 * WIDTH["arm"]) if CHARACTER["pose"] == "tpose" \
    else WIDTH["shoulder"]
result = {
    "name": NM,
    "collection": coll.name,
    "parts": made,
    "part_count": len(made),
    "pose": CHARACTER["pose"],
    "height_m": round(total_height, 4),
    "height_heads": round(total_height / HEAD, 2),
    "head_m": round(HEAD, 4),
    # ค่าเทียบกับ "ความสูงรวม" — ไว้เทียบกับที่วัดจากรูปได้ตรง ๆ (1.0 = ความสูงรวม)
    "ratios": {
        "head_h": round(HEAD / total_height, 3),
        "arm_span": round(arm_span_m / total_height, 3),
        "shoulder_w": round(WIDTH["shoulder"] / total_height, 3),
        "torso_len": round(LEN["torso"] / total_height, 3),
        "leg_len": round(LEN["leg"] / total_height, 3),
        # "เป้า" ที่มองเห็นในภาพ = ยอดของขา (จุดที่เงาแยกเป็น 2 ช่วง) — ไม่ใช่ยอดสะโพก
        "crotch_z": round(LEN["leg"] / total_height, 3),
    },
    "note": "blockout จากสัดส่วน — ขั้นต่อไปปรับรายละเอียดหรือปั้นต่อได้",
}
print("[character_blockout] สร้างแล้ว", result["part_count"], "ชิ้น · สูง",
      result["height_m"], "ม. ·", result["height_heads"], "หัว · หัวสูง", result["head_m"], "ม.")
