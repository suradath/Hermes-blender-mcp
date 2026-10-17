#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender_bridge.py — ตัวเชื่อมที่รัน "อยู่ข้างใน Blender 5.2"
================================================================

หน้าที่: รับคำสั่งจาก MCP server ทางซ็อกเก็ต แล้วเรียก ``bpy`` **บน main thread
ของ Blender เท่านั้น** (bpy ไม่ thread-safe — เรียกจาก thread อื่นได้ hard crash
ไม่ใช่ exception) แล้วส่งผลลัพธ์กลับ

ทำไมต้องมีไฟล์นี้แยกจาก MCP server
----------------------------------
1. **stdout สะอาด** — MCP สื่อสารผ่าน stdio ซึ่งใช้ stdout เป็นท่อ JSON-RPC
   แต่ ``blender -b`` พ่นข้อความต้อนรับ/บันทึกต่าง ๆ ลง stdout ตั้งแต่ก่อนสคริปต์
   จะได้รันด้วยซ้ำ ถ้าให้ MCP server รันใน Blender เอง JSON-RPC จะพังทันที
   → ไฟล์นี้จึงใช้ **ซ็อกเก็ต** และปล่อยให้ stdout ของ Blender เป็นแค่บันทึก
2. **ไม่ต้อง pip install อะไรลง Blender** — ไฟล์นี้ใช้แค่ stdlib
   ทำให้ไม่ต้องติดตั้งแพ็กเกจลง Python ของ Blender (บน Windows มักต้องสิทธิ์
   ผู้ดูแลระบบ + wheel ที่คอมไพล์แล้วต้องตรงรุ่น Python ของ Blender พอดี)

สองโหมดการรัน (ต่างกันเพราะ bpy บังคับ)
---------------------------------------
- ``--mode main``  ใช้กับ ``blender -b`` (ไม่มีหน้าต่าง)
  ``bpy.app.timers`` **ไม่ทำงานในโหมด background** จึงต้องวนรับงานบน main thread
  แบบบล็อกอยู่เลย — ทุกคำสั่งจึงอยู่บน main thread โดยธรรมชาติ ✅
- ``--mode timer`` ใช้กับ Blender ที่เปิดหน้าต่าง (GUI)
  main thread เป็นของ Blender ไปแล้ว จึงรับงานใน thread แยก แล้วส่งงานให้
  main thread ทำผ่าน ``bpy.app.timers`` (คิวงาน + Future รอผล)
- ``--mode auto``  เลือกให้เองจาก ``bpy.app.background``

รันตรง ๆ (ปกติ MCP server จะเป็นคนสั่งให้):
    blender -b --factory-startup --python blender_bridge.py -- --port 0 --token XXX
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import io
import contextlib
import json
import os
import pathlib
import queue
import socket
import sys
import tempfile
import threading
import time
import traceback

# bpy มีให้เฉพาะตอนรันใน Blender — โหมดทดสอบจะฉีด bpy ปลอมเข้า sys.modules ก่อน import
try:  # pragma: no cover
    import bpy  # type: ignore
except ImportError:  # รันนอก Blender (ใช้ตอนเทสต์)
    bpy = None  # type: ignore

PROTOCOL_VERSION = 1
BRIDGE_VERSION = "1.0.0"
LOG_PREFIX = "[blender-bridge]"


def log(*parts: object) -> None:
    """บันทึกของเราไปที่ stderr เสมอ — ห้ามแตะ stdout เด็ดขาด"""
    print(LOG_PREFIX, *parts, file=sys.stderr, flush=True)


# ===========================================================================
#  ทะเบียนเครื่องมือ
# ===========================================================================

_TOOLS: dict[str, dict] = {}


def tool(name: str, description: str):
    """ลงทะเบียนฟังก์ชันเป็นเครื่องมือ MCP (ให้ทั้ง bridge และเทสต์เห็นรายการเดียวกัน)"""

    def decorator(fn):
        _TOOLS[name] = {"fn": fn, "description": description, "name": name}
        return fn

    return decorator


class ToolError(Exception):
    """ข้อผิดพลาดที่ 'คาดไว้' — ส่งข้อความกลับแบบอ่านรู้เรื่อง ไม่ต้องมี traceback"""


class ToolArgumentError(ToolError):
    """พารามิเตอร์ที่ส่งมาไม่ถูกต้อง (แยกจากข้อผิดพลาดขณะทำงาน)"""


# --------------------------------------------------------------- ตัวช่วยเล็ก ๆ

def _v3(value) -> list[float]:
    """แปลง Vector/Euler/tuple ให้เป็น list ของ float ที่ JSON ส่งได้"""
    try:
        return [round(float(value[0]), 6), round(float(value[1]), 6), round(float(value[2]), 6)]
    except Exception:
        return [0.0, 0.0, 0.0]


def _scene():
    if bpy is None:
        raise ToolError("ไม่พบโมดูล bpy — ไฟล์นี้ต้องรันอยู่ภายใน Blender")
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        scene = bpy.data.scenes[0] if len(bpy.data.scenes) else None
    if scene is None:
        raise ToolError("ไม่พบ scene ในไฟล์นี้")
    return scene


def _find_object(name: str):
    obj = bpy.data.objects.get(name)
    if obj is None:
        # ช่วยผู้ใช้: เสนอชื่อที่ใกล้เคียง
        names = [o.name for o in bpy.data.objects]
        near = [n for n in names if name.lower() in n.lower()][:5]
        hint = f" ชื่อที่ใกล้เคียง: {', '.join(near)}" if near else ""
        raise ToolError(f"ไม่พบวัตถุชื่อ '{name}'{hint} "
                        f"(ในไฟล์มีทั้งหมด {len(names)} ชิ้น)")
    return obj


def _object_summary(obj) -> dict:
    """ข้อมูลวัตถุแบบสั้น (ใช้ในลำดับชั้นของฉาก)"""
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": _v3(obj.location),
        "rotation_euler": _v3(obj.rotation_euler),
        "scale": _v3(obj.scale),
        "visible": bool(obj.visible_get()) if hasattr(obj, "visible_get") else True,
    }
    if obj.type == "MESH" and getattr(obj, "data", None) is not None:
        try:
            info["vertices"] = len(obj.data.vertices)
            info["polygons"] = len(obj.data.polygons)
            info["materials"] = [m.name for m in obj.data.materials if m]
        except Exception:
            pass
    if obj.parent is not None:
        info["parent"] = obj.parent.name
    return info


def _collection_path(coll, root=None) -> str:
    """เส้นทางของคอลเลกชัน เช่น 'Scene Collection/Props/trees'

    ⚠️ ``bpy.types.Collection`` **ไม่มี** ``.parent`` (Blender 5.2 โยน
    ``AttributeError: 'Collection' object has no attribute 'parent'``) —
    ความสัมพันธ์เก็บด้านเดียวที่ ``parent.children`` จึงต้องไล่จากรากลงมา
    คอลเลกชันอาจถูก link ไว้ใต้หลายที่ (DAG) — คืนเส้นทางแรกที่เจอ พร้อมกันวนซ้ำ
    """
    name = getattr(coll, "name", "?")
    try:
        root = _scene().collection if root is None else root
    except Exception:
        return name
    if root is None:
        return name
    found = _find_collection_in(root, coll, trail=None, depth=0)
    return "/".join(found) if found else name


def _collection_children(coll):
    try:
        return [c for c in coll.children]
    except Exception:
        return []


def _find_collection_in(node, want, trail=None, depth=0):
    """DFS จากรากลงมา (ไม่ใช้ .parent) — คืน list ของชื่อหรือ None"""
    if depth > 32:                      # กันฉากแปลก ๆ ที่อ้างกันเป็นวง
        return None
    trail = list(trail or ()) + [getattr(node, "name", "?")]
    try:
        if node == want:                # bpy สร้าง wrapper ใหม่ทุกครั้ง → ใช้ == ไม่ใช่ is
            return trail
    except Exception:
        pass
    for child in _collection_children(node):
        got = _find_collection_in(child, want, trail=trail, depth=depth + 1)
        if got:
            return got
    return None


def _objects_in(coll):
    try:
        return list(coll.objects)
    except Exception:
        return []


# ===========================================================================
#  เครื่องมือ 1 : get_scene_hierarchy
# ===========================================================================

@tool(
    "get_scene_hierarchy",
    "Return the active scene as JSON: collections tree, every object with its "
    "transform/type/mesh stats, plus counts. Optional include_hidden and "
    "name_filter. Use this first to see what exists before adding or moving things.",
)
def get_scene_hierarchy(include_hidden: bool = True, name_filter: str = "",
                        max_objects: int = 500) -> dict:
    scene = _scene()
    render = getattr(scene, "render", None)

    collections = []
    for coll in bpy.data.collections:
        collections.append({
            "name": coll.name,
            "path": _collection_path(coll),
            "child_collections": [c.name for c in coll.children],
            "objects": [o.name for o in _objects_in(coll)],
            "hide_viewport": bool(getattr(coll, "hide_viewport", False)),
        })
    # Scene Collection เอง (คอลเลกชันราก) ไม่ได้อยู่ใน bpy.data.collections
    root = getattr(scene, "collection", None)
    if root is not None:
        collections.insert(0, {
            "name": root.name,
            "path": _collection_path(root),
            "child_collections": [c.name for c in root.children],
            "objects": [o.name for o in _objects_in(root)],
            "hide_viewport": bool(getattr(root, "hide_viewport", False)),
            "is_root": True,
        })

    objects, skipped = [], 0
    for obj in bpy.data.objects:
        try:
            visible = bool(obj.visible_get())
        except Exception:
            visible = True
        if not include_hidden and not visible:
            continue
        if name_filter and name_filter.lower() not in obj.name.lower():
            continue
        if len(objects) >= max_objects:
            skipped += 1
            continue
        info = _object_summary(obj)
        info["collections"] = [c.name for c in obj.users_collection]
        objects.append(info)

    counts: dict[str, int] = {}
    for obj in bpy.data.objects:
        counts[obj.type] = counts.get(obj.type, 0) + 1

    return {
        "scene": {
            "name": scene.name,
            "frame_current": getattr(scene, "frame_current", 0),
            "frame_start": getattr(scene, "frame_start", 0),
            "frame_end": getattr(scene, "frame_end", 0),
            "fps": getattr(render, "fps", None),
            "engine": getattr(render, "engine", None),
            "unit_system": getattr(scene, "unit_settings.system", None),
        },
        "blender_version": _blender_version(),
        "collections": collections,
        "objects": objects,
        "counts_by_type": counts,
        "totals": {
            "objects": len(bpy.data.objects),
            "shown": len(objects),
            "not_shown": skipped,
            "collections": len(bpy.data.collections),
        },
        "note": ("มีวัตถุมากกว่าที่แสดง — เพิ่ม max_objects หรือใช้ name_filter"
                 if skipped else ""),
    }


@tool(
    "get_object_details",
    "Return full details for one object by name: world matrix, modifiers, "
    "materials, vertex groups, custom properties and data-block users. "
    "Use after get_scene_hierarchy when you need to inspect a single object.",
)
def get_object_details(name: str, include_custom_properties: bool = True) -> dict:
    obj = _find_object(name)
    out = _object_summary(obj)
    out["matrix_world"] = [[round(v, 6) for v in row] for row in obj.matrix_world]
    out["dimensions"] = _v3(obj.dimensions)
    out["rotation_mode"] = getattr(obj, "rotation_mode", None)
    out["rotation_quaternion"] = _v3(obj.rotation_quaternion) if hasattr(obj, "rotation_quaternion") else None
    out["hide_render"] = bool(getattr(obj, "hide_render", False))
    out["modifiers"] = [
        {"name": m.name, "type": m.type,
         "show_viewport": bool(getattr(m, "show_viewport", True))}
        for m in getattr(obj, "modifiers", [])
    ]
    out["vertex_groups"] = [g.name for g in getattr(obj, "vertex_groups", [])]
    out["children"] = [c.name for c in getattr(obj, "children", [])]
    if getattr(obj, "data", None) is not None:
        out["data_name"] = obj.data.name
        out["users"] = getattr(obj.data, "users", None)
    if include_custom_properties:
        out["custom_properties"] = {
            k: (v if isinstance(v, (int, float, str, bool, list, dict)) else str(v))
            for k, v in dict(getattr(obj, "items", lambda: [])()).items()
        }
    return out


# ===========================================================================
#  เครื่องมือ 2 : add_primitive_mesh
# ===========================================================================

_PRIMITIVES = {
    "cube": "primitive_cube_add",
    "sphere": "primitive_uv_sphere_add",
    "cylinder": "primitive_cylinder_add",
    "plane": "primitive_plane_add",
    "cone": "primitive_cone_add",
    "torus": "primitive_torus_add",
    "monkey": "primitive_monkey_add",
    "circle": "primitive_circle_add",
    "grid": "primitive_grid_add",
    "ico_sphere": "primitive_ico_sphere_add",
}


@tool(
    "add_primitive_mesh",
    "Add a primitive mesh object to the scene. primitive: cube|sphere|cylinder|"
    "plane|cone|torus|monkey|circle|grid|ico_sphere. location/rotation/scale are "
    "[x,y,z] (rotation in degrees). Returns the created object name and transform.",
)
def add_primitive_mesh(primitive: str = "cube", name: str = "",
                       location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0),
                       scale=(1.0, 1.0, 1.0), radius: float = 1.0,
                       size: float = 2.0, collection: str = "") -> dict:
    key = (primitive or "").strip().lower()
    if key not in _PRIMITIVES:
        raise ToolError(f"ไม่รู้จักรูปทรง '{primitive}' — เลือกได้: "
                        f"{', '.join(sorted(_PRIMITIVES))}")
    op_name = _PRIMITIVES[key]
    op = getattr(bpy.ops.mesh, op_name, None)
    if op is None:
        raise ToolError(f"Blender รุ่นนี้ไม่มี bpy.ops.mesh.{op_name}")

    before = {o.name for o in bpy.data.objects}
    import math

    kwargs = dict(
        align="WORLD",
        location=tuple(float(v) for v in location),
        rotation=[math.radians(float(r)) for r in rotation],
    )
    # ใส่พารามิเตอร์เฉพาะรูปทรงที่รับได้ (ชื่อคีย์ต้องตรงกับ operator จริง)
    if key in ("sphere", "ico_sphere", "cylinder", "cone", "circle"):
        kwargs["radius"] = float(radius)
    if key in ("cube", "plane", "monkey", "grid"):
        kwargs["size"] = float(size)
    if key in ("cone", "cylinder"):
        kwargs["depth"] = float(size)
    if key == "torus":
        kwargs["major_radius"] = float(radius)
        kwargs["minor_radius"] = float(radius) * 0.25

    try:
        op(**_filter_kwargs(op, kwargs))
    except TypeError:
        # บางรุ่น/บางรูปทรงไม่รับพารามิเตอร์บางตัว — ลองแบบพื้นฐานที่สุด
        op(align="WORLD", location=kwargs["location"], rotation=kwargs["rotation"])
    except RuntimeError as exc:
        raise ToolError(f"Blender สร้างรูปทรงไม่สำเร็จ: {exc}") from exc

    created = [o for o in bpy.data.objects if o.name not in before]
    if not created:
        raise ToolError("Blender ไม่ได้สร้างวัตถุใหม่ (อาจถูกยกเลิกกลางทาง)")
    obj = created[-1]
    obj.scale = tuple(float(v) for v in scale)
    if name:
        obj.name = name
        if obj.data is not None:
            obj.data.name = name

    if collection:
        coll = bpy.data.collections.get(collection) or bpy.data.scenes[0].collection
        for c in list(obj.users_collection):
            try:
                c.objects.unlink(obj)
            except Exception:
                pass
        try:
            coll.objects.link(obj)
        except Exception:
            pass
    return {"created": obj.name, "primitive": key,
            "location": _v3(obj.location), "rotation_euler_deg": list(rotation),
            "scale": _v3(obj.scale), "collection": obj.users_collection[0].name
            if obj.users_collection else ""}


def _filter_kwargs(op, kwargs: dict) -> dict:
    """ส่งเฉพาะคีย์ที่ operator นี้รู้จัก (กัน TypeError จากพารามิเตอร์เกิน)"""
    props = getattr(getattr(op, "get_rna_type", lambda: None)(), "properties", None)
    if props is None:
        return kwargs
    known = {p.identifier for p in props}
    return {k: v for k, v in kwargs.items() if k in known}


# ===========================================================================
#  เครื่องมือ 3 : modify_object_transform
# ===========================================================================

@tool(
    "modify_object_transform",
    "Update an existing object's transform by name. Pass only the parts you want "
    "to change (location / rotation / scale); rotation is degrees. Set "
    "relative=true to add to the current value instead of replacing it.",
)
def modify_object_transform(name: str, location=None, rotation=None, scale=None,
                            relative: bool = False, rotation_mode: str = "") -> dict:
    obj = _find_object(name)
    import math

    before = {"location": _v3(obj.location), "rotation_euler": _v3(obj.rotation_euler),
              "scale": _v3(obj.scale)}

    if rotation_mode:
        if rotation_mode not in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX", "QUATERNION", "AXIS_ANGLE"):
            raise ToolError(f"rotation_mode '{rotation_mode}' ไม่ถูกต้อง")
        obj.rotation_mode = rotation_mode

    if location is not None:
        vals = [float(v) for v in location]
        obj.location = [_v3(obj.location)[i] + vals[i] for i in range(3)] if relative else vals
    if rotation is not None:
        vals = [math.radians(float(v)) for v in rotation]
        if relative:
            cur = list(obj.rotation_euler)
            obj.rotation_euler = [cur[i] + vals[i] for i in range(3)]
        else:
            obj.rotation_euler = vals
    if scale is not None:
        vals = [float(v) for v in scale]
        if relative:
            cur = _v3(obj.scale)
            obj.scale = [cur[i] * vals[i] for i in range(3)]  # ญาติ = คูณ (ตามความหมายของ scale)
        else:
            obj.scale = vals

    if all(x is None for x in (location, rotation, scale)):
        raise ToolError("ต้องระบุอย่างน้อยหนึ่งอย่าง: location, rotation หรือ scale")

    return {"name": obj.name, "before": before,
            "location": _v3(obj.location),
            "rotation_euler_deg": [round(math.degrees(v), 4) for v in obj.rotation_euler],
            "scale": _v3(obj.scale)}


# ===========================================================================
#  เครื่องมือ 4 : delete_object / set_material / save_blend_file
# ===========================================================================

@tool("delete_object",
      "Delete one object by name. Set confirm=true to actually delete "
      "(safety latch so an accidental call cannot wipe work).")
def delete_object(name: str, confirm: bool = False) -> dict:
    obj = _find_object(name)
    if not confirm:
        return {"deleted": False, "name": obj.name,
                "message": "ยังไม่ลบ — ต้องส่ง confirm=true ด้วย (กันลบพลาด)"}
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    # เก็บกวาด mesh ที่ไม่มีใครใช้แล้ว (เหมือนที่ผู้ใช้สั่ง purge)
    removed_data = False
    if data is not None and getattr(data, "users", 0) == 0 and hasattr(bpy.data, "meshes"):
        try:
            bpy.data.meshes.remove(data)
            removed_data = True
        except Exception:
            pass
    return {"deleted": True, "name": name, "mesh_data_removed": removed_data}


@tool("set_object_material",
      "Assign a simple Principled BSDF material of the given colour to an object. "
      "colour is [r,g,b] or [r,g,b,a] in 0..1 linear values. Creates or reuses "
      "a material named after the colour unless material_name is given.")
def set_object_material(name: str, color=(0.8, 0.8, 0.8), material_name: str = "",
                        metallic: float = 0.0, roughness: float = 0.5,
                        alpha: float = 1.0) -> dict:
    obj = _find_object(name)
    if obj.type != "MESH":
        raise ToolError(f"วัตถุ '{obj.name}' เป็นชนิด {obj.type} — ใส่สีได้เฉพาะ MESH")
    rgb = [float(c) for c in color][:3]
    if len(rgb) < 3:
        raise ToolError("color ต้องมี 3 ค่า (r,g,b)")
    rgba = rgb + [float(alpha)]

    mat_name = material_name or f"LPM_{'_'.join(str(round(c, 3)) for c in rgb)}"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    bsdf = None
    try:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") or next(
            (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    except Exception:
        pass
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = float(metallic)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = float(roughness)
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = float(alpha)
    else:
        mat.diffuse_color = rgba  # fallback รุ่นเก่า/โหนดหาย

    if obj.data is not None:
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat
            for slot in range(1, len(obj.data.materials)):
                obj.data.materials[slot] = mat
    return {"object": obj.name, "material": mat.name,
            "color": [round(c, 4) for c in rgba]}


@tool("save_blend_file",
      "Save the current .blend file. Without filepath it saves in place "
      "(fails if the file was never saved). Returns the path written.")
def save_blend_file(filepath: str = "") -> dict:
    target = filepath or getattr(bpy.data, "filepath", "") or ""
    if not target:
        raise ToolError("ไฟล์นี้ยังไม่เคยบันทึก — ต้องส่ง filepath มาด้วย")
    if not target.lower().endswith(".blend"):
        target += ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=target)
    return {"saved": True, "filepath": target}


@tool(
    "get_viewport_screenshot",
    "Render a PNG of the current view so you can SEE the scene. Default mode "
    "'render' uses the active camera and works everywhere, including blender -b "
    "with no window; mode 'viewport' grabs the 3D viewport instead and needs a "
    "Blender window. Returns the PNG path plus metadata. Use this to check your "
    "own work: after adding or moving objects, look at the result.",
)
def get_viewport_screenshot(filepath: str = "", width: int = 0, height: int = 0,
                            mode: str = "auto", camera: str = "") -> dict:
    scene = _scene()
    render = getattr(scene, "render", None)
    if render is None:
        raise ToolError("ฉากนี้ไม่มีค่าตั้งการเรนเดอร์ (scene.render)")

    if mode not in ("auto", "render", "viewport"):
        raise ToolArgumentError(f"mode '{mode}' ไม่ถูกต้อง — ใช้ auto | render | viewport")

    has_window = not bool(getattr(bpy.app, "background", True))
    use = ("viewport" if has_window else "render") if mode == "auto" else mode
    if use == "viewport" and not has_window:
        raise ToolError(
            "โหมด -b (ไม่มีหน้าต่าง) ถ่ายภาพ viewport ไม่ได้ — ใช้ mode='render' "
            "(เรนเดอร์จากกล้อง ใช้ได้ทุกโหมด) หรือเปิด Blender แบบมีหน้าต่าง")

    # ต้องมีกล้อง (สำหรับโหมด render)
    cam_obj = None
    if camera:
        cam_obj = _find_object(camera)
        if cam_obj.type != "CAMERA":
            raise ToolError(f"วัตถุ '{cam_obj.name}' ไม่ใช่กล้อง (เป็น {cam_obj.type})")
    else:
        cam_obj = getattr(scene, "camera", None)
        if cam_obj is None:
            cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
            if not cams:
                raise ToolError(
                    "ฉากนี้ไม่มีกล้อง — โหมด render ต้องมีกล้องก่อน "
                    "(สร้างได้ด้วย execute_blender_script: bpy.ops.object.camera_add())")
            cam_obj = cams[0]
    if use == "render" and getattr(scene, "camera", None) is None:
        scene.camera = cam_obj          # ตั้งกล้องให้ชั่วคราวเพื่อเรนเดอร์

    # จำค่าตั้งเดิมไว้ แล้วคืนกลับเสมอ (ห้ามทิ้งค่าของผู้ใช้เปลี่ยนไป)
    saved = {
        "filepath": render.filepath,
        "format": getattr(render.image_settings, "file_format", None),
        "res_x": render.resolution_x, "res_y": render.resolution_y,
        "res_pct": render.resolution_percentage,
    }
    target = filepath or str(pathlib.Path(tempfile.gettempdir()) / "Hermes-blender-mcp" /
                             f"view-{int(time.time() * 1000)}.png")
    pathlib.Path(target).parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    effective = [int(render.resolution_x), int(render.resolution_y)]
    try:
        render.filepath = target
        if getattr(render.image_settings, "file_format", None) is not None:
            render.image_settings.file_format = "PNG"
        if width:
            render.resolution_x = int(width)
        if height:
            render.resolution_y = int(height)
        if width or height:
            render.resolution_percentage = 100
        # ⚠️ ต้องจำค่าที่ใช้จริง "ก่อน" คืนค่าเดิมตอน finally — ไม่งั้นจะรายงานค่าเก่า
        effective = [int(render.resolution_x), int(render.resolution_y)]
        try:
            if use == "viewport":
                bpy.ops.render.opengl(write_still=True)
            else:
                bpy.ops.render.render(write_still=True)
        except Exception as exc:  # noqa: BLE001 - ต้องไม่ทำให้ Blender ตาย
            raise ToolError(
                f"เรนเดอร์ไม่สำเร็จ ({type(exc).__name__}: {exc})"
                + (" — โหมด viewport ต้องมีหน้าต่าง Blender และ 3D View ที่ใช้งานอยู่"
                   if use == "viewport" else
                   " — ตรวจว่ามีกล้องในฉากและ engine ที่เลือกใช้ได้")) from exc
    finally:
        render.filepath = saved["filepath"]
        if saved["format"] is not None:
            render.image_settings.file_format = saved["format"]
        render.resolution_x = saved["res_x"]
        render.resolution_y = saved["res_y"]
        render.resolution_percentage = saved["res_pct"]

    # เผื่อ Blender เขียนนามสกุลต่อท้ายเอง (เช่น .png ซ้ำ)
    written = pathlib.Path(target)
    if not written.is_file():
        for cand in (pathlib.Path(target + ".png"), pathlib.Path(target).with_suffix(".png")):
            if cand.is_file():
                written = cand
                break
    if not written.is_file():
        raise ToolError(f"เรนเดอร์เสร็จแต่ไม่พบไฟล์ผลลัพธ์ที่ {target}")

    return {
        "filepath": str(written),
        "bytes": written.stat().st_size,
        "mode": use,
        "engine": getattr(render, "engine", None),
        "resolution": effective,
        "camera": cam_obj.name,
        "seconds": round(time.time() - started, 2),
        "note": "ไฟล์นี้อยู่ในโฟลเดอร์ชั่วคราว — ระบุ filepath ถ้าต้องการเก็บไว้",
    }


# ===========================================================================
#  คลังของฟรีจาก Poly Haven (CC0 — ไม่ต้องใช้คีย์)  ใช้แค่ stdlib
# ===========================================================================

POLYHAVEN_API = "https://api.polyhaven.com"
# ⚠️ User-Agent ต้องเป็น ASCII เท่านั้น — HTTP header เข้ารหัสเป็น latin-1
# (เคยใส่ชื่อไทยตรงนี้แล้ว urllib โยน UnicodeEncodeError — เทสต์ออนไลน์จับได้)
POLYHAVEN_UA = "Hermes-blender-mcp-lpm/1.0 (LPM school project; +https://polyhaven.com)"
POLYHAVEN_TYPES = ("hdris", "textures", "models")
_PH_LIST_CACHE: dict[str, dict] = {}


def _blender_can_import(operator: str) -> bool:
    """Blender รุ่นนี้มีตัวนำเข้าไฟล์ชนิดนั้นไหม (เช่น gltf อาจถูกปิด)"""
    try:
        mod, op = operator.split(".")
        return hasattr(getattr(bpy.ops, mod, None) or object(), op)
    except Exception:
        return False


def _http_json(url: str, timeout: float = 30.0):
    """อ่าน JSON จาก Poly Haven — ที่เดียวในโปรเจกต์ที่แตะเครือข่าย"""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": POLYHAVEN_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise ToolError(f"Poly Haven ตอบกลับผิดพลาด HTTP {exc.code} — ลองใหม่ภายหลัง") from exc
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"ต่อ Poly Haven ไม่ได้ ({type(exc).__name__}: {exc}) — "
                        f"ตรวจอินเทอร์เน็ต/ไฟร์วอลล์ หรือลองใหม่") from exc
    text = raw.decode("utf-8", errors="replace").lstrip()
    if not text[:1] in ("[", "{"):
        # Poly Haven กัน IP ของศูนย์ข้อมูลด้วยหน้า challenge (HTML) — ต้องบอกให้เข้าใจ
        raise ToolError("Poly Haven ตอบกลับไม่ใช่ JSON (อาจเป็นหน้า challenge ของศูนย์ข้อมูล) "
                        "— เครือข่ายนี้เข้าไม่ถึง คลังนี้")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError(f"อ่านข้อมูลจาก Poly Haven ไม่ได้: {exc}") from exc


def _http_download(url: str, dest: pathlib.Path, max_bytes: int) -> tuple[int, bool]:
    """ดาวน์โหลดไฟล์ (ข้ามถ้ามีอยู่แล้วครบ) คืน (ขนาดไบต์, ดึงใหม่ไหม)"""
    import urllib.error
    import urllib.request

    if dest.is_file() and dest.stat().st_size > 0:
        return dest.stat().st_size, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": POLYHAVEN_UA})
    tmp = dest.with_name(dest.name + ".part")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            declared = int(resp.headers.get("Content-Length") or 0)
            if declared and declared > max_bytes:
                raise ToolError(
                    f"ไฟล์ใหญ่ {declared / 1e6:.0f} MB เกินเพดาน {max_bytes / 1e6:.0f} MB "
                    f"— เลือกความละเอียดต่ำลง หรือเพิ่ม max_mb")
            got = 0
            with tmp.open("wb") as fh:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > max_bytes:
                        raise ToolError(f"ไฟล์ใหญ่เกินเพดาน {max_bytes / 1e6:.0f} MB — ยกเลิกกลางทาง")
                    fh.write(chunk)
    except ToolError:
        tmp.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise ToolError(f"ดาวน์โหลดไม่สำเร็จ HTTP {exc.code}: {url}") from exc
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise ToolError(f"ดาวน์โหลดไม่สำเร็จ ({type(exc).__name__}: {exc})") from exc
    tmp.replace(dest)
    return dest.stat().st_size, True


def _ph_list(asset_type: str) -> dict:
    """รายการ asset ทั้งหมดของชนิดนั้น (แคชไว้ในหน่วยความจำต่อการรันหนึ่งครั้ง)"""
    if asset_type not in POLYHAVEN_TYPES:
        raise ToolArgumentError(f"asset_type '{asset_type}' ไม่ถูกต้อง — "
                                f"ใช้ {' | '.join(POLYHAVEN_TYPES)}")
    if asset_type not in _PH_LIST_CACHE:
        _PH_LIST_CACHE[asset_type] = _http_json(f"{POLYHAVEN_API}/assets?t={asset_type}")
    return _PH_LIST_CACHE[asset_type]


@tool(
    "search_polyhaven",
    "Search Poly Haven — a library of CC0 (public domain, no API key, free for any "
    "use) HDRIs, PBR textures and 3D models. Call this to find real-world assets "
    "instead of modelling everything by hand: e.g. an outdoor HDRI for lighting, a "
    "wood/metal texture, or a ready-made prop like a chair or barrel. Returns ids "
    "you then pass to get_polyhaven_info / download_polyhaven_asset.",
)
def search_polyhaven(query: str = "", asset_type: str = "models", categories: str = "",
                     limit: int = 20) -> dict:
    items = _ph_list(asset_type)
    q = (query or "").strip().lower()
    cats = [c.strip().lower() for c in (categories or "").split(",") if c.strip()]

    out = []
    for aid, meta in items.items():
        haystack = " ".join([aid, meta.get("name", ""), " ".join(meta.get("tags") or []),
                             " ".join(meta.get("categories") or [])]).lower()
        if q and q not in haystack:
            continue
        if cats and not all(c in [x.lower() for x in (meta.get("categories") or [])] for c in cats):
            continue
        out.append({"id": aid, "name": meta.get("name", aid),
                    "categories": meta.get("categories") or [],
                    "tags": (meta.get("tags") or [])[:8],
                    "authors": list((meta.get("authors") or {}).keys()),
                    "polycount": meta.get("polycount"),
                    "max_resolution": meta.get("max_resolution")})
    out.sort(key=lambda a: (a["polycount"] is None, a["polycount"] or 0))
    return {"asset_type": asset_type, "total_matching": len(out), "returned": min(limit, len(out)),
            "assets": out[:max(1, int(limit))],
            "licence": "CC0 (public domain) — ใช้ฟรี ไม่ต้องอ้างอิงที่มา (แต่ให้เครดิตก็ดี)",
            "next": "เรียก get_polyhaven_info(asset_id) เพื่อดูความละเอียด/รูปแบบที่มี"}


@tool(
    "get_polyhaven_info",
    "Show what is inside one Poly Haven asset before downloading it: available "
    "formats (gltf/fbx/blend/usd for models; hdr/exr for HDRIs; map types for "
    "textures), resolutions, sizes and the author. Use this to pick a resolution "
    "that is not huge.",
)
def get_polyhaven_info(asset_id: str) -> dict:
    if not asset_id:
        raise ToolArgumentError("ต้องระบุ asset_id (ดูได้จาก search_polyhaven)")
    info = _http_json(f"{POLYHAVEN_API}/info/{asset_id}")
    files = _http_json(f"{POLYHAVEN_API}/files/{asset_id}")

    available = {}
    for kind, per_res in (files or {}).items():
        if not isinstance(per_res, dict):
            continue
        sizes = {}
        for res, entry in per_res.items():
            if not isinstance(entry, dict):
                continue
            if "url" in entry:                      # HDRI: {"1k": {"hdr": {url,...}}}
                sizes[res] = {k: v.get("size") for k, v in entry.items() if isinstance(v, dict)}
            else:                                   # โมเดล/เท็กซ์เจอร์: {"1k": {"gltf": {...}}}
                for fmt, det in entry.items():
                    if isinstance(det, dict):
                        sizes.setdefault(res, {})[fmt] = det.get("size")
        available[kind] = sizes
    return {"id": asset_id, "name": info.get("name", asset_id),
            "categories": info.get("categories"), "tags": (info.get("tags") or [])[:10],
            "authors": list((info.get("authors") or {}).keys()),
            "dimensions": info.get("dimensions"), "polycount": info.get("polycount"),
            "max_resolution": info.get("max_resolution"),
            "available": available,
            "licence": "CC0 — Poly Haven ให้ใช้ฟรีทุกวัตถุประสงค์"}


@tool(
    "download_polyhaven_asset",
    "Download one Poly Haven asset (plus the texture files it needs) into the local "
    "cache and optionally bring it into the scene: kind='hdri' applies it as the "
    "world lighting, kind='gltf' imports the model, kind='texture' builds a material "
    "from the base-colour map. Everything is CC0. Prefer resolution '1k' or '2k' — "
    "4k/8k/16k files are hundreds of MB.",
)
def download_polyhaven_asset(asset_id: str, kind: str = "gltf", resolution: str = "1k",
                             apply: bool = True, target_dir: str = "",
                             max_mb: float = 200.0, texture_map: str = "") -> dict:
    if not asset_id:
        raise ToolArgumentError("ต้องระบุ asset_id")
    files = _http_json(f"{POLYHAVEN_API}/files/{asset_id}")
    if not isinstance(files, dict) or not files:
        raise ToolError(f"ไม่พบไฟล์ของ '{asset_id}'")

    cache = pathlib.Path(target_dir) if target_dir else (
        pathlib.Path(tempfile.gettempdir()) / "Hermes-blender-mcp" / "polyhaven" /
        f"{asset_id}_{resolution}")
    max_bytes = int(float(max_mb) * 1_000_000)

    # ---- เลือกไฟล์หลัก + ไฟล์ประกอบ ----
    main_url = main_path = None
    include: dict = {}
    if kind == "hdri":
        if "hdri" not in files:
            raise ToolArgumentError(f"'{asset_id}' ไม่ใช่ HDRI (มี: {', '.join(files)})")
        per_res = files["hdri"]
        sizes = per_res.get(resolution) or per_res.get("1k") or next(iter(per_res.values()))
        fmt = "hdr" if "hdr" in sizes else next(iter(sizes))
        entry = sizes[fmt]
        main_url, main_path, declared = entry.get("url"), f"{asset_id}_{resolution}.{fmt}", entry.get("size")
    else:
        block = files.get(kind)
        if not isinstance(block, dict):
            raise ToolArgumentError(
                f"'{asset_id}' ไม่มีรูปแบบ '{kind}' (มี: {', '.join(files)})\n"
                f"สำหรับโมเดลให้ใช้ kind='gltf' (หรือ fbx/blend/usd) · "
                f"สำหรับเท็กซ์เจอร์ให้ใช้ชื่อแผนที่ เช่น kind='Diffuse'")
        per_res = block
        sizes = per_res.get(resolution) or per_res.get("1k") or next(iter(per_res.values()))
        fmt = next(iter(sizes))
        entry = sizes[fmt]
        main_url = entry.get("url")
        declared = entry.get("size")
        main_path = pathlib.Path(main_url).name if main_url else None
        include = entry.get("include") or {}

    if not main_url:
        raise ToolError(f"ไม่พบที่อยู่ไฟล์ของ '{asset_id}' ({kind} {resolution})")
    if declared and declared > max_bytes:
        raise ToolError(f"ไฟล์ความละเอียด {resolution} ใหญ่ {declared / 1e6:.0f} MB "
                        f"เกินเพดาน {max_mb:.0f} MB — เลือกความละเอียดต่ำลงหรือเพิ่ม max_mb")

    downloaded, reused, total = [], 0, 0
    size, fresh = _http_download(main_url, cache / (main_path or "asset.bin"), max_bytes)
    total += size
    downloaded.append({"file": main_path, "bytes": size, "new": fresh})
    reused += 0 if fresh else 1

    for rel, det in include.items():                 # ไฟล์เท็กซ์เจอร์ที่ต้องมีคู่กัน
        if not isinstance(det, dict) or not det.get("url"):
            continue
        dest = cache / rel
        size, fresh = _http_download(det["url"], dest, max_bytes)
        total += size
        downloaded.append({"file": rel, "bytes": size, "new": fresh})
        reused += 0 if fresh else 1

    result = {"asset_id": asset_id, "kind": kind, "resolution": resolution,
              "directory": str(cache), "files": downloaded,
              "total_mb": round(total / 1e6, 2), "reused_from_cache": reused,
              "main_file": str(cache / (main_path or "asset.bin")),
              "licence": "CC0 (public domain)"}

    if not apply:
        result["note"] = "ยังไม่ได้ใส่เข้าฉาก (apply=False) — ไฟล์อยู่ในโฟลเดอร์ข้างบน"
        return result

    # ---- นำเข้าฉาก ----
    if kind == "hdri":
        image = bpy.data.images.load(str(cache / main_path))
        world = getattr(_scene(), "world", None) or bpy.data.worlds.new("PolyHaven")
        _scene().world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        bg = nodes.get("Background") or nodes.new("ShaderNodeBackground")
        tex = nodes.new("ShaderNodeTexEnvironment")
        tex.image = image
        world.node_tree.links.new(bg.inputs["Color"], tex.outputs["Color"])
        result.update({"applied": "world", "world": world.name, "image": image.name})
    elif kind in ("gltf", "glb", "fbx", "obj", "usd"):
        op = getattr(bpy.ops.import_scene, kind, None)
        if op is None:
            raise ToolError(f"Blender รุ่นนี้ไม่มีตัวนำเข้า '{kind}' — ลอง kind='gltf' "
                            f"หรือติดตั้ง add-on ที่เกี่ยวข้อง")
        before = {o.name for o in bpy.data.objects}
        op(filepath=str(cache / main_path))
        new_objs = [o.name for o in bpy.data.objects if o.name not in before]
        result.update({"applied": "imported", "objects": new_objs,
                       "object_count": len(new_objs)})
    else:                                             # เท็กซ์เจอร์
        images = [f for f in downloaded if str(f["file"]).lower().endswith(
            (".jpg", ".jpeg", ".png", ".exr", ".hdr", ".tif", ".tiff"))]
        if not images:
            result["note"] = "ไม่พบไฟล์รูปในเท็กซ์เจอร์ชุดนี้"
            return result
        chosen = next((f for f in images if texture_map and texture_map.lower()
                       in str(f["file"]).lower()), images[0])
        image = bpy.data.images.load(str(cache / chosen["file"]))
        mat = bpy.data.materials.new(f"PH_{asset_id}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        if bsdf is not None:
            mat.node_tree.links.new(bsdf.inputs["Base Color"], node.outputs["Color"])
        result.update({"applied": "material", "material": mat.name, "image": image.name,
                       "map_used": chosen["file"],
                       "note": "ผูกเป็น Base Color ให้แล้ว — แผนที่อื่น (normal/roughness) "
                               "นำไปต่อเองได้ด้วย execute_blender_script"})
    return result


# ===========================================================================
#  เครื่องมือ 5 : execute_blender_script  (มีด่านตรวจ ไม่ใช่ sandbox!)
# ===========================================================================

# โมดูลที่ห้าม import ในโหมดปลอดภัย (แตะระบบปฏิบัติการ/เครือข่าย/process)
_BLOCKED_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "ssl", "ctypes", "importlib",
    "pickle", "marshal", "shelve", "multiprocessing", "pty", "webbrowser",
    "urllib", "http", "requests", "httpx", "ftplib", "smtplib", "telnetlib",
    "socketserver", "asyncio", "threading", "resource", "signal", "platform",
    "site", "sysconfig", "pathlib", "glob", "tempfile", "getpass", "fcntl",
    "msvcrt", "winreg", "atexit", "gc",
}
# ฟังก์ชันในตัวที่ห้ามใช้
_BLOCKED_BUILTINS = {
    "eval", "exec", "compile", "open", "input", "__import__", "globals",
    "locals", "vars", "dir", "getattr", "setattr", "delattr", "memoryview",
    "breakpoint", "exit", "quit", "help",
}
# operator ที่ทำลายงานของผู้ใช้
_BLOCKED_OPS = ("wm.quit_blender", "wm.read_homefile", "wm.read_factory_settings")


class GuardResult:
    def __init__(self, violations: list[str], warnings: list[str]):
        self.violations = violations
        self.warnings = warnings


def scan_code(code: str) -> GuardResult:
    """ตรวจโค้ดก่อนรัน — คืนรายการที่ 'ห้าม' และที่ 'น่าสงสัย'"""
    violations: list[str] = []
    warnings: list[str] = []
    if not code or not code.strip():
        return GuardResult(["โค้ดว่าง"], [])

    # 1) ตรวจด้วย AST (แม่นกว่าจับสตริง)
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return GuardResult([f"ไวยากรณ์ Python ผิด: บรรทัด {exc.lineno}: {exc.msg}"], [])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_MODULES:
                    violations.append(f"ห้าม import '{alias.name}' (บรรทัด {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _BLOCKED_MODULES:
                violations.append(f"ห้าม from '{node.module}' import (บรรทัด {node.lineno})")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _BLOCKED_BUILTINS:
                violations.append(f"ห้ามเรียก '{fn.id}()' (บรรทัด {node.lineno})")
            if isinstance(fn, ast.Attribute) and fn.attr in _BLOCKED_BUILTINS:
                violations.append(f"ห้ามเรียก '.{fn.attr}()' (บรรทัด {node.lineno})")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                violations.append(
                    f"ห้ามเข้าถึง attribute พิเศษ '{node.attr}' (บรรทัด {node.lineno}) "
                    "— เป็นทางหลบหนีการจำกัดที่พบบ่อย")
        elif isinstance(node, ast.Name):
            if node.id in ("__builtins__", "__loader__", "__spec__", "__import__"):
                violations.append(f"ห้ามใช้ '{node.id}' (บรรทัด {node.lineno})")

    # 2) ตรวจ operator ที่ทำลายงาน
    for op in _BLOCKED_OPS:
        if op in code:
            violations.append(f"ห้ามเรียก bpy.ops.{op} — จะทำลายงานที่เปิดอยู่/ปิด Blender")

    # 3) เตือน (ไม่บล็อก) ของที่มักเป็นความตั้งใจผิด
    for pat, msg in (("bpy.ops.wm.save_mainfile", "กำลังบันทึกทับไฟล์เดิม"),
                     ("bpy.data.objects.remove", "กำลังลบวัตถุออกจากไฟล์"),
                     ("bpy.ops.object.delete", "กำลังลบวัตถุ"),
                     ("for ", "มีลูป — ถ้ากว้างมาก Blender จะค้างจนกว่าจะเสร็จ")):
        if pat in code:
            warnings.append(msg)
    return GuardResult(violations, warnings)


@tool(
    "execute_blender_script",
    "Run raw bpy Python code inside Blender and return its output, the value of "
    "an optional final 'result' variable, and any error. By default the code is "
    "checked first (no os/sys/subprocess imports, no open(), no dunder access, no "
    "session-destroying operators) and refused if it breaks those rules; pass "
    "allow_unsafe=true to skip the check. NOTE: this is a guardrail for honest "
    "mistakes, NOT a sandbox — code that passes can still touch the whole scene.",
)
def execute_blender_script(code: str, allow_unsafe: bool = False,
                           return_variables: str = "result") -> dict:
    guard = scan_code(code) if not allow_unsafe else GuardResult([], ["ข้ามการตรวจความปลอดภัยแล้ว"])
    if guard.violations:
        raise ToolError(
            "โค้ดถูกปฏิเสธเพราะฝ่าด่านความปลอดภัย:\n  - "
            + "\n  - ".join(guard.violations)
            + "\nถ้าเป็นความตั้งใจจริง ให้ส่ง allow_unsafe=true"
        )

    # เตรียมสภาพแวดล้อมรัน
    import builtins as _bi

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        """ตัว import ที่ใช้เมื่อ 'ไม่ได้' สั่ง allow_unsafe"""
        top = name.split(".")[0]
        if top in _BLOCKED_MODULES:
            raise ImportError(f"ห้าม import '{name}' ในโหมดปลอดภัย "
                              "(ถ้าจำเป็นจริงให้ส่ง allow_unsafe=true)")
        return __import__(name, globals, locals, fromlist, level)

    if allow_unsafe:
        # ผู้ใช้สั่งข้ามด่านเอง → ให้ของจริงทั้งหมด (รวม __import__ ที่ไม่ถูกจำกัด)
        g = {"__builtins__": dict(vars(_bi)), "__name__": "__lpm_blender_script__"}
    else:
        safe_builtins = {k: v for k, v in vars(_bi).items() if k not in _BLOCKED_BUILTINS}
        safe_builtins["__import__"] = _guarded_import
        g = {"__builtins__": safe_builtins, "__name__": "__lpm_blender_script__"}

    import math as _math

    g.update({"bpy": bpy, "math": _math, "mathutils": _safe_mathutils()})

    buffer = io.StringIO()
    result = {"ok": True, "stdout": "", "warnings": guard.warnings}
    try:
        with contextlib.redirect_stdout(buffer):
            exec(compile(code, "<agent_script>", "exec"), g, g)
        if return_variables:
            for var in [v.strip() for v in return_variables.split(",") if v.strip()]:
                if var in g:
                    result[var] = _jsonable(g[var])
    except Exception as exc:  # ต้องไม่ให้ Blender ตาย
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()[-2000:]
    finally:
        result["stdout"] = buffer.getvalue()[-8000:]
    return result


def _safe_mathutils():
    try:
        import mathutils  # noqa: F401
        return mathutils
    except Exception:
        return None


def _jsonable(value):
    """แปลงค่าที่ bpy คืนมาให้เป็นสิ่งที่ JSON ส่งได้"""
    for conv in (lambda v: list(v) if hasattr(v, "__len__") and not isinstance(v, str) else None,
                 lambda v: float(v), lambda v: str(v)):
        try:
            if isinstance(value, (int, float, str, bool)) or value is None:
                return value
            if isinstance(value, dict):
                return {k: _jsonable(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_jsonable(v) for v in value]
            if hasattr(value, "__len__") and hasattr(value, "__getitem__"):
                return [_jsonable(value[i]) for i in range(len(value))]
            out = conv(value)
            if out is not None:
                return out
        except Exception:
            continue
    return str(value)


# ===========================================================================
#  ข้อมูลไฟล์ .blend (ใช้เป็น MCP Resource)
# ===========================================================================

def get_file_metadata() -> dict:
    scene = _scene()
    render = getattr(scene, "render", None)
    image = getattr(render, "image_settings", None)
    path = getattr(bpy.data, "filepath", "") or ""
    return {
        "filepath": path,
        "filename": os.path.basename(path) if path else "(ยังไม่บันทึก)",
        "is_dirty": bool(getattr(bpy.data, "is_dirty", False)),
        "blender_version": _blender_version(),
        "scene": getattr(scene, "name", ""),
        "frame": {
            "current": getattr(scene, "frame_current", 0),
            "start": getattr(scene, "frame_start", 0),
            "end": getattr(scene, "frame_end", 0),
            "fps": getattr(render, "fps", None),
        },
        "render_engine": getattr(render, "engine", None),
        "resolution": {
            "x": getattr(render, "resolution_x", None),
            "y": getattr(render, "resolution_y", None),
            "percentage": getattr(render, "resolution_percentage", None),
            "file_format": getattr(image, "file_format", None),
        },
        "world": getattr(getattr(scene, "world", None), "name", None),
        "counts": {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "collections": len(bpy.data.collections),
            "cameras": len(bpy.data.cameras),
            "lights": len(bpy.data.lights),
        },
    }


def _blender_version() -> str:
    v = getattr(bpy, "app", None)
    if v is not None and getattr(v, "version", None):
        return ".".join(str(x) for x in v.version)
    return "unknown"


# ===========================================================================
#  การรับส่ง
# ===========================================================================

class Request:
    __slots__ = ("id", "method", "params")

    def __init__(self, msg: dict):
        self.id = msg.get("id")
        self.method = msg.get("method")
        self.params = msg.get("params") or {}


def handle_message(msg: dict) -> dict:
    """ประมวลผลคำขอ 1 ครั้ง แล้วคืนคำตอบ (ใช้ทั้งสองโหมด และใช้ในเทสต์)"""
    req = Request(msg)
    try:
        if req.method == "ping":
            return {"id": req.id, "ok": True, "result": {"pong": True,
                                                         "bridge": BRIDGE_VERSION,
                                                         "protocol": PROTOCOL_VERSION}}
        if req.method == "hello":
            return {"id": req.id, "ok": True,
                    "result": {"blender": _blender_version(), "bridge": BRIDGE_VERSION,
                               "protocol": PROTOCOL_VERSION, "background": bool(
                                   getattr(getattr(bpy, "app", None), "background", False)),
                               "filepath": getattr(bpy.data, "filepath", "") if bpy else ""}}
        if req.method == "list_tools":
            return {"id": req.id, "ok": True,
                    "result": [{"name": t["name"], "description": t["description"]}
                               for t in _TOOLS.values()]}
        if req.method == "file_metadata":
            return {"id": req.id, "ok": True, "result": get_file_metadata()}
        if req.method == "call_tool":
            name = req.params.get("name")
            args = req.params.get("arguments") or {}
            if name not in _TOOLS:
                raise ToolError(f"ไม่รู้จักเครื่องมือ '{name}' — มีอยู่: "
                                f"{', '.join(sorted(_TOOLS))}")
            if not isinstance(args, dict):
                raise ToolArgumentError("arguments ต้องเป็นออบเจ็กต์ JSON")
            fn = _TOOLS[name]["fn"]
            # ตรวจว่าอาร์กิวเมนต์ตรงกับที่ฟังก์ชันรับ (จับผิดพลาดก่อนเรียกจริง)
            import inspect as _inspect
            sig = _inspect.signature(fn)
            unknown = [k for k in args if k not in sig.parameters]
            if unknown:
                raise ToolArgumentError(
                    f"เครื่องมือ '{name}' ไม่รับพารามิเตอร์: {', '.join(unknown)} "
                    f"(รับได้: {', '.join(sig.parameters)})")
            return {"id": req.id, "ok": True, "result": _jsonable(fn(**args))}
        raise ToolError(f"ไม่รู้จักคำสั่ง '{req.method}'")
    except ToolArgumentError as exc:
        return {"id": req.id, "ok": False, "error": str(exc), "error_type": "arguments"}
    except ToolError as exc:
        return {"id": req.id, "ok": False, "error": str(exc), "error_type": "tool"}
    except TypeError as exc:
        return {"id": req.id, "ok": False,
                "error": f"เรียกเครื่องมือด้วยพารามิเตอร์ไม่ถูกต้อง: {exc}",
                "error_type": "arguments"}
    except Exception as exc:  # noqa: BLE001 - ต้องเก็บทุกอย่างไว้ ไม่ให้ Blender ตาย
        log("เกิดข้อผิดพลาด:", traceback.format_exc())
        return {"id": req.id, "ok": False,
                "error": f"{type(exc).__name__}: {exc}", "error_type": "internal",
                "traceback": traceback.format_exc()[-1500:]}


# --------------------------------------------------- โหมด 1: main thread (headless)

def serve_blocking(host: str, port: int, token: str) -> None:
    """วนรับงานบน main thread แบบบล็อก — ใช้กับ ``blender -b``

    ทำไมต้องบล็อก: ``bpy.app.timers`` ไม่ทำงานในโหมด background (มีรายงานบั๊กจริง
    ว่าเซิร์ฟเวอร์ที่พึ่ง timer จะค้างทุกคำสั่ง) การบล็อกอยู่บน main thread
    จึงเป็นทางเดียวที่ทุกคำสั่งจะได้รันบน main thread อย่างปลอดภัย
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    real_port = srv.getsockname()[1]
    log(f"พร้อมรับงานที่ {host}:{real_port} (โหมด main thread / headless)")
    print(json.dumps({"bridge_ready": True, "port": real_port,
                      "pid": os.getpid()}), file=sys.stderr, flush=True)
    while True:
        try:
            conn, _ = srv.accept()
        except KeyboardInterrupt:
            log("ถูกสั่งให้หยุด")
            return
        with conn:
            f = _authenticate(conn, token)
            if f is None:
                continue
            _pump(f)


def _authenticate(conn: socket.socket, token: str):
    """ตรวจ token ก่อนรับคำสั่ง — คืนไฟล์ที่พร้อมใช้งาน หรือ None ถ้าไม่ผ่าน

    ⚠️ ห้ามเก็บไฟล์ไว้เป็น attribute ของ socket
    ``socket.socket`` นิยาม ``__slots__`` ไว้ จึงกำหนด attribute ใหม่ไม่ได้
    (เจอบั๊กนี้จริงตอนทดสอบ end-to-end: สะพานปฏิเสธทุกการเชื่อมต่อเงียบ ๆ
     เพราะบรรทัดที่เก็บไฟล์ระเบิด แล้วถูกกลืนโดย except)
    """
    if not token:
        return conn.makefile("rwb")
    conn.settimeout(10)
    try:
        f = conn.makefile("rwb")
        line = f.readline()
        if not line:
            return None
        msg = json.loads(line.decode("utf-8"))
        if msg.get("token") != token:
            f.write(json.dumps({"ok": False, "error": "token ไม่ถูกต้อง"}).encode() + b"\n")
            f.flush()
            log("ปฏิเสธการเชื่อมต่อ: token ไม่ถูกต้อง")
            return None
        f.write(json.dumps({"ok": True, "hello": True}).encode() + b"\n")
        f.flush()
        conn.settimeout(None)
        return f
    except Exception as exc:
        log("ตรวจ token ไม่ได้:", exc)
        return None


def _pump(f) -> None:
    """อ่านบรรทัด JSON ทีละคำขอ ประมวลผล แล้วตอบกลับ"""
    while True:
        try:
            line = f.readline()
        except Exception as exc:
            log("อ่านจากซ็อกเก็ตไม่ได้:", exc)
            return
        if not line:
            log("ไคลเอนต์ปิดการเชื่อมต่อ")
            return
        try:
            msg = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            f.write(json.dumps({"ok": False, "error": f"JSON ผิดรูป: {exc}"}).encode() + b"\n")
            f.flush()
            continue
        reply = handle_message(msg)
        try:
            f.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            f.flush()
        except Exception as exc:
            log("ตอบกลับไม่ได้:", exc)
            return


# ------------------------------------------- โหมด 2: timer (Blender ที่เปิดหน้าต่าง)

_LIVE_PUMPS: list = []      # กัน GC: เก็บ TimerPump ที่ยังทำงานอยู่


class TimerPump:
    """รับงานใน thread แยก แล้วให้ main thread ทำผ่าน ``bpy.app.timers``"""

    def __init__(self, host: str, port: int, token: str, interval: float = 0.05):
        self.host, self.port, self.token = host, port, token
        self.interval = interval
        self.jobs: "queue.Queue[tuple[dict, concurrent.futures.Future]]" = queue.Queue()
        self.srv: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ---- ฝั่ง main thread ----
    def drain(self) -> float:
        """เรียกโดย bpy.app.timers — ทำงาน bpy ทีละงานบน main thread

        ⚠️ ต้องไม่มีวัน raise: ถ้า timer callback โยน exception Blender จะ
        **ถอด timer ออกทันที** → ตัว pump ไม่มีใครอ้างถึง → GC เก็บ → ซ็อกเก็ตปิด
        → ผลคือ "ต่อติดครั้งแรกแล้ว refused ตลอด" (เจอจริงบน Blender 5.2.2)
        จึงห่อทั้งก้อนและคืน interval เสมอ
        """
        try:
            while True:
                try:
                    msg, fut = self.jobs.get_nowait()
                except queue.Empty:
                    break
                if not fut.set_running_or_notify_cancel():
                    continue
                try:
                    fut.set_result(handle_message(msg))
                except BaseException as exc:  # noqa: BLE001
                    try:
                        fut.set_exception(exc)
                    except Exception:
                        pass
                    log(f"งานล้มเหลว: {type(exc).__name__}: {exc}")
        except BaseException as exc:  # noqa: BLE001
            log(f"timer pump ผิดพลาด (ยังทำงานต่อ): {type(exc).__name__}: {exc}")
        # กล่องดำ: ยืนยันว่า timer ยังเต้นอยู่ (ไม่สแปม — แค่ 5 ครั้งแรก ๆ)
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks in (1, 20, 100, 1000, 10000):
            log(f"timer เต้นปกติ (tick {self._ticks})")
        return self.interval

    # ---- ฝั่ง thread รับงาน ----
    def start(self) -> None:
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((self.host, self.port))
        self.srv.listen(1)
        self.srv.settimeout(0.5)
        real_port = self.srv.getsockname()[1]
        self.thread = threading.Thread(target=self._accept_loop, name="blender-bridge",
                                       daemon=True)
        self.thread.start()
        log(f"พร้อมรับงานที่ {self.host}:{real_port} (โหมด timer / GUI)")
        print(json.dumps({"bridge_ready": True, "port": real_port,
                          "pid": os.getpid()}), file=sys.stderr, flush=True)

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.srv.accept()  # type: ignore[union-attr]
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._client_loop, args=(conn,),
                             name="blender-bridge-client", daemon=True).start()

    def _client_loop(self, conn: socket.socket) -> None:
        with conn:
            f = _authenticate(conn, self.token)
            if f is None:
                return
            while True:
                try:
                    line = f.readline()
                except Exception:
                    return
                if not line:
                    return
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    f.write(json.dumps({"ok": False, "error": f"JSON ผิดรูป: {exc}"}).encode() + b"\n")
                    f.flush()
                    continue
                # ส่งงานให้ main thread แล้วรอผล
                fut: concurrent.futures.Future = concurrent.futures.Future()
                self.jobs.put((msg, fut))
                try:
                    reply = fut.result(timeout=600)
                except concurrent.futures.TimeoutError:
                    reply = {"id": msg.get("id"), "ok": False,
                             "error": "งานใช้เวลาเกิน 600 วินาที — Blender อาจยังทำงานอยู่"}
                except Exception as exc:  # noqa: BLE001
                    reply = {"id": msg.get("id"), "ok": False, "error": f"{type(exc).__name__}: {exc}"}
                try:
                    f.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
                    f.flush()
                except Exception:
                    return

    def stop(self) -> None:
        self._stop.set()
        if self.srv is not None:
            try:
                self.srv.close()
            except Exception:
                pass
        try:
            import bpy as _bpy  # type: ignore
            if _bpy.app.timers.is_registered(self.drain):
                _bpy.app.timers.unregister(self.drain)
        except Exception:
            pass


# ===========================================================================
#  จุดเริ่มต้น
# ===========================================================================

def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # ตัด "--" ที่ Blender ใส่คั่นก่อนอาร์กิวเมนต์ของสคริปต์
    if "--" in raw:
        raw = raw[raw.index("--") + 1:]
    p = argparse.ArgumentParser(prog="blender_bridge", add_help=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0, help="0 = ให้ระบบเลือกให้")
    p.add_argument("--token", default="")
    p.add_argument("--mode", choices=["auto", "main", "timer"], default="auto")
    p.add_argument("--interval", type=float, default=0.05)
    p.add_argument("--selftest", action="store_true", help="ทดสอบภายในแล้วจบ (ไม่เปิดซ็อกเก็ต)")
    args, _unknown = p.parse_known_args(raw)

    if args.selftest:
        print(json.dumps(handle_message({"id": 1, "method": "hello"}), ensure_ascii=False))
        return 0

    if bpy is None:
        log("ไม่พบ bpy — ไฟล์นี้ต้องรันภายใน Blender "
            "(blender -b --python blender_bridge.py -- --port 0)")
        return 2

    mode = args.mode
    if mode == "auto":
        mode = "main" if getattr(bpy.app, "background", False) else "timer"
    log(f"เริ่มโหมด {mode} · Blender {_blender_version()} · ไฟล์ "
        f"{getattr(bpy.data, 'filepath', '') or '(ยังไม่บันทึก)'}")

    if mode == "main":
        try:
            serve_blocking(args.host, args.port, args.token)
        except KeyboardInterrupt:
            pass
        return 0

    pump = TimerPump(args.host, args.port, args.token, args.interval)
    pump.start()
    # ⚠️ ต้องมี reference ที่มีชีวิตยาว: สคริปต์ --python จบแล้วตัวแปรใน main()
    #    อาจถูกเก็บกวาด → ซ็อกเก็ตปิด → เซิร์ฟเวอร์ "refused" ทุกครั้งหลังจากนั้น
    _LIVE_PUMPS.append(pump)
    try:
        bpy.app.driver_namespace["blender_mcp_pump"] = pump
    except Exception:
        pass
    try:
        bpy.app.timers.register(pump.drain, first_interval=args.interval, persistent=True)
    except Exception as exc:
        log("ลงทะเบียน timer ไม่ได้:", exc)
        return 3
    log("ทำงานอยู่ — ปิด Blender หรือสั่งหยุดเพื่อจบ")
    return 0


if __name__ == "__main__":
    # ⚠️⚠️ ห้ามใช้ sys.exit() ในสคริปต์ --python ของ Blender ⚠️⚠️
    #    Blender ตีความ SystemExit ที่หลุดจากสคริปต์ = สั่ง "ปิดโปรแกรม"
    #    อาการที่เจอจริง (โหมด timer / --gui):
    #      • หน้าต่าง Blender เปิดขึ้นแล้วปิดทันที
    #      • เซิร์ฟเวอร์ต่อติดครั้งแรก (ConnectionReset) แล้ว refused ตลอด
    #      • ไม่มี log "timer เต้นปกติ" เพราะโปรเซสตายก่อน timer จะได้ทำงาน
    #    โหมด main ไม่โดนเพราะ serve_blocking ไม่คืนค่า จนไคลเอนต์ตัดการเชื่อมต่อ
    _code = main()
    if _code:
        log(f"จบด้วยรหัส {_code}")
