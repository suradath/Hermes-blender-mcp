#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender_mcp_server.py — MCP Server (stdio) สำหรับบังคับ Blender 5.2
====================================================================

รันด้วย Python ของ *เครื่อง* (ไม่ใช่ของ Blender) แล้วมันจะเปิด Blender ให้เอง
    python blender_mcp_server.py                  # เปิด Blender แบบไม่มีหน้าต่าง
    python blender_mcp_server.py --gui            # เปิด Blender พร้อมหน้าต่าง
    python blender_mcp_server.py --attach 127.0.0.1:9876 --token XXX

ทำไมต้องมีสองโปรเซส (อ่านก่อนแก้โค้ด)
------------------------------------
MCP สื่อสารผ่าน stdio = ใช้ **stdout เป็นท่อ JSON-RPC** แต่ ``blender -b``
พ่นข้อความต้อนรับและบันทึกของตัวเองลง stdout ตั้งแต่ก่อนสคริปต์จะได้รัน
ถ้าให้ MCP server รันใน Blender เอง ไคลเอนต์จะอ่านเจอขยะก่อน JSON แรก → พัง

และ ``bpy`` **ไม่ thread-safe** — เรียกจาก thread อื่นได้ hard crash ไม่ใช่ exception
ดังนั้น:

    Hermes ──stdio(JSON-RPC)──► ไฟล์นี้ (Python ของเครื่อง, ใช้ mcp SDK)
                                   │  ซ็อกเก็ต 127.0.0.1 + token
                                   ▼
                              blender_bridge.py  (รันใน Blender, main thread, stdlib ล้วน)

ผลพลอยได้ที่สำคัญ: **ไม่ต้อง pip install อะไรลง Blender เลย** — บน Windows จึงไม่ต้อง
สิทธิ์ผู้ดูแลระบบ และไม่ต้องกังวลว่า wheel จะตรงรุ่น Python ของ Blender หรือไม่
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import pathlib
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_SCRIPT = HERE / "blender_bridge.py"
SERVER_VERSION = "1.0.0"
MIN_BLENDER = (4, 0)          # ใช้ API ที่มีมาตั้งแต่ 4.0 (5.2 คือเป้าหมาย)


# ===========================================================================
#  บันทึก — ห้ามเขียนลง stdout เด็ดขาด (stdout เป็นของ JSON-RPC)
# ===========================================================================

class Log:
    def __init__(self) -> None:
        self.path: pathlib.Path | None = None
        self._lock = threading.Lock()

    def open(self, path: pathlib.Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            self.path = path
        except Exception:
            self.path = None

    def __call__(self, *parts: object) -> None:
        line = "[blender-mcp] " + " ".join(str(p) for p in parts)
        with self._lock:
            print(line, file=sys.stderr, flush=True)
            if self.path is not None:
                try:
                    with self.path.open("a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
                except Exception:
                    pass


log = Log()


# ===========================================================================
#  หาตัว Blender
# ===========================================================================

def _windows_roots() -> list[str]:
    """โฟลเดอร์รากที่ Blender มักถูกติดตั้งไว้ (ค่าเริ่มต้นไม่ต้องพึ่ง env)

    ⚠️ Hermes ส่งตัวแปรสภาพแวดล้อมแบบ **กรองแล้ว** ให้โปรเซสลูก
    (เฉพาะ PATH/HOME/USER/LANG/... — ไม่มี PROGRAMFILES/LOCALAPPDATA)
    ถ้าพึ่งตัวแปรอย่างเดียว จะหา Blender ไม่เจอทั้งที่ติดตั้งอยู่
    """
    home = pathlib.Path.home()
    roots = [
        os.environ.get("ProgramFiles") or r"C:\Program Files",
        os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)",
        os.environ.get("ProgramW6432") or r"C:\Program Files",
        os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local"),
    ]
    out: list[str] = []
    for root in roots:
        if root and root not in out:
            out.append(root)
    return out


def _windows_candidates() -> list[pathlib.Path]:
    """ไฟล์ blender.exe ที่มีอยู่จริง — ไล่ทุกรุ่นที่ติดตั้งไว้"""
    out: list[pathlib.Path] = []
    for root in _windows_roots():
        out += sorted((pathlib.Path(root) / "Blender Foundation")
                      .glob("Blender */blender.exe"))
        out += sorted((pathlib.Path(root) / "Programs" / "Blender Foundation")
                      .glob("Blender */blender.exe"))
    # Steam
    for steam in (r"C:\Program Files (x86)\Steam\steamapps\common",
                  r"C:\Program Files\Steam\steamapps\common"):
        p = pathlib.Path(steam) / "Blender" / "blender.exe"
        if p.is_file():
            out.append(p)
    return out


def _other_candidates() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    mac = pathlib.Path("/Applications")
    if mac.is_dir():
        out += sorted(mac.glob("Blender*.app/Contents/MacOS/Blender"))
    out += [pathlib.Path(p) for p in
            ("/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender",
             "/var/lib/flatpak/exports/bin/org.blender.Blender")]
    return out


def _version_key(path: pathlib.Path) -> tuple:
    m = re.search(r"(\d+)\.(\d+)", str(path))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blender(explicit: str | None = None) -> tuple[pathlib.Path | None, str]:
    """คืน (ที่อยู่ blender, วิธีที่เจอ) — บอกที่มาเพื่อให้ผู้ใช้ง่ายต่อการแก้"""
    if explicit:
        p = pathlib.Path(explicit).expanduser()
        return (p, "ระบุเองจาก --blender") if p.is_file() else (None, f"ไม่พบไฟล์: {p}")

    env = os.environ.get("BLENDER_EXE")
    if env:
        p = pathlib.Path(env).expanduser()
        if p.is_file():
            return p, "จากตัวแปรสภาพแวดล้อม BLENDER_EXE"

    which = shutil.which("blender")
    if which:
        return pathlib.Path(which), "เจอใน PATH"

    cands = _windows_candidates() if platform.system() == "Windows" else _other_candidates()
    cands = [c for c in cands if c.is_file()]
    if cands:
        cands.sort(key=_version_key, reverse=True)   # เอารุ่นใหม่สุดก่อน
        return cands[0], f"เจอในเครื่อง ({len(cands)} รุ่น)"
    return None, "หาไม่เจอ"


# ===========================================================================
#  ฝั่งไคลเอนต์ของสะพาน (ซ็อกเก็ต)
# ===========================================================================

class BridgeError(RuntimeError):
    pass


class BridgeClient:
    """คุยกับ blender_bridge.py ที่รันอยู่ใน Blender (บรรทัดละ JSON)"""

    def __init__(self, host: str, port: int, token: str, timeout: float = 120.0):
        self.host, self.port, self.token = host, port, token
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._file = None
        self._lock = threading.Lock()
        self._seq = 0
        self.info: dict = {}

    # ---------------------------------------------------------------- ต่อ
    def connect(self, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        last: Exception | None = None
        while time.time() < deadline:
            try:
                s = socket.create_connection((self.host, self.port), timeout=3.0)
                s.settimeout(self.timeout)
                f = s.makefile("rwb")
                f.write(json.dumps({"token": self.token}).encode() + b"\n")
                f.flush()
                line = f.readline()
                if not line:
                    raise BridgeError("สะพานไม่ตอบตอนตรวจ token")
                reply = json.loads(line.decode("utf-8"))
                if not reply.get("ok"):
                    raise BridgeError(f"สะพานปฏิเสธ: {reply.get('error')}")
                self._sock, self._file = s, f
                self.info = self._request_unlocked("hello", {}, timeout=10.0)
                return
            except Exception as exc:  # noqa: BLE001 - ลองซ้ำจนหมดเวลา
                last = exc
                time.sleep(0.4)
        raise BridgeError(f"ต่อสะพานไม่สำเร็จใน {timeout:.0f} วินาที: {last}")

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def close(self) -> None:
        try:
            if self._file:
                self._file.close()
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = self._file = None

    # -------------------------------------------------------------- รับส่ง
    def _request_unlocked(self, method: str, params: dict, timeout: float | None = None):
        if self._sock is None or self._file is None:
            raise BridgeError("ยังไม่ได้เชื่อมต่อกับ Blender")
        self._seq += 1
        rid = self._seq
        payload = json.dumps({"id": rid, "method": method, "params": params},
                             ensure_ascii=False)
        old = self._sock.gettimeout()
        self._sock.settimeout(timeout or self.timeout)
        try:
            self._file.write(payload.encode("utf-8") + b"\n")
            self._file.flush()
            line = self._file.readline()
        except socket.timeout as exc:
            raise BridgeError(
                "Blender ไม่ตอบภายในเวลาที่ตั้งไว้ — คำสั่งอาจยังทำงานอยู่ "
                "(เช่น ลูปยาวหรือเรนเดอร์) Blender ไม่สามารถถูกสั่งหยุดกลางคันได้"
            ) from exc
        except Exception as exc:
            self._sock = self._file = None
            raise BridgeError(f"ขาดการเชื่อมต่อกับ Blender: {exc}") from exc
        finally:
            if self._sock is not None:
                try:
                    self._sock.settimeout(old)
                except Exception:
                    pass
        if not line:
            self._sock = self._file = None
            raise BridgeError("Blender ปิดการเชื่อมต่อ (อาจปิดตัวไปแล้ว)")
        try:
            reply = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise BridgeError(f"สะพานตอบกลับไม่ใช่ JSON: {line[:200]!r}") from exc
        if reply.get("id") not in (rid, None):
            raise BridgeError(f"คำตอบสลับลำดับ (ได้ id {reply.get('id')} คาดว่า {rid})")
        if not reply.get("ok"):
            kind = reply.get("error_type", "")
            raise BridgeError(reply.get("error") or "สะพานรายงานข้อผิดพลาด",
                              ) if kind == "internal" else BridgeError(reply.get("error"))
        return reply.get("result")

    def request(self, method: str, params: dict | None = None, timeout: float | None = None):
        with self._lock:                      # ซ็อกเก็ตใช้พร้อมกันไม่ได้
            return self._request_unlocked(method, params or {}, timeout)

    def call_tool(self, name: str, arguments: dict, timeout: float | None = None):
        clean = {k: v for k, v in (arguments or {}).items() if v is not None}
        return self.request("call_tool", {"name": name, "arguments": clean}, timeout)


# ===========================================================================
#  ตัวจัดการ Blender (เปิด/ปิด/ตามหา)
# ===========================================================================

class BlenderProcess:
    def __init__(self, blender: pathlib.Path, args: argparse.Namespace):
        self.blender = blender
        self.args = args
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self.token = secrets.token_urlsafe(24)
        self._ready = threading.Event()
        self._failed = threading.Event()
        self._err_lines: list[str] = []

    # ---------------------------------------------------------------- เปิด
    def start(self) -> None:
        cmd = [str(self.blender), "--background", "--factory-startup",
               "--python", str(BRIDGE_SCRIPT), "--",
               "--host", "127.0.0.1", "--port", "0", "--token", self.token]
        if not self.args.headless_safe_startup:
            # เปิดไฟล์ .blend ที่ระบุ (ถ้ามี) — Blender จะโหลดก่อนรันสคริปต์
            if self.args.blend_file:
                cmd.insert(2, str(self.args.blend_file))
        if self.args.gui:
            # เอา --background ออก แล้วเปิดหน้าต่างปกติ
            cmd = [c for c in cmd if c != "--background"]
            cmd = [c for c in cmd if c != "--factory-startup"]
            if self.args.blend_file:
                cmd.insert(1, str(self.args.blend_file))
        # ส่งตัวแปรที่บอกโหมด bridge ชัดเจน
        cmd += ["--mode", "main" if not self.args.gui else "timer",
                "--interval", str(self.args.interval)]

        log("เปิด Blender:", " ".join(cmd))
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
            errors="replace", bufsize=1, cwd=str(self.args.working_dir or HERE),
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
        )
        threading.Thread(target=self._read_output, name="blender-output", daemon=True).start()

    def _read_output(self) -> None:
        """อ่าน stdout/stderr ของ Blender — หาบรรทัดที่บอกว่าสะพานพร้อม"""
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.rstrip("\n")
            self._err_lines.append(line)
            if len(self._err_lines) > 400:
                del self._err_lines[:200]
            # สะพานประกาศตัวด้วย JSON บรรทัดเดียว — ต้องมาก่อนบรรทัดของ Blender เอง
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict) and obj.get("bridge_ready") and obj.get("port"):
                    self.port = int(obj["port"])
                    self._ready.set()
                    continue
            if "[blender-bridge]" in line or "Error" in line or "error" in line:
                log("blender:", line)
        self._failed.set()

    def wait_ready(self, timeout: float) -> bool:
        if self._ready.wait(timeout):
            return True
        return False

    def tail(self, n: int = 25) -> str:
        return "\n".join(self._err_lines[-n:])

    def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            log("ปิด Blender")
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None


# ===========================================================================
#  ตั้งค่า MCP server
# ===========================================================================

def build_server(cfg: argparse.Namespace) -> tuple[MCPServer, "Runtime"]:
    srv = MCPServer(
        name="blender",
        version=SERVER_VERSION,
        instructions=(
            "ควบคุม Blender 5.2 ผ่าน bpy — อ่านฉาก สร้าง/ขยับวัตถุ ใส่สี และรันสคริปต์ bpy\n"
            "เริ่มด้วย get_scene_hierarchy เพื่อดูว่ามีอะไรอยู่ในไฟล์ก่อนเสมอ\n"
            "ระวัง: หน่วยหมุนเป็น 'องศา' ในเครื่องมือนี้ แต่ bpy เก็บเป็นเรเดียน (แปลงให้แล้ว)\n"
            "execute_blender_script มีด่านตรวจโค้ด — ถ้าจำเป็นจริงให้ส่ง allow_unsafe=true"
        ),
    )
    rt = Runtime(cfg)
    register_tools(srv, rt)
    register_resources(srv, rt)
    return srv, rt


class Runtime:
    """ถือการเชื่อมต่อกับ Blender — เปิด Blender ตอนใช้ครั้งแรก (lazy)"""

    def __init__(self, cfg: argparse.Namespace):
        self.cfg = cfg
        self.client = BridgeClient("127.0.0.1", 0, "", timeout=cfg.timeout)
        self.proc: BlenderProcess | None = None
        self._lock = threading.Lock()

    # --------------------------------------------------------- เตรียมพร้อม
    def ensure(self) -> BridgeClient:
        with self._lock:
            if self.client.connected:
                return self.client

            if self.cfg.attach:
                host, _, port = self.cfg.attach.rpartition(":")
                self.client.host, self.client.port = host or "127.0.0.1", int(port)
                self.client.token = self.cfg.token or self.client.token
                self.client.connect(timeout=self.cfg.spawn_timeout)
                log(f"ต่อกับ Blender ที่กำลังรันอยู่ที่ {self.cfg.attach}")
                return self.client

            found, how = find_blender(self.cfg.blender)
            if found is None:
                raise BridgeError(
                    f"หา Blender ไม่เจอ ({how}) — ระบุด้วย --blender "
                    f"หรือตัวแปรสภาพแวดล้อม BLENDER_EXE "
                    f"(Windows: \"C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe\")")
            log(f"ใช้ Blender: {found} ({how})")

            self.proc = BlenderProcess(found, self.cfg)
            self.proc.start()
            if not self.proc.wait_ready(self.cfg.spawn_timeout):
                tail = self.proc.tail()
                self.proc.stop()
                self.proc = None
                raise BridgeError(
                    f"Blender ไม่พร้อมภายใน {self.cfg.spawn_timeout:.0f} วินาที — "
                    f"บันทึกท้าย ๆ:\n{tail}\n"
                    f"ลองเปิดด้วยตนเองเพื่อดูข้อผิดพลาด: "
                    f"\"{found}\" --background --python \"{BRIDGE_SCRIPT}\" -- --port 0 --selftest")
            self.client.port = self.proc.port or 0
            self.client.token = self.proc.token
            self.client.connect(timeout=30)
            log(f"พร้อมใช้งาน · Blender {self.client.info.get('blender')} · "
                f"ไฟล์ {self.client.info.get('filepath') or '(ยังไม่บันทึก)'}")
            return self.client

    def call(self, tool: str, /, **kwargs):
        client = self.ensure()
        return client.call_tool(tool, kwargs)

    def shutdown(self) -> None:
        try:
            if self.client.connected:
                self.client.close()
        finally:
            if self.proc is not None:
                self.proc.stop()
                self.proc = None


# ===========================================================================
#  เครื่องมือ (ลงทะเบียนกับ MCP)
# ===========================================================================

async def _run(fn):
    """งานที่บล็อก (ซ็อกเก็ต/bpy) ต้องไม่ไปอุด event loop ของ MCP

    ⚠️ ต้องแปลงข้อผิดพลาดเป็น ``ToolError`` ของ SDK เองเสมอ
    ถ้าปล่อย exception ธรรมดาออกไป SDK จะ **กลืนข้อความทิ้ง** เหลือแค่
    "Error executing tool X" — AI จะไม่รู้ว่าทำไมผิด (เช่น "ไม่พบวัตถุชื่อ ...")
    เจอพฤติกรรมนี้จริงตอนทดสอบ end-to-end (ดู README หัวข้อ "บทเรียน")
    """
    try:
        return await anyio.to_thread.run_sync(fn)
    except BridgeError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"{type(exc).__name__}: {exc}") from exc


def register_tools(srv: MCPServer, rt: Runtime) -> None:

    @srv.tool()
    async def get_scene_hierarchy(include_hidden: bool = True, name_filter: str = "",
                                  max_objects: int = 500) -> dict:
        """Read the active scene: collection tree, every object with its
        transform/type/mesh stats, and counts by type. Start here to see what
        exists before changing anything. Use name_filter to find objects by
        partial name, max_objects to limit a very large scene."""
        return await _run(lambda: rt.call("get_scene_hierarchy",
                                          include_hidden=include_hidden,
                                          name_filter=name_filter,
                                          max_objects=max_objects))

    @srv.tool()
    async def add_primitive_mesh(primitive: str = "cube", name: str = "",
                                 location: list[float] | None = None,
                                 rotation: list[float] | None = None,
                                 scale: list[float] | None = None,
                                 radius: float = 1.0, size: float = 2.0,
                                 collection: str = "") -> dict:
        """Add a primitive mesh to the scene. primitive is one of: cube, sphere,
        cylinder, plane, cone, torus, monkey, circle, grid, ico_sphere.
        location/rotation/scale are [x,y,z]; rotation is in DEGREES. radius
        applies to sphere/cylinder/cone/circle/torus, size to cube/plane/monkey.
        collection optionally moves the new object into a named collection."""
        return await _run(lambda: rt.call(
            "add_primitive_mesh", primitive=primitive, name=name,
            location=location or [0.0, 0.0, 0.0],
            rotation=rotation or [0.0, 0.0, 0.0],
            scale=scale or [1.0, 1.0, 1.0],
            radius=radius, size=size, collection=collection))

    @srv.tool()
    async def modify_object_transform(name: str,
                                      location: list[float] | None = None,
                                      rotation: list[float] | None = None,
                                      scale: list[float] | None = None,
                                      relative: bool = False,
                                      rotation_mode: str = "") -> dict:
        """Move, rotate or resize an existing object by name. Pass only what you
        want to change; rotation is in DEGREES. relative=true adds to the current
        value (for scale it multiplies). Returns the values before and after."""
        return await _run(lambda: rt.call(
            "modify_object_transform", name=name, location=location,
            rotation=rotation, scale=scale, relative=relative, rotation_mode=rotation_mode))

    @srv.tool()
    async def get_object_details(name: str, include_custom_properties: bool = True) -> dict:
        """Full details for one object: world matrix, dimensions, rotation mode,
        modifiers, vertex groups, materials, parent/children and custom
        properties. Use when get_scene_hierarchy is not deep enough."""
        return await _run(lambda: rt.call("get_object_details", name=name,
                                          include_custom_properties=include_custom_properties))

    @srv.tool()
    async def delete_object(name: str, confirm: bool = False) -> dict:
        """Delete an object by name. The first call only reports what would be
        deleted — pass confirm=true to actually remove it."""
        return await _run(lambda: rt.call("delete_object", name=name, confirm=confirm))

    @srv.tool()
    async def set_object_material(name: str, color: list[float] | None = None,
                                  material_name: str = "", metallic: float = 0.0,
                                  roughness: float = 0.5, alpha: float = 1.0) -> dict:
        """Give a mesh object a simple Principled BSDF material. color is
        [r,g,b] in 0..1 (linear). Creates or reuses the material and assigns it
        to every slot of the object."""
        return await _run(lambda: rt.call(
            "set_object_material", name=name, color=color or [0.8, 0.8, 0.8],
            material_name=material_name, metallic=metallic, roughness=roughness, alpha=alpha))

    @srv.tool()
    async def save_blend_file(filepath: str = "") -> dict:
        """Save the current .blend. Without filepath it saves in place (the file
        must have been saved before). A '.blend' extension is added if missing."""
        return await _run(lambda: rt.call("save_blend_file", filepath=filepath))

    @srv.tool()
    async def execute_blender_script(code: str, allow_unsafe: bool = False,
                                     return_variables: str = "result") -> dict:
        """Run raw bpy Python inside Blender and return stdout, the value of the
        'result' variable (or names given in return_variables) and any error.
        By default the code is checked first and refused if it imports
        os/sys/subprocess/socket/..., calls open()/eval()/exec(), touches dunder
        attributes, or calls session-destroying operators like
        bpy.ops.wm.quit_blender(). Pass allow_unsafe=true to skip that check.
        This is a guardrail against mistakes, NOT a sandbox: allowed code can
        still modify the whole scene, so save your file first."""
        return await _run(lambda: rt.call("execute_blender_script", code=code,
                                          allow_unsafe=allow_unsafe,
                                          return_variables=return_variables))


# ===========================================================================
#  ทรัพยากร (Resources)
# ===========================================================================

def register_resources(srv: MCPServer, rt: Runtime) -> None:

    @srv.resource("blender://file/metadata", name="Blender file metadata",
                  description="ไฟล์ .blend ที่เปิดอยู่: ที่อยู่ไฟล์, render engine, "
                              "เฟรมปัจจุบัน/ช่วงเฟรม, ความละเอียด, และจำนวนของในไฟล์",
                  mime_type="application/json")
    def file_metadata() -> str:
        try:
            rt.ensure()
            payload = rt.client.request("file_metadata")
        except BridgeError as exc:
            raise ResourceError(str(exc)) from exc
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @srv.resource("blender://scene/hierarchy", name="Blender scene hierarchy",
                  description="ลำดับชั้นของฉากที่ใช้งานอยู่ (คอลเลกชัน + วัตถุ + transform)",
                  mime_type="application/json")
    def scene_hierarchy() -> str:
        try:
            return json.dumps(rt.call("get_scene_hierarchy"), ensure_ascii=False, indent=2)
        except BridgeError as exc:
            raise ResourceError(str(exc)) from exc


# ===========================================================================
#  CLI
# ===========================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="blender_mcp_server",
        description="MCP server (stdio) ที่บังคับ Blender 5.2 ผ่าน bpy")
    p.add_argument("--blender", default=os.environ.get("BLENDER_EXE", ""),
                   help="ที่อยู่ของ blender(.exe) — ถ้าไม่ใส่จะค้นหาเอง")
    p.add_argument("--blend-file", default="", help="ไฟล์ .blend ที่จะเปิดตั้งแต่ต้น")
    p.add_argument("--gui", action="store_true",
                   help="เปิด Blender พร้อมหน้าต่าง (ใช้โหมด timer ให้ bpy อยู่บน main thread)")
    p.add_argument("--attach", default="",
                   help="ต่อกับ Blender ที่รันอยู่แล้ว เช่น 127.0.0.1:9876 (ไม่เปิดใหม่)")
    p.add_argument("--token", default="", help="token ของสะพาน (ใช้กับ --attach)")
    p.add_argument("--timeout", type=float, default=120.0,
                   help="เวลารอต่อหนึ่งคำสั่ง (วินาที) — ค่าปริยาย 120")
    p.add_argument("--spawn-timeout", type=float, default=90.0,
                   help="เวลารอให้ Blender เปิดเสร็จ (วินาที)")
    p.add_argument("--interval", type=float, default=0.05,
                   help="คาบที่โหมด GUI ตรวจคิวงาน (วินาที)")
    p.add_argument("--log-file", default="", help="เขียนบันทึกลงไฟล์นี้ (stdout สงวนไว้ให้ JSON-RPC)")
    p.add_argument("--working-dir", default="", help="โฟลเดอร์ทำงานของ Blender")
    p.add_argument("--headless-safe-startup", action="store_true",
                   help="อย่าใส่ไฟล์ .blend ในบรรทัดคำสั่ง (ใช้เมื่อพาธมีปัญหากับ Blender)")
    p.add_argument("--check", action="store_true", help="ตรวจว่าเจอ Blender ไหม แล้วจบ")
    p.add_argument("--list-tools", action="store_true", help="พิมพ์รายการเครื่องมือแล้วจบ")
    p.add_argument("--selftest", action="store_true",
                   help="เริ่ม Blender จริง เรียกทุกเครื่องมือ แล้วจบ (ใช้ตรวจการติดตั้ง)")
    # ⚠️ ใช้ parse_known_args ไม่ใช่ parse_args
    #
    # ไคลเอนต์ MCP หลายตัวเติมอาร์กิวเมนต์ของตัวเองต่อท้ายบรรทัดคำสั่ง
    # (เกิดกับเราจริงตอน `hermes mcp add` ที่ต้องให้ --args อยู่ท้ายสุด — พอมี
    # ตัวเลือกของ Hermes ต่อท้าย มันกลายเป็นอาร์กิวเมนต์ของเซิร์ฟเวอร์)
    # ถ้าเราออกทันทีเพราะเจออาร์กิวเมนต์แปลก ไคลเอนต์จะรายงานแค่
    # "Connection closed" ซึ่งชี้ทางผิดไปไกลและหาสาเหตุยากมาก
    #
    # ⇒ ไม่ล้ม แต่ **บันทึกไว้ให้เห็น** (แนวทางเดียวกับ ahujasid/mcp-for-blender)
    args, unknown = p.parse_known_args(argv)
    args.unknown_args = list(unknown)
    if not args.log_file:
        args.log_file = str(pathlib.Path(tempfile.gettempdir()) / "blender-mcp" /
                            f"server-{os.getpid()}.log")
    if not args.working_dir:
        args.working_dir = None
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log.open(pathlib.Path(args.log_file))
    log(f"เริ่ม MCP server · บันทึกที่ {args.log_file} · Python {platform.python_version()}")
    if getattr(args, "unknown_args", None):
        log(f"⚠️  ข้ามอาร์กิวเมนต์ที่ไม่รู้จัก {len(args.unknown_args)} ตัว: "
            f"{' '.join(args.unknown_args)}")
        log("    มักเกิดจากไคลเอนต์ MCP เติมอาร์กิวเมนต์ของตัวเองต่อท้ายบรรทัดคำสั่ง "
            "(ถ้าไม่ตั้งใจ ให้ตรวจ config — โดยเฉพาะลำดับ --args ที่ต้องอยู่ท้ายสุด)")

    if args.check:
        found, how = find_blender(args.blender)
        print(f"Blender: {found if found else 'หาไม่เจอ'} ({how})")
        print(f"สคริปต์สะพาน: {BRIDGE_SCRIPT} {'✅' if BRIDGE_SCRIPT.is_file() else '❌ ไม่พบ'}")
        return 0 if found else 1

    srv, rt = build_server(args)

    if args.list_tools:
        import anyio as _anyio

        for t in _anyio.run(srv.list_tools):
            schema = (getattr(t, "input_schema", None)
                      or getattr(t, "inputSchema", None) or {})
            params = ", ".join((schema or {}).get("properties", {}))
            print(f"  • {t.name}({params})")
        return 0

    if args.selftest:
        return _selftest(rt)

    atexit.register(rt.shutdown)

    # เปิด Blender ล่วงหน้า (ให้ข้อผิดพลาดโผล่ตอนเริ่ม ไม่ใช่ตอน AI เรียกครั้งแรก)
    try:
        rt.ensure()
    except Exception as exc:  # noqa: BLE001
        log("เตือน: ยังเปิด Blender ไม่ได้ตอนเริ่ม — จะลองอีกครั้งเมื่อมีคำสั่งเรียก")
        log(f"       สาเหตุ: {exc}")

    log("พร้อมรับคำสั่งผ่าน stdio")
    try:
        srv.run(transport="stdio")
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        rt.shutdown()
    return 0


def _selftest(rt: Runtime) -> int:
    """เปิด Blender จริงแล้วไล่เรียกทุกเครื่องมือ — ใช้ตรวจการติดตั้ง"""
    print("── ตรวจการติดตั้ง (selftest) ──")
    try:
        rt.ensure()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ เปิด Blender ไม่ได้: {exc}")
        return 1
    print(f"✅ ต่อได้ · Blender {rt.client.info.get('blender')}")
    checks = [
        ("get_scene_hierarchy", {}),
        ("add_primitive_mesh", {"primitive": "cube", "name": "LPM_Test", "location": [1, 1, 1]}),
        ("modify_object_transform", {"name": "LPM_Test", "location": [2, 2, 2], "rotation": [45, 0, 0]}),
        ("set_object_material", {"name": "LPM_Test", "color": [0.9, 0.2, 0.2]}),
        ("get_object_details", {"name": "LPM_Test"}),
        ("execute_blender_script", {"code": "result = 6 * 7"}),
        ("delete_object", {"name": "LPM_Test", "confirm": True}),
    ]
    bad = 0
    for tool, kwargs in checks:
        try:
            res = rt.call(tool, **kwargs)
            snippet = json.dumps(res, ensure_ascii=False)[:110]
            print(f"✅ {tool}: {snippet}")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"❌ {tool}: {exc}")
    try:
        meta = rt.client.request("file_metadata")
        print(f"✅ resource file_metadata: {json.dumps(meta, ensure_ascii=False)[:110]}")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"❌ resource file_metadata: {exc}")
    rt.shutdown()
    print("── จบ ──")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
