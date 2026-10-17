#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_thai_house.py — ทดสอบบ้านทรงไทยโพลิกอน (stdlib ล้วน · ไม่ต้องมี Blender)

ตรวจ "ความถูกต้องเชิงสถาปัตยกรรม" ไม่ใช่แค่ภาพสวย:
  · ทุกชิ้นปิดสนิท · ออยเลอร์ 2 · ปริมาตรบวก
  · เสาแตะพื้น · พื้นอยู่ระดับเสา · ฝาอยู่บนพื้น · หลังคาอยู่บนฝา · สันอยู่บนสุด
  · ช่อฟ้าต้อง "นั่งบนสัน" (ไม่ลอย — เคยพลาดมาแล้ว) · หลังคาต้องชันแบบไทย (>= 35°)
  · บันไดต้องไล่ลงจากระเบียงถึงพื้น · ราวระเบียงต้องไม่ทับบันได (ตรวจด้วย AABB)
  · หน้าจั่ว/ป้านลม/ช่อฟ้า ต้องอยู่ "นอก" ตัวหลังคา มองเห็นได้จริง
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import mesh_lib as ml              # noqa: E402
import thai_house_builder as th     # noqa: E402

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


def box(part):
    return ml.bbox(part[0])


def overlap_3d(a, b, eps=0.005) -> bool:
    (alo, ahi), (blo, bhi) = box(a), box(b)
    return all(alo[i] < bhi[i] - eps and blo[i] < ahi[i] - eps for i in range(3))


SPEC = json.loads(json.dumps(th.SPEC))
parts = th.build(SPEC)
rep = th.summarize(parts)
by_name = {n: p for n, p, _m in parts}
names = [n for n, _p, _m in parts]

# ===========================================================================
section("[1] ทุกชิ้นต้องเป็นเมชปิดสนิท")
# ===========================================================================
bad = []
for n, p, _m in parts:
    r = ml.check_part(n, *p)
    if not (r["watertight"] and r["outward"] and r["finite"] and not r["duplicate_verts"]
            and euler(p) == 2 and r["volume_m3"] > 0):
        bad.append(f"{n}: {r['why']}")
check(f"ทั้ง {rep['parts']} ชิ้นปิดสนิท/หน้าหันถูก/ออยเลอร์ 2", not bad, "; ".join(bad[:4]))
check("มีชิ้นส่วนจำนวนมากพอ (>= 70)", rep["parts"] >= 70, str(rep["parts"]))

# ===========================================================================
section("[2] ความถูกต้องเชิงสถาปัตยกรรม (ระดับชั้นต้องต่อกันจริง)")
# ===========================================================================
ph = SPEC["post_height"]
ft = SPEC["floor_thickness"]
wh = SPEC["wall_height"]
rl = SPEC["roof_lower_height"]
ru = SPEC["roof_upper_height"]
floor_top = ph + ft
wall_top = floor_top + wh
ridge = wall_top + rl + ru

posts = [p for n, p, _m in parts if n.startswith("post_")]
plo = min(box(p)[0][2] for p in posts)
phi_ = max(box(p)[1][2] for p in posts)
check("เสาแตะพื้นจริง (ล่างสุด z ≈ 0)", abs(plo) < 0.01, f"{plo:.4f}")
check("เสาสูงถึงระดับพื้น (ยอดเสา ≈ post_height)", abs(phi_ - ph) < 0.01, f"{phi_:.4f} vs {ph}")

dlo, dhi = box(by_name["deck"])
check("พื้นอยู่บนยอดเสา (ล่างของพื้น ≈ post_height)", abs(dlo[2] - ph) < 0.01, f"{dlo[2]:.4f}")
check("ยอดพื้น = post_height + floor_thickness", abs(dhi[2] - floor_top) < 0.01, f"{dhi[2]:.4f}")

wlo, whi = box(by_name["walls"])
check("ฝาเรือนตั้งอยู่บนพื้น (ล่างของฝา ≈ ยอดพื้น)", abs(wlo[2] - floor_top) < 0.01, f"{wlo[2]:.4f}")
check("ฝาสูง = wall_height", abs((whi[2] - wlo[2]) - wh) < 0.01, f"{whi[2]-wlo[2]:.4f}")

rlo, rhi = box(by_name["roof_lower"])
check("หลังคาชั้นล่างวางบนยอดฝา", abs(rlo[2] - wall_top) < 0.02, f"{rlo[2]:.4f} vs {wall_top}")
ulo, uhi = box(by_name["roof_upper"])
check("หลังคาชั้นบนวางบนชั้นล่าง (ต่อเนื่อง)", abs(ulo[2] - (wall_top + rl)) < 0.02,
      f"{ulo[2]:.4f} vs {wall_top + rl}")
check("สันหลังคาคือจุดสูงสุดของหลังคาชั้นบน", abs(uhi[2] - ridge) < 0.02, f"{uhi[2]:.4f} vs {ridge}")

# ระยะชายคายื่น (เอกลักษณ์บ้านไทย)
roof_base = SPEC["depth"] + 2 * SPEC["roof_overhang_y"]
roof_len = SPEC["width"] + 2 * SPEC["roof_overhang_x"]
check("ชายคายื่นพ้นฝาข้างละ >= 0.8 ม.",
      (rhi[1] - rlo[1]) / 2 - SPEC["depth"] / 2 >= 0.8, f"{((rhi[1]-rlo[1])/2 - SPEC['depth']/2):.2f} ม.")
check("ชายคาหัว-ท้ายยื่น >= 0.8 ม.",
      (rhi[0] - rlo[0]) / 2 - SPEC["width"] / 2 >= 0.8, f"{((rhi[0]-rlo[0])/2 - SPEC['width']/2):.2f} ม.")

# หลังคาต้องชันแบบไทย
pitch = math.degrees(math.atan2(rl, roof_base / 2))
check("หลังคาชัน >= 35° (เอกลักษณ์บ้านไทย)", pitch >= 35.0, f"{pitch:.1f}°")

# ช่อฟ้า: ต้องนั่งบนสัน ไม่ลอย (บั๊กที่เคยเกิด) และอยู่ในแนวสัน
up_len = roof_len * (SPEC["roof_upper_scale"] + 0.16)
# ── ช่อฟ้า: สร้างจากหลายท่อนที่เอียงเพิ่มขึ้น → ต้อง "โค้ง" จริงและนั่งบนสัน ──
for side_tag, label in (("chofa_L", "ซ้าย"), ("chofa_R", "ขวา")):
    seg_names = [f"{side_tag}_{k}" for k in range(5)]
    check(f"ช่อฟ้า{label}: มีครบ 5 ท่อนต่อกัน (สร้างส่วนโค้ง)",
          all(n in by_name for n in seg_names), str([n for n in seg_names if n not in by_name]))
    segs = [by_name[n][0] for n in seg_names if n in by_name]
    if not segs:
        continue
    allv = [v for s in segs for v in s]
    lo_c, hi_c = ml.bbox(allv)
    check(f"ช่อฟ้า{label}: ฐานติดสันหลังคา", -0.15 <= (lo_c[2] - ridge) <= 0.25,
          f"ล่าง {lo_c[2]:.3f} · สัน {ridge:.3f}")
    check(f"ช่อฟ้า{label}: อยู่ในแนวสัน (|y| < 0.2)", abs((lo_c[1] + hi_c[1]) / 2) < 0.2,
          f"{(lo_c[1]+hi_c[1])/2:.3f}")
    check(f"ช่อฟ้า{label}: ไม่ยื่นพ้นหลังคาชั้นบนเกิน 0.4 ม.",
          max(abs(lo_c[0]), abs(hi_c[0])) <= up_len / 2 + 0.40,
          f"{max(abs(lo_c[0]), abs(hi_c[0])):.3f} vs {up_len/2:.3f}")
    check(f"ช่อฟ้า{label}: สูง >= 0.8 ม. (มองเห็นแต่ไกล)", (hi_c[2] - lo_c[2]) >= 0.8,
          f"{hi_c[2]-lo_c[2]:.2f} ม.")
    # ความโค้ง: ท่อนบนต้องเยื้องออกนอกกว่าท่อนล่าง
    x_first = abs((ml.bbox(segs[0])[0][0] + ml.bbox(segs[0])[1][0]) / 2)
    x_last = abs((ml.bbox(segs[-1])[0][0] + ml.bbox(segs[-1])[1][0]) / 2)
    check(f"ช่อฟ้า{label}: โค้งออกจริง (ท่อนปลายเยื้องออกมากกว่าท่อนโคน)",
          x_last > x_first + 0.05, f"{x_first:.3f} → {x_last:.3f}")

# บันได: ไล่ลงจากระเบียงถึงพื้น
stairs = [(n, p) for n, p, _m in parts if n.startswith("stair_") and "rail" not in n
          and "stringer" not in n]
zs = sorted(box(p)[1][2] for _n, p in stairs)
check("มีขั้นบันไดตามจำนวนที่ตั้งไว้", len(stairs) == int(SPEC["stair_steps"]), str(len(stairs)))
check("ขั้นบันไดไล่ระดับลงจริง (ขั้นสูงสุดอยู่บน ขั้นต่ำสุดอยู่ล่าง)",
      zs[-1] > zs[0] + 0.5, f"{zs[0]:.2f}..{zs[-1]:.2f}")
check("ขั้นล่างสุดใกล้พื้น (<= 0.6 ม.)", zs[0] <= 0.6, f"{zs[0]:.2f}")
check("ขั้นบนสุดอยู่ระดับพื้นระเบียง (±0.3 ม.)", abs(zs[-1] - floor_top) <= 0.3,
      f"{zs[-1]:.2f} vs {floor_top:.2f}")
ylo = min(box(p)[0][1] for _n, p in stairs)
check("บันไดอยู่ด้านหน้าระเบียง (ยื่นออกไปทาง -Y นอกฝาเรือน)",
      ylo < -SPEC["depth"] / 2 - SPEC["veranda_depth"] + 0.3, f"y ต่ำสุด {ylo:.2f}")

# ราวระเบียง: ระดับถูก + ต้องไม่ทับบันได (ตรวจด้วย AABB จริง ไม่ใช่ดูภาพ)
rail_h = SPEC["rail_height"]
rails = [p for n, p, _m in parts if n.startswith("rail_front_top")]
check("ราวบนของระเบียงอยู่ที่ระดับ rail_height",
      all(abs(box(p)[1][2] - (floor_top + rail_h)) < 0.06 for p in rails), str(len(rails)))
rail_all = [p for n, p, _m in parts if n.startswith(("rail_", "baluster_"))]
stair_all = [p for n, p, _m in parts if n.startswith("stair")]
clash = [(i, j) for i, a in enumerate(rail_all) for j, b in enumerate(stair_all) if overlap_3d(a, b)]
check("ราวระเบียงไม่ทับบันไดเลย (0 คู่)", not clash, f"ทับ {len(clash)} คู่")

# ความสมมาตรซ้าย-ขวา และทิศทางระเบียง
lo, hi = box(([v for _n, (vs, _f), _m in parts for v in vs], []))
check("บ้านสมมาตรตามแกน X (กลาง ≈ 0)", abs((lo[0] + hi[0]) / 2) < 0.05, f"{(lo[0]+hi[0])/2:.3f}")
check("ระเบียงอยู่ด้านหน้า (-Y) ไม่ใช่ด้านหลัง", min(box(p)[0][1] for p in [by_name["deck"]]) < -SPEC["depth"] / 2 - 1.0)
check("ทุกชิ้นอยู่เหนือพื้นดิน (ไม่จม)", lo[2] >= -0.15, f"{lo[2]:.3f}")

# หน้าจั่ว/ป้านลม ต้องอยู่ "นอก" ตัวหลังคา จึงจะมองเห็น
gables = [p for n, p, _m in parts if n.startswith("gable_")]
check("หน้าจั่วอยู่ปลายหลังคาทั้งสองข้าง", len(gables) == 2, str(len(gables)))
for p in gables:
    glo, ghi = box(p)
    check("หน้าจั่วอยู่ที่/nอกปลายหลังคา (มองเห็นได้)",
          max(abs(glo[0]), abs(ghi[0])) >= roof_len / 2 - 0.01,
          f"{max(abs(glo[0]), abs(ghi[0])):.3f} vs {roof_len/2:.3f}")
barges = [p for n, p, _m in parts if n.startswith("barge_")]
check("มีป้านลม 4 แผ่น (2 ด้าน × 2 หัวเรือน)", len(barges) == 4, str(len(barges)))
for p in barges:
    blo, bhi = box(p)
    check("ป้านลมอยู่พ้นแผงหน้าจั่ว (ไม่ซ่อนข้างใน)",
          max(abs(blo[0]), abs(bhi[0])) > roof_len / 2 + 0.05,
          f"{max(abs(blo[0]), abs(bhi[0])):.3f}")

# ===========================================================================
section("[3] ปุ่มปรับแบบต้องทำงานจริง")
# ===========================================================================
def build_with(**over):
    s = json.loads(json.dumps(SPEC))
    s.update(over)
    p = th.build(s)
    return th.summarize(p), p


r_plain, _ = build_with(chofa=False, bargeboards=False, balusters=False, braces=False, ground=False)
check("ปิดช่อฟ้า/ป้านลม/ลูกกรง/ค้ำยัน/พื้นดิน → ชิ้นน้อยลง", r_plain["parts"] < rep["parts"],
      f"{r_plain['parts']} vs {rep['parts']}")
check("ปิดของเสริมแล้วยังปิดสนิททุกชิ้น", r_plain["all_watertight"], str(r_plain["bad_parts"]))
r_more, p_more = build_with(stair_steps=8)
check("เพิ่มขั้นบันไดเป็น 8 → ชิ้นมากขึ้น", r_more["parts"] > rep["parts"], str(r_more["parts"]))
r_ch, _ = build_with(chamfer=0.0)
check("chamfer=0 → จุดน้อยลง", r_ch["vertices"] < rep["vertices"], f"{r_ch['vertices']} vs {rep['vertices']}")
r_big, _ = build_with(width=8.0, depth=5.5)
check("ขยายขนาดเรือนได้ (กว้างขึ้นจริง)", r_big["size_m"][0] > rep["size_m"][0],
      f"{r_big['size_m'][0]} vs {rep['size_m'][0]}")

# ===========================================================================
section("[4] ไฟล์ .obj/.mtl")
# ===========================================================================
with tempfile.TemporaryDirectory() as td:
    obj = ml.write_obj(pathlib.Path(td) / "h.obj", parts, pathlib.Path(td) / "h.mtl")
    txt = obj.read_text(encoding="utf-8").splitlines()
    vs = [ln for ln in txt if ln.startswith("v ")]
    fs = [ln for ln in txt if ln.startswith("f ")]
    check("จำนวน v/f ตรงกับเมช", len(vs) == rep["vertices"] and len(fs) == rep["faces"],
          f"{len(vs)}/{rep['vertices']} · {len(fs)}/{rep['faces']}")
    idx_ok = all(1 <= int(tok.split("/")[0]) <= len(vs) for ln in fs for tok in ln.split()[1:])
    check("ดัชนีใบหน้าไม่ล้น", idx_ok)
    check("มี mtllib + usemtl", any(ln.startswith("mtllib ") for ln in txt)
          and any(ln.startswith("usemtl ") for ln in txt))
    check("มี o ครบทุกชิ้น", sum(1 for ln in txt if ln.startswith("o ")) == rep["parts"])
    m = (pathlib.Path(td) / "h.mtl").read_text(encoding="utf-8")
    for key in ("post", "deck", "wall", "roof", "roof2", "trim", "frame", "opening", "rail", "ground"):
        check(f"วัสดุ «{key}» อยู่ใน .mtl", f"newmtl {key}" in m)
    check("สีหลังคา terracotta อยู่ในไฟล์", "0.55" in m)

# ===========================================================================
section("[5] สร้างซ้ำได้ผลเดิม")
# ===========================================================================
p2 = th.build(json.loads(json.dumps(SPEC)))
same = [round(c, 9) for v in parts[0][1][0] for c in v] == [round(c, 9) for v in p2[0][1][0] for c in v]
check("deterministic (สร้างซ้ำได้จุดเดิม)", same)

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
