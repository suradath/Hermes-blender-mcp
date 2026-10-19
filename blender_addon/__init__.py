# -*- coding: utf-8 -*-
"""
Hermes Blender MCP Bridge — ส่วนเสริม (Add-on) สำหรับ Blender 5.2
================================================================

ใช้เมื่อคุณ **เปิด Blender พร้อมหน้าต่างอยู่แล้ว** และอยากให้ Hermes เข้ามาสั่งงาน
(โหมด ``-b`` ไม่ต้องใช้ไฟล์นี้ — MCP server เปิด Blender ให้เองอยู่แล้ว)

ทำไมต้องเป็นแบบนี้
------------------
``bpy`` ไม่ thread-safe: เรียกจาก thread อื่นได้ hard crash ไม่ใช่ exception
แต่ในโหมดมีหน้าต่าง main thread เป็นของ Blender ไฟล์นี้จึง:

  1. ให้ ``blender_bridge.TimerPump`` รับคำสั่งใน **thread แยก** (ซ็อกเก็ต)
  2. ส่งงานให้ main thread ทำผ่าน ``bpy.app.timers`` (คิวงาน + Future รอผล)

ติดตั้ง
------
คัดลอก **ทั้งโฟลเดอร์** นี้พร้อม ``blender_bridge.py`` ไปไว้ในโฟลเดอร์ชื่อ
``blender_mcp_bridge`` ใต้ addons ของ Blender:

    Windows : %APPDATA%\\Blender Foundation\\Blender\\5.2\\scripts\\addons\\blender_mcp_bridge\\
    Linux   : ~/.config/blender/5.2/scripts/addons/blender_mcp_bridge/
    macOS   : ~/Library/Application Support/Blender/5.2/scripts/addons/blender_mcp_bridge/

(ต้องมี ``__init__.py`` = ไฟล์นี้ และ ``blender_bridge.py`` อยู่ในโฟลเดอร์เดียวกัน)
"""

bl_info = {
    "name": "Hermes Blender MCP Bridge",
    "author": "LPM-AI-AST / โรงเรียนลำปลายมาศ",
    "version": (1, 0, 10),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > Blender MCP",
    "description": "เปิดสะพานให้ Hermes (MCP) สั่งงาน Blender ได้ระหว่างที่หน้าต่างเปิดอยู่",
    "category": "Development",
}

import importlib.util
import os
import pathlib
import secrets
import sys

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

ADDON_DIR = pathlib.Path(__file__).resolve().parent
RUNTIME: dict = {"pump": None, "timer": None, "error": ""}


# --------------------------------------------------------------------- โหลดสะพาน
def _bridge_candidates():
    """ที่ที่อาจมี blender_bridge.py — เรียงตามความน่าจะเป็น"""
    env = os.environ.get("BLENDER_MCP_DIR", "").strip()
    out = [ADDON_DIR, ADDON_DIR.parent]
    if env:
        out.append(pathlib.Path(env))
    try:  # เผื่อผู้ใช้ตั้งค่าไว้ในหน้าตั้งค่าของ add-on
        out.append(pathlib.Path(bpy.context.preferences.addons[__package__]
                                .preferences.bridge_dir))
    except Exception:
        pass
    return [p / "blender_bridge.py" for p in out if p]


def load_bridge():
    """โหลดโมดูลสะพานจากไฟล์ (ไม่พึ่ง sys.path เพื่อไม่ให้ชนกับอย่างอื่น)"""
    for path in _bridge_candidates():
        if path.is_file():
            name = "lpm_blender_bridge"
            if name in sys.modules:
                return sys.modules[name]
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            return mod
    tried = "\n".join(f"  • {p}" for p in _bridge_candidates())
    raise FileNotFoundError(
        "หา blender_bridge.py ไม่เจอ — ต้องวางไฟล์นี้ไว้โฟลเดอร์เดียวกับ add-on\n"
        f"ค้นหาใน:\n{tried}\n"
        "หรือตั้งตัวแปรสภาพแวดล้อม BLENDER_MCP_DIR ให้ชี้ไปที่โฟลเดอร์โปรเจกต์")


def start_bridge(context=None) -> tuple[bool, str]:
    """เริ่มสะพาน — ใช้ร่วมกันทั้งปุ่มในแผงและการเปิดอัตโนมัติ

    คืน (สำเร็จ?, ข้อความ) เพื่อให้ผู้เรียกแสดงผลได้ทั้งสองทาง
    """
    context = context or bpy.context
    s = _settings(context)
    if s.running:
        return False, "สะพานทำงานอยู่แล้ว"
    if s.use_token and not s.token:
        s.token = secrets.token_urlsafe(18)
    try:
        bridge = load_bridge()
    except Exception as exc:  # noqa: BLE001
        RUNTIME["error"] = str(exc)
        s.status = "โหลด blender_bridge.py ไม่ได้"
        return False, str(exc)
    try:
        pump = bridge.TimerPump(s.host, s.port, s.token if s.use_token else "", interval=0.05)
        pump.start()
        # ลงทะเบียน timer บน main thread — ต้องเรียกจากตรงนี้เท่านั้น
        RUNTIME["timer"] = pump.drain
        bpy.app.timers.register(pump.drain, first_interval=0.05, persistent=True)
        RUNTIME["pump"] = pump
        RUNTIME["error"] = ""
        s.running = True
        s.status = f"ทำงานอยู่ที่ {s.host}:{s.port}" + (" (มี token)" if s.use_token else "")
        return True, f"เริ่มสะพานที่ {s.host}:{s.port} แล้ว"
    except Exception as exc:  # noqa: BLE001
        RUNTIME["error"] = str(exc)
        s.status = "เริ่มไม่สำเร็จ"
        return False, f"เริ่มสะพานไม่สำเร็จ: {exc}"


def stop_bridge(context=None) -> tuple[bool, str]:
    """หยุดสะพาน (ใช้ร่วมกันทั้งปุ่มและการปิด add-on)"""
    context = context or bpy.context
    s = _settings(context)
    pump, timer = RUNTIME.get("pump"), RUNTIME.get("timer")
    if timer is not None:
        try:
            if bpy.app.timers.is_registered(timer):
                bpy.app.timers.unregister(timer)
        except Exception:
            pass
    if pump is not None:
        try:
            pump.stop()
        except Exception:
            pass
    RUNTIME.update({"pump": None, "timer": None})
    s.running = False
    s.status = "หยุดแล้ว"
    return True, "หยุดสะพานแล้ว"


# --------------------------------------------------------------------- เปิดอัตโนมัติ
def _autostart_timer():
    """เรียกโดย bpy.app.timers หลังโหลดไฟล์ — เปิดสะพานให้เองถ้าผู้ใช้เปิดไว้

    ⚠️ ทำเฉพาะเมื่อมีหน้าต่าง Blender: ในโหมด ``-b`` ค่า ``bpy.app.timers``
    ไม่ทำงานอยู่แล้ว (นี่คือเหตุที่โปรเจกต์นี้เลือก "บล็อกบน main thread" ในโหมด -b
    แทนที่จะพึ่ง timer) จึงไม่ต้องพยายาม
    """
    try:
        if bpy.app.background:
            return None
        s = _settings()
        if s.autostart and not s.running:
            ok, msg = start_bridge()
            print(f"[lpm-bridge] เปิดอัตโนมัติ: {msg}" if ok else f"[lpm-bridge] {msg}")
    except Exception as exc:  # noqa: BLE001
        print(f"[lpm-bridge] เปิดอัตโนมัติไม่สำเร็จ: {exc}")
    return None      # ไม่ต้องเรียกซ้ำ


def _schedule_autostart(_unused=None):
    """ต่อท้าย bpy.app.handlers.load_post — ตั้ง timer ไว้คอยเปิดสะพาน"""
    try:
        if bpy.app.background:
            return
        if not bpy.app.timers.is_registered(_autostart_timer):
            bpy.app.timers.register(_autostart_timer, first_interval=1.0)
    except Exception as exc:  # noqa: BLE001
        print(f"[lpm-bridge] ตั้งเวลเปิดอัตโนมัติไม่สำเร็จ: {exc}")


# --------------------------------------------------------------------- ตั้งค่า
class LPMBridgeSettings(PropertyGroup):
    port: IntProperty(
        name="พอร์ต", default=9876, min=1024, max=65535,
        description="พอร์ตที่สะพานจะเปิดรอ (ให้ MCP server ต่อเข้ามา)")
    token: StringProperty(
        name="Token", default="",
        description="รหัสผ่านของสะพาน — ให้ MCP server ใช้ค่าเดียวกัน")
    use_token: BoolProperty(
        name="ใช้ token", default=True,
        description="ปิดได้ถ้าเครื่องนี้ใช้คนเดียวและอยากให้ตั้งค่าง่าย (ไม่แนะนำ)")
    host: StringProperty(name="โฮสต์", default="127.0.0.1")
    autostart: BoolProperty(
        name="เปิดสะพานอัตโนมัติเมื่อโหลดไฟล์", default=True,
        description="เปิดสะพานให้เองเมื่อเปิดไฟล์ .blend — ทำเฉพาะเมื่อมีหน้าต่าง Blender "
                    "(โหมด -b ไม่ทำ เพราะ bpy.app.timers ไม่ทำงานในโหมดนั้น)")
    running: BoolProperty(default=False)
    status: StringProperty(default="ยังไม่เริ่ม")


def _settings(context=None) -> LPMBridgeSettings:
    return (context or bpy.context).scene.lpm_bridge


# --------------------------------------------------------------------- ตัวดำเนินการ
class LPM_OT_start_bridge(Operator):
    bl_idname = "lpm_bridge.start"
    bl_label = "เริ่มสะพาน (Start bridge)"
    bl_description = "เปิดพอร์ตให้ Hermes เชื่อมต่อเข้ามาสั่งงาน Blender"

    def execute(self, context):
        ok, msg = start_bridge(context)
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        return {"FINISHED"} if ok else {"CANCELLED"}


class LPM_OT_stop_bridge(Operator):
    bl_idname = "lpm_bridge.stop"
    bl_label = "หยุดสะพาน (Stop bridge)"
    bl_description = "ปิดพอร์ตและยกเลิก timer"

    def execute(self, context):
        ok, msg = stop_bridge(context)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class LPM_OT_new_token(Operator):
    bl_idname = "lpm_bridge.new_token"
    bl_label = "สร้าง token ใหม่"
    bl_description = "สุ่มรหัสใหม่ (ต้องอัปเดตฝั่ง Hermes ด้วย)"

    def execute(self, context):
        s = _settings(context)
        s.token = secrets.token_urlsafe(18)
        self.report({"INFO"}, "สร้าง token ใหม่แล้ว — อย่าลืมอัปเดต config ของ Hermes")
        return {"FINISHED"}


class LPM_OT_copy_hint(Operator):
    bl_idname = "lpm_bridge.copy_hint"
    bl_label = "คัดลอกคำสั่งเชื่อมต่อ"
    bl_description = "คัดลอกบรรทัดที่ต้องใส่ใน config ของ Hermes"

    def execute(self, context):
        s = _settings(context)
        line = (f'--attach {s.host}:{s.port}'
                + (f' --token {s.token}' if s.use_token and s.token else ""))
        context.window_manager.clipboard = line
        self.report({"INFO"}, f"คัดลอกแล้ว: {line}")
        return {"FINISHED"}


# --------------------------------------------------------------------- แผงควบคุม
class LPM_PT_bridge(Panel):
    bl_label = "Blender MCP (Hermes)"
    bl_idname = "LPM_PT_bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Blender MCP"

    def draw(self, context):
        layout = self.layout
        s = _settings(context)

        box = layout.box()
        box.label(text="สถานะสะพาน", icon="INFO")
        box.label(text=s.status, icon="CHECKMARK" if s.running else "X")

        col = layout.column()
        col.prop(s, "host")
        col.prop(s, "port")
        col.prop(s, "autostart")
        col.prop(s, "use_token")
        if s.use_token:
            col.prop(s, "token", text="Token")
            col.operator("lpm_bridge.new_token", icon="FILE_REFRESH")

        row = layout.row(align=True)
        row.enabled = not s.running
        row.operator("lpm_bridge.start", icon="PLAY")
        row2 = layout.row()
        row2.enabled = s.running
        row2.operator("lpm_bridge.stop", icon="PAUSE")

        if s.running:
            layout.operator("lpm_bridge.copy_hint", icon="COPYDOWN")
            layout.label(text="เอาไปใส่ใน config ของ Hermes:", icon="INFO")
            hint = (f'--attach {s.host}:{s.port}'
                    + (f' --token {s.token}' if s.use_token and s.token else ""))
            box = layout.box()
            for chunk in [hint[i:i + 34] for i in range(0, len(hint), 34)]:
                box.label(text=chunk)

        if RUNTIME.get("error"):
            err = layout.box()
            err.label(text="ข้อผิดพลาด:", icon="ERROR")
            for line in str(RUNTIME["error"]).split("\n")[:6]:
                err.label(text=line[:60])


# --------------------------------------------------------------------- ลงทะเบียน
CLASSES = (LPMBridgeSettings, LPM_OT_start_bridge, LPM_OT_stop_bridge,
           LPM_OT_new_token, LPM_OT_copy_hint, LPM_PT_bridge)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lpm_bridge = bpy.props.PointerProperty(type=LPMBridgeSettings)
    # เปิดสะพานให้เองเมื่อโหลดไฟล์ (ถ้าผู้ใช้เปิดตัวเลือกไว้ และมีหน้าต่าง Blender)
    if _schedule_autostart not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_schedule_autostart)
    print("[lpm-bridge] add-on พร้อมใช้งาน — ดูแผงที่ View3D > Sidebar > Blender MCP")


def unregister():
    # ปิดสะพานเสมอเมื่อปิด add-on (ไม่ทิ้งพอร์ต/เธรดค้าง)
    try:
        stop_bridge()
    except Exception:
        pass
    try:
        if _schedule_autostart in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_schedule_autostart)
        if bpy.app.timers.is_registered(_autostart_timer):
            bpy.app.timers.unregister(_autostart_timer)
    except Exception:
        pass
    RUNTIME.update({"pump": None, "timer": None})
    del bpy.types.Scene.lpm_bridge
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
