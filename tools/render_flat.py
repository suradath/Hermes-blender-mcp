# -*- coding: utf-8 -*-
"""
render_flat.py — ตัวเรนเดอร์แบบ flat shading อย่างง่าย (Pillow · ไม่ต้องใช้ Blender)
=====================================================================================
ใช้ดู "หน้าตา" ของเมชที่สร้างจาก ``mesh_lib`` ก่อนไปเข้า Blender — งาน low-poly
ที่ทุกหน้าแบนและหันเป็นเหลี่ยม การเรนเดอร์แบบ "ระนาบสีเรียบ + แสงทิศเดียว" ให้ภาพ
ที่ใกล้เคียงกับรูปเรนเดอร์จริงพอสมควร จึงใช้ตรวจสัดส่วน/รูปทรงได้ก่อนติดตั้ง Blender

ข้อจำกัด (พูดตรง ๆ): ไม่มีเงาตกกระทบ · ไม่มีแสงสะท้อน · ไม่มี anti-alias หลายชั้น
· เรียงหน้าไกล-ใกล้แบบ painter's algorithm (พอเพียงกับรูปนูนที่ใช้จริง แต่ถ้าชิ้นซ้อนกัน
มาก ๆ อาจมีหน้าผิดลำดับได้บ้าง)
"""

from __future__ import annotations

import math


def _rot_x(p, deg):
    """เอียงกล้อง (ก้มลงมอง) — หมุนรอบแกน X"""
    if not deg:
        return p
    a = math.radians(deg)
    return (p[0], p[1] * math.cos(a) + p[2] * math.sin(a), -p[1] * math.sin(a) + p[2] * math.cos(a))


def _rot_z(p, deg):
    if not deg:
        return p
    a = math.radians(deg)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a), p[2])


def render(parts, out_path, width=560, height=780, view="front", rot_z=0.0, rot_x=0.0,
           light=(-0.42, -0.72, 0.55), ambient=0.34, background=(250, 250, 252),
           outline=(40, 40, 48), pad_frac=0.05, draw_outline=True,
           shadow=False, gradient=False, shadow_bbox=None,
           no_outline_mats=()):
    """เรนเดอร์มุมมองด้านหน้า (มองจาก -Y) · ``rot_z`` > 0 = หมุนตัวเป็นมุม 3/4

    parts = [(ชื่อ, (verts, faces), วัสดุ), ...] โดยวัสดุ = {"name":…, "color":(r,g,b)}
    คืนพจนานุกรมสรุป (จำนวนหน้าที่เรนเดอร์ · ขนาดพิกเซลต่อเมตร)
    """
    from PIL import Image, ImageDraw

    # รวมทุกจุดเพื่อหากรอบและสเกล (หลังหมุน)
    def xform(v):
        return _rot_z(_rot_x(v, rot_x), rot_z) if (rot_x or rot_z) else v

    all_v = []
    for _n, (verts, _f), _m in parts:
        all_v.extend(xform(v) for v in verts)
    xs = [v[0] for v in all_v]
    ys = [v[1] for v in all_v]
    zs = [v[2] for v in all_v]
    lo_x, hi_x = min(xs), max(xs)
    lo_y, hi_y = min(ys), max(ys)
    lo_z, hi_z = min(zs), max(zs)
    span_x, span_z = (hi_x - lo_x) or 1.0, (hi_z - lo_z) or 1.0
    scale = min(width * (1 - 2 * pad_frac) / span_x, height * (1 - 2 * pad_frac) / span_z)
    cx = width / 2.0 - (lo_x + hi_x) / 2.0 * scale
    cy = height / 2.0 + (lo_z + hi_z) / 2.0 * scale          # z ขึ้นบน → y จอลงล่าง

    def to_screen(q):
        """จุดที่หมุนแล้ว → พิกัดจอ (z ขึ้นบน → y จอลงล่าง)"""
        return (cx + q[0] * scale, cy - q[2] * scale)

    # เก็บทุกหน้า พร้อมความลึกและสีที่คำนวณแสงแล้ว
    light_len = math.sqrt(sum(c * c for c in light)) or 1.0
    L = tuple(c / light_len for c in light)
    tris = []
    for _name, (verts, faces), mat in parts:
        col = mat["color"]
        for f in faces:
            pts = [verts[i] for i in f]
            p0, p1, p2 = pts[0], pts[1], pts[2]
            u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
            w = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
            nrm = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            ln = math.sqrt(sum(c * c for c in nrm)) or 1.0
            nrm = tuple(c / ln for c in nrm)
            rot_pts = [xform(q) for q in pts]                 # แปลงครั้งเดียว ใช้ทั้งหน้า
            if rot_x or rot_z:
                nrm = xform(nrm)
            if nrm[1] >= 0:                                  # หันหลังให้กล้อง (มองจาก -Y)
                continue
            depth = sum(q[1] for q in rot_pts) / len(rot_pts)
            lam = max(0.0, sum(nrm[i] * L[i] for i in range(3)))
            k = ambient + (1 - ambient) * lam
            # สว่างน้อย = สีเข้มลง (ไม่ใช้ฟังก์ชันแกมมา เพื่อความง่ายและคาดเดาได้)
            fill = tuple(max(0, min(255, int(255 * c * k))) for c in col)
            tris.append((depth, [to_screen(q) for q in rot_pts], fill,
                         mat.get("name") in no_outline_mats))

    tris.sort(key=lambda t: -t[0])                            # ไกลก่อน ใกล้ทับทีหลัง
    if gradient:                                              # พื้นหลังไล่สีอ่อน ๆ
        from PIL import Image as _I
        img = _I.new("RGB", (width, height))
        _d = ImageDraw.Draw(img)
        for yy in range(height):
            k = yy / max(1, height - 1)
            col = tuple(int(background[i] + (232 + 6 * i - background[i]) * k * 0.85)
                        for i in range(3))
            _d.line([(0, yy), (width, yy)], fill=col)
    else:
        img = Image.new("RGB", (width, height), background)
    d = ImageDraw.Draw(img)
    if shadow:                                                # เงาสัมผัส (ได้หลายวง)
        from PIL import ImageFilter
        boxes = shadow_bbox if isinstance(shadow_bbox, list) else \
            [shadow_bbox or ((lo_x, lo_y, lo_z), (hi_x, hi_y, hi_z))]
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for sb in boxes:
            corners = [to_screen(xform((x, y, sb[0][2])))
                       for x in (sb[0][0], sb[1][0]) for y in (sb[0][1], sb[1][1])]
            px_ = [c[0] for c in corners]
            py_ = [c[1] for c in corners]
            cx_ = (min(px_) + max(px_)) / 2.0
            cy_ = (min(py_) + max(py_)) / 2.0
            rx_ = max(5.0, (max(px_) - min(px_)) / 2.0 * 0.90)
            ry_ = max(3.0, rx_ * 0.26)
            ld.ellipse([cx_ - rx_, cy_ - ry_, cx_ + rx_, cy_ + ry_], fill=(26, 28, 34, 122))
        img = Image.alpha_composite(img.convert("RGBA"),
                                    layer.filter(ImageFilter.GaussianBlur(9))).convert("RGB")
        d = ImageDraw.Draw(img)
    for _depth, poly, fill, skip_out in tris:
        d.polygon(poly, fill=fill, outline=None if (skip_out or not draw_outline) else outline)
    img.save(out_path)
    return {"faces_drawn": len(tris), "px_per_m": round(scale, 2), "view": view,
            "rot_z": rot_z, "width": width, "height": height}
