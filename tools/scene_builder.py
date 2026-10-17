# -*- coding: utf-8 -*-
"""
scene_builder.py — ประกอบทุกอย่างที่สร้างไว้เป็น "ฉากเดียว" (ภาพหมู่)
=====================================================================
ใช้ของที่สร้างเสร็จแล้วทั้งหมด: บ้านทรงไทย · ต้นไม้ 3 ต้น · สุนัข · ตัวละคร
แล้ววางตำแหน่ง/หมุน/ย่อขนาด รวมเป็นฉากเดียว → ส่งออก .obj + เรนเดอร์ภาพหมู่

ทุกชิ้นยัง "ปิดสนิท" หลังการแปลง (ตรวจซ้ำด้วย mesh_lib.check_part) — การย้าย/หมุน/ย่อ
ไม่ทำให้เมชเสีย เว้นแต่สเกลกลับด้าน (ซึ่ง `scale_part` จัดการพลิกหน้าให้แล้ว)

ใช้:
    python tools/scene_builder.py --out-dir out --render scene.png --rot-z 34 --rot-x 15
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mesh_lib as ml                # noqa: E402
import character_builder as cb        # noqa: E402
import thai_house_builder as th       # noqa: E402
import tree_builder as tb             # noqa: E402
import dog_builder as db              # noqa: E402

# ── สเปกฉาก: วางอะไร ที่ไหน หมุนเท่าไร ย่อเท่าไร ──
SCENE = {
    "name": "Village",
    "ground": {"size": (24.5, 20.0), "thickness": 0.16,
               "color": (0.50, 0.57, 0.36)},
    "items": [
        # (ชื่อ, ตำแหน่ง x,y | z อัตโนมัติ, หมุนรอบ Z, ย่อขนาด)
        {"builder": "house", "at": (0.0, 0.4), "rot_z": 0.0, "scale": 1.0,
         "spec": {"stair_handrails": False, "ground": False}},
       
        {"builder": "tree", "at": (-8.6, 2.6), "rot_z": 24.0, "scale": 1.05},
        {"builder": "tree", "at": (7.6, 5.4), "rot_z": 118.0, "scale": 0.88},
        {"builder": "tree", "at": (-8.4, -7.2), "rot_z": 202.0, "scale": 0.62},
        {"builder": "tree", "at": (3.0, 7.4), "rot_z": 300.0, "scale": 0.70},   # ต้นหลังบ้าน เพิ่มมิติ
        {"builder": "dog", "at": (2.4, -7.6), "rot_z": 174.0, "scale": 1.30},
        {"builder": "character", "at": (-3.0, -6.0), "rot_z": 168.0, "scale": 1.15},
    ],
    # สเปกย่อยของแต่ละแบบ (ใช้ค่าเริ่มต้นที่ผ่านการตรวจมาแล้ว)
    "character_spec": {
        "name": "Chibi", "heads_tall": 3.04, "shoulder_width_heads": 0.85,
        "arm_length_heads": 0.95, "leg_length_heads": 2.2, "pose": "tpose",
        "shirt": False, "pants": False, "hair": False, "face": True,
        "belt": True, "feet": True, "detail": {"limb_thick_heads": 0.50},
        "colors": {"skin": (0.88, 0.69, 0.50), "belt": (0.44, 0.25, 0.13),
                   "cloth": (0.49, 0.32, 0.16)},
    },
}


def _make(builder: str, spec_over):
    """สร้างชิ้นส่วนของของแต่ละอย่าง (คืน [(ชื่อ, part, วัสดุ)])"""
    if builder == "house":
        spec = json.loads(json.dumps(th.SPEC))
        for k, v in spec_over.items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k].update(v)
            else:
                spec[k] = v
        return th.build(spec)
    if builder == "tree":
        spec = json.loads(json.dumps(tb.SPEC))
        for k, v in spec_over.items():
            spec[k] = v
        return tb.build(spec)
    if builder == "dog":
        spec = json.loads(json.dumps(db.SPEC))
        for k, v in spec_over.items():
            spec[k] = v
        return db.build(spec)
    if builder == "character":
        spec = json.loads(json.dumps(cb.SPEC))
        for k, v in (spec_over or {}).items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k].update(v)
            else:
                spec[k] = v
        parts, _d = cb.build(spec)
        return parts
    raise ValueError(f"ไม่รู้จัก builder: {builder}")


def build(scene=None):
    scene = scene or SCENE
    g = scene["ground"]
    parts = []
    # ── พื้นดิน ──
    parts.append(("ground", ml.chamfered_box(g["size"][0] / 2, g["size"][1] / 2,
                                             g["thickness"] / 2, 0.0,
                                             (0.0, 0.0, -g["thickness"] / 2)),
                  ml.mat("ground", g["color"])))

    for idx, item in enumerate(scene["items"]):
        kind = item["builder"]
        over = item.get("spec", {})
        if kind == "character" and not over:
            over = scene.get("character_spec", {})
        sub = _make(kind, over)
        # หา z ของฐาน เพื่อให้วาง "บนพื้น" พอดี
        allv = [v for _n, (vs, _f), _m in sub for v in vs]
        lo, _hi = ml.bbox(allv)
        sx, sy = item["at"]
        rot = float(item.get("rot_z", 0.0))
        sc = item.get("scale", 1.0)
        for name, part, mat in sub:
            p = ml.scale_part(part, sc)                      # ย่อ/ขยายก่อน
            p = ml.rotate(p, rz=rot)                          # แล้วหมุน
            p = ml.translate(p, sx, sy, -lo[2] * sc)          # ให้ฐานแตะพื้น z=0
            parts.append((f"{kind}{idx}_{name}", p, mat))
    return parts


def summarize(parts):
    rows = [ml.check_part(n, *p) for n, p, _m in parts]
    lo, hi = ml.bbox([v for _n, (vs, _f), _m in parts for v in vs])
    bad = [r["name"] for r in rows
           if not (r["watertight"] and r["outward"] and r["finite"] and not r["duplicate_verts"])]
    return {"parts": len(parts), "vertices": sum(r["verts"] for r in rows),
            "faces": sum(r["faces"] for r in rows), "all_watertight": not bad,
            "bad_parts": bad[:5], "bad_count": len(bad),
            "size_m": [round(hi[i] - lo[i], 2) for i in range(3)],
            "height_m": round(hi[2] - lo[2], 2),
            "bbox_min": [round(v, 2) for v in lo], "bbox_max": [round(v, 2) for v in hi]}


def main() -> int:
    ap = argparse.ArgumentParser(description="ประกอบฉากภาพหมู่ (ไม่ต้องใช้ Blender)")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--render", default="")
    ap.add_argument("--rot-z", type=float, default=34.0)
    ap.add_argument("--rot-x", type=float, default=15.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    parts = build()
    rep = summarize(parts)
    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = ml.write_obj(out_dir / "scene.obj", parts, out_dir / "scene.mtl")
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"[scene] {rep['parts']} ชิ้น · {rep['vertices']} จุด · {rep['faces']} หน้า · "
              f"ขนาด {rep['size_m'][0]}×{rep['size_m'][1]} ม. · สูง {rep['height_m']} ม.")
        print(f"  ปิดสนิททุกชิ้น: {rep['all_watertight']}" +
              (f" · เสีย {rep['bad_count']} ชิ้น: {rep['bad_parts']}" if rep["bad_count"] else ""))
        print(f"  ส่งออก: {obj}")
    if a.render:
        import render_flat
        # เงาแยกวงตามของแต่ละชิ้น (บ้าน/ต้นไม้/สุนัข/คน) → ดูมีที่ยืนจริง
        groups = {}
        for n, p, m in parts:
            key = n.split("_")[0]
            if key == "ground":
                continue
            groups.setdefault(key, []).append(p)
        boxes = [ml.bbox([v for pr in ps for v in pr[0]]) for ps in groups.values()]
        info = render_flat.render(parts, out_dir / a.render, rot_z=a.rot_z, rot_x=a.rot_x,
                                  width=1240, height=820, shadow=True, gradient=True,
                                  shadow_bbox=boxes, light=(-0.36, -0.62, 0.70),
                                  ambient=0.44, pad_frac=0.04, no_outline_mats=("ground",))
        print(f"  เรนเดอร์: {out_dir / a.render} ({info['faces_drawn']} หน้า)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
