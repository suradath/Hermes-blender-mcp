# -*- coding: utf-8 -*-
"""
thai_house_builder.py — บ้านทรงไทยสไตล์โพลิกอน (low-poly) ที่สร้างจากเรขาคณิตจริง
=================================================================================
องค์ประกอบตามบ้านไทยดั้งเดิม:
  · ยกพื้นสูงบนเสา (ใต้ถุนโปร่ง) · ระเบียงพร้อมราวลูกกรง · บันไดขึ้นหน้าเรือน
  · ฝาเรือนพร้อมประตู/หน้าต่าง · หน้าบัน (จั่ว) สองข้าง · หลังคาจั่วสูงชายคายื่น
  · หลังคาระเบียงซ้อนชั้น · ป้านลม · ช่อฟ้าที่สันหลังคา

ทุกชิ้นเป็นเมชปิดสนิท (ตรวจด้วย ``mesh.check_part``) → ตรวจสอบได้ทุกครั้งที่รัน
ใช้:
    python tools/thai_house_builder.py --out-dir out --render house.png --rot-z 25
    python tools/thai_house_builder.py --json            # สรุปเป็น JSON
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mesh_lib as ml                                              # noqa: E402

SPEC = {
    "name": "ThaiHouse",
    # ── ขนาดหลัก (เมตร) ──
    "width": 6.0,             # ความกว้างเรือน (แกน X = ความยาวสันหลังคา)
    "depth": 4.2,             # ความลึกเรือน (แกน Y)
    "post_height": 2.20,      # เสายกพื้น (ใต้ถุน)
    "floor_thickness": 0.20,
    "wall_height": 2.60,
    "roof_lower_height": 2.70,   # หลังคาชั้นล่าง (ชายคา) — สูงให้ชันแบบไทย ~40°
    "roof_upper_height": 1.35,   # หลังคาชั้นบน (ซ้อนชั้นแบบไทย)
    "roof_upper_scale": 0.70,    # ชั้นบนแคบกว่าเท่าไร
    "roof_overhang_x": 1.10,
    "roof_overhang_y": 1.05,
    "veranda_depth": 1.80,
    "veranda_roof_height": 0.95,
    "rail_height": 0.95,
    "stair_steps": 5,
    "stair_width": 1.40,
    "ground": True,           # แผ่นฐานดินใต้เรือน
    # ── ความละเอียด ──
    "chamfer": 0.035,
    "chofa": True,            # ช่อฟ้า (ยอดสันหลังคา)
    "bargeboards": True,      # ป้านลม
    "balusters": True,        # ลูกกรงระเบียง
    "braces": True,           # ไม้ค้ำยันใต้พื้น
    # ── สี (r,g,b 0..1) ──
    "colors": {
        "post": (0.28, 0.17, 0.10),
        "deck": (0.56, 0.38, 0.22),
        "wall": (0.78, 0.64, 0.46),
        "roof": (0.55, 0.21, 0.14),
        "roof2": (0.62, 0.26, 0.17),
        "trim": (0.32, 0.20, 0.11),
        "frame": (0.88, 0.84, 0.74),
        "opening": (0.09, 0.07, 0.05),
        "rail": (0.44, 0.29, 0.17),
        "ground": (0.42, 0.50, 0.30),
    },
}


def build(spec):
    """คืนรายการชิ้นส่วน [(ชื่อ, (verts, faces), วัสดุ), ...]"""
    W = float(spec["width"])
    D = float(spec["depth"])
    ph = float(spec["post_height"])
    ft = float(spec["floor_thickness"])
    wh = float(spec["wall_height"])
    rl = float(spec["roof_lower_height"])
    ru = float(spec["roof_upper_height"])
    us = float(spec["roof_upper_scale"])
    ox, oy = float(spec["roof_overhang_x"]), float(spec["roof_overhang_y"])
    vd = float(spec["veranda_depth"])
    vrh = float(spec["veranda_roof_height"])
    ch = float(spec["chamfer"])
    C = {k: ml.mat(k, v) for k, v in spec["colors"].items()}

    floor_top = ph + ft
    wall_top = floor_top + wh
    ridge = wall_top + rl + ru
    roof_len = W + 2 * ox
    roof_base = D + 2 * oy
    parts = []

    def add(name, part, mat):
        parts.append((name, part, mat))

    # ── แผ่นดิน ──
    if spec["ground"]:
        add("ground", ml.chamfered_box(roof_len * 0.62, (D + vd) * 0.62, 0.06, 0.02,
                                       (0.0, -vd * 0.30, -0.06)), C["ground"])

    # ── เสายกพื้น + ไม้ค้ำยัน ──
    post = max(0.17, W * 0.030)
    xs = (-W * 0.42, 0.0, W * 0.42)
    ys = (-D * 0.40, D * 0.40)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            add(f"post_{i}{j}", ml.chamfered_box(post / 2, post / 2, ph / 2, ch * 0.4,
                                                 (x, y, ph / 2)), C["post"])
    for i, x in enumerate((-W * 0.46, W * 0.46)):
        add(f"post_veranda_{i}", ml.chamfered_box(post / 2, post / 2, ph / 2, ch * 0.4,
                                                  (x, -D / 2 - vd * 0.92, ph / 2)), C["post"])
    if spec["braces"]:
        bl = math.hypot(post * 2.6, ph * 0.42)
        for j, y in enumerate(ys):
            for s in (-1, 1):
                # เอียงในระนาบ X-Z → ต้องหมุนรอบแกน Y (ไม่ใช่ round X)
                add(f"brace_{j}_{'L' if s < 0 else 'R'}",
                    ml.translate(ml.rotate(ml.chamfered_box(post * 0.34, post * 0.34, bl / 2,
                                                            ch * 0.3), ry=-s * 34),
                                 s * (W * 0.42 - post * 1.4), y, ph * 0.58), C["post"])

    # ── คานรับพื้น ──
    beam_w = post * 1.3
    for j, y in enumerate(ys):
        add(f"beam_x_{j}", ml.chamfered_box(W * 0.47, beam_w / 2, beam_w / 2, ch * 0.4,
                                            (0.0, y, ph - beam_w / 2)), C["post"])
    for i, x in enumerate(xs):
        add(f"beam_y_{i}", ml.chamfered_box(beam_w / 2, (D + vd) * 0.46, beam_w / 2, ch * 0.4,
                                            (x, -vd / 2, ph - beam_w / 2)), C["post"])

    # ── พื้นไม้ (เรือน + ระเบียง ผืนเดียว) ──
    deck_w = W * 1.06
    deck_d = D + vd
    add("deck", ml.chamfered_box(deck_w / 2, deck_d / 2, ft / 2, ch,
                                 (0.0, -vd / 2, ph + ft / 2)), C["deck"])

    # ── ฝาเรือน + ขอบบน/ล่าง ──
    add("walls", ml.chamfered_box(W / 2, D / 2, wh / 2, ch, (0.0, 0.0, floor_top + wh / 2)),
        C["wall"])
    for tag, z in (("bottom", floor_top + 0.07), ("top", wall_top - 0.07)):
        add(f"trim_{tag}", ml.chamfered_box(W / 2 + 0.06, D / 2 + 0.06, 0.055, ch * 0.5,
                                            (0.0, 0.0, z)), C["trim"])

    # ── หน้าบัน (แผงไม้สามเหลี่ยมที่หัวเรือน — ต้องอยู่ "นอก" ตัวหลังคาจึงจะเห็น) ──
    for s, tag in ((-1, "L"), (1, "R")):
        add(f"gable_{tag}", ml.isosceles_prism(roof_base * 0.985, rl * 0.985, 0.10,
                                               (s * (roof_len / 2 + 0.02), 0.0,
                                                wall_top + rl / 2), chamfer=ch * 0.5),
            C["wall"])

    # ── หลังคาสองชั้น (ซ้อนชั้นแบบไทย) ──
    add("roof_lower", ml.isosceles_prism(roof_base, rl, roof_len,
                                         (0.0, 0.0, wall_top + rl / 2), chamfer=ch * 0.7),
        C["roof"])
    up_base = roof_base * us
    add("roof_upper", ml.isosceles_prism(up_base, ru, roof_len * (us + 0.16),
                                         (0.0, 0.0, wall_top + rl + ru / 2), chamfer=ch * 0.7),
        C["roof2"])

    # ── ขอบชายคา (fascia) — ทำให้หลังคาดูมีความหนาและแยกชั้นชัด ──
    for s, tag in ((-1, "F"), (1, "B")):
        add(f"fascia_lower_{tag}", ml.chamfered_box(roof_len / 2 * 0.995, 0.055, 0.075, ch * 0.4,
                                                    (0.0, s * (roof_base / 2 - 0.06),
                                                     wall_top + 0.03)), C["trim"])
        add(f"fascia_upper_{tag}", ml.chamfered_box(up_base / 2 * 0.995, 0.05, 0.065, ch * 0.4,
                                                    (0.0, s * (up_base / 2 - 0.05),
                                                     wall_top + rl + 0.03)), C["trim"])

    # ── ชายคาระเบียง ──
    add("veranda_roof", ml.isosceles_prism(roof_base * 0.46, vrh, roof_len * 0.94,
                                           (0.0, -D / 2 - vd * 0.52,
                                            floor_top + wh * 0.62 - vrh / 2), chamfer=ch * 0.6),
        C["roof"])

    # ── ป้านลม (แผ่นริมหลังคา — วางนอกระนาบหลังคาให้เห็นชัด) ──
    if spec["bargeboards"]:
        pitch = math.degrees(math.atan2(rl, roof_base / 2))
        slab_len = math.hypot(roof_base / 2, rl) * 0.98
        for s in (-1, 1):
            for side in (-1, 1):
                add(f"barge_{'L' if s < 0 else 'R'}_{'F' if side < 0 else 'B'}",
                    ml.slanted_slab(0.16, slab_len, 0.10, -side * pitch,
                                    (s * (roof_len / 2 + 0.17), side * roof_base / 4,
                                     wall_top + rl / 2 + 0.02), chamfer=ch * 0.3), C["trim"])

    # ── ช่อฟ้า (ยอดสันหลังคา · เอียงออกเล็กน้อยแล้วมีปลายชี้ขึ้น) ──
    if spec["chofa"]:
        up_len = roof_len * (us + 0.16)                 # ความยาวหลังคาชั้นบน
        for s, tag in ((-1, "L"), (1, "R")):
            # ⚠️ ต้องอยู่ปลาย "ชั้นบน" และขยับเข้ามาเล็กน้อย — ปลายสันเป็นจุดแหลม
            #    ถ้าวางที่ปลายสุด ช่อฟ้าจะเกาะแค่จุดเดียวและดูเหมือนลอย
            x_end = s * (up_len / 2 - 0.30)
            add(f"chofa_base_{tag}", ml.chamfered_box(0.17, 0.17, 0.07, ch * 0.4,
                                                      (x_end, 0.0, ridge + 0.06)), C["trim"])
            # ⚠️ ช่อฟ้าไทยต้อง "ตวัดโค้ง" ไม่ใช่แท่งตรง → ประกอบจากหลายท่อนที่เอียงเพิ่มขึ้น
            #    (ท่อนสั้นลงเรื่อย ๆ ตามส่วนโค้ง) จะอ่านเป็นเขาวัว/เปลวไฟแบบไทยได้ทันที
            segs = 5
            px, pz = x_end, ridge + 0.10
            for k in range(segs):
                tt = k / (segs - 1)
                ang = s * (10.0 + 46.0 * tt)             # 10° → 56°
                seg_len = 0.30 - 0.045 * k
                w = 0.075 - 0.007 * k
                dx = math.sin(math.radians(ang)) * seg_len * 0.5
                dz = math.cos(math.radians(ang)) * seg_len * 0.5
                add(f"chofa_{tag}_{k}", ml.translate(
                    ml.rotate(ml.chamfered_box(w, 0.15 - 0.012 * k, seg_len / 2, ch * 0.35),
                              ry=-ang), px + dx, 0.0, pz + dz), C["trim"])
                px += dx * 2.0
                pz += dz * 2.0

    # ── ประตู + หน้าต่าง ──
    door_w, door_h = W * 0.17, wh * 0.62
    add("door", ml.chamfered_box(door_w / 2, 0.05, door_h / 2, 0.02,
                                 (0.0, -D / 2 - 0.06, floor_top + door_h / 2)), C["opening"])
    add("door_frame", ml.chamfered_box(door_w / 2 + 0.11, 0.05, door_h / 2 + 0.11, ch * 0.4,
                                       (0.0, -D / 2 - 0.035, floor_top + door_h / 2)), C["frame"])
    win_w, win_h = W * 0.15, wh * 0.28
    for s, tag in ((-1, "L"), (1, "R")):
        add(f"window_front_frame_{tag}", ml.chamfered_box(win_w / 2 + 0.10, 0.05,
                                                          win_h / 2 + 0.10, ch * 0.4,
                                                          (s * W * 0.29, -D / 2 - 0.035,
                                                           floor_top + wh * 0.62)), C["frame"])
        add(f"window_front_{tag}", ml.chamfered_box(win_w / 2, 0.05, win_h / 2, 0.02,
                                                    (s * W * 0.29, -D / 2 - 0.06,
                                                     floor_top + wh * 0.62)), C["opening"])
        add(f"window_side_frame_{tag}", ml.chamfered_box(0.05, win_w / 2 + 0.10,
                                                         win_h / 2 + 0.10, ch * 0.4,
                                                         (s * (W / 2 + 0.035), D * 0.12,
                                                          floor_top + wh * 0.62)), C["frame"])
        add(f"window_side_{tag}", ml.chamfered_box(0.05, win_w / 2, win_h / 2, 0.02,
                                                   (s * (W / 2 + 0.06), D * 0.12,
                                                    floor_top + wh * 0.62)), C["opening"])

    # ── ราวระเบียง (ราวบน + ราวล่าง + ลูกกรง) ──
    rail_h = float(spec["rail_height"])
    ry = -D / 2 - vd + 0.07
    rail_th = 0.075
    stair_gap = float(spec["stair_width"]) / 2 + 0.12       # ช่องขึ้นบันได
    for tag, z in (("top", floor_top + rail_h), ("bottom", floor_top + rail_h * 0.22)):
        # ⚠️ ราวหน้าต้องแยกเป็น 2 ท่อนเว้นช่องบันได ไม่งั้นราวจะทับบันได
        seg = (deck_w / 2 - 0.06 - stair_gap) / 2
        for s, tg in ((-1, "L"), (1, "R")):
            add(f"rail_front_{tag}_{tg}",
                ml.chamfered_box(seg, rail_th / 2, rail_th / 2, ch * 0.4,
                                 (s * (stair_gap + seg), ry, z)), C["rail"])
        for s, tg in ((-1, "L"), (1, "R")):
            add(f"rail_side_{tag}_{tg}", ml.chamfered_box(rail_th / 2, vd / 2 - 0.06,
                                                          rail_th / 2, ch * 0.4,
                                                          (s * (deck_w / 2 - 0.06),
                                                           -D / 2 - vd / 2, z)), C["rail"])
    if spec["balusters"]:
        n_front = 11
        for i in range(n_front):
            x = -deck_w * 0.43 + (deck_w * 0.86) * i / (n_front - 1)
            if abs(x) < (W * 0.17) * 0.85:                 # เว้นช่องทางขึ้นบันได
                continue
            add(f"baluster_front_{i}", ml.chamfered_box(0.032, 0.032, rail_h / 2 - 0.05, ch * 0.3,
                                                        (x, ry, floor_top + rail_h / 2)), C["rail"])
        for s, tag in ((-1, "L"), (1, "R")):
            for i in range(3):
                y = -D / 2 - vd * (0.28 + 0.24 * i)
                add(f"baluster_side_{tag}_{i}",
                    ml.chamfered_box(0.032, 0.032, rail_h / 2 - 0.05, ch * 0.3,
                                     (s * (deck_w / 2 - 0.06), y, floor_top + rail_h / 2)),
                    C["rail"])

    # ── บันได (ขั้นบันได + ไม้ข้างสองข้าง) ──
    steps = int(spec["stair_steps"])
    sw = float(spec["stair_width"])
    step_h = ph / steps
    step_d = 0.33
    run = step_d * steps
    y_top = ry - 0.22          # เริ่มบันไดนอกราวระเบียง
    ang = math.degrees(math.atan2(ph, run))
    for i in range(steps):
        z_top = ph - (i + 1) * step_h + step_h
        y = y_top - step_d * (i + 0.5)
        add(f"stair_{i}", ml.chamfered_box(sw / 2 * 0.94, step_d / 2 * 0.92, 0.055, ch * 0.3,
                                           (0.0, y, z_top - 0.03)), C["deck"])
    stringer = math.hypot(ph, run)
    for s, tag in ((-1, "L"), (1, "R")):
        add(f"stair_stringer_{tag}", ml.slanted_slab(0.15, stringer, 0.26, -ang,
                                                     (s * (sw / 2 - 0.02),
                                                      y_top - run / 2 + 0.06, ph / 2),
                                                     chamfer=ch * 0.3), C["rail"])
        add(f"stair_handrail_{tag}", ml.slanted_slab(0.07, stringer * 0.96, 0.09, -ang,
                                                     (s * (sw / 2 - 0.02),
                                                      y_top - run / 2 + 0.06,
                                                      ph / 2 + rail_h * 0.92),
                                                     chamfer=ch * 0.3), C["rail"])
    return parts


def summarize(parts):
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
        "size_m": [round(hi[i] - lo[i], 3) for i in range(3)],
        "height_m": round(hi[2] - lo[2], 3),
        "bbox_min": [round(v, 3) for v in lo],
        "bbox_max": [round(v, 3) for v in hi],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="สร้างบ้านทรงไทย low-poly (ไม่ต้องใช้ Blender)")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--set", default="")
    ap.add_argument("--render", default="")
    ap.add_argument("--rot-z", type=float, default=0.0)
    ap.add_argument("--rot-x", type=float, default=0.0, help="ก้มกล้อง (องศา) ให้เห็นหลังคา")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    spec = json.loads(json.dumps(SPEC))
    if a.set.strip():
        for k, v in json.loads(a.set).items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k].update(v)
            else:
                spec[k] = v

    parts = build(spec)
    rep = summarize(parts)
    out_dir = pathlib.Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = ml.write_obj(out_dir / "thai_house.obj", parts, out_dir / "thai_house.mtl")

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"[thai_house] {rep['parts']} ชิ้น · {rep['vertices']} จุด · {rep['faces']} หน้า · "
              f"สูง {rep['height_m']} ม. · กว้าง×ลึก {rep['size_m'][0]}×{rep['size_m'][1]} ม.")
        print(f"  ปิดสนิททุกชิ้น: {rep['all_watertight']}" +
              (f" · ที่ยังไม่ผ่าน: {rep['bad_parts']}" if rep["bad_parts"] else ""))
        print(f"  ส่งออก: {obj} + {obj.with_suffix('.mtl').name}")
    if a.render:
        import render_flat
        info = render_flat.render(parts, out_dir / a.render, rot_z=a.rot_z, rot_x=a.rot_x,
                                  width=980, height=700,
                                  light=(-0.38, -0.66, 0.64), shadow=True, gradient=True,
                                  ambient=0.40)
        print(f"  เรนเดอร์: {out_dir / a.render} ({info['faces_drawn']} หน้า)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
