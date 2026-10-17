#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fake_bpy.py — ``bpy`` ปลอมสำหรับทดสอบตรรกะของ bridge บนเครื่องที่ไม่มี Blender

ทำไมต้องมี: ตรรกะของเครื่องมือ (สร้างรูปทรง, แก้ transform, อ่านลำดับชั้นฉาก)
เป็นส่วนที่ **ทดสอบได้จริง** ถ้ามีออบเจ็กต์ที่ทำตัวเหมือน bpy
ส่วนที่ทดสอบไม่ได้คือตัว Blender เอง (การเรนเดอร์, UI) — ซึ่งเทสต์จะไม่แตะ

หลักการ: เลียนแบบ "รูปพรรณ" ของ API จริงให้พอที่จะจับบั๊กได้ เช่น
  - ``bpy.ops.mesh.primitive_cube_add()`` **บันทึกอาร์กิวเมนต์ที่ถูกเรียก**
    → เทสต์ตรวจได้ว่าเราส่ง rotation เป็น "เรเดียน" จริง (บั๊กคลาสสิก)
  - ``bpy.ops.X.get_rna_type().properties`` → ทดสอบเส้นทาง _filter_kwargs
"""

from __future__ import annotations

import base64
import math
import pathlib

# PNG 1x1 ตัวจริง (ใช้แทนผลการเรนเดอร์) — เทสต์ตรวจหัวไฟล์ PNG ได้จริง
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


# ------------------------------------------------------------------ คอลเลกชัน
class _Named:
    """วัตถุที่มีชื่อ — เปลี่ยนชื่อแล้วต้องย้ายคีย์ในคอลเลกชันด้วย

    ⚠️ ของจริง (bpy) ทำแบบนี้: ``obj.name = "ใหม่"`` แล้ว ``bpy.data.objects["ใหม่"]``
    ต้องเจอทันที ถ้าของปลอมไม่ทำ เทสต์จะผ่าน/ไม่ผ่านด้วยเหตุผลที่ไม่จริง
    (เจอบั๊กนี้จริงตอนรันเทสต์ครั้งแรก — ดูประวัติใน README)
    """

    _registry = None

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        old = getattr(self, "_name", None)
        self._name = str(value)
        reg = self._registry
        if reg is not None and old is not None and old in reg and old != self._name:
            items = list(reg.items())      # คงลำดับเดิมไว้เหมือนของจริง
            reg.clear()
            for k, v in items:
                reg[self._name if k == old else k] = v


class FakeCollection(dict):
    """เลียนแบบ bpy_prop_collection: มี .get() / len() / วนซ้ำได้"""

    def __init__(self, items=None):
        super().__init__()
        for it in items or []:
            self.add(it)

    def add(self, item):
        item._registry = self          # ให้ตัวตั้งชื่อใหม่อัปเดตคีย์ได้
        self[item.name] = item
        return item

    def remove(self, item, do_unlink=True):  # noqa: ARG002
        self.pop(getattr(item, "name", item), None)

    def __iter__(self):
        return iter(self.values())


class FakeTypedCollection(FakeCollection):
    """คอลเลกชันที่สร้างของใหม่ได้ — ``bpy.data.materials.new("ชื่อ")``"""

    def __init__(self, item_class, items=None):
        self.item_class = item_class
        super().__init__(items)

    def new(self, name, *args, **kwargs):  # noqa: ARG002
        return self.add(self.item_class(_unique_in(self, name)))


def _unique_in(collection, base: str) -> str:
    if base not in collection:
        return base
    n = 1
    while f"{base}.{n:03d}" in collection:
        n += 1
    return f"{base}.{n:03d}"


# ------------------------------------------------------------------ วัสดุ
class FakeNodeInput:
    def __init__(self, default=None):
        self.default_value = default


class FakeNode:
    def __init__(self, name="Principled BSDF", ntype="BSDF_PRINCIPLED"):
        self.name, self.type = name, ntype
        self.inputs = {
            "Base Color": FakeNodeInput((0.8, 0.8, 0.8, 1.0)),
            "Metallic": FakeNodeInput(0.0),
            "Roughness": FakeNodeInput(0.5),
            "Alpha": FakeNodeInput(1.0),
        }


class FakeNodeTree:
    def __init__(self):
        self.nodes = {"Principled BSDF": FakeNode()}

    def get(self, name):
        return self.nodes.get(name)


class FakeMaterial(_Named):
    _seq = 0

    def __init__(self, name):
        FakeMaterial._seq += 1
        self.name = name
        self.use_nodes = False
        self.node_tree = FakeNodeTree()
        self.diffuse_color = (0.8, 0.8, 0.8, 1.0)

    def __repr__(self):
        return f"<FakeMaterial {self.name}>"


# ------------------------------------------------------------------ mesh data
class FakeMesh(_Named):
    _seq = 0

    def __init__(self, name, verts=8, polys=6):
        FakeMesh._seq += 1
        self.name = name
        self.vertices = list(range(verts))
        self.polygons = list(range(polys))
        self.materials = []
        self.users = 1

    def __repr__(self):
        return f"<FakeMesh {self.name}>"


class FakeCamera:
    def __init__(self, name):
        self.name = name


class FakeLight:
    def __init__(self, name):
        self.name = name


# ------------------------------------------------------------------ วัตถุ
class FakeObject(_Named):
    _seq = 0

    def __init__(self, name="Object", otype="MESH", loc=(0.0, 0.0, 0.0)):
        FakeObject._seq += 1
        self.name = name
        self.type = otype
        self.location = list(loc)
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.rotation_quaternion = [1.0, 0.0, 0.0, 0.0]
        self.rotation_mode = "XYZ"
        self.scale = [1.0, 1.0, 1.0]
        self.dimensions = [2.0, 2.0, 2.0]
        self.matrix_world = [[1.0, 0.0, 0.0, loc[0]], [0.0, 1.0, 0.0, loc[1]],
                             [0.0, 0.0, 1.0, loc[2]], [0.0, 0.0, 0.0, 1.0]]
        self.parent = None
        self.children = []
        self.modifiers = []
        self.vertex_groups = []
        self.hide_render = False
        self.hidden = False
        self.users_collection = []
        self.data = FakeMesh(name + "_mesh") if otype == "MESH" else None
        self._custom = {}

    def visible_get(self):
        return not self.hidden

    def items(self):
        return list(self._custom.items())

    def __repr__(self):
        return f"<FakeObject {self.name} ({self.type})>"


class FakeModifier:
    def __init__(self, name, mtype="SUBSURF"):
        self.name, self.type = name, mtype
        self.show_viewport = True


# ------------------------------------------------------------------ คอลเลกชันฉาก
class _ObjectList(list):
    """``collection.objects`` ของจริงมี .link()/.unlink() อยู่ในตัว"""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def link(self, obj):
        return self.owner.link(obj)

    def unlink(self, obj):
        return self.owner.unlink(obj)


class FakeSceneCollection:
    def __init__(self, name="Collection", parent=None):
        self.name = name
        self.parent = parent
        self.objects = _ObjectList(self)
        self.children = []
        self.hide_viewport = False

    def link(self, obj):
        """เหมือนของจริง — ย้ายวัตถุเข้าคอลเลกชันนี้"""
        if obj not in self.objects:
            self.objects.append(obj)
        if self not in obj.users_collection:
            obj.users_collection.append(self)
        return None

    def unlink(self, obj):
        if obj in self.objects:
            self.objects.remove(obj)
        if self in obj.users_collection:
            obj.users_collection.remove(self)
        return None

    def __repr__(self):
        return f"<FakeSceneCollection {self.name}>"


class FakeScene:
    def __init__(self, name="Scene"):
        self.name = name
        self.frame_current = 1
        self.frame_start = 1
        self.frame_end = 250
        self.unit_settings = type("U", (), {"system": "METRIC"})()
        self.render = type("R", (), {
            "fps": 24, "engine": "BLENDER_EEVEE_NEXT",
            "resolution_x": 1920, "resolution_y": 1080, "resolution_percentage": 100,
            "filepath": "",
            "image_settings": type("I", (), {"file_format": "PNG"})(),
        })()
        self.world = type("W", (), {"name": "World"})()
        self.collection = FakeSceneCollection("Scene Collection")
        self.camera = None          # ของจริงตั้งกล้องให้ฉากเริ่มต้น — reset() จะตั้งให้


# ------------------------------------------------------------------ ops
class _RnaType:
    """ให้ _filter_kwargs ทำงานได้เหมือนของจริง"""

    def __init__(self, identifiers=()):
        self.properties = [type("P", (), {"identifier": i})() for i in identifiers]


class FakeOps:
    """บันทึกการเรียกทุกครั้งใน .calls เพื่อให้เทสต์ตรวจได้"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._mesh = _FakeMeshOps(self)
        self._wm = _FakeWmOps(self)
        self._render = _FakeRenderOps(self)

    # bpy.ops.mesh.*
    @property
    def mesh(self):
        return self._mesh

    # bpy.ops.wm.*
    @property
    def wm(self):
        return self._wm

    # bpy.ops.render.*
    @property
    def render(self):
        return self._render


_MESH_IDENTIFIERS = {
    "primitive_cube_add": ("size", "location", "rotation", "align"),
    "primitive_uv_sphere_add": ("radius", "location", "rotation", "align", "segments"),
    "primitive_ico_sphere_add": ("radius", "location", "rotation", "align", "subdivisions"),
    "primitive_cylinder_add": ("radius", "depth", "location", "rotation", "align", "vertices"),
    "primitive_cone_add": ("radius1", "radius2", "depth", "location", "rotation", "align"),
    "primitive_plane_add": ("size", "location", "rotation", "align"),
    "primitive_circle_add": ("radius", "location", "rotation", "align", "vertices"),
    "primitive_torus_add": ("major_radius", "minor_radius", "location", "rotation", "align"),
    "primitive_monkey_add": ("size", "location", "rotation", "align"),
    "primitive_grid_add": ("size", "location", "rotation", "align"),
}


class _FakeMeshOps:
    def __init__(self, ops: FakeOps):
        self._ops = ops
        for op_name in _MESH_IDENTIFIERS:
            setattr(self, op_name, self._make(op_name))

    def _make(self, op_name):
        def op(**kwargs):
            self._ops.calls.append((f"mesh.{op_name}", dict(kwargs)))
            # ตรวจว่าไม่ได้ส่งพารามิเตอร์ที่ operator นี้ไม่รู้จัก
            known = set(_MESH_IDENTIFIERS[op_name])
            unknown = set(kwargs) - known
            if unknown:
                raise TypeError(f"unexpected keyword argument(s): {unknown}")
            _create_object_for(op_name, kwargs)
            return {"FINISHED"}

        def get_rna_type():
            return _RnaType(_MESH_IDENTIFIERS[op_name])

        op.get_rna_type = get_rna_type
        op.__name__ = op_name
        return op


class _FakeRenderOps:
    """bpy.ops.render.* — เขียนไฟล์ PNG จริง เพื่อให้ทดสอบเส้นทางได้ครบ

    Blender จริงจะ **เติมนามสกุลให้เอง** ถ้า filepath ไม่มี (เช่น `view.png` → `view.png.png`
    ถ้าตั้งชื่อมี .png อยู่แล้วจะไม่เติม) — ของปลอมก็ทำเหมือนกัน เพื่อให้เทสต์
    ตรวจเส้นทาง "ตามหาไฟล์ที่ Blender เขียนจริง" ได้
    """

    def __init__(self, ops: FakeOps):
        self._ops = ops
        self.saved_to: list[str] = []

    def _write(self, op_name: str, write_still: bool) -> dict:
        scene = DATA.scenes[0]
        render = scene.render
        self._ops.calls.append((f"render.{op_name}", {"write_still": write_still}))
        if not write_still:
            return {"FINISHED"}
        target = render.filepath
        if not target:
            raise RuntimeError("ไม่ตั้ง render.filepath — Blender จะไม่รู้จะเขียนที่ไหน")
        path = pathlib.Path(target)
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            path = pathlib.Path(str(path) + ".png")     # เลียนแบบการเติมนามสกุลของ Blender
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG_1X1)
        self.saved_to.append(str(path))
        return {"FINISHED"}

    def render(self, write_still: bool = False, **kwargs):  # noqa: ARG002
        if DATA.scenes[0].camera is None:
            # ตรงกับของจริง: เรนเดอร์โดยไม่มีกล้อง = error
            raise RuntimeError("Cannot render, no camera")
        return self._write("render", write_still)

    def opengl(self, write_still: bool = False, **kwargs):  # noqa: ARG002
        if getattr(app, "background", True):
            # ของจริง: opengl render ใช้ไม่ได้ในโหมด -b (ไม่มี OpenGL context)
            raise RuntimeError("OpenGL render is not available in background mode")
        return self._write("opengl", write_still)


class _FakeWmOps:
    def __init__(self, ops: FakeOps):
        self._ops = ops
        self.saved_to = []

    def save_as_mainfile(self, filepath=""):
        self._ops.calls.append(("wm.save_as_mainfile", {"filepath": filepath}))
        self.saved_to.append(filepath)
        return {"FINISHED"}

    def save_mainfile(self):
        self._ops.calls.append(("wm.save_mainfile", {}))
        return {"FINISHED"}

    def quit_blender(self):  # มีไว้ให้เทสต์ตรวจว่าด่านความปลอดภัยกันได้จริง
        self._ops.calls.append(("wm.quit_blender", {}))
        return {"FINISHED"}


_VERT_COUNTS = {"cube": (8, 6), "sphere": (482, 480), "ico_sphere": (42, 80),
                "cylinder": (64, 64), "cone": (66, 64), "plane": (4, 1),
                "circle": (32, 1), "torus": (576, 576), "monkey": (507, 500),
                "grid": (121, 100)}
_BASE_NAMES = {"cube": "Cube", "sphere": "Sphere", "ico_sphere": "Icosphere",
               "cylinder": "Cylinder", "cone": "Cone", "plane": "Plane",
               "circle": "Circle", "torus": "Torus", "monkey": "Suzanne",
               "grid": "Grid"}


def _create_object_for(op_name: str, kwargs: dict) -> FakeObject:
    key = op_name.replace("primitive_", "").replace("_add", "")
    loc = kwargs.get("location", (0.0, 0.0, 0.0))
    obj = FakeObject(_unique_name(_BASE_NAMES.get(key, "Object")), "MESH", loc)
    v, p = _VERT_COUNTS.get(key, (8, 6))
    obj.data = FakeMesh(obj.name + "_mesh", v, p)
    if "rotation" in kwargs:
        obj.rotation_euler = list(kwargs["rotation"])
    DATA.objects.add(obj)
    DATA.scenes[0].collection.objects.append(obj)
    obj.users_collection = [DATA.scenes[0].collection]
    return obj


def _unique_name(base: str) -> str:
    if base not in DATA.objects:
        return base
    n = 1
    while f"{base}.{n:03d}" in DATA.objects:
        n += 1
    return f"{base}.{n:03d}"


# ------------------------------------------------------------------ app
class FakeTimers:
    def __init__(self):
        self.registered = []

    def register(self, fn, first_interval=0.1, persistent=False):  # noqa: ARG002
        self.registered.append(fn)
        return fn

    def unregister(self, fn):
        if fn in self.registered:
            self.registered.remove(fn)
        return fn

    def is_registered(self, fn):
        return fn in self.registered


class FakeApp:
    def __init__(self, version=(5, 2, 0), background=True):
        self.version = version
        self.background = background
        self.timers = FakeTimers()


# ------------------------------------------------------------------ data
class FakeData:
    def __init__(self):
        self.objects = FakeCollection()
        self.meshes = FakeTypedCollection(FakeMesh)
        self.materials = FakeTypedCollection(FakeMaterial)
        self.collections = FakeCollection()
        self.cameras = FakeTypedCollection(FakeCamera)
        self.lights = FakeTypedCollection(FakeLight)
        self.scenes = [FakeScene()]
        self.filepath = ""
        self.is_dirty = False


DATA = FakeData()


def reset(background: bool = True):
    """ล้างสถานะให้เทสต์แต่ละข้อเริ่มจากศูนย์"""
    global DATA, app, ops, context, data
    DATA = FakeData()
    globals()["DATA"] = DATA
    globals()["data"] = DATA          # bpy.data
    app = FakeApp(background=background)
    ops = FakeOps()
    scene = DATA.scenes[0]
    # ฉากตั้งต้น: กล้อง 1 + ไฟ 1 + ลูกบาศก์ 1 (เหมือนไฟล์เริ่มต้นของ Blender)
    cam = FakeObject("Camera", "CAMERA", (7.36, -6.93, 4.96))
    light = FakeObject("Light", "LIGHT", (4.08, 1.01, 5.90))
    cube = FakeObject("Cube", "MESH", (0.0, 0.0, 0.0))
    for o in (cam, light, cube):
        DATA.objects.add(o)
        scene.collection.objects.append(o)
        o.users_collection = [scene.collection]
    DATA.cameras.add(cam)
    DATA.lights.add(light)
    scene.camera = cam              # เหมือนไฟล์เริ่มต้นของ Blender (มีกล้องตั้งไว้แล้ว)
    props = FakeSceneCollection("Props", parent=scene.collection)
    scene.collection.children.append(props)
    DATA.collections.add(props)
    a = FakeObject("tree_a", "MESH", (1.0, 2.0, 3.0))
    a.parent = cube
    cube.children.append(a)
    DATA.objects.add(a)
    props.objects.append(a)
    a.users_collection = [props]
    a.modifiers.append(FakeModifier("Subdivision"))
    context = type("Ctx", (), {"scene": scene})()
    globals()["context"] = context


# ค่าเริ่มต้นเมื่อ import (ให้เทสต์เรียก reset() เองได้)
app = FakeApp()
ops = FakeOps()
context = type("Ctx", (), {"scene": DATA.scenes[0]})()
# ชื่อ attribute ต้องตรงกับ API จริง: bpy.data / bpy.ops / bpy.app / bpy.context
data = DATA

