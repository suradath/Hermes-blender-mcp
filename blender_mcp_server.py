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
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import TextContent

HERE = pathlib.Path(__file__).resolve().parent
BRIDGE_SCRIPT = HERE / "blender_bridge.py"
SERVER_VERSION = "1.0.11"
MIN_BLENDER = (4, 0)          # ใช้ API ที่มีมาตั้งแต่ 4.0 (5.2 คือเป้าหมาย)
# เวอร์ชันโปรโตคอลระหว่างเซิร์ฟเวอร์กับสะพาน — ต้องตรงกัน ไม่งั้นมักแปลว่า
# add-on ที่ติดตั้งไว้เป็นเวอร์ชันเก่า (bridge เก่าคุยกับเซิร์ฟเวอร์ใหม่)
EXPECTED_BRIDGE_PROTOCOL = 1
# เพดานขนาดรูปที่ส่งกลับให้ AI — ใหญ่กว่านี้จะกินบริบท/เวลาเกินคุ้ม
MAX_IMAGE_BYTES = 4 * 1024 * 1024


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
        line = "[Hermes-blender-mcp] " + " ".join(str(p) for p in parts)
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
#  ติดตั้ง add-on ให้เอง (ตัดขั้นตอนคัดลอกไฟล์ด้วยมือออก)
# ===========================================================================

ADDON_DIRNAME = "blender_mcp_bridge"


def _blender_config_root() -> pathlib.Path | None:
    """ที่ที่ Blender เก็บค่าตั้ง/add-on ในเครื่องนี้"""
    home = pathlib.Path.home()
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return pathlib.Path(base) / "Blender Foundation" / "Blender"
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Blender"
    base = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return pathlib.Path(base) / "blender"


def blender_versions(explicit: str = "") -> list[str]:
    """เวอร์ชัน Blender ที่ควรติดตั้ง add-on ให้ (ใหม่สุดก่อน)

    ดูจาก 2 ทาง: โฟลเดอร์ค่าตั้งที่มีอยู่จริง และชื่อโฟลเดอร์ของโปรแกรม Blender
    (เช่น `C:\\Program Files\\Blender Foundation\\Blender 5.2` → "5.2")
    """
    found: list[str] = []
    root = _blender_config_root()
    if root and root.is_dir():
        found += [p.name for p in root.iterdir() if p.is_dir() and re.match(r"^\d+\.\d+", p.name)]
    exe, _ = find_blender(explicit)
    if exe is not None:
        m = re.search(r"(\d+\.\d+)", str(exe))
        if m:
            found.append(m.group(1))
    return sorted(dict.fromkeys(found), key=_version_key, reverse=True)


def install_addon(explicit_blender: str = "", dry_run: bool = False,
                  force: bool = False) -> dict:
    """คัดลอก add-on ไปไว้ในโฟลเดอร์ addons ของ Blender ทุกเวอร์ชันที่พบ"""
    sources = {"__init__.py": HERE / "blender_addon" / "__init__.py",
               "blender_bridge.py": HERE / "blender_bridge.py"}
    missing = [str(p) for p in sources.values() if not p.is_file()]
    if missing:
        raise BridgeError("ไฟล์ต้นทางของ add-on ไม่ครบ:\n  - " + "\n  - ".join(missing))

    root = _blender_config_root()
    versions = blender_versions(explicit_blender)
    if not versions:
        raise BridgeError(
            "ไม่พบเวอร์ชันของ Blender — ยังไม่เคยเปิด Blender บนเครื่องนี้?\n"
            f"  เปิด Blender หนึ่งครั้ง แล้วลองใหม่ หรือคัดลอกไฟล์เองไปที่:\n"
            f"  {root / '<เวอร์ชัน>' / 'scripts' / 'addons' / ADDON_DIRNAME}{os.sep}\n"
            "  (ดูขั้นตอนใน INSTALL.md หัวข้อ add-on)")

    results = []
    for ver in versions:
        target = (root or pathlib.Path(".")) / ver / "scripts" / "addons" / ADDON_DIRNAME
        if dry_run:
            results.append({"version": ver, "target": str(target), "installed": False,
                            "dry_run": True})
            continue
        if target.exists() and not force:
            # เขียนทับได้ แต่บอกให้รู้ (มี add-on ของเราเวอร์ชันก่อนอยู่)
            results.append({"version": ver, "target": str(target), "installed": True,
                            "replaced": True})
        else:
            results.append({"version": ver, "target": str(target), "installed": True})
        target.mkdir(parents=True, exist_ok=True)
        for name, src in sources.items():
            shutil.copy2(src, target / name)
    return {"addon": ADDON_DIRNAME, "versions": versions, "results": results,
            "next": "เปิด Blender > Edit > Preferences > Add-ons > ติ๊ก 'Hermes Blender MCP Bridge'"
                    " (หรือเปิดใช้ auto-start ในแผง)"}


def uninstall_addon(explicit_blender: str = "") -> dict:
    """ลบ add-on ที่ติดตั้งไว้ (ทุกเวอร์ชันที่พบ)"""
    root = _blender_config_root()
    removed, not_found = [], []
    for ver in blender_versions(explicit_blender):
        target = (root or pathlib.Path(".")) / ver / "scripts" / "addons" / ADDON_DIRNAME
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(str(target))
        else:
            not_found.append(str(target))
    return {"removed": removed, "not_found": not_found}


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
                # ⚠️ ตรวจ token ต้องตอบเร็วมาก (มิลลิวินาที) — เดิมตั้ง timeout เท่า
                #    self.timeout (300 วิ) ทำให้ค้างเงียบได้ 5 นาทีโดยไม่มี log อะไรเลย
                s.settimeout(8.0)
                f = s.makefile("rwb")
                log(f"TCP ต่อติด พอร์ต {self.port} · กำลังตรวจ token ...")
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
                # กล่องดำ: บอกทุกครั้งว่า attempt นี้พลาดเพราะอะไร (เดิมเงียบสนิท)
                if not self.info:
                    log(f"ต่อสะพานยังไม่สำเร็จ ({type(exc).__name__}: {exc}) — ลองใหม่")
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
        # ⚠️ ห้ามขึ้นต้นด้วย - หรือ _ : ตอนส่งต่อให้ Blender ผ่าน argparse
        #    ค่าที่เริ่มด้วย - จะถูกตีความเป็น option (เจอจริง: expected one argument)
        self.token = secrets.token_urlsafe(24).lstrip("-_")
        if len(self.token) < 16:
            self.token = "t" + secrets.token_urlsafe(24).replace("-", "x").replace("_", "y")
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
        # ⚠️ ต้องเป็น --token=<ค่า> ไม่ใช่ ["--token", token] เพราะถ้าโทเคนบังเอิญ
        #    เริ่มด้วย - (เช่น "-95vRW...") argparse จะตีความเป็น option แล้วขึ้น
        #    "argument --token: expected one argument" (เจอจริงจาก log ของผู้ใช้)
        # ลบ "--token" พร้อม "ค่าที่ตามมา" ออกให้ครบ (เดิมลบแค่ชื่อออปชัน
        # → ค่าโทเคนกลายเป็นอาร์กิวเมนต์ลอย ๆ แล้วเราก็ใส่ --token= อีกที = ซ้ำ)
        _clean, _skip = [], False
        for _c in cmd:
            if _skip:
                _skip = False
                continue
            if _c == "--token":
                _skip = True
                continue
            if _c.startswith("--token="):
                continue
            _clean.append(_c)
        cmd = _clean + [f"--token={self.token}",
                "--mode", "main" if not self.args.gui else "timer",
                "--interval", str(self.args.interval)]

        log("เปิด Blender:", " ".join(cmd))
        # กันความเข้าใจผิดที่เจอจริง: ผู้ใช้เปิด Blender หน้าต่างไว้เองแล้วคาดว่า
        # ของจะไปโผล่ที่นั่น แต่เซิร์ฟเวอร์เปิด Blender ของตัวเองแบบไม่มีหน้าต่าง
        if not self.args.gui and not self.args.attach:
            log("โหมด headless: วัตถุจะไปอยู่ใน Blender ที่เซิร์ฟเวอร์เปิดเอง "
                "(มองไม่เห็น) — ถ้าต้องการเห็นสดในหน้าต่าง ให้ใส่ --gui "
                "หรือติด add-on แล้วใช้ --attach 127.0.0.1:9876 --token <token>")
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
            # สะพานประกาศตัวด้วย JSON บรรทัดเดียว
            # ⚠️ บทเรียนจริง (โหมด GUI): Blender หน้าต่างพิมพ์ warning ปนหน้ามาได้
            #    จึงต้องหา "ก้อน JSON" ในบรรทัด ไม่ใช่ดูว่าเริ่มต้นด้วย { เท่านั้น
            #    (เดิมพลาด → พอร์ตยังเป็น 0 → ต่อพอร์ต 0 → WinError 10061 refused)
            stripped = line.strip()
            cut = stripped.find("{")
            if cut >= 0:
                try:
                    obj = json.loads(stripped[cut:])
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict) and obj.get("bridge_ready") and obj.get("port"):
                    if self._ready.is_set():
                        # ต่อสำเร็จแล้ว — ready line อื่น (เช่น add-on ที่รันใน Blender
                        # เดียวกันและประกาศพอร์ต 9876) ต้องไม่มาเขียนทับพอร์ตเดิม
                        log(f"ข้าม ready line ของสะพานอื่น (พอร์ต {obj['port']})")
                        continue
                    self.port = int(obj["port"])
                    log(f"สะพานพร้อมที่พอร์ต {self.port}")
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


def check_bridge_protocol(info: dict | None) -> str | None:
    """คืนข้อความเตือนถ้าโปรโตคอลของสะพานไม่ตรงกับที่เซิร์ฟเวอร์คาด (None = ปกติ)

    แยกเป็นฟังก์ชันบริสุทธิ์เพื่อทดสอบได้โดยไม่ต้องเปิด Blender
    """
    proto = (info or {}).get("protocol")
    if proto is None or proto == EXPECTED_BRIDGE_PROTOCOL:
        return None
    return (f"สะพานเป็นโปรโตคอล v{proto} แต่เซิร์ฟเวอร์นี้คาดว่า v{EXPECTED_BRIDGE_PROTOCOL} "
            f"— มักเกิดจาก add-on ที่ติดตั้งไว้เป็นเวอร์ชันเก่า "
            f"แก้ด้วย: blender_mcp_server.py --install-addon --force")


class Runtime:
    """ถือการเชื่อมต่อกับ Blender — เปิด Blender ตอนใช้ครั้งแรก (lazy)"""

    def __init__(self, cfg: argparse.Namespace):
        self.cfg = cfg
        self.client = BridgeClient("127.0.0.1", 0, "", timeout=cfg.timeout)
        self.proc: BlenderProcess | None = None
        self._lock = threading.Lock()
        # กัน "Blender เปิดแล้วปิดรัว ๆ": ถ้าเพิ่งล้มเหลว อย่าเปิดใหม่ทันที
        # (Hermes จะเรียกเครื่องมือซ้ำ ๆ → เดิมเปิด/ปิด Blender ทุกครั้ง)
        self._fail_at: float = 0.0
        self._fail_msg: str = ""
        self._fail_cooldown = 20.0

    # --------------------------------------------------------- เตรียมพร้อม
    def ensure(self) -> BridgeClient:
        with self._lock:
            if self.client.connected:
                return self.client

            # เพิ่งล้มเหลวเมื่อครู่ → ไม่ต้องเปิด Blender ใหม่ (กันหน้าต่างเด้งรัว ๆ)
            if self._fail_msg and (time.monotonic() - self._fail_at) < self._fail_cooldown:
                left = int(self._fail_cooldown - (time.monotonic() - self._fail_at))
                raise BridgeError(
                    f"ยังต่อ Blender ไม่ได้ (จะลองใหม่ในอีก {left} วินาที) — "
                    f"สาเหตุครั้งก่อน: {self._fail_msg}")

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
                self._fail_at, self._fail_msg = time.monotonic(), "Blender ไม่พร้อมภายในเวลาที่กำหนด"
                raise BridgeError(
                    f"Blender ไม่พร้อมภายใน {self.cfg.spawn_timeout:.0f} วินาที — "
                    f"บันทึกท้าย ๆ:\n{tail}\n"
                    f"ลองเปิดด้วยตนเองเพื่อดูข้อผิดพลาด: "
                    f"\"{found}\" --background --python \"{BRIDGE_SCRIPT}\" -- --port 0 --selftest")
            self.client.port = self.proc.port or 0
            self.client.token = self.proc.token
            if not self.client.port:
                tail = self.proc.tail()
                self.proc.stop()
                self.proc = None
                raise BridgeError(
                    "Blender แจ้งว่าพร้อม แต่ไม่ได้บอกพอร์ต (บรรทัด JSON หาย) — "
                    f"บันทึกท้าย ๆ:\n{tail}")
            try:
                self.client.connect(timeout=30)
            except BridgeError as exc:
                # กัน Blender ค้างเป็นหน้าต่างผีหลังต่อไม่ติด (เจอจริง: เปิดค้างหลายบาน)
                self._fail_at = time.monotonic()
                self._fail_msg = str(exc).splitlines()[0][:200]
                tail = self.proc.tail()
                self.proc.stop()
                self.proc = None
                raise BridgeError(f"ต่อสะพานไม่สำเร็จ — บันทึกท้าย ๆ:\n{tail}") from None
            warn = check_bridge_protocol(self.client.info)
            if warn:
                log(f"⚠️  {warn}")
            self._fail_msg = ""          # สำเร็จ → ล้างสถานะล้มเหลว
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
    async def show_in_blender(filepath: str = "") -> dict:
        """Save the scene and SHOW it to the human in a Blender window.

        Use this when the work is done and somebody wants to look at it: in
        headless mode it writes a .blend and launches a normal Blender window with
        that file (a separate, detached process - your own session keeps running),
        while in --gui/--attach mode the already-open window is used and nothing is
        launched twice. Returns the file path and whether a window was opened.
        """
        import tempfile as _tf

        target = filepath.strip()
        if not target:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            target = str(pathlib.Path(_tf.gettempdir()) / "Hermes-blender-mcp"
                         / f"result-{stamp}.blend")
        target = str(pathlib.Path(target).expanduser())
        if not target.lower().endswith(".blend"):
            target += ".blend"
        saved = await _run(lambda: rt.call("save_blend_file", filepath=target))
        scene = await _run(lambda: rt.call("get_scene_hierarchy", max_objects=1))

        # หน้าต่างที่มีอยู่แล้ว (gui / attach) = เห็นงานอยู่แล้ว ไม่ต้องเปิดซ้ำ
        if rt.cfg.gui or rt.cfg.attach:
            return {"opened_new_window": False, "filepath": target, "saved": saved,
                    "note": "หน้าต่าง Blender ที่เปิดอยู่แสดงฉากนี้ให้ดูแล้ว "
                            "(โหมด gui/attach) — ไม่ได้เปิดหน้าต่างใหม่"}

        exe, how = find_blender(rt.cfg.blender)
        if exe is None:
            raise ToolError(f"หา Blender ไม่เจอ ({how}) — บันทึกไฟล์ไว้ที่ {target} "
                            f"แล้ว แต่เปิดหน้าต่างให้ไม่ได้")
        # เปิดเป็นโปรเซสแยกแบบ detachment: ไม่บล็อก MCP และไม่ผูกกับชีวิตเซิร์ฟเวอร์
        kwargs: dict = {"cwd": str(exe.parent)}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200   # DETACHED | NEW_GROUP
        else:
            kwargs["start_new_session"] = True
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
        proc = subprocess.Popen([str(exe), target], **kwargs)
        return {"opened_new_window": True, "filepath": target, "saved": saved,
                "pid": proc.pid, "blender": str(exe),
                "objects": (scene.get("totals") or {}).get("objects"),
                "note": "เปิด Blender หน้าต่างใหม่ให้ดูผลงานแล้ว — "
                        "เซสชัน MCP ยังทำงานต่อได้ปกติ"}


    @srv.tool()
    async def get_viewport_screenshot(filepath: str = "", width: int = 0,
                                      height: int = 0, mode: str = "auto",
                                      camera: str = "") -> list[TextContent | Image]:
        """Render a picture of the current view and return it so you can LOOK at
        the scene, together with a JSON block (path, size, engine, camera). Use
        this to check your own work after adding or moving objects.

        mode 'auto' picks 'render' when Blender runs without a window (-b) and
        'viewport' when a Blender window is open. 'render' needs a camera in the
        scene; 'viewport' needs an open 3D viewport. width/height override the
        resolution (0 = keep the scene's settings, which are restored afterwards)."""
        res = await _run(lambda: rt.call("get_viewport_screenshot", filepath=filepath,
                                         width=width, height=height, mode=mode,
                                         camera=camera))
        meta = dict(res or {})
        source = pathlib.Path(str(meta.get("filepath", "")))
        blocks: list[TextContent | Image] = [
            TextContent(type="text", text=json.dumps(meta, ensure_ascii=False, indent=2))]

        # ⚠️ ต้องกัน 2 กรณี: อ่านไฟล์ไม่ได้ (Blender คนละเครื่อง) และไฟล์ใหญ่เกิน
        try:
            size = source.stat().st_size
        except OSError:
            blocks[0] = TextContent(type="text", text=json.dumps(
                {**meta, "warning": "อ่านไฟล์รูปไม่ได้ — ถ้า Blender อยู่คนละเครื่องกับ "
                                    "เซิร์ฟเวอร์ ระบบจะส่งได้แค่ข้อมูล ไม่ส่งรูป"},
                ensure_ascii=False, indent=2))
            return blocks
        if size > MAX_IMAGE_BYTES:
            blocks[0] = TextContent(type="text", text=json.dumps(
                {**meta, "warning": f"รูปใหญ่เกินกำหนด ({size:,} ไบต์ > {MAX_IMAGE_BYTES:,}) "
                                    f"จึงไม่ส่งกลับ — ลด width/height แล้วลองใหม่"},
                ensure_ascii=False, indent=2))
            return blocks
        blocks.append(Image(path=source))
        return blocks

    @srv.tool()
    async def search_polyhaven(query: str = "", asset_type: str = "models",
                               categories: str = "", limit: int = 20) -> dict:
        """Search Poly Haven, a library of CC0 (public domain — no API key, free for
        any use) HDRIs, PBR textures and 3D models. Use it instead of modelling
        everything by hand: an outdoor HDRI for lighting, a wood/metal texture, or a
        ready-made prop (chair, barrel, tree, …). asset_type is hdris | textures |
        models. Returns ids for get_polyhaven_info / download_polyhaven_asset."""
        return await _run(lambda: rt.call("search_polyhaven", query=query,
                                          asset_type=asset_type, categories=categories,
                                          limit=limit))

    @srv.tool()
    async def get_polyhaven_info(asset_id: str) -> dict:
        """List what is inside one Poly Haven asset before downloading: formats
        (gltf/fbx/blend/usd for models, hdr/exr for HDRIs, map types for textures),
        resolutions, file sizes, author and polycount. Check this to avoid pulling a
        multi-hundred-MB 8k file."""
        return await _run(lambda: rt.call("get_polyhaven_info", asset_id=asset_id))

    @srv.tool()
    async def download_polyhaven_asset(asset_id: str, kind: str = "gltf",
                                       resolution: str = "1k", apply: bool = True,
                                       target_dir: str = "", max_mb: float = 200.0,
                                       texture_map: str = "") -> dict:
        """Download a Poly Haven asset plus the texture files it needs, then bring it
        into the scene: kind='hdri' sets it as the world lighting, kind='gltf' imports
        the model, a texture map name (e.g. 'Diffuse') builds a material from it.
        Files are cached locally so a second call is instant. Prefer resolution '1k'
        or '2k' — 4k and above are hundreds of MB. Everything is CC0."""
        return await _run(lambda: rt.call("download_polyhaven_asset", asset_id=asset_id,
                                          kind=kind, resolution=resolution, apply=apply,
                                          target_dir=target_dir, max_mb=max_mb,
                                          texture_map=texture_map))

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
    p.add_argument("--install-addon", action="store_true",
                   help="คัดลอก add-on ไปไว้ในโฟลเดอร์ของ Blender ให้เอง แล้วจบ")
    p.add_argument("--uninstall-addon", action="store_true",
                   help="ลบ add-on ที่ติดตั้งไว้")
    p.add_argument("--dry-run", action="store_true",
                   help="กับ --install-addon: บอกว่าจะเขียนที่ไหน แต่ไม่เขียนจริง")
    p.add_argument("--force", action="store_true",
                   help="กับ --install-addon: เขียนทับของเดิม")
    p.add_argument("--list-tools", action="store_true", help="พิมพ์รายการเครื่องมือแล้วจบ")
    p.add_argument("--selftest", action="store_true",
                   help="เริ่ม Blender จริง เรียกทุกเครื่องมือ แล้วจบ (ใช้ตรวจการติดตั้ง)")
    p.add_argument("--warmup", action="store_true",
                   help="เปิด/ตรวจ Blender ทันทีตอนสตาร์ต (ค่าปริยายคือรอให้เรียกก่อน)")
    p.add_argument("--deep", action="store_true",
                   help="ใช้คู่กับ --selftest: ตรวจเพิ่มของที่ต้องใช้เครือข่าย/ไฟล์ "
                        "(ค้น+โหลด Poly Haven แล้วนำเข้าโมเดล · บันทึก .blend)")
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
        args.log_file = str(pathlib.Path(tempfile.gettempdir()) / "Hermes-blender-mcp" /
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

    if args.install_addon or args.uninstall_addon:
        try:
            if args.uninstall_addon:
                out = uninstall_addon(args.blender)
                for path in out["removed"]:
                    print(f"🗑️  ลบแล้ว: {path}")
                for path in out["not_found"]:
                    print(f"•  ไม่มีอยู่: {path}")
                if not out["removed"]:
                    print("ไม่พบ add-on ที่ติดตั้งไว้")
            else:
                out = install_addon(args.blender, dry_run=args.dry_run, force=args.force)
                verb = "จะติดตั้งที่" if args.dry_run else "ติดตั้งแล้วที่"
                for r in out["results"]:
                    mark = "⚠️ เขียนทับของเดิม " if r.get("replaced") else ""
                    print(f"✅ {verb} (Blender {r['version']}): {mark}{r['target']}")
                print(f"\n👉 {out['next']}")
            return 0
        except BridgeError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1

    if args.check:
        found, how = find_blender(args.blender)
        print(f"Blender: {found if found else 'หาไม่เจอ'} ({how})")
        print(f"สคริปต์สะพาน: {BRIDGE_SCRIPT} {'✅' if BRIDGE_SCRIPT.is_file() else '❌ ไม่พบ'}")
        root = _blender_config_root()
        states = []
        for ver in blender_versions(args.blender):
            target = (root or pathlib.Path(".")) / ver / "scripts" / "addons" / ADDON_DIRNAME
            states.append(f"{ver}: {'ติดตั้งแล้ว' if target.is_dir() else 'ยังไม่ได้ติดตั้ง'}")
        print(f"Add-on: {' · '.join(states) if states else 'ไม่พบเวอร์ชัน Blender (ยังไม่เคยเปิด?)'}")
        print("        ติดตั้งด้วย: python blender_mcp_server.py --install-addon")
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
        return _selftest(rt, deep=bool(getattr(args, "deep", False)))

    atexit.register(rt.shutdown)

    # ⚠️ ค่าปริยาย = LAZY: ห้ามเปิด Blender จนกว่าจะมีการเรียกเครื่องมือจริง
    #    บทเรียนจริง: Hermes Desktop เริ่ม MCP server ทันทีตอนเปิดแอป → ถ้า warm up
    #    ที่นี่ Blender จะเปิดเองทั้งที่ผู้ใช้ยังไม่ได้สั่งอะไร (น่ารำคาญและกินแรม)
    #    ใช้ --warmup ถ้าอยากให้ตรวจ/เปิดล่วงหน้า (เช่น ตอน debug)
    if getattr(args, "warmup", False):
        try:
            rt.ensure()
        except Exception as exc:  # noqa: BLE001
            log("เตือน: ยังเปิด Blender ไม่ได้ตอนเริ่ม — จะลองอีกครั้งเมื่อมีคำสั่งเรียก")
            log(f"       สาเหตุ: {exc}")
    else:
        log("โหมด lazy: จะเปิด Blender เมื่อมีการเรียกเครื่องมือครั้งแรกเท่านั้น")

    log("พร้อมรับคำสั่งผ่าน stdio")
    try:
        srv.run(transport="stdio")
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        rt.shutdown()
    return 0


def _selftest(rt: Runtime, deep: bool = False) -> int:
    """เปิด Blender จริงแล้วไล่เรียกทุกเครื่องมือ — ใช้ตรวจการติดตั้ง

    deep=True → ตรวจเพิ่มส่วนที่ต้องใช้เครือข่าย/ไฟล์จริง (Poly Haven + บันทึก .blend)
    """
    print("── ตรวจการติดตั้ง (selftest) ──")
    try:
        rt.ensure()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ เปิด Blender ไม่ได้: {exc}")
        return 1
    _cfg = rt.cfg                      # Runtime เก็บ argparse.Namespace ไว้ที่ .cfg
    mode = "timer (มีหน้าต่าง — เห็นสด)" if _cfg.gui else (
        "attach (ต่อกับ Blender ที่เปิดอยู่)" if _cfg.attach else "main (headless — มองไม่เห็น)")
    print(f"✅ ต่อได้ · Blender {rt.client.info.get('blender')} · โหมด: {mode}")
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
    results = {}
    for tool, kwargs in checks:
        try:
            res = rt.call(tool, **kwargs)
            results[tool] = res
            snippet = json.dumps(res, ensure_ascii=False)[:110]
            print(f"✅ {tool}: {snippet}")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"❌ {tool}: {exc}")

    # ตรวจเส้นทางคอลเลกชัน — บั๊กจริงที่เจอบน Blender 5.2.2:
    #   AttributeError: 'Collection' object has no attribute 'parent'
    hier = results.get("get_scene_hierarchy") or {}
    colls = hier.get("collections") or []
    root_name = colls[0].get("name", "") if colls else ""
    bad_paths = [c.get("path", "") for c in colls
                 if not c.get("path") or (root_name and not c["path"].startswith(root_name))]
    if bad_paths or not colls:
        bad += 1
        print(f"❌ collection path: {bad_paths or 'ไม่พบคอลเลกชันเลย'}")
    else:
        print("✅ collection path: %d คอลเลกชัน · ตัวอย่าง %s"
              % (len(colls), [c["path"] for c in colls[:3]]))

    # screenshot ใต้ --background — จุดที่พังง่ายที่สุดของ Blender headless
    try:
        shot = rt.call("get_viewport_screenshot", mode="render", width=320, height=240)
        fp = pathlib.Path(str((shot or {}).get("filepath", "")))
        if fp.is_file() and fp.stat().st_size > 0:
            print(f"✅ get_viewport_screenshot: {fp.name} · {fp.stat().st_size} ไบต์")
        else:
            bad += 1
            print(f"❌ get_viewport_screenshot: ไม่ได้ไฟล์ ({(shot or {}).get('filepath')})")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"❌ get_viewport_screenshot: {exc}")
    try:
        meta = rt.client.request("file_metadata")
        print(f"✅ resource file_metadata: {json.dumps(meta, ensure_ascii=False)[:110]}")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"❌ resource file_metadata: {exc}")

    # ── ตรวจเชิงลึก (ต้องใช้เครือข่าย/ไฟล์จริง) ──────────────────────────────
    if deep:
        print("── ตรวจเชิงลึก (--deep) ──")
        # 1) บันทึก .blend ลงโฟลเดอร์ชั่วคราว (ไม่ทับไฟล์ของผู้ใช้)
        try:
            target = pathlib.Path(tempfile.gettempdir()) / "Hermes-blender-mcp" / "selftest.blend"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            rt.call("save_blend_file", filepath=str(target))
            size = target.stat().st_size if target.is_file() else 0
            if size > 0:
                print(f"✅ save_blend_file: {target.name} · {size:,} ไบต์")
            else:
                bad += 1
                print(f"❌ save_blend_file: ไม่ได้ไฟล์ ({target})")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"❌ save_blend_file: {exc}")

        # 2) ค้น + โหลดของฟรีจาก Poly Haven แล้วนำเข้าโมเดล
        #    (ข้ามอย่างซื่อสัตย์ถ้าเครื่องนี้ต่อเน็ตไม่ได้ — ไม่นับเป็นความล้มเหลว)
        try:
            found = rt.call("search_polyhaven", query="chair", asset_type="models", limit=6)
            assets = found.get("assets") or []
            print(f"✅ search_polyhaven: เจอ {found.get('total_matching', len(assets))} รายการ")
            before_objs = ((rt.call("get_scene_hierarchy") or {}).get("totals") or {}).get("objects", 0)
            # ผลค้นหียงตาม polycount อยู่แล้ว — ลองชิ้นเบา ๆ ก่อน 3 อัน
            candidates = [a for a in assets if a.get("id")][:3]
            imported = None
            last_err = ""
            for cand in candidates:
                try:
                    rt.call("download_polyhaven_asset", asset_id=cand["id"], kind="gltf",
                            resolution="1k", apply=True, max_mb=25)
                    imported = cand["id"]
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = f"{type(exc).__name__}: {str(exc)[:80]}"
            after_objs = ((rt.call("get_scene_hierarchy") or {}).get("totals") or {}).get("objects", 0)
            if imported and after_objs > before_objs:
                print(f"✅ download_polyhaven_asset: {imported} → วัตถุ {before_objs} → {after_objs}")
            elif imported:
                bad += 1
                print(f"❌ download_polyhaven_asset: โหลดได้แต่ไม่มีวัตถุเพิ่ม "
                      f"({before_objs} → {after_objs})")
            else:
                print(f"⏭️  ข้ามการโหลด: ลอง {len(candidates)} ชิ้นแล้วไม่สำเร็จ · {last_err}")
        except Exception as exc:  # noqa: BLE001
            print(f"⏭️  ข้ามการทดสอบออนไลน์: {type(exc).__name__}: {str(exc)[:110]}")

    rt.shutdown()
    print("── จบ ──")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
