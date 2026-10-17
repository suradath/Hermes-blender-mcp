# -*- coding: utf-8 -*-
"""
mesh_lib.py — เมชเรขาคณิตบริสุทธิ์ (ไม่ต้องใช้ Blender · stdlib ล้วน)
=====================================================================
ทำไมต้องมี: blockout ด้วยกล่องทื่อ ๆ ดู "หุ่นกล่อง" ไม่ใกล้รูปเรนเดอร์ low-poly
ที่คุณครูแนบ — ของจริงมี "การลบมุม" (chamfer/bevel) ทุกชิ้น, หัวเป็นเหลี่ยมหลายด้าน,
มือเป็นถุงมือมีนิ้วโป้ง, เท้าเป็นลิ่ม · งานแบบนี้ทำได้ด้วย **เรขาคณิตที่คำนวณเอง**
ไม่ต้องพึ่งการปั้นมือ

จุดสำคัญที่ทำให้ตรวจสอบได้: เมชทั้งหมดถูกสร้างเป็น "ข้อมูลล้วน" (รายการจุด + หน้า)
จึง **ทดสอบได้ทุกชิ้นบนเครื่องนี้** ว่า:
  · ปิดสนิทจริงไหม (ทุกเส้นเชื่อมมี 2 หน้า)
  · หน้าหันออกนอกจริงไหม (ปริมาตรมีเครื่องหมายถูก)
  · ไม่มีจุดซ้ำ/หน้าเสื่อม/ค่าอนันต์
  · ขนาดตรงกับสเปกที่สั่งไหม
แล้วค่อยส่งเข้า Blender ด้วยคำสั่งเดียว (`mesh.from_pydata`) หรือส่งออกเป็น .obj

ทุกฟังก์ชันคืนค่า ``(verts, faces)`` โดย verts = [(x,y,z), ...] · faces = [[i,j,k], ...]
"""

from __future__ import annotations

import math

EPS = 1e-9


# ───────────────────────────── พื้นฐาน ─────────────────────────────

def bbox(verts):
    """กรอบ (min, max) ของเมช"""
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def face_normal(verts, face):
    """เวกเตอร์ตั้งฉากของหน้า (ไม่ทำให้เป็นหน่วย — ขนาด = 2×พื้นที่)"""
    ax, ay, az = verts[face[0]]
    bx, by, bz = verts[face[1]]
    cx, cy, cz = verts[face[2]]
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def centroid(verts):
    n = len(verts)
    return (sum(v[0] for v in verts) / n, sum(v[1] for v in verts) / n, sum(v[2] for v in verts) / n)


def ensure_outward(verts, faces):
    """พลิกหน้าที่หันเข้าด้านใน (อาศัยจุดศูนย์กลางของชิ้น — ใช้ได้กับรูปนูนที่ปิดสนิท)"""
    c = centroid(verts)
    out = []
    for f in faces:
        n = face_normal(verts, f)
        fx, fy, fz = sum(verts[i][0] for i in f) / len(f), sum(verts[i][1] for i in f) / len(f), \
            sum(verts[i][2] for i in f) / len(f)
        if (n[0] * (fx - c[0]) + n[1] * (fy - c[1]) + n[2] * (fz - c[2])) < 0:
            out.append(list(reversed(f)))
        else:
            out.append(list(f))
    return out


def signed_volume(verts, faces):
    """ปริมาตรแบบมีเครื่องหมาย (บวก = หน้าหันออกนอกถูกต้อง · ใช้ตรวจว่าเมชปิดสนิท)"""
    tot = 0.0
    for f in faces:
        a = verts[f[0]]
        for k in range(1, len(f) - 1):
            b, c = verts[f[k]], verts[f[k + 1]]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1])
                    - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return tot


def is_watertight(verts, faces, tol=1e-6):
    """ทุกเส้นเชื่อมต้องถูกใช้ 2 หน้า (คนละทิศ) → เมชปิดสนิท ไม่มีรู

    คืน (ผ่านไหม, ข้อความอธิบาย) — ใช้ tol เพื่อทนความคลาดเคลื่อนทศนิยม
    """
    key = lambda p: (round(p[0] / tol), round(p[1] / tol), round(p[2] / tol))   # noqa: E731
    seen: dict[tuple, int] = {}
    for f in faces:
        if len(f) < 3:
            return False, f"มีหน้าที่มีจุดน้อยกว่า 3 ({len(f)})"
        for i in range(len(f)):
            a, b = key(verts[f[i]]), key(verts[f[(i + 1) % len(f)]])
            if a == b:
                return False, "มีเส้นเชื่อมที่จุดต้นกับจุดปลายซ้ำกัน (หน้าเสื่อม)"
            seen[(a, b)] = seen.get((a, b), 0) + 1
    bad = [(e, n) for e, n in seen.items() if n != 1]
    if bad:
        return False, f"มีเส้นเชื่อมที่ถูกใช้ไม่พอดี 1 ครั้งต่อทิศ: {len(bad)} เส้น"
    for (a, b), _ in list(seen.items()):
        if (b, a) not in seen:
            return False, "มีเส้นเชื่อมที่ไม่มีคู่ทิศตรงข้าม (มีรู)"
    return True, "ปิดสนิท"


def check_part(name, verts, faces):
    """ตรวจชิ้นส่วนหนึ่งชิ้นแบบครบชุด · คืนพจนานุกรมรายงาน"""
    ok_w, why = is_watertight(verts, faces)
    vol = signed_volume(verts, faces)
    lo, hi = bbox(verts)
    finite = all(math.isfinite(c) for v in verts for c in v)
    dup = len({(round(v[0], 6), round(v[1], 6), round(v[2], 6)) for v in verts}) != len(verts)
    return {"name": name, "verts": len(verts), "faces": len(faces), "watertight": ok_w,
            "why": why, "volume_m3": round(vol, 9), "outward": vol > 0 and finite,
            "finite": finite, "duplicate_verts": dup, "size": [round(hi[i] - lo[i], 4) for i in range(3)],
            "bbox_min": [round(v, 4) for v in lo], "bbox_max": [round(v, 4) for v in hi]}


# ───────────────────────────── รูปทรง ─────────────────────────────

def _solve3(p1, p2, p3):
    """จุดตัดของระนาบ 3 ระนาบ (กฎของคราเมอร์) · คืน None ถ้าขนานกัน"""
    (a1, b1, c1), d1 = p1
    (a2, b2, c2), d2 = p2
    (a3, b3, c3), d3 = p3
    det = (a1 * (b2 * c3 - b3 * c2) - b1 * (a2 * c3 - a3 * c2) + c1 * (a2 * b3 - a3 * b2))
    if abs(det) < 1e-12:
        return None
    dx = (d1 * (b2 * c3 - b3 * c2) - b1 * (d2 * c3 - d3 * c2) + c1 * (d2 * b3 - d3 * b2))
    dy = (a1 * (d2 * c3 - d3 * c2) - d1 * (a2 * c3 - a3 * c2) + c1 * (a2 * d3 - a3 * d2))
    dz = (a1 * (b2 * d3 - b3 * d2) - b1 * (a2 * d3 - a3 * d2) + d1 * (a2 * b3 - a3 * b2))
    return (dx / det, dy / det, dz / det)


def convex_from_planes(planes, tol=1e-7):
    """สร้างรูปนูนจาก "ระนาบครึ่งปริภูมิ" — n·p <= offset ทุกระนาบ

    จุดยอด = จุดตัดของระนาบ 3 ระนาบที่ยังอยู่ในทุกเงื่อนไข · หน้า = จุดทั้งหมดบนระนาบนั้น
    วิธีนี้ **พิสูจน์ได้** (ไม่ต้องไล่ลำดับจุดเอง) จึงไม่พลาดแบบกล่องลบมุมที่เขียนมือ
    """
    from itertools import combinations

    verts = []
    for i, j, k in combinations(range(len(planes)), 3):
        pt = _solve3(planes[i], planes[j], planes[k])
        if pt is None:
            continue
        if all(n[0] * pt[0] + n[1] * pt[1] + n[2] * pt[2] <= off + 1e-6 for n, off in planes):
            if not any(sum((pt[a] - q[a]) ** 2 for a in (0, 1, 2)) < 1e-12 for q in verts):
                verts.append(pt)
    faces = []
    for n, off in planes:
        on = [i for i, v in enumerate(verts) if abs(n[0] * v[0] + n[1] * v[1] + n[2] * v[2] - off) < 1e-6]
        if len(on) < 3:
            continue
        c = centroid([verts[i] for i in on])
        ux = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
        u = (n[1] * ux[2] - n[2] * ux[1], n[2] * ux[0] - n[0] * ux[2], n[0] * ux[1] - n[1] * ux[0])
        ln = math.sqrt(sum(x * x for x in u)) or 1.0
        u = tuple(x / ln for x in u)
        v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
        on.sort(key=lambda i: math.atan2(
            sum((verts[i][a] - c[a]) * v[a] for a in (0, 1, 2)),
            sum((verts[i][a] - c[a]) * u[a] for a in (0, 1, 2))))
        faces.append(on)
    faces = ensure_outward(verts, faces)
    return verts, faces


def box_planes(hx, hy, hz):
    """ระนาบของกล่องทื่อ"""
    return [((1, 0, 0), hx), ((-1, 0, 0), hx), ((0, 1, 0), hy), ((0, -1, 0), hy),
            ((0, 0, 1), hz), ((0, 0, -1), hz)]


def chamfered_box(hx, hy, hz, chamfer, center=(0.0, 0.0, 0.0)):
    """กล่องที่ "ลบมุม" ทุกมุม — สร้างจากระนาบ (พิสูจน์ได้ว่าปิดสนิท)

    ลบมุมคือหัวใจของลุค low-poly: กล่องทื่อจะดูเป็นหุ่นกล่อง แต่พอเฉือนทุกมุม
    แสงจะกระทบเป็นเหลี่ยมเหมือนงานเรนเดอร์จริง · ได้ 24 จุด 26 หน้า
    """
    c = min(chamfer, hx * 0.49, hy * 0.49, hz * 0.49)
    planes = box_planes(hx, hy, hz)
    if c > EPS:
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    a = (sx * (hx - c), sy * hy, sz * hz)      # ตัดที่ขอบ X
                    b = (sx * hx, sy * (hy - c), sz * hz)      # ตัดที่ขอบ Y
                    d = (sx * hx, sy * hy, sz * (hz - c))      # ตัดที่ขอบ Z
                    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                    w = (d[0] - a[0], d[1] - a[1], d[2] - a[2])
                    nrm = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
                    ln = math.sqrt(sum(x * x for x in nrm)) or 1.0
                    nrm = tuple(x / ln for x in nrm)
                    if sum(nrm[i] * (a[i] - (0, 0, 0)[i]) for i in (0, 1, 2)) < 0:
                        nrm = tuple(-x for x in nrm)
                    planes.append((nrm, sum(nrm[i] * a[i] for i in (0, 1, 2))))
    verts, faces = convex_from_planes(planes)
    return [(v[0] + center[0], v[1] + center[1], v[2] + center[2]) for v in verts], faces


def prism(sides, radius, height, center=(0.0, 0.0, 0.0), axis="z", rot_z=0.0):
    """แท่งเหลี่ยม n ด้าน (แขน/ขา/คอ) · ด้านน้อย = low-poly · ด้านมาก = เนียน"""
    verts = []
    """แท่งเหลี่ยม n ด้าน (แขน/ขา/คอ) · ด้านน้อย = low-poly · ด้านมาก = เนียน"""
    verts = []
    for sign in (-1, 1):
        for i in range(sides):
            a = 2.0 * math.pi * i / sides + rot_z
            verts.append((math.cos(a) * radius, math.sin(a) * radius, sign * height / 2.0))
    faces = [list(range(sides)), list(reversed(range(sides, sides * 2)))]
    for i in range(sides):
        j = (i + 1) % sides
        faces.append([i, j, sides + j, sides + i])
    faces = ensure_outward(verts, faces)
    if axis == "x":                                  # หันความยาวไปตามแกน X (แขนท่า T)
        verts = [(v[2], v[1], -v[0]) for v in verts]
    elif axis == "y":
        verts = [(v[0], v[2], -v[1]) for v in verts]
    return [(v[0] + center[0], v[1] + center[1], v[2] + center[2]) for v in verts], faces


def frustum(bottom, top, height, center=(0.0, 0.0, 0.0), rot_z=0.0):
    """กล่องบน-ล่างไม่เท่ากัน (อกสอบลงเอว · เท้าบานปลาย · ผ้าเตี่ยว) — 8 จุด 6 หน้า"""
    bw, bd = bottom[0] / 2.0, bottom[1] / 2.0
    tw, td = top[0] / 2.0, top[1] / 2.0
    verts = []
    for w, d, z in ((bw, bd, -height / 2.0), (tw, td, height / 2.0)):
        verts.extend([(-w, -d, z), (w, -d, z), (w, d, z), (-w, d, z)])
    if rot_z:
        a = math.radians(rot_z)
        verts = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a), z)
                 for x, y, z in verts]
    faces = [[0, 1, 2, 3], [7, 6, 5, 4],
             [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    faces = ensure_outward(verts, faces)
    return [(v[0] + center[0], v[1] + center[1], v[2] + center[2]) for v in verts], faces


def triangular_prism(width, height, depth, center=(0.0, 0.0, 0.0), axis="x"):
    """แท่งสามเหลี่ยม (จมูก/ลิ่ม) · axis = แกนที่ความยาววิ่งไปตามนั้น"""
    hw, hd = width / 2.0, depth / 2.0
    if axis == "x":
        verts = [(-hd, -hw, -height / 2), (hd, -hw, -height / 2), (-hd, -hw, height / 2),
                 (-hd, hw, -height / 2), (hd, hw, -height / 2), (-hd, hw, height / 2)]
    elif axis == "y":
        verts = [(-hw, -hd, -height / 2), (-hw, hd, -height / 2), (-hw, -hd, height / 2),
                 (hw, -hd, -height / 2), (hw, hd, -height / 2), (hw, -hd, height / 2)]
    else:
        verts = [(-hw, -hd, -height / 2), (hw, -hd, -height / 2), (-hw, hd, -height / 2),
                 (-hw, -hd, height / 2), (hw, -hd, height / 2), (-hw, hd, height / 2)]
    faces = ensure_outward(verts, [[0, 1, 2], [3, 5, 4], [0, 2, 5, 3], [0, 3, 4, 1], [1, 4, 5, 2]])
    return [(v[0] + center[0], v[1] + center[1], v[2] + center[2]) for v in verts], faces


def rotate(part, rx=0.0, ry=0.0, rz=0.0):
    """หมุนเมชรอบจุดกำเนิด (องศา) — ลำดับ Z → Y → X"""
    verts, faces = part
    out = []
    for x, y, z in verts:
        if rz:
            a = math.radians(rz)
            x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        if ry:
            a = math.radians(ry)
            x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
        if rx:
            a = math.radians(rx)
            y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
        out.append((x, y, z))
    return out, [list(f) for f in faces]


def translate(part, dx=0.0, dy=0.0, dz=0.0):
    verts, faces = part
    return [(v[0] + dx, v[1] + dy, v[2] + dz) for v in verts], [list(f) for f in faces]


def mirror_x(part):
    """พลิกซ้าย-ขวา (จุด x กลับเครื่องหมาย + พลิกหน้าเพื่อคงทิศตั้งฉากออกนอก)"""
    verts, faces = part
    return [(-v[0], v[1], v[2]) for v in verts], [list(reversed(f)) for f in faces]


def merge(parts):
    """รวมหลายชิ้นเป็นเมชเดียว (จุด + หน้า ต่อเนื่องกัน)"""
    verts, faces = [], []
    for v, f in parts:
        off = len(verts)
        verts.extend(v)
        faces.extend([[i + off for i in face] for face in f])
    return verts, faces


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    ln = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def chamfer_all(planes, chamfer):
    """ลบมุม "ทุกจุดยอด" ของรูปนูนที่นิยามด้วยระนาบ — ใช้ได้กับทุกรูป (กล่อง/แท่งสอบ/ลิ่ม)

    วิธี: หาจุดยอดก่อน → แต่ละจุดมี 3 ขอบบรรจบ → ตัดด้วยระนาบผ่านจุดที่ถอยเข้ามา
    ตามขอบทั้งสามเป็นระยะ ``chamfer`` · ได้ลุค low-poly แบบเหลี่ยมเหมือนงานเรนเดอร์จริง
    """
    from itertools import combinations

    verts, _ = convex_from_planes(planes)
    out = list(planes)
    c_all = centroid(verts)
    for v in verts:
        idx = [i for i, (n, off) in enumerate(planes) if abs(_dot(n, v) - off) < 1e-6]
        if len(idx) < 3:
            continue
        dirs = []
        for i, j in combinations(idx, 2):
            d = _cross(planes[i][0], planes[j][0])
            if math.sqrt(_dot(d, d)) < 1e-9:
                continue
            d = _norm(d)
            for sgn in (1, -1):
                probe = tuple(v[k] + sgn * d[k] * 1e-5 for k in (0, 1, 2))
                if all(_dot(n, probe) <= off + 1e-9 for n, off in planes):
                    dirs.append(tuple(sgn * x for x in d))
                    break
        if len(dirs) != 3:
            continue
        pts = [tuple(v[k] + d[k] * chamfer for k in (0, 1, 2)) for d in dirs]
        n = _cross(tuple(pts[1][k] - pts[0][k] for k in (0, 1, 2)),
                   tuple(pts[2][k] - pts[0][k] for k in (0, 1, 2)))
        if math.sqrt(_dot(n, n)) < 1e-12:
            continue
        n = _norm(n)
        if _dot(n, tuple(v[k] - c_all[k] for k in (0, 1, 2))) < 0:
            n = tuple(-x for x in n)
        off = _dot(n, pts[0])
        if not any(abs(off - o) < 1e-9 and abs(_dot(n, nn) - 1.0) < 1e-9 for nn, o in out):
            out.append((n, off))
    return out


def tapered_prism(sides, bottom_d, top_d, height, center=(0.0, 0.0, 0.0), axis="z",
                  chamfer=0.0, rot_z=0.0):
    """แท่งเหลี่ยมที่ปลายบน-ล่างไม่เท่ากัน (ขาไล่ถึงข้อเท้า · แขนไล่ถึงข้อมือ)

    ``bottom_d``/``top_d`` = เส้นผ่านศูนย์กลาง (เต็ม) ที่ปลายล่าง/บน
    """
    rb, rt = bottom_d / 2.0, top_d / 2.0
    planes = [((0.0, 0.0, 1.0), height / 2.0), ((0.0, 0.0, -1.0), height / 2.0)]
    for i in range(sides):
        a = 2.0 * math.pi * i / sides + rot_z
        ca, sa = math.cos(a), math.sin(a)
        n = _norm((height * ca, height * sa, rb - rt))
        planes.append((n, _dot(n, (rb * ca, rb * sa, -height / 2.0))))
    if chamfer > EPS:
        planes = chamfer_all(planes, chamfer)
    verts, faces = convex_from_planes(planes)
    if axis == "x":
        verts = [(v[2], v[1], -v[0]) for v in verts]
    elif axis == "y":
        verts = [(v[0], v[2], -v[1]) for v in verts]
    return [(v[0] + center[0], v[1] + center[1], v[2] + center[2]) for v in verts], faces


def chamfered_frustum(bottom, top, height, chamfer, center=(0.0, 0.0, 0.0)):
    """กล่องสอบ (บน-ล่างไม่เท่ากัน) ที่ลบมุมทุกมุม — หัว/อกไล่ถึงเอว"""
    bw, bd = bottom[0] / 2.0, bottom[1] / 2.0
    tw, td = top[0] / 2.0, top[1] / 2.0
    lo = [(-bw, -bd, -height / 2.0), (bw, -bd, -height / 2.0),
          (bw, bd, -height / 2.0), (-bw, bd, -height / 2.0)]
    hi = [(-tw, -td, height / 2.0), (tw, -td, height / 2.0),
          (tw, td, height / 2.0), (-tw, td, height / 2.0)]
    mid = centroid(lo + hi)
    planes = [((0.0, 0.0, 1.0), height / 2.0), ((0.0, 0.0, -1.0), height / 2.0)]
    for i in range(4):
        j = (i + 1) % 4
        p1, p2, p3 = lo[i], lo[j], hi[i]
        u = tuple(p2[k] - p1[k] for k in (0, 1, 2))
        w = tuple(p3[k] - p1[k] for k in (0, 1, 2))
        n = _norm(_cross(u, w))
        edge_mid = tuple((p1[k] + p2[k]) / 2.0 for k in (0, 1, 2))
        if _dot(n, tuple(edge_mid[k] - mid[k] for k in (0, 1, 2))) < 0:
            n = tuple(-x for x in n)
        planes.append((n, _dot(n, p1)))
    if chamfer > EPS:
        planes = chamfer_all(planes, chamfer)
    verts, faces = convex_from_planes(planes)
    return [(v[0] + center[0], v[1] + center[1], v[2] + center[2]) for v in verts], faces


# ───────────────────────────── ส่งออก ─────────────────────────────

def write_obj(path, groups, mtl_path=None):
    """เขียนไฟล์ .obj (+ .mtl) · groups = [(ชื่อ, (verts, faces), ชื่อวัสดุ), ...]

    Blender นำเข้าได้ด้วยคำสั่งเดียว: ``bpy.ops.wm.obj_import(filepath=...)``
    """
    import pathlib

    path = pathlib.Path(path)
    mtl_name = None
    if mtl_path:
        mtl_path = pathlib.Path(mtl_path)
        mtl_name = mtl_path.name
    lines = ["# สร้างด้วย mesh_lib.py (เรขาคณิตบริสุทธิ์ · ตรวจสอบได้)", f"# groups: {len(groups)}"]
    if mtl_name:
        lines.append(f"mtllib {mtl_name}")
    base = 1
    for name, (verts, faces), m in groups:
        lines.append(f"o {name}")
        if m and mtl_name:
            lines.append(f"usemtl {m['name']}")          # ⚠️ ขาดบรรทัดนี้ = นำเข้าแล้วไม่มีวัสดุ
        for v in verts:
            lines.append(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")
        for f in faces:
            lines.append("f " + " ".join(str(i + base) for i in f))
        base += len(verts)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if mtl_path:
        m = ["# วัสดุสำหรับ mesh_lib"]
        for mat in _unique_mats(groups):
            m.append(f"newmtl {mat['name']}")
            m.append(f"Kd {mat['color'][0]:.4f} {mat['color'][1]:.4f} {mat['color'][2]:.4f}")
            m.append("Ka 0.2 0.2 0.2")
            m.append("Ks 0.05 0.05 0.05")
            m.append("Ns 20")
            m.append(f"d {mat.get('alpha', 1.0)}")
            m.append("")
        mtl_path.write_text("\n".join(m), encoding="utf-8")
    return path


def _unique_mats(groups):
    seen, out = set(), []
    for _n, _p, mat in groups:
        if mat and mat["name"] not in seen:
            seen.add(mat["name"])
            out.append(mat)
    return out


def mat(name, color, alpha=1.0):
    """วัสดุแบบง่าย (ชื่อ + สี 0..1)"""
    return {"name": name, "color": tuple(color), "alpha": alpha}
