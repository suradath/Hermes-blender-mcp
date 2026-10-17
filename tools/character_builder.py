# -*- coding: utf-8 -*-
"""
character_builder.py — สร้างตัวละคร "ละเอียด" (low-poly แบบลบมุม) จากสเปกเดียวกับ blockout
============================================================================================
ต่างจาก ``examples/character_blockout.py`` ตรงที่:
  · ทุกชิ้น **ลบมุม** (chamfer) → ได้ลุคเหลี่ยมแบบงานเรนเดอร์ low-poly ไม่ใช่หุ่นกล่องทื่อ
  · แขน/ขาเป็น **แท่งแปดเหลี่ยม** ไม่ใช่กล่อง
  · มีรายละเอียด: ตา 2 ข้าง · จมูก · หู 2 ข้าง · มือถุงมือมีนิ้วโป้ง · เท้า+ปลายเท้า
    · เข็มขัด + ผ้าเตี่ยวหน้า + แผงข้าง 2 ข้าง · หัวไหล่ 2 ข้าง
  · สร้างเป็น "ข้อมูลเมช" ล้วน → **ตรวจสอบได้ทุกชิ้น** (ปิดสนิท/หันหน้าออก/ปริมาตรถูก)
    แล้วส่งออกเป็น ``.obj`` (+``.mtl``) ให้ Blender นำเข้าด้วยคำสั่งเดียว

ใช้
--
    python tools/character_builder.py --out-dir out                 # สร้าง obj + เรนเดอร์ 2 มุม
    python tools/character_builder.py --set '{"height_m":1.6}' --render 3q.png --rot-z 35

ตัวอย่างสเปกสำหรับรูปตัวละครที่แนบ (วัดจากพิกเซล)::

    --set '{"heads_tall":3.04,"shoulder_width_heads":0.85,"arm_length_heads":0.95,
            "leg_length_heads":2.2,"pose":"tpose","shirt":false,"pants":false,
            "hair":false,"face":true,"belt":true,"feet":true}'

จากนั้นใน Blender::

    bpy.ops.wm.obj_import(filepath="out/character.obj")   # แทนได้: import_scene.obj
    bpy.ops.object.shade_flat()                            # ลุค low-poly (เหลี่ยม)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mesh_lib as ml                                              # noqa: E402

# ---------------------------------------------------------------------------
# สเปก (คีย์เดียวกับ examples/character_blockout.py + ส่วน "detail")
# ---------------------------------------------------------------------------
SPEC = {
    "name": "Detailed",
    "height_m": 1.70,
    "heads_tall": 7.5,
    "shoulder_width_heads": 1.7,
    "arm_length_heads": 3.0,
    "leg_length_heads": 3.8,
    "body_depth_heads": 0.8,
    "pose": "stand",
    "shirt": True,
    "pants": True,
    "hair": True,
    "face": False,
    "belt": False,
    "feet": False,
    "colors": {
        "skin": (0.88, 0.69, 0.50),
        "shirt": (0.20, 0.45, 0.85),
        "pants": (0.15, 0.15, 0.20),
        "hair": (0.10, 0.08, 0.07),
        "eye": (0.08, 0.07, 0.06),
        "belt": (0.30, 0.17, 0.09),
        "cloth": (0.45, 0.29, 0.15),
    },
    "detail": {
        "limb_thick_heads": 0.70,   # ความหนาแขน/ขา (เท่าความสูงหัว) · ตัวการ์ตูนหัวโตใช้ ~0.50
        "chamfer": 0.16,        # สัดส่วนการลบมุม (เทียบกับความสูงหัว) · 0 = กล่องทื่อ
        "limb_sides": 8,        # จำนวนด้านของแขน/ขา (8 = เหลี่ยมสวย · 4 = หยาบมาก)
        "ears": True,
        "nose": True,
        "thumbs": True,
        "leg_gap_ratio": 1.00,      # ตำแหน่งขา = รัศมีขา × ค่านี้ (1.0 = ขาชิดกันพอดี ตามที่วัดจากรูป)
        "loincloth_panels": True,
        "deltoids": True,       # หัวไหล่ (ทำให้ช่วงไหล่ดูเป็นธรรมชาติขึ้น)
    },
}


def derive(spec):
    """คำนวณขนาดทุกช่วงจากสเปก (หลักเดียวกับ blockout: หัวตรงจาก heads_tall ที่เหลือแบ่งตามส่วน)"""
    H = float(spec["height_m"])
    heads = float(spec["heads_tall"])
    HEAD = H / heads
    BODY = H - HEAD
    share = {"leg": float(spec["leg_length_heads"]), "hip": 1.0, "torso": 2.6, "neck": 0.3}
    tot = sum(share.values())
    LEN = {k: BODY * v / tot for k, v in share.items()}
    W = {
        "shoulder": float(spec["shoulder_width_heads"]) * HEAD,
        "depth": float(spec["body_depth_heads"]) * HEAD,
        "arm": float(spec["arm_length_heads"]) * HEAD,
        "limb": HEAD * float(spec["detail"].get("limb_thick_heads", 0.70)),
        "arm_thick": HEAD * 0.46,
        "neck_thick": HEAD * 0.60,      # คอสั้นหนาแบบตัวการ์ตูน (คนจริงใช้ราว 0.46)
    }
    return {"H": H, "HEAD": HEAD, "LEN": LEN, "W": W}


# ---------------------------------------------------------------------------
# ประกอบตัวละคร
# ---------------------------------------------------------------------------
def build(spec):
    """คืน (รายการชิ้นส่วน, ข้อมูลสเปกที่คำนวณแล้ว) · ชิ้นส่วน = (ชื่อ, (verts, faces), วัสดุ)"""
    d = derive(spec)
    HEAD, LEN, W = d["HEAD"], d["LEN"], d["W"]
    det = spec["detail"]
    C = spec["colors"]
    ch = float(det["chamfer"]) * HEAD                     # ขนาดลบมุมจริง (เมตร)
    sides = int(det["limb_sides"])
    M = {k: ml.mat(k, v) for k, v in C.items()}
    skin = M["skin"] if not spec.get("shirt") else ml.mat("shirt", C["shirt"])
    legm = M["skin"] if not spec.get("pants") else ml.mat("pants", C["pants"])

    leg_z = LEN["leg"]
    hip_z = leg_z + LEN["hip"]
    torso_z = hip_z + LEN["torso"]
    neck_z = torso_z + LEN["neck"]
    head_z = neck_z + HEAD
    # ⚠️ ต้องอิง "ความหนาขา" ไม่ใช่ความกว้างไหล่ — ถ้าใช้ไหล่ ขาทั้งสองจะทับกันตรงกลาง
    # ระยะจากกลางตัวถึงกลางขา = "รัศมีขา" × ค่า (1.0 = ขาชิดกันพอดี ตรงกับที่วัดจากรูป 0.332H)
    side = (W["limb"] / 2.0) * float(det["leg_gap_ratio"])
    parts = []

    def add(name, part, mat):
        parts.append((name, part, mat))

    # ── ขา + เท้า + ปลายเท้า ──
    for s, tag in ((1, "L"), (-1, "R")):
        # ปลายล่าง = ข้อเท้า (ผอม) · ปลายบน = ต้นขา (หนา) — อย่าสลับ ไม่งั้นขาจะคว่ำ
        add(f"leg_{tag}", ml.tapered_prism(sides, W["limb"] * 0.62, W["limb"], LEN["leg"],
                                           (s * side, 0.0, leg_z / 2), chamfer=ch * 0.55), legm)
        if spec.get("feet"):
            fh = LEN["leg"] * 0.11
            fr = W["limb"] / 2.0                                  # รัศมีขา
            add(f"foot_{tag}", ml.chamfered_box(fr * 0.78, HEAD * 0.40, fh / 2, ch * 0.5,
                                                (s * side, -HEAD * 0.10, fh / 2)), legm)
            add(f"toe_{tag}", ml.chamfered_box(fr * 0.70, HEAD * 0.19, fh * 0.32, ch * 0.4,
                                               (s * side, -HEAD * 0.35, fh * 0.32)), legm)

    # ── สะโพก ──
    add("hips", ml.chamfered_box(W["shoulder"] * 0.44, W["depth"] / 2, LEN["hip"] / 2, ch,
                                 (0.0, 0.0, leg_z + LEN["hip"] / 2)), legm)

    # ── เข็มขัด + ผ้าเตี่ยว (หน้า + แผงข้าง) ──
    if spec.get("belt"):
        bh = LEN["hip"] * 0.34
        add("belt", ml.chamfered_box(W["shoulder"] * 0.47, W["depth"] * 0.56, bh / 2, ch * 0.6,
                                     (0.0, 0.0, leg_z + LEN["hip"] * 0.80)), M["belt"])
        cw = W["shoulder"] * 0.30
        add("cloth_front", ml.chamfered_box(cw / 2, W["depth"] * 0.17, LEN["hip"] * 0.72, ch * 0.6,
                                            (0.0, -W["depth"] * 0.58, leg_z + LEN["hip"] * 0.36)),
            M["cloth"])
        if det["loincloth_panels"]:
            for s, tag in ((1, "L"), (-1, "R")):
                add(f"cloth_side_{tag}",
                    ml.chamfered_box(W["depth"] * 0.16, W["depth"] * 0.40, LEN["hip"] * 0.52,
                                     ch * 0.5,
                                     (s * W["shoulder"] * 0.46, 0.0, leg_z + LEN["hip"] * 0.50)),
                    M["cloth"])

    # ── ลำตัว + หัวไหล่ ──
    add("torso", ml.chamfered_frustum((W["shoulder"] * 0.84, W["depth"] * 0.88),
                                      (W["shoulder"], W["depth"]), LEN["torso"], ch,
                                      (0.0, 0.0, torso_z - LEN["torso"] / 2)), skin)
    if det["deltoids"]:
        for s, tag in ((1, "L"), (-1, "R")):
            add(f"deltoid_{tag}",
                ml.chamfered_box(W["arm_thick"] * 0.68, W["arm_thick"] * 0.68,
                                 W["arm_thick"] * 0.68, ch * 0.5,
                                 (s * (W["shoulder"] / 2 - W["arm_thick"] * 0.15), 0.0,
                                  torso_z - W["arm_thick"] * 0.55)), skin)

    # ── แขน + มือถุงมือ + นิ้วโป้ง ──
    arm_top = torso_z - LEN["torso"] * 0.18
    # ⚠️ ความยาวแขน = ถึง "ปลายนิ้ว" · มือต้องอยู่ในความยาวนี้ ไม่งั้นช่วงแขนจะเกินสเปก
    hand_len = W["arm_thick"] * 0.72
    arm_span_len = max(W["arm"], hand_len * 1.5)          # กันกรณีสเปกตั้งแขนสั้นกว่ามือ
    arm_len = arm_span_len - hand_len
    hx, hy, hz = hand_len / 2, W["arm_thick"] * 0.38, W["arm_thick"] * 0.44
    if spec["pose"] == "tpose":
        ax = W["shoulder"] / 2 + arm_len / 2
        arm = ml.tapered_prism(sides, W["arm_thick"], W["arm_thick"] * 0.60, arm_len,
                               (ax, 0.0, arm_top), axis="x", chamfer=ch * 0.5)
        hand_c = (W["shoulder"] / 2 + arm_len + hx, 0.0, arm_top)
    else:
        az = arm_top - arm_len / 2
        arm = ml.tapered_prism(sides, W["arm_thick"] * 0.60, W["arm_thick"], arm_len,
                               (W["shoulder"] / 2 + W["arm_thick"] * 0.5, 0.0, az),
                               chamfer=ch * 0.5)
        hand_c = (W["shoulder"] / 2 + W["arm_thick"] * 0.5, 0.0, arm_top - arm_len - hz)
    for s, tag in ((1, "L"), (-1, "R")):
        a = arm if s > 0 else ml.mirror_x(arm)
        add(f"arm_{tag}", a, M["skin"])
        if spec["pose"] == "tpose":
            add(f"hand_{tag}", ml.chamfered_box(hx, hy, hz, ch * 0.5,
                                                (s * hand_c[0], 0.0, hand_c[2])), M["skin"])
            if det["thumbs"]:
                add(f"thumb_{tag}", ml.chamfered_box(hx * 0.42, hy * 0.55, hz * 0.55, ch * 0.35,
                                                     (s * (hand_c[0] - hx * 0.25),
                                                      -hy - hz * 0.20, hand_c[2])), M["skin"])
        else:
            add(f"hand_{tag}", ml.chamfered_box(hx, hy, hz, ch * 0.5,
                                                (s * hand_c[0], 0.0, hand_c[2])), M["skin"])
            if det["thumbs"]:
                add(f"thumb_{tag}", ml.chamfered_box(hz * 0.45, hy * 0.55, hx * 0.42, ch * 0.35,
                                                     (s * (hand_c[0] + hx * 0.5),
                                                      -hy - hz * 0.20, hand_c[2] - hz * 0.25)),
                    M["skin"])

    # ── คอ ──
    # ⚠️ จุดกลางของคอ = torso_z + LEN.neck/2 (ถ้าใส่ neck_z ตรง ๆ คอจะลอยขึ้นไปครึ่งช่วง
    #    เหลือช่องว่างระหว่างคอกับอกให้เห็นชัด)
    add("neck", ml.prism(sides, W["neck_thick"] / 2, LEN["neck"],
                         (0.0, 0.0, torso_z + LEN["neck"] / 2)), M["skin"])

    # ── หัว + ตา + จมูก + หู (+ ผมถ้าเปิด) ──
    hw, hd = HEAD * 0.44, HEAD * 0.47                        # ครึ่งกว้าง/ครึ่งลึก
    add("head", ml.chamfered_frustum((hw * 1.68, hd * 1.66), (hw * 2.0, hd * 2.0), HEAD, ch,
                                     (0.0, 0.0, head_z - HEAD / 2)), M["skin"])
    if spec.get("face"):
        ew, eh = hw * 0.42, HEAD * 0.10
        for s, tag in ((1, "L"), (-1, "R")):
            add(f"eye_{tag}", ml.chamfered_box(ew / 2, hd * 0.14, eh / 2, eh * 0.18,
                                               (s * hw * 0.42, -hd * 0.97,
                                                head_z - HEAD * 0.34)), M["eye"])
        if det["nose"]:
            add("nose", ml.triangular_prism(hw * 0.42, hd * 0.34, HEAD * 0.16,
                                            (0.0, -hd * 1.05, head_z - HEAD * 0.50), axis="y"),
                M["skin"])
    if det["ears"]:
        for s, tag in ((1, "L"), (-1, "R")):
            add(f"ear_{tag}", ml.chamfered_box(hw * 0.22, hd * 0.30, HEAD * 0.16, ch * 0.4,
                                               (s * (hw + hw * 0.20), hd * 0.15,
                                                head_z - HEAD * 0.42)), M["skin"])
    if spec.get("hair"):
        add("hair", ml.chamfered_box(hw * 1.06, hd * 1.06, HEAD * 0.20, ch * 0.7,
                                     (0.0, 0.0, head_z - HEAD * 0.02)), ml.mat("hair", C["hair"]))
    return parts, d


# ---------------------------------------------------------------------------
# สรุปผล / ส่งออก
# ---------------------------------------------------------------------------
def summarize(parts, d):
    rows = [ml.check_part(n, *p) for n, p, _m in parts]
    lo, hi = ml.bbox([v for _n, (vs, _f), _m in parts for v in vs])
    bad = [r["name"] for r in rows
           if not (r["watertight"] and r["outward"] and r["finite"] and not r["duplicate_verts"])]
    return {
        "parts": len(parts),
        "vertices": sum(r["verts"] for r in rows),
        "faces": sum(r["faces"] for r in rows),
        "all_watertight": not bad,
        "bad_parts": bad,
        "size_m": [round(hi[i] - lo[i], 4) for i in range(3)],
        "height_m": round(hi[2] - lo[2], 4),
        "height_heads": round((hi[2] - lo[2]) / d["HEAD"], 2),
        "ratios": {
            "head_h": round(d["HEAD"] / (hi[2] - lo[2]), 3),
            "arm_span": round((hi[0] - lo[0]) / (hi[2] - lo[2]), 3),
            "crotch_z": round((d["LEN"]["leg"]) / (hi[2] - lo[2]), 3),
            "leg_len": round(d["LEN"]["leg"] / (hi[2] - lo[2]), 3),
        },
        "detail": [{"name": r["name"], "verts": r["verts"], "faces": r["faces"],
                    "watertight": r["watertight"]} for r in rows],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="สร้างตัวละคร low-poly ละเอียด (ไม่ต้องใช้ Blender)")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--set", default="", help="ทับค่าสเปกเป็น JSON")
    ap.add_argument("--render", default="", help="ชื่อไฟล์ภาพที่ต้องการ (ใน out-dir)")
    ap.add_argument("--rot-z", type=float, default=0.0, help="หมุนตัว (องศา) เพื่อดูมุม 3/4")
    ap.add_argument("--json", action="store_true", help="พิมพ์สรุปเป็น JSON")
    a = ap.parse_args()

    spec = json.loads(json.dumps(SPEC))                    # คัดลอกลึก
    if a.set.strip():
        ov = json.loads(a.set)
        for k, v in ov.items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k].update(v)
            else:
                spec[k] = v

    parts, d = build(spec)
    rep = summarize(parts, d)
    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = ml.write_obj(out_dir / "character.obj", parts, out_dir / "character.mtl")

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"[character_builder] {rep['parts']} ชิ้น · {rep['vertices']} จุด · {rep['faces']} หน้า")
        print(f"  สูง {rep['height_m']} ม. ({rep['height_heads']} หัว) · ขนาด {rep['size_m']}")
        print(f"  ปิดสนิททุกชิ้น: {rep['all_watertight']}" +
              (f" · ที่ยังไม่ผ่าน: {rep['bad_parts']}" if rep["bad_parts"] else ""))
        print(f"  สัดส่วน: {rep['ratios']}")
        print(f"  ส่งออก: {obj} + {obj.with_suffix('.mtl').name}")

    if a.render:
        import render_flat
        mat_map = {}
        for _n, _p, m in parts:
            mat_map.setdefault(m["name"], m)
        info = render_flat.render(parts, out_dir / a.render, rot_z=a.rot_z)
        print(f"  เรนเดอร์: {out_dir / a.render} ({info['faces_drawn']} หน้า · "
              f"{info['px_per_m']} พิกเซล/เมตร)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
