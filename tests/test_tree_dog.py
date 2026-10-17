#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_tree_dog.py — ทดสอบต้นไม้และสุนัขโพลิกอน (stdlib ล้วน · ไม่ต้องมี Blender)

จุดที่ต้องล็อกไว้ (บทเรียนจริงจากการปรับแบบ):
  · ทุกชิ้นปิดสนิท/ออยเลอร์ 2/ปริมาตรบวก
  · ต้นไม้: ลำต้นแตะพื้น · พุ่มอยู่บนลำต้น (ไม่ลอย/ไม่จมพื้น) · ลำต้นเรียวขึ้น · กิ่งยื่นพ้นลำต้น
  · สุนัข: 4 ขาแตะพื้น · ลำตัวอยู่บนขา · หัว/ปาก/จมูกเรียงไปข้างหน้าถูก · หางอยู่ท้าย
    · **ตาต้องอยู่พ้นความกว้างของปาก** (เคยซ่อนอยู่หลังปาก มองไม่เห็น)
    · สมมาตรซ้าย-ขวา
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import mesh_lib as ml          # noqa: E402
import tree_builder as tb       # noqa: E402
import dog_builder as db        # noqa: E402

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
    v, f = part
    return len(v) - sum(len(x) for x in f) // 2 + len(f)


def ok_part(p) -> bool:
    r = ml.check_part("x", *p)
    return (r["watertight"] and r["outward"] and r["finite"]
            and not r["duplicate_verts"] and euler(p) == 2 and r["volume_m3"] > 0)


def bx(p):
    return ml.bbox(p[0])


# ===========================================================================
section("[1] ต้นไม้")
# ===========================================================================
tspec = json.loads(json.dumps(tb.SPEC))
tparts = tb.build(tspec)
trep = tb.summarize(tparts)
tby = {n: p for n, p, _m in tparts}

bad = [n for n, p, _m in tparts if not ok_part(p)]
check(f"ต้นไม้: ทั้ง {trep['parts']} ชิ้นปิดสนิท/ออยเลอร์ 2", not bad, str(bad[:4]))
check("ต้นไม้: มีลำต้น + โคนบาน + กิ่ง + พุ่มครบ",
      all(k in tby for k in ("trunk", "root_flare")) and
      any(n.startswith("branch_") for n in tby) and
      sum(1 for n in tby if n.startswith("canopy_")) >= 5,
      str(sorted(tby)))

rlo, rhi = bx(tby["root_flare"])
check("ต้นไม้: โคนบานแตะพื้น (z ล่าง ≈ 0)", abs(rlo[2]) < 0.01, f"{rlo[2]:.3f}")
tlo, thi = bx(tby["trunk"])
check("ต้นไม้: ลำต้นต่อจากโคนบานขึ้นไป", abs(tlo[2] - rhi[2]) < 0.02, f"{tlo[2]:.3f} vs {rhi[2]:.3f}")

# ลำต้นเรียวขึ้น: วัดความกว้างที่ปลายบน/ล่าง
def width_at_ends(p):
    vs = p[0]
    lo, hi = ml.bbox(vs)
    eps = (hi[2] - lo[2]) * 0.03 + 1e-9
    top = [v for v in vs if v[2] > hi[2] - eps]
    bot = [v for v in vs if v[2] < lo[2] + eps]
    return ((max(v[0] for v in top) - min(v[0] for v in top)),
            (max(v[0] for v in bot) - min(v[0] for v in bot)))


w_top, w_bot = width_at_ends(tby["trunk"])
check("ต้นไม้: ลำต้นเรียวขึ้น (ยอดเล็กกว่าโคน)", w_top < w_bot * 0.85, f"{w_top:.3f} vs {w_bot:.3f}")

canopy = [(n, p) for n, p, _m in tparts if n.startswith("canopy_")]
clo = min(bx(p)[0][2] for _n, p in canopy)
chi = max(bx(p)[1][2] for _n, p in canopy)
check("ต้นไม้: พุ่มอยู่เหนือพื้นชัดเจน (ไม่จม/ไม่ลอย)", clo > tspec["trunk_height"] * 0.55,
      f"ล่างสุด {clo:.2f} · ลำต้นสูง {tspec['trunk_height']}")
check("ต้นไม้: พุ่มซ้อนกับยอดลำต้น (ติดกันจริง)", clo < thi[2] + 0.6,
      f"พุ่มล่าง {clo:.2f} · ยอดลำต้น {thi[2]:.2f}")
check("ต้นไม้: ความสูงรวมใกล้ค่าที่ตั้ง (7.0 ม.)", abs(trep["height_m"] - 7.0) <= 0.35,
      str(trep["height_m"]))
# กิ่งต้องยื่นพ้นลำต้น (ไม่ใช่ติ่งสั้นติดลำต้น)
trunk_r = w_bot / 2
bmax = max(max(abs(bx(p)[0][0]), abs(bx(p)[1][0])) for n, p, _m in tparts if n.startswith("branch_"))
check("ต้นไม้: กิ่งยื่นพ้นลำต้นออกไปจริง (> 2 เท่ารัศมีลำต้น)", bmax > trunk_r * 2.0,
      f"{bmax:.2f} vs รัศมี {trunk_r:.2f}")
check("ต้นไม้: จำนวนก้อนพุ่มตรงกับสเปก", len(canopy) == int(tspec["blobs"]), str(len(canopy)))
t2 = tb.build(json.loads(json.dumps(tspec)))
check("ต้นไม้: deterministic", [round(c, 9) for v in tparts[0][1][0] for c in v] ==
      [round(c, 9) for v in t2[0][1][0] for c in v])

# ===========================================================================
section("[2] สุนัข")
# ===========================================================================
dspec = json.loads(json.dumps(db.SPEC))
dparts = db.build(dspec)
drep = db.summarize(dparts)
dby = {n: p for n, p, _m in dparts}

bad = [n for n, p, _m in dparts if not ok_part(p)]
check(f"สุนัข: ทั้ง {drep['parts']} ชิ้นปิดสนิท/ออยเลอร์ 2", not bad, str(bad[:4]))
for part in ("body", "chest", "hips", "neck", "head", "muzzle", "nose", "tail"):
    check(f"สุนัข: มีชิ้น «{part}»", part in dby, str(sorted(dby)))

legs = [n for n in dby if n.startswith("leg_")]
paws = [n for n in dby if n.startswith("paw_")]
check("สุนัข: มีขา 4 ข้าง", len(legs) == 4, str(legs))
check("สุนัข: มีอุ้งเท้า 4 ข้าง", len(paws) == 4, str(paws))
leg_bottom = min(bx(dby[n])[0][2] for n in legs)
check("สุนัข: ขาแตะพื้น (z ล่าง ≈ 0)", abs(leg_bottom) < 0.02, f"{leg_bottom:.3f}")
blo, bhi = bx(dby["body"])
check("สุนัข: ลำตัวอยู่บนขา (ล่างของลำตัว ≈ ความยาวขา)", abs(blo[2] - dspec["leg_length"]) < 0.05,
      f"{blo[2]:.3f} vs {dspec['leg_length']}")

hlo, hhi = bx(dby["head"])
check("สุนัข: หัวอยู่หน้าลำตัว (-Y)", (hlo[1] + hhi[1]) / 2 < blo[1], 
      f"หัว {(hlo[1]+hhi[1])/2:.2f} · ลำตัวหน้า {blo[1]:.2f}")
mlo, mhi = bx(dby["muzzle"])
check("สุนัข: ปากยื่นออกหน้าหัว", mhi[1] < hlo[1] + 0.02, f"ปากหน้า {mhi[1]:.2f} · หัวหน้า {hlo[1]:.2f}")
nlo, nhi = bx(dby["nose"])
check("สุนัข: จมูกอยู่ปลายปาก", nhi[1] <= mlo[1] + 0.03, f"จมูก {nhi[1]:.2f} · ปากหน้า {mlo[1]:.2f}")
tlo_, thi_ = bx(dby["tail"])
check("สุนัข: หางอยู่ท้ายลำตัว (+Y)", (tlo_[1] + thi_[1]) / 2 > bhi[1] * 0.9,
      f"หาง {(tlo_[1]+thi_[1])/2:.2f} · ลำตัวท้าย {bhi[1]:.2f}")

ears = [n for n in dby if n.startswith("ear_")]
check("สุนัข: มีหู 2 ข้าง", len(ears) == 2, str(ears))
# หูต้อง "โผล่พ้นยอดหัว" (ฐานอาจฝังในหัวได้ แต่ยอดต้องอยู่สูงกว่า)
check("สุนัข: หูโผล่พ้นยอดหัว", all(bx(dby[n])[1][2] > hhi[2] + 0.02 for n in ears),
      str([round(bx(dby[n])[1][2], 3) for n in ears]) + f" vs ยอดหัว {hhi[2]:.3f}")
check("สุนัข: หูอยู่บนหัว (ช่วง Y ไม่พ้นหัว)", all(
      hlo[1] - 0.05 <= (bx(dby[n])[0][1] + bx(dby[n])[1][1]) / 2 <= hhi[1] + 0.05 for n in ears),
      str([round((bx(dby[n])[0][1] + bx(dby[n])[1][1]) / 2, 3) for n in ears]))

# ⚠️ ตาต้องพ้นความกว้างของปาก (เคยมองไม่เห็นเพราะซ่อนหลังปาก)
eyes = [n for n in dby if n.startswith("eye_")]
check("สุนัข: มีตา 2 ข้าง", len(eyes) == 2, str(eyes))
muzzle_half_w = (mhi[0] - mlo[0]) / 2
eye_inner = min(min(abs(bx(dby[n])[0][0]), abs(bx(dby[n])[1][0])) for n in eyes)
check("สุนัข: ตาอยู่นอกความกว้างของปาก (มองเห็นได้จริง)", eye_inner >= muzzle_half_w - 0.005,
      f"ตาในสุด {eye_inner:.3f} · ปากครึ่งกว้าง {muzzle_half_w:.3f}")
eye_front = min(bx(dby[n])[0][1] for n in eyes)
check("สุนัข: ตาอยู่ด้านหน้าหัว (ไม่จมในหัว)", eye_front < (hlo[1] + hhi[1]) / 2,
      f"ตา {eye_front:.3f} · กลางหัว {(hlo[1]+hhi[1])/2:.3f}")

if "collar" in dby:
    clo2, chi2 = bx(dby["collar"])
    check("สุนัข: ปลอกคออยู่ระหว่างลำตัวกับหัว",
          hhi[1] <= (clo2[1] + chi2[1]) / 2 <= blo[1] + 0.05,
          f"คอ {(clo2[1]+chi2[1])/2:.2f}")

lo, hi = ml.bbox([v for _n, (vs, _f), _m in dparts for v in vs])
check("สุนัข: สมมาตรซ้าย-ขวา (กลาง X ≈ 0)", abs((lo[0] + hi[0]) / 2) < 0.03,
      f"{(lo[0]+hi[0])/2:.3f}")
check("สุนัข: ทุกชิ้นเหนือพื้น (ไม่จม)", lo[2] >= -0.02, f"{lo[2]:.3f}")
check("สุนัข: ความสูงใกล้ค่าจริงของสุนัข (0.9–1.6 ม.)", 0.9 <= drep["height_m"] <= 1.6,
      str(drep["height_m"]))
d2 = db.build(json.loads(json.dumps(dspec)))
check("สุนัข: deterministic", [round(c, 9) for v in dparts[0][1][0] for c in v] ==
      [round(c, 9) for v in d2[0][1][0] for c in v])

# ===========================================================================
section("[3] ส่งออก .obj ได้ทั้งสองแบบ")
# ===========================================================================
for label, parts, rep, fname in (("ต้นไม้", tparts, trep, "tree"), ("สุนัข", dparts, drep, "dog")):
    with tempfile.TemporaryDirectory() as td:
        obj = ml.write_obj(pathlib.Path(td) / f"{fname}.obj", parts,
                           pathlib.Path(td) / f"{fname}.mtl")
        txt = obj.read_text(encoding="utf-8").splitlines()
        vs = [ln for ln in txt if ln.startswith("v ")]
        fs = [ln for ln in txt if ln.startswith("f ")]
        check(f"{label}: จำนวน v/f ตรงกับเมช",
              len(vs) == rep["vertices"] and len(fs) == rep["faces"], f"{len(vs)}/{len(fs)}")
        check(f"{label}: ดัชนีไม่ล้น",
              all(1 <= int(t.split("/")[0]) <= len(vs) for ln in fs for t in ln.split()[1:]))
        check(f"{label}: มี mtllib/usemtl", any(ln.startswith("mtllib ") for ln in txt)
              and any(ln.startswith("usemtl ") for ln in txt))
        check(f"{label}: มี o ครบทุกชิ้น", sum(1 for ln in txt if ln.startswith("o ")) == rep["parts"])

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
