# -*- coding: utf-8 -*-
"""
tree_builder.py — ต้นไม้สไตล์โพลิกอน (low-poly) จากเรขาคณิตจริง
================================================================
องค์ประกอบ: โคนต้นบาน (ราก) · ลำต้นเหลี่ยมเรียวขึ้น · กิ่ง 4 กิ่งทำมุม ·
พุ่มใบจาก "ก้อนเหลี่ยมลบมุม" หลายก้อน (อ่านเป็นพุ่มไม้โพลิกอน)

ใช้:
    python tools/tree_builder.py --out-dir out --render tree.png --rot-z 25
    python tools/tree_builder.py --json
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
    "name": "Tree",
    "height": 7.0,           # ความสูงรวม (เมตร)
    "trunk_height": 4.15,    # ลำต้นถึงโคนพุ่ม (สูงขึ้น → ไม่ดูเป็นเห็ด)
    "trunk_bottom": 0.62,    # เส้นผ่านศูนย์กลางโคน
    "trunk_top": 0.34,       # เส้นผ่านศูนย์กลางยอด
    "root_flare": 0.95,      # ความกว้างโคนบาน (ราก)
    "sides": 8,              # จำนวนด้านของลำต้น (8 = เหลี่ยมสวย)
    "branches": 4,
    "blobs": 9,              # จำนวนก้อนพุ่มใบ
    "canopy_spread": 1.95,   # รัศมีพุ่มโดยประมาณ
    "chamfer": 0.04,
    "colors": {
        "trunk": (0.36, 0.25, 0.16),
        "trunk_dark": (0.29, 0.20, 0.13),
        "leaf": (0.30, 0.48, 0.22),
        "leaf2": (0.38, 0.56, 0.26),
        "leaf3": (0.24, 0.41, 0.19),
    },
}


def _blob(radius, center, squash=1.0, rot_z=0.0, chamfer_frac=0.46):
    """ก้อนพุ่มใบแบบโพลิกอน (กล่องลบมุมเยอะ ๆ → ดูเป็นก้อนเหลี่ยมกลม)"""
    part = ml.chamfered_box(radius, radius, radius * squash, radius * chamfer_frac)
    if rot_z:
        part = ml.rotate(part, rz=rot_z)
    return ml.translate(part, *center)


def build(spec):
    H = float(spec["height"])
    th = float(spec["trunk_height"])
    tb, tt = float(spec["trunk_bottom"]), float(spec["trunk_top"])
    sides = int(spec["sides"])
    ch = float(spec["chamfer"])
    C = {k: ml.mat(k, v) for k, v in spec["colors"].items()}
    parts = []

    def add(name, part, mat):
        parts.append((name, part, mat))

    # ── โคนบาน (ราก) ──
    rf = float(spec["root_flare"])
    add("root_flare", ml.tapered_prism(sides, rf, tb, 0.38, (0.0, 0.0, 0.19), chamfer=ch * 0.9),
        C["trunk_dark"])

    # ── ลำต้น (เรียวขึ้น) ──
    add("trunk", ml.tapered_prism(sides, tb, tt, th, (0.0, 0.0, 0.38 + th / 2), chamfer=ch),
        C["trunk"])

    # ── กิ่ง (เอียงออก 4 ทิศ) ──
    nb = int(spec["branches"])
    for i in range(nb):
        ang = 2.0 * math.pi * i / nb + 0.35
        z = th * (0.62 + 0.10 * (i % 2))
        ln = 2.05 - 0.22 * (i % 2)      # ยาวพอให้จมเข้าไปในพุ่ม
        lean = 46.0 - 6.0 * (i % 2)
        br = ml.tapered_prism(6, tt * 0.62, tt * 0.30, ln, (0.0, 0.0, 0.0), chamfer=ch * 0.8)
        br = ml.rotate(br, ry=lean)                     # เอียงออกในระนาบ X-Z
        br = ml.rotate(br, rz=math.degrees(ang))        # หมุนไปรอบต้น
        br = ml.translate(br, 0.0, 0.0, z)
        add(f"branch_{i}", br, C["trunk"])

    # ── พุ่มใบ (ก้อนเหลี่ยมหลายก้อน) ──
    spread = float(spec["canopy_spread"])
    nblob = int(spec["blobs"])
    leaf_mats = [C["leaf"], C["leaf2"], C["leaf3"]]
    # ก้อนกลางใหญ่
    add("canopy_0", _blob(spread * 0.72, (0.0, 0.0, th + spread * 0.46), 0.92, 12.0),
        C["leaf"])
    # ก้อนรอบ ๆ เรียงเป็นวง (ตำแหน่งกำหนดได้แน่นอน ไม่สุ่ม)
    ring = max(1, nblob - 2)
    for i in range(ring):
        ang = 2.0 * math.pi * i / ring + 0.6
        r = spread * 0.62
        z = th + spread * (0.30 + 0.34 * (i % 2))
        rad = spread * (0.52 if i % 2 == 0 else 0.44)
        add(f"canopy_{i + 1}",
            _blob(rad, (math.cos(ang) * r, math.sin(ang) * r, z), 0.88, 20.0 * i + 8.0),
            leaf_mats[i % 3])
    # ก้อนยอดบน
    add(f"canopy_{nblob - 1}", _blob(spread * 0.40, (0.0, 0.0, H - spread * 0.34), 0.90, 28.0),
        C["leaf2"])
    return parts


def summarize(parts):
    rows = [ml.check_part(n, *p) for n, p, _m in parts]
    lo, hi = ml.bbox([v for _n, (vs, _f), _m in parts for v in vs])
    bad = [r["name"] for r in rows
           if not (r["watertight"] and r["outward"] and r["finite"] and not r["duplicate_verts"])]
    return {"parts": len(parts), "vertices": sum(r["verts"] for r in rows),
            "faces": sum(r["faces"] for r in rows), "all_watertight": not bad,
            "bad_parts": bad, "size_m": [round(hi[i] - lo[i], 3) for i in range(3)],
            "height_m": round(hi[2] - lo[2], 3),
            "bbox_min": [round(v, 3) for v in lo], "bbox_max": [round(v, 3) for v in hi]}


def main() -> int:
    ap = argparse.ArgumentParser(description="สร้างต้นไม้โพลิกอน (ไม่ต้องใช้ Blender)")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--set", default="")
    ap.add_argument("--render", default="")
    ap.add_argument("--rot-z", type=float, default=0.0)
    ap.add_argument("--rot-x", type=float, default=0.0)
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
    obj = ml.write_obj(out_dir / "tree.obj", parts, out_dir / "tree.mtl")
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"[tree] {rep['parts']} ชิ้น · {rep['vertices']} จุด · {rep['faces']} หน้า · "
              f"สูง {rep['height_m']} ม. · ปิดสนิททุกชิ้น: {rep['all_watertight']}")
        print(f"  ส่งออก: {obj}")
    if a.render:
        import render_flat
        info = render_flat.render(parts, out_dir / a.render, rot_z=a.rot_z, rot_x=a.rot_x,
                                  width=760, height=860, shadow=True, gradient=True,
                                  light=(-0.40, -0.62, 0.68), ambient=0.42)
        print(f"  เรนเดอร์: {out_dir / a.render} ({info['faces_drawn']} หน้า)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
