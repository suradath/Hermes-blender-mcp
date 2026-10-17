# -*- coding: utf-8 -*-
"""
dog_builder.py — สุนัขสไตล์โพลิกอน (low-poly) จากเรขาคณิตจริง
==============================================================
องค์ประกอบ: ลำตัว · อก/สะโพก · คอ · หัว · ปากยื่น+จมูก · หูสามเหลี่ยม · ตา ·
ขา 4 ข้างพร้อมอุ้งเท้า · หางชี้ขึ้น · ปลอกคอ

ใช้:
    python tools/dog_builder.py --out-dir out --render dog.png --rot-z 30 --rot-x 10
    python tools/dog_builder.py --json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mesh_lib as ml                                              # noqa: E402

SPEC = {
    "name": "Dog",
    "length": 1.02,          # ความยาวลำตัว (แกน Y)
    "body_width": 0.40,      # ความกว้างลำตัว (แกน X)
    "body_height": 0.40,     # ความสูงลำตัว
    "leg_length": 0.52,      # ความยาวขา (ถึงท้อง)
    "head_size": 0.30,       # ความกว้างหัว
    "snout_length": 0.20,    # ความยาวปากที่ยื่นออกไป
    "ear_size": 0.17,
    "tail_length": 0.46,
    "sides": 6,              # จำนวนด้านของขา/หาง
    "chamfer": 0.022,
    "collar": True,
    "colors": {
        "fur": (0.62, 0.44, 0.26),
        "fur_dark": (0.45, 0.31, 0.18),
        "muzzle": (0.34, 0.24, 0.14),
        "paw": (0.72, 0.62, 0.48),
        "dark": (0.09, 0.07, 0.06),
        "collar": (0.66, 0.18, 0.14),
    },
}


def build(spec):
    L = float(spec["length"])
    bw = float(spec["body_width"])
    bh = float(spec["body_height"])
    ll = float(spec["leg_length"])
    hs = float(spec["head_size"])
    sn = float(spec["snout_length"])
    es = float(spec["ear_size"])
    tl = float(spec["tail_length"])
    sides = int(spec["sides"])
    ch = float(spec["chamfer"])
    C = {k: ml.mat(k, v) for k, v in spec["colors"].items()}
    parts = []

    def add(name, part, mat):
        parts.append((name, part, mat))

    body_z = ll + bh / 2.0                      # กลางลำตัว
    # ── ลำตัว (ท้ายสอบ) + อกหนา ──
    add("body", ml.chamfered_box(bw / 2, L * 0.34, bh / 2, ch, (0.0, 0.0, body_z)), C["fur"])
    add("chest", ml.chamfered_box(bw / 2 * 1.04, L * 0.16, bh / 2 * 1.08, ch,
                                  (0.0, -L * 0.22, body_z + 0.01)), C["fur"])
    add("hips", ml.chamfered_box(bw / 2 * 0.94, L * 0.13, bh / 2 * 0.94, ch,
                                 (0.0, L * 0.30, body_z - 0.01)), C["fur"])

    # ── คอ (เอียงไปหน้า) ──
    neck_z = body_z + bh * 0.36
    add("neck", ml.tapered_prism(sides, bw * 0.50, hs * 0.74, 0.30,
                                 (0.0, -L * 0.30, neck_z + 0.02), chamfer=ch),
        C["fur"])

    # ── หัว + ปาก + จมูก + ตา + หู ──
    head_y = -L * 0.30 - 0.16
    head_z = neck_z + 0.30
    add("head", ml.chamfered_box(hs / 2, hs / 2 * 1.02, hs / 2, ch, (0.0, head_y, head_z)),
        C["fur"])
    # ปากเรียว (frustum) — กล่องทื่อจะดูเป็นลัง
    add("muzzle", ml.chamfered_frustum((hs * 0.60, sn * 0.55), (hs * 0.44, sn * 0.40), sn, ch * 1.2,
                                       (0.0, head_y - hs * 0.46 - sn / 2, head_z - hs * 0.12)),
        C["muzzle"])
    add("nose", ml.chamfered_box(hs * 0.13, 0.035, hs * 0.10, 0.012,
                                 (0.0, head_y - hs * 0.46 - sn - 0.02, head_z - hs * 0.06)),
        C["dark"])
    for s, tag in ((-1, "L"), (1, "R")):
        # ⚠️ ตาต้องอยู่ "นอกความกว้างของปาก" ไม่งั้นจะซ่อนอยู่หลังปาก (เคยมองไม่เห็น)
        add(f"eye_{tag}", ml.chamfered_box(hs * 0.085, 0.028, hs * 0.085, 0.008,
                                           (s * hs * 0.38, head_y - hs * 0.50,
                                            head_z + hs * 0.16)), C["dark"])
        # หูสามเหลี่ยม เอียงออก
        ear = ml.triangular_prism(es * 0.62, es, es * 0.55, (0.0, 0.0, 0.0), axis="y")
        ear = ml.rotate(ear, rx=-12.0)
        ear = ml.rotate(ear, ry=-s * 18.0)
        add(f"ear_{tag}", ml.translate(ear, s * hs * 0.30, head_y + hs * 0.10,
                                       head_z + hs * 0.52), C["fur_dark"])

    # ── ขา 4 ข้าง + อุ้งเท้า ──
    leg_x = bw * 0.34
    for i, y in enumerate((L * 0.24, -L * 0.26)):
        for s, tag in ((-1, "L"), (1, "R")):
            add(f"leg_{i}_{tag}",
                ml.translate(ml.rotate(ml.tapered_prism(sides, bw * 0.27, bw * 0.20, ll,
                                                        (0.0, 0.0, 0.0), chamfer=ch * 0.8),
                                       ry=-s * 4.0), s * leg_x, y, ll / 2.0), C["fur"])
            add(f"paw_{i}_{tag}",
                ml.chamfered_box(bw * 0.17, L * 0.075, ll * 0.10, ch * 0.8,
                                 (s * leg_x, y - L * 0.02, ll * 0.10)), C["paw"])

    # ── หาง (ชี้ขึ้น-ไปท้าย) ──
    tail = ml.tapered_prism(sides, bw * 0.22, bw * 0.08, tl * 1.35, (0.0, 0.0, 0.0),
                            chamfer=ch * 0.7)
    tail = ml.rotate(tail, rx=-58.0)                      # เอียงขึ้นไปทางท้าย (+Y)
    tail = ml.translate(tail, 0.0, L * 0.36 + 0.06, body_z + bh * 0.10 + tl * 0.42)
    add("tail", tail, C["fur"])

    # ── ปลอกคอ ──
    if spec["collar"]:
        add("collar", ml.tapered_prism(sides, hs * 0.86, hs * 0.86, 0.075,
                                       (0.0, -L * 0.30, neck_z + 0.12), chamfer=ch * 0.5),
            C["collar"])
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
    ap = argparse.ArgumentParser(description="สร้างสุนัขโพลิกอน (ไม่ต้องใช้ Blender)")
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
    obj = ml.write_obj(out_dir / "dog.obj", parts, out_dir / "dog.mtl")
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"[dog] {rep['parts']} ชิ้น · {rep['vertices']} จุด · {rep['faces']} หน้า · "
              f"สูง {rep['height_m']} ม. · ปิดสนิททุกชิ้น: {rep['all_watertight']}")
        print(f"  ส่งออก: {obj}")
    if a.render:
        import render_flat
        info = render_flat.render(parts, out_dir / a.render, rot_z=a.rot_z, rot_x=a.rot_x,
                                  width=860, height=700, shadow=True, gradient=True,
                                  light=(-0.42, -0.66, 0.62), ambient=0.40)
        print(f"  เรนเดอร์: {out_dir / a.render} ({info['faces_drawn']} หน้า)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
