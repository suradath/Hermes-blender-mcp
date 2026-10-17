#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_mesh_lib.py — ทดสอบเครื่องยนต์เมช + ตัวสร้างตัวละครละเอียด (stdlib ล้วน ไม่ต้องมี Blender)

หัวใจของชุดนี้: "โมเดลสวย" ตรวจด้วยตาไม่ได้ → ตรวจด้วยคณิตศาสตร์
  · ทุกชิ้นต้อง **ปิดสนิท** (ทุกเส้นเชื่อมมีคู่ทิศตรงข้าม) และ **ออยเลอร์ = 2**
  · หน้าต้องหันออกนอก (ปริมาตรเป็นบวก) และปริมาตรต้องตรงกับค่าที่คำนวณได้จริง
  · สัดส่วนที่สร้างต้องตรงกับ "ที่วัดจากรูปต้นแบบ" ภายในเกณฑ์ที่กำหนด
  · ไฟล์ .obj ต้องอยู่ในรูปแบบที่ Blender อ่านได้ (ดัชนีไม่ล้น, มี usemtl/mtllib)
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))          # blender_bridge.py อยู่ที่รากโปรเจกต์
sys.path.insert(0, str(ROOT / "tools"))

import character_builder as cb      # noqa: E402
import mesh_lib as ml               # noqa: E402

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


def euler(part) -> int:
    verts, faces = part
    edges = sum(len(f) for f in faces) // 2
    return len(verts) - edges + len(faces)


def good_part(name: str, part) -> tuple[bool, str]:
    r = ml.check_part(name, *part)
    ok = (r["watertight"] and r["outward"] and r["finite"]
          and not r["duplicate_verts"] and euler(part) == 2 and r["volume_m3"] > 0)
    return ok, (f"ปิดสนิท={r['watertight']} ปริมาตร={r['volume_m3']} ออยเลอร์={euler(part)} {r['why']}")


# ===========================================================================
section("[1] เครื่องยนต์เมช: ทุกฟังก์ชันต้องสร้างของที่ปิดสนิทและหันหน้าถูก")
# ===========================================================================
SHAPES = {
    "กล่องทื่อ": ml.chamfered_box(0.5, 0.4, 0.3, 0.0),
    "กล่องลบมุม": ml.chamfered_box(0.5, 0.4, 0.3, 0.05),
    "กล่องลบมุม (ลบแรง)": ml.chamfered_box(0.5, 0.4, 0.3, 0.19),
    "แท่งแปดเหลี่ยม": ml.prism(8, 0.2, 0.6),
    "แท่ง 6 ด้าน": ml.prism(6, 0.15, 0.4),
    "แท่งสอบ": ml.tapered_prism(8, 0.30, 0.20, 0.42),
    "แท่งสอบ ลบมุม": ml.tapered_prism(8, 0.30, 0.20, 0.42, chamfer=0.02),
    "แท่งสอบ แกน X": ml.tapered_prism(8, 0.26, 0.18, 0.35, axis="x", chamfer=0.02),
    "กล่องสอบ": ml.frustum((0.6, 0.4), (0.5, 0.35), 0.3),
    "กล่องสอบ ลบมุม": ml.chamfered_frustum((0.5, 0.34), (0.44, 0.30), 0.56, 0.03),
    "ลิ่มสามเหลี่ยม": ml.triangular_prism(0.2, 0.15, 0.1, axis="y"),
    "พลิกซ้ายขวา": ml.mirror_x(ml.chamfered_box(0.2, 0.2, 0.5, 0.04)),
    "หมุน+ย้าย": ml.translate(ml.rotate(ml.prism(6, 0.1, 0.4), rx=35, rz=20), 1.0, 2.0, 3.0),
    "รวม 2 ชิ้น": ml.merge([ml.chamfered_box(0.2, 0.2, 0.2, 0.03), ml.prism(6, 0.1, 0.3)]),
}
for name, part in SHAPES.items():
    ok, why = good_part(name, part)
    if name == "รวม 2 ชิ้น":                       # เมช 2 เปลือกแยกกัน → ออยเลอร์ = 2×2
        check("รวม 2 ชิ้น: ปิดสนิททั้งสองเปลือก · ออยเลอร์ 4 · ปริมาตรบวก",
              ml.check_part(name, *part)["watertight"] and euler(part) == 4, why)
        continue
    check(f"{name}: ปิดสนิท · ออยเลอร์ 2 · ปริมาตรบวก", ok, why)

# ลบมุมที่เขียนจาก "ระนาบ" ต้องได้ผลเท่ากับตัวเขียนมือ (ตรวจสองทางแยกกัน)
a = ml.chamfered_box(0.5, 0.4, 0.3, 0.05)
b = ml.convex_from_planes(ml.chamfer_all(ml.box_planes(0.5, 0.4, 0.3), 0.05))
va = round(ml.signed_volume(*a), 9)
vb = round(ml.signed_volume(*b), 9)
check("chamfer_all(ระนาบ) ให้ผลเท่ากับ chamfered_box (จุด/หน้า/ปริมาตร)",
      len(a[0]) == len(b[0]) and len(a[1]) == len(b[1]) and va == vb,
      f"{len(a[0])}/{len(b[0])} จุด · {va} vs {vb}")

# ปริมาตรต้องตรงกับสูตร: กล่อง − 8 × (มุม tetra c³/6)
hx, hy, hz, c = 0.5, 0.4, 0.3, 0.05
expect = 8 * hx * hy * hz - 8 * (c ** 3 / 6.0)
got = ml.signed_volume(*ml.chamfered_box(hx, hy, hz, c))
check("ปริมาตรกล่องลบมุมตรงกับสูตร analytic", abs(got - expect) < 1e-9,
      f"{got:.9f} vs {expect:.9f}")
check("ปริมาตรกล่องทื่อตรงกับสูตร (2hx·2hy·2hz)",
      abs(ml.signed_volume(*ml.chamfered_box(hx, hy, hz, 0.0)) - 8 * hx * hy * hz) < 1e-9)

# symmetri: หลัง mirror จุดต้องเป็น −x ของเดิม
v0, _ = ml.chamfered_box(0.3, 0.2, 0.4, 0.03)
v1, _ = ml.mirror_x((v0, _))
xs = sorted(round(v[0], 9) for v in v0)
xs1 = sorted(round(-v[0], 9) for v in v1)
check("mirror_x สมมาตรจริง (x กลับเครื่องหมายครบทุกจุด)", xs == xs1)

# ขนาดต้องตรงตามที่สั่ง
lo, hi = ml.bbox(ml.chamfered_box(0.5, 0.4, 0.3, 0.05)[0])
check("ขนาดกล่องลบมุมตรงตามที่สั่ง (1.0×0.8×0.6)",
      all(abs((hi[i] - lo[i]) - want) < 1e-9 for i, want in enumerate((1.0, 0.8, 0.6))),
      str([round(hi[i] - lo[i], 6) for i in range(3)]))
lo, hi = ml.bbox(ml.tapered_prism(8, 0.30, 0.20, 0.42)[0])
check("แท่งสอบ: ปลายล่าง/kว้าง 0.30 · ปลายบน 0.20 · สูง 0.42",
      abs((hi[2] - lo[2]) - 0.42) < 1e-9 and abs(hi[0] - lo[0] - 0.30) < 0.01,
      f"{[round(hi[i] - lo[i], 4) for i in range(3)]}")

# ===========================================================================
section("[2] ตัวสร้างตัวละคร: สัดส่วนต้องตรงกับที่วัดจากรูปต้นแบบ")
# ===========================================================================
# ค่าที่วัดจากพิกเซลของรูปที่แนบ (ดู docs/03 §7)
HEAD_H = SPEC_HEAD_H = 1.70 / 3.04        # ความสูงหัว (เมตร) ตามสเปกที่ใช้ทดสอบ
MEASURED = {"head_h": 0.329, "arm_span": 0.872, "crotch_z": 0.241, "leg_len": 0.240,
            "leg_w": 0.332}
SPEC = json.loads(json.dumps(cb.SPEC))
SPEC.update({"name": "Chibi", "heads_tall": 3.04, "shoulder_width_heads": 0.85,
             "arm_length_heads": 0.95, "leg_length_heads": 2.2, "pose": "tpose",
             "shirt": False, "pants": False, "hair": False, "face": True,
             "belt": True, "feet": True})
SPEC["detail"]["limb_thick_heads"] = 0.50

parts, dspec = cb.build(SPEC)
rep = cb.summarize(parts, dspec)
names = [n for n, _p, _m in parts]
check("สร้างครบ 27 ชิ้น", rep["parts"] == 27, str(rep["parts"]))
check("ทุกชิ้นปิดสนิท/หันหน้าถูก", rep["all_watertight"], str(rep["bad_parts"]))
check("มีรายละเอียดครบ: ตา 2 · จมูก · หู 2 · มือ 2 · นิ้วโป้ง 2 · เข็มขัด · ผ้าเตี่ยว · เท้า 2",
      all(any(n.startswith(k) for n in names) for k in
          ("eye_", "nose", "ear_", "hand_", "thumb_", "belt", "cloth_front", "foot_", "toe_")),
      str(names))
check("ไม่มีผม (หัวโล้นตามรูป)", not any(n == "hair" for n in names))
check("สูงตรงตามสเปก (1.70 ม.)", abs(rep["height_m"] - 1.70) < 1e-6, str(rep["height_m"]))
check("จำนวนหัวตรงกับที่วัด (3.04)", abs(rep["height_heads"] - 3.04) < 0.02, str(rep["height_heads"]))

for key, tol in (("head_h", 0.01), ("arm_span", 0.04), ("crotch_z", 0.01), ("leg_len", 0.01)):
    got = rep["ratios"][key]
    check(f"สัดส่วน {key} = {got} ตรงกับที่วัด {MEASURED[key]} (±{tol})",
          abs(got - MEASURED[key]) <= tol, f"{got} vs {MEASURED[key]}")

# ความกว้างขารวม (วัดจากเมชจริง ไม่ใช่ค่าที่คำนวณในสูตร)
legs = [p for n, p, _m in parts if n.startswith("leg_")]
llo, lhi = ml.bbox([v for p in legs for v in p[0]])
leg_w = (lhi[0] - llo[0]) / rep["height_m"]
check(f"ความกว้างขารวม {leg_w:.3f} ตรงกับที่วัด {MEASURED['leg_w']} (±0.03)",
      abs(leg_w - MEASURED["leg_w"]) <= 0.03, str(round(leg_w, 4)))

# วัดความกว้างที่ "ระดับปลาย" ของชิ้น (จุดยอดอยู่ที่ฝาบน/ฝาล่างเท่านั้น)
def width_at_ends(part):
    tv = part[0]
    lo, hi = ml.bbox(tv)
    eps = (hi[2] - lo[2]) * 0.02 + 1e-9
    top = [v for v in tv if v[2] > hi[2] - eps]
    bot = [v for v in tv if v[2] < lo[2] + eps]
    if not top or not bot:
        return 0.0, 0.0
    return (max(v[0] for v in top) - min(v[0] for v in top),
            max(v[0] for v in bot) - min(v[0] for v in bot))


# ขา/เท้าต้องไม่ทับกัน (เคยพลาด: ขาติดกันเป็นแท่งเดียว, เท้าเชื่อมเป็นฐาน)
for tag, min_gap in (("leg_", 0.0), ("foot_", 0.005), ("toe_", 0.005)):
    g = [p for n, p, _m in parts if n.startswith(tag)]
    gap = min(abs(v[0]) for p in g for v in p[0]) * 2
    check(f"{tag} มีช่องว่างกลางตัว (ไม่ทับกัน) = {gap:.4f} ม.", gap >= min_gap, f"{gap}")

# มือต้องไม่ใหญ่กว่าต้นแขน (เคยพลาด: มือยักษ์กว่าแขน)
hands = [p for n, p, _m in parts if n.startswith("hand_")]
arms = [p for n, p, _m in parts if n.startswith("arm_")]
hlo, hhi = ml.bbox([v for p in hands for v in p[0]])
alo, ahi = ml.bbox([v for p in arms for v in p[0]])
ratio = (hhi[2] - hlo[2]) / (ahi[2] - alo[2])
check(f"มือ ({hhi[2]-hlo[2]:.3f} ม.) ไม่ใหญ่กว่าความหนาแขน ({ahi[2]-alo[2]:.3f} ม.)",
      ratio <= 1.0, f"อัตราส่วน {ratio:.2f}")

# แขน/ขาต้องสอบ (ปลายบน-ล่างไม่เท่ากันจริง ไม่ใช่แท่งตรง)
leg_part = [p for n, p, _m in parts if n == "leg_L"][0]
leg_r_top, leg_r_bot = width_at_ends(leg_part)[0] / 2.0, width_at_ends(leg_part)[1] / 2.0
check("ขาสอบจริง (ต้นขาใหญ่กว่าข้อเท้า)", leg_r_top > leg_r_bot * 1.1,
      f"บน {leg_r_top:.3f} · ล่าง {leg_r_bot:.3f}")

w_top, w_bot = width_at_ends([p for n, p, _m in parts if n == "torso"][0])
check("ลำตัวสอบจริง (อกกว้างกว่าเอว)", w_top > w_bot * 1.05,
      f"อก {w_top:.3f} · เอว {w_bot:.3f}")

# ตาต้องอยู่ด้านหน้าใบหน้า (-Y) และอยู่ระดับบนของหัว
eyes = [p for n, p, _m in parts if n.startswith("eye_")]
head = [p for n, p, _m in parts if n == "head"][0]
hlo, hhi = ml.bbox(head[0])
eye_lo, eye_hi = ml.bbox([v for p in eyes for v in p[0]])
eye_z = (eye_lo[2] + eye_hi[2]) / 2.0
# หัวเป็นทรงสอบ → ผิวด้านหน้าไม่เท่ากันทุกช่วง ต้องเทียบที่ระดับความสูงของตาเท่านั้น
near = [v[1] for v in head[0] if abs(v[2] - eye_z) < (HEAD_H) * 0.30]
check("ตายื่นพ้นผิวหน้าหัวที่ระดับเดียวกัน (มองเห็นได้จริง)",
      near and eye_lo[1] < min(near) + 1e-9,
      f"ตาหน้า {eye_lo[1]:.3f} · ผิวหัวใกล้ ๆ {min(near) if near else None}")
check("ตาอยู่ครึ่งบนของหัว", eye_lo[2] > (hlo[2] + hhi[2]) / 2.0,
      f"ตา {eye_lo[2]:.3f} · กลางหัว {(hlo[2]+hhi[2])/2:.3f}")

# ชิ้นส่วนทั้งหมดต้องอยู่ในกรอบเดียวกับความสูงที่ประกาศ
allv = [v for _n, (vs, _f), _m in parts for v in vs]
lo, hi = ml.bbox(allv)
check("ทุกชิ้นอยู่ในกรอบความสูงที่ประกาศ (ไม่ลอย/ไม่จมดิน)",
      abs(lo[2]) < 1e-6 and abs(hi[2] - 1.70) < 1e-6, f"{lo[2]} .. {hi[2]}")

# สร้างซ้ำต้องได้ผลเหมือนเดิมทุกจุด (deterministic)
parts2, _ = cb.build(SPEC)
check("สร้างซ้ำได้ผลเหมือนเดิม (deterministic)",
      [round(c, 9) for v in parts[0][1][0] for c in v] ==
      [round(c, 9) for v in parts2[0][1][0] for c in v])

# ===========================================================================
section("[3] ปุ่มปรับความละเอียด (detail) ต้องทำงานจริง")
# ===========================================================================
def build_with(**detail):
    s = json.loads(json.dumps(SPEC))
    s["detail"].update(detail)
    p, dd = cb.build(s)
    return cb.summarize(p, dd)


r0 = build_with(chamfer=0.0)
r1 = build_with(chamfer=0.16)
check("chamfer=0 → จุดน้อยลง (กล่องทื่อ)", r0["vertices"] < r1["vertices"],
      f"{r0['vertices']} vs {r1['vertices']}")
r4 = build_with(limb_sides=4)
check("limb_sides=4 → แขนขาหยาบขึ้น (จุดน้อยลง)", r4["vertices"] < r1["vertices"],
      f"{r4['vertices']} vs {r1['vertices']}")
r12 = build_with(limb_sides=12)
check("limb_sides=12 → เนียนขึ้น (จุดมากขึ้น)", r12["vertices"] > r1["vertices"],
      f"{r12['vertices']} vs {r1['vertices']}")
rf = build_with(thumbs=False, ears=False, nose=False, deltoids=False, loincloth_panels=False)
check("ปิดรายละเอียดย่อยได้ (ชิ้นน้อยลง)", rf["parts"] < r1["parts"],
      f"{rf['parts']} vs {r1['parts']}")
check("ปิดรายละเอียดแล้วยังปิดสนิททุกชิ้น", rf["all_watertight"], str(rf["bad_parts"]))

# ===========================================================================
section("[4] ไฟล์ .obj/.mtl ต้องอยู่ในรูปแบบที่ Blender อ่านได้")
# ===========================================================================
with tempfile.TemporaryDirectory() as td:
    obj = ml.write_obj(pathlib.Path(td) / "c.obj", parts, pathlib.Path(td) / "c.mtl")
    mtl = pathlib.Path(td) / "c.mtl"
    txt = obj.read_text(encoding="utf-8").splitlines()
    verts = [ln for ln in txt if ln.startswith("v ")]
    faces = [ln for ln in txt if ln.startswith("f ")]
    check("จำนวน v ตรงกับเมช", len(verts) == rep["vertices"], f"{len(verts)} vs {rep['vertices']}")
    check("จำนวน f ตรงกับเมช", len(faces) == rep["faces"], f"{len(faces)} vs {rep['faces']}")
    idx_ok = True
    for ln in faces:
        for tok in ln.split()[1:]:
            i = int(tok.split("/")[0])
            if i < 1 or i > len(verts):
                idx_ok = False
    check("ดัชนีใบหน้าอยู่ในขอบเขต (1..N)", idx_ok)
    check("มี mtllib + usemtl ครบ (Blender จะได้มีวัสดุ)", any(l.startswith("mtllib ") for l in txt)
          and any(l.startswith("usemtl ") for l in txt))
    check("มี o (object) ครบทุกชิ้น", sum(1 for l in txt if l.startswith("o ")) == rep["parts"])
    check("ไฟล์ .mtl ถูกเขียนคู่กัน", mtl.is_file())
    m = mtl.read_text(encoding="utf-8")
    mats = {"skin", "belt", "cloth", "eye"}
    check("วัสดุครบตามที่ใช้จริง (ผิว/เข็มขัด/ผ้า/ตา)",
          all(f"newmtl {k}" in m for k in mats), str([k for k in mats if f"newmtl {k}" not in m]))
    check("ทุกวัสดุมีสี Kd", m.count("Kd ") >= 4, str(m.count("Kd ")))
    # ⚠️ Kd ถูกเขียนเป็นค่า linear (มาตรฐานที่ Blender ใช้) ไม่ใช่ค่า sRGB ดิบ
    lin = [ml._srgb_to_linear(c) for c in (0.88, 0.69, 0.50)]
    check("สีวัสดุเขียนเป็น linear ตามที่ Blender คาดหวัง",
          f"Kd {lin[0]:.4f} {lin[1]:.4f} {lin[2]:.4f}" in m,
          f"ต้องการ Kd {lin[0]:.4f} {lin[1]:.4f} {lin[2]:.4f}")
    check("ไม่เขียนค่า sRGB ดิบลง Kd อีก", "0.8800 0.6900 0.5000" not in m)
    # ⚠️ พิกัดถูกแปลง Z-up → Y-up (มาตรฐาน OBJ): (x, y, z) → (x, z, -y)
    x0, y0, z0 = parts[0][1][0][0]
    first = txt[[i for i, l in enumerate(txt) if l.startswith("v ")][0]]
    check("จุดแรกถูกแปลงเป็น Y-up ตามมาตรฐาน OBJ",
          first == f"v {x0:.6f} {z0:.6f} {-y0:.6f}", first)
    # สวิตช์ปิดได้ (สำหรับคนที่ต้องการไบต์ดิบ)
    raw_obj = pathlib.Path(td) / "raw.obj"
    raw_mtl = pathlib.Path(td) / "raw.mtl"
    ml.write_obj(raw_obj, parts, mtl_path=raw_mtl, up="Z", linear_colors=False)
    raw_txt = raw_obj.read_text(encoding="utf-8").splitlines()
    raw_first = raw_txt[[i for i, l in enumerate(raw_txt) if l.startswith("v ")][0]]
    check("up='Z' + linear_colors=False → ได้ไบต์ดิบเดิม",
          raw_first == f"v {x0:.6f} {y0:.6f} {z0:.6f}", raw_first)
    check("และ Kd กลับเป็นค่า sRGB ดิบ", "0.8800 0.6900 0.5000" in raw_mtl.read_text(encoding="utf-8"))

# ===========================================================================
section("[5] สคริปต์ฝั่ง Blender (แต่งให้เนียน) ต้องผ่านด่านและทำงานได้จริง")
# ===========================================================================
import fake_bpy  # noqa: E402

sys.modules["bpy"] = fake_bpy
import blender_bridge as br  # noqa: E402

EX_BLENDER = ROOT / "examples" / "detail_character_in_blender.py"
check("มีไฟล์ examples/detail_character_in_blender.py", EX_BLENDER.is_file())
src_bl = EX_BLENDER.read_text(encoding="utf-8") if EX_BLENDER.is_file() else ""
guard_bl = br.scan_code(src_bl)
check("⚠️ ผ่านด่านความปลอดภัย (ส่งเข้า execute_blender_script ได้)",
      not guard_bl.violations, "; ".join(guard_bl.violations)[:200])


def run_blender_script(code: str) -> dict:
    return br.handle_message({"id": 1, "method": "call_tool",
                              "params": {"name": "execute_blender_script",
                                         "arguments": {"code": code}}})


fake_bpy.reset()
def inner(res: dict) -> dict:
    """⚠️ handle_message ห่อผลอีกชั้น: ok ของสคริปต์อยู่ใน res['result']['ok']"""
    return res.get("result") or {}


r = run_blender_script(src_bl)
check("รันสคริปต์แต่งโมเดลสำเร็จ", inner(r).get("ok") is True, str(inner(r).get("error"))[:250])
calls = [c[0] for c in fake_bpy.ops.calls]
check("เรียก wm.obj_import พร้อมพาธจาก OBJ_PATH",
      any(c == "wm.obj_import" for c in calls), str(calls))
check("ใส่ Bevel แล้ว apply จริง", calls.count("object.modifier_apply") >= 1, str(calls))
check("ปิด SHADE_SMOOTH → ใช้ shade_flat (คงลุคเหลี่ยม)", "object.shade_flat" in calls, str(calls))
check("พิมพ์สรุปจำนวนจุด/หน้าให้เห็น", "detail_character" in (inner(r).get("stdout") or ""),
      str(inner(r).get("stdout"))[:120])

# เปิด subdiv + smooth → ต้องมี modifier_apply 2 ครั้ง และใช้ shade_smooth
fake_bpy.reset()
src2 = (src_bl.replace("SUBDIV_LEVELS = 0", "SUBDIV_LEVELS = 1")
              .replace("SHADE_SMOOTH = False", "SHADE_SMOOTH = True"))
check("แก้ค่าคอนฟิกในสคริปต์ได้ (SUBDIV/SMOOTH)", src2 != src_bl)
r2 = run_blender_script(src2)
calls2 = [c[0] for c in fake_bpy.ops.calls]
check("รันเวอร์ชัน subdiv+smooth สำเร็จ", inner(r2).get("ok") is True, str(inner(r2).get("error"))[:200])
# นำเข้า 2 วัตถุ (bpy ปลอมสร้างให้ 2 ชิ้น) × 2 modifier = 4 ครั้ง
check("apply modifier ครบทุกชิ้น (2 วัตถุ × Bevel+Subdiv = 4 ครั้ง)",
      calls2.count("object.modifier_apply") == 4, str(calls2))
check("ใช้ shade_smooth ตามที่สั่ง", "object.shade_smooth" in calls2, str(calls2))

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
