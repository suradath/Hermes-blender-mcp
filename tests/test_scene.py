#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_scene.py — ทดสอบ "ฉากภาพหมู่" ที่ประกอบจากทุกแบบ (stdlib ล้วน)

สิ่งที่ต้องล็อก:
  · การย้าย/หมุน/ย่อ ไม่ทำให้เมชเสีย → ทุกชิ้นยังปิดสนิท/ออยเลอร์ 2
  · ของทุกชิ้น "ยืนบนพื้น" (min z ≈ 0) ไม่ลอย/ไม่จม
  · ของจัดวาง **ไม่ทับกัน** (ตรวจ AABB ทุกคู่) — AI วิจารณ์ภาพเคยบอกว่าทับ แต่ของจริงไม่ทับ
  · มีแผ่นดินแผ่นเดียว (บ้านมีแผ่นดินของตัวเอง → ต้องปิดตอนประกอบฉาก)
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import mesh_lib as ml          # noqa: E402
import scene_builder as sc      # noqa: E402

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


parts = sc.build()
rep = sc.summarize(parts)
groups: dict[str, list] = {}
for n, p, _m in parts:
    groups.setdefault(n.split("_")[0], []).append(p)

# ===========================================================================
section("[1] เมชยังสมบูรณ์หลังแปลง (ย้าย/หมุน/ย่อ)")
# ===========================================================================
bad = []
for n, p, _m in parts:
    r = ml.check_part(n, *p)
    if not (r["watertight"] and r["outward"] and r["finite"]
            and not r["duplicate_verts"] and euler(p) == 2 and r["volume_m3"] > 0):
        bad.append(f"{n}: {r['why']}")
check(f"ทั้ง {rep['parts']} ชิ้นปิดสนิท/หันหน้าถูก/ออยเลอร์ 2 หลังแปลง", not bad,
      "; ".join(bad[:4]))
check("มีแผ่นดินแผ่นเดียวเท่านั้น", len(groups.get("ground", [])) == 1,
      str(list(groups)))

# ===========================================================================
section("[2] ของทุกชิ้นต้องยืนบนพื้น")
# ===========================================================================
check("มีของจัดวางตามที่กำหนด (>= 6 ชิ้น)",
      len([k for k in groups if k != "ground"]) == len(sc.SCENE["items"]),
      str(len([k for k in groups if k != "ground"])))
for key, ps in groups.items():
    if key == "ground":
        continue
    lo, hi = ml.bbox([v for p in ps for v in p[0]])
    check(f"{key}: ฐานอยู่บนพื้น (min z ≈ 0)", abs(lo[2]) <= 0.02, f"{lo[2]:.3f}")
    check(f"{key}: ยืนสูงเกิน 0.8 ม. (ไม่ใช่ของแบน)", hi[2] - lo[2] > 0.8, f"{hi[2]-lo[2]:.2f}")

glo, ghi = ml.bbox([v for p in groups["ground"] for v in p[0]])
check("แผ่นดินอยู่ใต้ทุกอย่าง (ยอดพื้น ≈ 0)", abs(ghi[2]) <= 0.02, f"{ghi[2]:.3f}")

# ===========================================================================
section("[3] ของจัดวางต้องไม่ทับกัน (AABB ทุกคู่)")
# ===========================================================================
keys = [k for k in groups if k != "ground"]


def bbox_of(ps):
    return ml.bbox([v for p in ps for v in p[0]])


def overlap(a, b, eps=0.02):
    (alo, ahi), (blo, bhi) = bbox_of(a), bbox_of(b)
    return all(alo[i] < bhi[i] - eps and blo[i] < ahi[i] - eps for i in range(3))


clash = [(a, b) for a, b in itertools.combinations(keys, 2) if overlap(groups[a], groups[b])]
check("ไม่มีของทับกันเลย (0 คู่)", not clash, str(clash))

# ทุกชิ้นต้องอยู่ในแผ่นดิน (ไม่ยื่นตกขอบ)
for key in keys:
    lo, hi = bbox_of(groups[key])
    check(f"{key}: อยู่ในขอบแผ่นดิน",
          lo[0] >= glo[0] - 0.05 and hi[0] <= ghi[0] + 0.05
          and lo[1] >= glo[1] - 0.05 and hi[1] <= ghi[1] + 0.05,
          f"x {lo[0]:.1f}..{hi[0]:.1f} · y {lo[1]:.1f}..{hi[1]:.1f}")

check("ขนาดฉากสมเหตุสมผล (15–35 ม.)", 15 <= rep["size_m"][0] <= 35,
      str(rep["size_m"][0]))
check("ความสูงฉาก = ความสูงบ้าน (สูงสุด)", 9.0 <= rep["height_m"] <= 12.0,
      str(rep["height_m"]))

# ===========================================================================
section("[4] ส่งออกไฟล์ + ความแน่นอน")
# ===========================================================================
with tempfile.TemporaryDirectory() as td:
    obj = ml.write_obj(pathlib.Path(td) / "s.obj", parts, pathlib.Path(td) / "s.mtl")
    txt = obj.read_text(encoding="utf-8").splitlines()
    vs = [ln for ln in txt if ln.startswith("v ")]
    fs = [ln for ln in txt if ln.startswith("f ")]
    check("จำนวน v/f ตรงกับเมช", len(vs) == rep["vertices"] and len(fs) == rep["faces"],
          f"{len(vs)}/{len(fs)}")
    check("ดัชนีไม่ล้น", all(1 <= int(t.split("/")[0]) <= len(vs) for ln in fs for t in ln.split()[1:]))
    check("มี mtllib/usemtl", any(ln.startswith("mtllib ") for ln in txt)
          and any(ln.startswith("usemtl ") for ln in txt))
    check("มี o ครบทุกชิ้น", sum(1 for ln in txt if ln.startswith("o ")) == rep["parts"])

p2 = sc.build()
same = [round(c, 9) for v in parts[-1][1][0] for c in v] == [round(c, 9) for v in p2[-1][1][0] for c in v]
check("deterministic (สร้างซ้ำได้ผลเดิม)", same)

# ปรับสเปกฉากได้
scene2 = json.loads(json.dumps(sc.SCENE))
scene2["items"] = scene2["items"][:2]
r2 = sc.summarize(sc.build(scene2))
check("ตัดของในฉากได้ (แก้สเปกแล้วชิ้นน้อยลง)", r2["parts"] < rep["parts"],
      f"{r2['parts']} vs {rep['parts']}")
check("ฉากที่ตัดของแล้วยังปิดสนิททุกชิ้น", r2["all_watertight"], str(r2["bad_parts"]))

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
