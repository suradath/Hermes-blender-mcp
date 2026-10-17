# -*- coding: utf-8 -*-
"""
preview_blockout.py — วาดภาพตัวอย่าง (front view) ของ blockout **ก่อน** ติดตั้ง Blender
=======================================================================================
เครื่องมือนี้เป็นตัวช่วยสำหรับพัฒนา (dev-only) — ต้องมี Pillow::

    python -m pip install pillow
    python tools/preview_blockout.py --ref รูปต้นแบบ.jpg --out preview.png

ทำไมมี: สคริปต์ ``examples/character_blockout.py`` คืนแต่ตัวเลข "สูงกี่เมตร" ซึ่งตรวจ
สัดส่วนให้ AI ได้ แต่**คน** อยากเห็นภาพก่อนว่าใกล้รูปต้นแบบแค่ไหน เครื่องมือนี้จึง:
  1. รันสคริปต์นั้นจริง (ผ่านสะพาน + ``bpy`` ปลอม) แล้ว **ดึงเรขาคณิตจริง** ของทุกชิ้น
     — ไม่ได้วาดขึ้นใหม่จากตัวเลขที่เดา
  2. วาดมุมมองด้านหน้า (แกน X-Z) ด้วยสีวัสดุจริงของแต่ละชิ้น
  3. วางเทียบกับรูปต้นแบบที่ย่อให้สูงเท่ากัน พร้อมเส้นบอกจุดอ้างอิงที่วัดจากรูป

⚠️ ภาพที่ได้คือ "ผังเรขาคณิต" ไม่ใช่ภาพเรนเดอร์จาก Blender — ถ้าต้องการภาพเรนเดอร์จริง
ให้ใช้เครื่องมือ ``get_viewport_screenshot`` บนเครื่องที่มี Blender
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_spec(spec_path: pathlib.Path, overrides: dict | None = None) -> tuple[list[dict], dict]:
    """รันสคริปต์สเปกผ่านสะพาน (bpy ปลอม) แล้วคืนเรขาคณิตของทุกชิ้น + สรุปผล"""
    probe = f'''
import json, sys, pathlib
sys.path.insert(0, {str(ROOT)!r}); sys.path.insert(0, {str(ROOT / "tests")!r})
import fake_bpy
sys.modules["bpy"] = fake_bpy
import blender_bridge as br
src = pathlib.Path({str(spec_path)!r}).read_text(encoding="utf-8")
marker = "\\n}}\\n"
_i = src.find(marker)
if {bool(overrides)} and _i >= 0:
    import json as _j
    # ต้องใช้ repr() ของค่าที่โหลดจาก JSON — json.dumps() ให้ false/true ซึ่งไพทอนไม่รู้จัก
    src = src[:_i + len(marker)] + "CHARACTER.update(" + repr(_j.loads({json.dumps(overrides)!r})) + ")\\n" + src[_i + len(marker):]
r = br.handle_message({{"id": 1, "method": "call_tool",
    "params": {{"name": "execute_blender_script",
                "arguments": {{"code": src, "return_variables": "result"}}}}}})
out = {{"ok": r.get("ok"), "error": r.get("error"),
       "summary": (r.get("result") or {{}}).get("result") or {{}},
       "parts": []}}
for o in fake_bpy.data.objects:
    col = None
    if o.data is not None and len(o.data.materials):
        m = fake_bpy.data.materials.get(o.data.materials[0].name)
        if m is not None:
            n = m.node_tree.nodes.get("Principled BSDF")
            if n is not None:
                c = n.inputs["Base Color"].default_value
                col = [float(c[0]), float(c[1]), float(c[2])]
    out["parts"].append({{"name": o.name, "loc": list(o.location), "scale": list(o.scale),
                          "rot": list(o.rotation_euler), "color": col}})
print("JSON" + json.dumps(out))
'''
    res = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120)
    line = next((ln for ln in res.stdout.splitlines() if ln.startswith("JSON")), None)
    if not line:
        raise SystemExit("รันสคริปต์ไม่ได้:\n" + (res.stderr or res.stdout)[-1500:])
    data = json.loads(line[4:])
    if not data.get("ok"):
        raise SystemExit("สคริปต์คืนข้อผิดพลาด: " + str(data.get("error"))[:400])
    return data["parts"], data["summary"]


FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/tlwg/Garuda.ttf",          # ไทย (มีเกือบทุกเครื่อง Linux ไทย)
    "/usr/share/fonts/opentype/tlwg/Loma.otf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",    # ไม่มีสระไทย ใช้เป็นทางสุดท้าย
]


def _font(size: int):
    from PIL import ImageFont
    for cand in FONT_CANDIDATES:
        if pathlib.Path(cand).is_file():
            try:
                f = ImageFont.truetype(cand, size)
                f._picked = cand                                  # ไว้รายงานว่าใช้ตัวไหน
                return f
            except Exception:                                     # noqa: BLE001, S112
                continue
    return ImageFont.load_default()


def _char_bbox(im, step: int = 2):
    """กรอบของ "ตัวละคร" ในรูป (ตัดพื้นขาว/เงาเทาออก) — ใช้จัดสเกลให้เทียบกันได้จริง"""
    px = im.load()
    W, H = im.size
    l, t_, r, b = W, H, 0, 0
    for y in range(0, H, step):
        for x in range(0, W, step):
            cr, cg, cb = px[x, y]
            if (max(cr, cg, cb) - min(cr, cg, cb)) > 18 or min(cr, cg, cb) < 120:
                l, t_ = min(l, x), min(t_, y)
                r, b = max(r, x), max(b, y)
    return (l, t_, r + 1, b + 1) if r > l and b > t_ else None


def _half_extent_x(part: dict) -> float:
    """ครึ่งความกว้างตามแกน X — ชิ้นที่หมุน 90° รอบ Y ความยาวจะไปอยู่ตามแกน X"""
    return abs(part["scale"][2] if abs(part["rot"][1]) > 1.0 else part["scale"][0])


def draw(parts: list[dict], summary: dict, ref: pathlib.Path | None, out: pathlib.Path,
         height_px: int = 720) -> pathlib.Path:
    """วาดผัง 2 มิติ (แกน X-Z) ของทุกชิ้นที่สคริปต์สร้างจริง เทียบกับรูปต้นแบบ"""
    from PIL import Image, ImageDraw

    pad, gap, top_pad = 46, 70, 34
    total_m = float(summary.get("height_m") or 1.0)
    S = height_px / total_m
    ext = max(abs(p["loc"][0]) + _half_extent_x(p) for p in parts)     # ครึ่งกว้างสุด (เมตร)
    panel_w = int(ext * 2 * S) + pad * 2

    # แยกรูปต้นแบบ + จัดสเกลให้ "ตัวละคร" สูงเท่ากับผัง (ไม่ใช่สูงเท่ากรอบรูป)
    ref_img, ref_bbox = None, None
    if ref and pathlib.Path(ref).is_file():
        raw = Image.open(ref).convert("RGB")
        ref_bbox = _char_bbox(raw)
        raw = raw.crop(ref_bbox) if ref_bbox else raw
        ratio = height_px / raw.height
        ref_img = raw.resize((max(1, int(raw.width * ratio)), height_px))

    ref_w = ref_img.width if ref_img is not None else panel_w
    W = pad + ref_w + gap + panel_w + pad
    canvas = Image.new("RGB", (W, top_pad + height_px + 96), (252, 252, 254))
    d = ImageDraw.Draw(canvas)
    big, small = _font(21), _font(17)

    top_y, base_y = top_pad, top_pad + height_px

    if ref_img is not None:
        canvas.paste(ref_img, (pad, top_y))
        d.rectangle([pad - 1, top_y - 1, pad + ref_img.width, base_y], outline=(205, 205, 210))
    d.text((pad, 8), "ต้นแบบ (รูปที่แนบ)", fill=(25, 25, 30), font=big)

    x0 = pad + ref_w + gap
    cx = x0 + panel_w // 2
    for p in sorted(parts, key=lambda q: -q["loc"][2]):                # บนลงล่าง
        hx, hz = _half_extent_x(p) * S, abs(p["scale"][2]) * S
        if abs(p["rot"][1]) > 1.0:                                     # หมุนแล้ว → สลับแกน
            hx, hz = abs(p["scale"][2]) * S, abs(p["scale"][0]) * S
        px_, py_ = cx + p["loc"][0] * S, base_y - p["loc"][2] * S
        col = tuple(int(255 * c) for c in (p["color"] or [0.8, 0.8, 0.8]))
        d.rectangle([px_ - hx, py_ - hz, px_ + hx, py_ + hz], fill=col, outline=(70, 70, 70))
    d.rectangle([x0 - 1, top_y - 1, x0 + panel_w, base_y], outline=(205, 205, 210))
    d.text((x0, 8), "blockout ที่สคริปต์สร้าง (ผังเรขาคณิต · ไม่ใช่ภาพเรนเดอร์)",
           fill=(25, 25, 30), font=big)

    r = summary.get("ratios") or {}
    head_h = float(r.get("head_h") or 0)
    for label, frac in [("ยอดหัว", 1.0), ("คอ", 1.0 - head_h), ("เป้า", float(r.get("crotch_z") or 0)),
                        ("พื้น", 0.0)]:
        y = base_y - frac * height_px
        d.line([6, y, W - pad // 2, y], fill=(228, 120, 120), width=1)
        d.text((8, y - 19), label, fill=(170, 55, 55), font=small)

    info = (f"จำนวนหัว {summary.get('height_heads')} · สูง {summary.get('height_m')} ม. · "
            f"{summary.get('part_count')} ชิ้น · ท่า {summary.get('pose')} · "
            f"เทียบได้กับ: หัว {r.get('head_h')} · ช่วงแขน {r.get('arm_span')} · "
            f"ไหล่ {r.get('shoulder_w')} · เป้า {r.get('crotch_z')} · ขา {r.get('leg_len')} "
            f"(1.0 = ความสูงรวม · ที่วัดจากรูป: หัว 0.329 · แขน 0.872 · เป้า 0.241 · ขา 0.24)")
    d.text((8, base_y + 22), info, fill=(40, 40, 60), font=small)
    d.text((8, base_y + 46), f"ฟอนต์: {pathlib.Path(getattr(small, '_picked', 'default')).name}"
                             f" · ฟอนต์ที่รูปต้นแบบตัดกรอบ: {ref_bbox}",
           fill=(120, 120, 130), font=small)
    canvas.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="วาดผัง blockout เทียบกับรูปต้นแบบ")
    ap.add_argument("--spec", default=str(ROOT / "examples" / "character_blockout.py"))
    ap.add_argument("--ref", default="")
    ap.add_argument("--out", default="preview.png")
    ap.add_argument("--set", default="", help='ทับค่าสเปก เช่น \'{"heads_tall":3.04,"pose":"tpose"}\'')
    a = ap.parse_args()
    overrides = json.loads(a.set) if a.set.strip() else {}
    parts, summary = run_spec(pathlib.Path(a.spec), overrides)
    out = draw(parts, summary, pathlib.Path(a.ref) if a.ref else None, pathlib.Path(a.out))
    print(f"✅ เขียนภาพแล้ว: {out} ({summary.get('part_count')} ชิ้น · "
          f"{summary.get('height_heads')} หัว)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
