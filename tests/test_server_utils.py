#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_server_utils.py — ทดสอบส่วนช่วยใน MCP server ที่ไม่ต้องเปิด Blender

จุดสำคัญ: Hermes ส่งตัวแปรสภาพแวดล้อมแบบกรองให้โปรเซสลูก
(ไม่มี PROGRAMFILES/LOCALAPPDATA) — การค้นหา Blender จึงต้องไม่พึ่ง env อย่างเดียว
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import blender_mcp_server as srv  # noqa: E402

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


# ===========================================================================
section("[1] ค้นหา Blender บน Windows — ต้องไม่พึ่ง env อย่างเดียว")
# ===========================================================================
with mock.patch.dict(os.environ, {}, clear=True):
    with mock.patch("pathlib.Path.home", return_value=pathlib.Path("C:/Users/Test")):
        roots = srv._windows_roots()

check("ไม่พังเมื่อไม่มีตัวแปรสภาพแวดล้อมเลย", isinstance(roots, list) and roots)
check("⚠️ ยังมี 'C:\\Program Files' เป็นทางถอย (Hermes กรอง env ออก)",
      r"C:\Program Files" in roots, str(roots))
check("มี Program Files (x86) ด้วย", r"C:\Program Files (x86)" in roots, str(roots))
check("มี LOCALAPPDATA ของผู้ใช้ (สำหรับติดตั้งแบบ per-user)",
      any("AppData" in r for r in roots), str(roots))
check("ไม่ซ้ำรากเดิมสองครั้ง", len(roots) == len(set(roots)), str(roots))

with mock.patch.dict(os.environ, {"ProgramFiles": "D:/Apps"}, clear=True):
    roots2 = srv._windows_roots()
check("ถ้ามีตัวแปรก็ใช้ค่าที่ผู้ใช้ตั้ง", "D:/Apps" in roots2, str(roots2))

# สร้างโครงสร้างโฟลเดอร์จริงในเครื่องชั่วคราว แล้วดูว่าค้นเจอไหม
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    base = pathlib.Path(td)
    made = []
    for rel in ("Blender Foundation/Blender 4.5", "Blender Foundation/Blender 5.2",
                "Programs/Blender Foundation/Blender 5.2"):
        d = base / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / "blender.exe").write_text("x", encoding="utf-8")
        made.append(str(d / "blender.exe"))
    (base / "Blender Foundation" / "Blender 6.0").mkdir(parents=True, exist_ok=True)  # ไม่มี exe

    with mock.patch.dict(os.environ, {"ProgramFiles": td}, clear=True):
        cands = [str(p) for p in srv._windows_candidates()]
        check("เจอ blender.exe ทุกที่ที่ติดตั้ง (3 ไฟล์)", len(cands) == 3, str(cands))
        check("เจอทั้งใน Program Files และใน ...\\Programs\\",
              any("Programs" in c for c in cands), str(cands))
        check("โฟลเดอร์รุ่นที่ไม่มี blender.exe ไม่ถูกนับ",
              not any("6.0" in c for c in cands), str(cands))

        with mock.patch("shutil.which", return_value=None), \
                mock.patch.object(srv.platform, "system", return_value="Windows"), \
                mock.patch.object(srv, "_other_candidates", return_value=[]):
            found, how = srv.find_blender()
        check("find_blender เลือกรุ่นใหม่สุดให้ก่อน",
              found is not None and "5.2" in str(found), str(found))
        check("บอกที่มาว่าเจอในเครื่องพร้อมจำนวนรุ่น",
              "เจอในเครื่อง" in how and "3" in how, how)

# ===========================================================================
section("[2] find_blender — บอกที่มาของคำตอบเสมอ")
# ===========================================================================
found, how = srv.find_blender(str(ROOT / "ไม่มีไฟล์นี้.exe"))
check("ระบุไฟล์ที่ไม่มี → คืน None พร้อมบอกเหตุผล", found is None and "ไม่พบไฟล์" in how, how)

found, how = srv.find_blender(str(ROOT / "blender_mcp_server.py"))
check("ระบุไฟล์ที่มีจริง → คืนไฟล์นั้น", found is not None and found.name == "blender_mcp_server.py", how)
check("บอกว่ามาจาก --blender", "--blender" in how, how)

with mock.patch.dict(os.environ, {"BLENDER_EXE": str(ROOT / "requirements.txt")}, clear=True):
    found, how = srv.find_blender()
check("อ่านจาก BLENDER_EXE ได้", found is not None and "BLENDER_EXE" in how, how)

with mock.patch.dict(os.environ, {}, clear=True), \
        mock.patch("shutil.which", return_value=None), \
        mock.patch.object(srv, "_other_candidates", return_value=[]):
    found, how = srv.find_blender()
check("หาไม่เจอ → คืน None ไม่ใช่ระเบิด", found is None and "หาไม่เจอ" in how, how)

# ===========================================================================
section("[3] ตัวเลือกบรรทัดคำสั่ง")
# ===========================================================================
a = srv.parse_args([])
check("ค่าปริยาย: รอต่อคำสั่ง 120 วินาที", a.timeout == 120, str(a.timeout))
check("ค่าปริยาย: รอ Blender เปิด 90 วินาที", a.spawn_timeout == 90, str(a.spawn_timeout))
check("ค่าปริยาย: เปิดแบบไม่มีหน้าต่าง", a.gui is False)
check("ค่าปริยาย: มีที่เขียนบันทึกเสมอ", bool(a.log_file), a.log_file)
check("ค่าปริยาย: ไม่ได้ attach ที่ไหน", a.attach == "")

a = srv.parse_args(["--gui", "--attach", "127.0.0.1:9876", "--timeout", "5.5"])
check("รับ --gui ได้", a.gui is True)
check("รับ --attach ได้", a.attach == "127.0.0.1:9876")
check("รับ --timeout ทศนิยมได้", a.timeout == 5.5)
check("--workdir ที่ไม่ระบุ → None (ใช้โฟลเดอร์โปรเจกต์)", a.working_dir is None)
check("ไม่มีอาร์กิวเมนต์แปลก → unknown_args ว่าง", a.unknown_args == [], str(a.unknown_args))

# ⚠️ ต้องอดทนต่ออาร์กิวเมนต์แปลก (บทเรียนจาก `hermes mcp add`:
#    ถ้าออกทันที ไคลเอนต์รายงานแค่ "Connection closed" ซึ่งหาสาเหตุยากมาก)
a = srv.parse_args(["blender_mcp_server.py", "--timeout", "7",
                    "--connect-timeout", "120", "--args"])
check("อาร์กิวเมนต์แปลกต้องไม่ทำให้ออก (ไม่ raise SystemExit)", a.timeout == 7, str(a.timeout))
check("ยังอ่านค่าที่รู้จักได้ตามปกติ", a.timeout == 7)
check("เก็บอาร์กิวเมนต์แปลกไว้รายงาน", "--connect-timeout" in a.unknown_args
      and "--args" in a.unknown_args, str(a.unknown_args))
check("พารามิเตอร์ที่เหลือยังใช้ค่าปริยาย",
      a.attach == "" and a.gui is False and a.timeout == 7)
src = (ROOT / "blender_mcp_server.py").read_text(encoding="utf-8")
check("ใช้ parse_known_args (กันคนเผลอเปลี่ยนกลับเป็น parse_args)",
      "parse_known_args" in src, "ต้องอดทนต่ออาร์กิวเมนต์ที่ไคลเอนต์เติมมา")
check("รายงานอาร์กิวเมนต์ที่ข้ามลงบันทึก (ไม่เงียบ)",
      "ข้ามอาร์กิวเมนต์ที่ไม่รู้จัก" in src)

# ===========================================================================
section("[4] BridgeClient — ส่งพารามิเตอร์ที่ไม่ใช้ต้องไม่หลุดไป")
# ===========================================================================
sent: dict = {}


class FakeClient(srv.BridgeClient):
    def request(self, method, params=None, timeout=None):  # noqa: ARG002
        sent.clear()
        sent.update(params or {})
        return {"ok": True}


fc = FakeClient("127.0.0.1", 1, "t")
fc.call_tool("add_primitive_mesh", {"primitive": "cube", "name": None, "scale": None,
                                    "radius": 1.0})
check("ตัดพารามิเตอร์ที่เป็น None ออก (กัน bridge ได้ค่า None)",
      "name" not in sent["arguments"] and "scale" not in sent["arguments"],
      str(sent.get("arguments")))
check("พารามิเตอร์ที่มีค่าจริงยังอยู่",
      sent["arguments"].get("primitive") == "cube" and sent["arguments"].get("radius") == 1.0,
      str(sent.get("arguments")))
check("ห่อเป็น method='call_tool' + name ที่ถูกต้อง",
      sent.get("name") == "add_primitive_mesh", str(sent))

fc.call_tool("get_scene_hierarchy", None)
check("arguments ที่ส่งมาเป็น None → ส่ง {} ไม่พัง", sent.get("arguments") == {}, str(sent))

# ===========================================================================
section("[5] ไม่มี Blender → ต้องได้ข้อความที่บอกทางแก้ ไม่ใช่ค้างหรือพัง")
# ===========================================================================
import argparse  # noqa: E402

cfg = argparse.Namespace(blender="", attach="", token="", timeout=1.0, spawn_timeout=2.0,
                         gui=False, interval=0.05, log_file="", working_dir=None,
                         headless_safe_startup=False, blend_file="")
rt = srv.Runtime(cfg)
with mock.patch.object(srv, "find_blender", return_value=(None, "หาไม่เจอ")):
    try:
        rt.ensure()
        check("หา Blender ไม่เจอ → ต้องไม่ผ่านเงียบ ๆ", False, "ไม่เกิดข้อผิดพลาด")
    except srv.BridgeError as exc:
        msg = str(exc)
        check("หา Blender ไม่เจอ → เกิดข้อผิดพลาดที่อธิบายได้", True)
        check("ข้อความบอกทางแก้ (--blender / BLENDER_EXE)", "--blender" in msg and "BLENDER_EXE" in msg, msg[:160])
        check("ข้อความยกตัวอย่างพาธจริงบน Windows",
              "Blender Foundation" in msg and "blender.exe" in msg, msg[:200])
    except Exception as exc:  # noqa: BLE001
        check("หา Blender ไม่เจอ → ข้อผิดพลาดต้องเป็นชนิดที่เราคุมเอง", False,
              f"{type(exc).__name__}: {exc}")

# สรุปค่าตั้งของสะพานก่อนเปิด Blender
p = srv.parse_args(["--blend-file", "งาน.blend"])
proc = srv.BlenderProcess(pathlib.Path("/tmp/ไม่มีจริง"), p)
check("มี token สุ่มให้ทุกครั้งที่เปิด (ไม่ซ้ำกัน)", len(proc.token) >= 20 and
      proc.token != srv.BlenderProcess(pathlib.Path("/tmp/x"), p).token,
      f"ความยาว {len(proc.token)}")

# ===========================================================================
section("[6] ติดตั้ง add-on ให้เอง (แทนการคัดลอกไฟล์ด้วยมือ)")
# ===========================================================================
import tempfile  # noqa: E402

with mock.patch.object(srv, "find_blender", return_value=(None, "หาไม่เจอ")):
    # ไม่มี Blender เลย → ต้องบอกให้ชัดว่าต้องทำอะไร ไม่ใช่ล้มเงียบ ๆ
    with tempfile.TemporaryDirectory() as td:
        with mock.patch.object(srv.platform, "system", return_value="Linux"), \
                mock.patch("pathlib.Path.home", return_value=pathlib.Path(td)):
            try:
                srv.install_addon()
                check("ไม่มีเวอร์ชัน Blender → ต้องไม่ผ่านเงียบ ๆ", False, "ไม่เกิดข้อผิดพลาด")
            except srv.BridgeError as exc:
                check("ไม่มีเวอร์ชัน Blender → บอกทางแก้", "เปิด Blender" in str(exc), str(exc)[:120])
                check("ข้อความบอกที่อยู่ปลายทางให้คัดลอกเอง",
                      "scripts" in str(exc) and "blender_mcp_bridge" in str(exc), str(exc)[:200])

    with tempfile.TemporaryDirectory() as td:
        home = pathlib.Path(td)
        (home / ".config" / "blender" / "5.2").mkdir(parents=True)
        with mock.patch.object(srv.platform, "system", return_value="Linux"), \
                mock.patch("pathlib.Path.home", return_value=home):
            check("หาเวอร์ชันจากโฟลเดอร์ค่าตั้งได้", srv.blender_versions() == ["5.2"],
                  str(srv.blender_versions()))
            dry = srv.install_addon(dry_run=True)
            target = home / ".config/blender/5.2/scripts/addons/blender_mcp_bridge"
            check("dry-run: ไม่เขียนไฟล์จริง", not target.exists())
            check("dry-run: บอกปลายทางให้ตรวจก่อน", str(target) in dry["results"][0]["target"])

            out = srv.install_addon()
            check("ติดตั้งจริง: ได้ทั้งสองไฟล์ที่ต้องมี",
                  (target / "__init__.py").is_file() and (target / "blender_bridge.py").is_file(),
                  str(list(target.iterdir())) if target.exists() else "ไม่มีโฟลเดอร์")
            check("⚠️ คัดลอกไฟล์ตรงกับต้นทางเป๊ะ (ไม่ใช่ของเก่า)",
                  (target / "blender_bridge.py").read_bytes() == (ROOT / "blender_bridge.py").read_bytes())
            check("บอกขั้นต่อไปให้ผู้ใช้ (ไปเปิด add-on ใน Blender)",
                  "Add-ons" in out["next"], out["next"])

            again = srv.install_addon()
            check("ติดตั้งซ้ำ → บอกว่าเขียนทับของเดิม ไม่เงียบ",
                  again["results"][0].get("replaced") is True, str(again["results"][0]))

            rm = srv.uninstall_addon()
            check("ถอนการติดตั้ง: ลบโฟลเดอร์จริง", not target.exists() and str(target) in rm["removed"])
            check("ถอนเมื่อไม่มีอยู่ → ไม่ระเบิด", srv.uninstall_addon()["removed"] == [])

            # macOS/Windows ต้องชี้คนละที่
            with mock.patch.object(srv.platform, "system", return_value="Darwin"):
                check("macOS → ใช้ ~/Library/Application Support/Blender",
                      "Application Support" in str(srv._blender_config_root()),
                      str(srv._blender_config_root()))
            with mock.patch.object(srv.platform, "system", return_value="Windows"), \
                    mock.patch.dict(os.environ, {"APPDATA": "C:/Users/x/AppData/Roaming"}, clear=True):
                check("Windows → ใช้ %APPDATA%\Blender Foundation",
                      "Blender Foundation" in str(srv._blender_config_root()),
                      str(srv._blender_config_root()))

section("[7] ตรวจเวอร์ชันโปรโตคอล (จับ add-on เก่าที่ค้างอยู่)")
check("โปรโตคอลตรงกัน → ไม่มีคำเตือน", srv.check_bridge_protocol({"protocol": 1}) is None)
check("ไม่มีข้อมูล → ไม่เตือน (สะพานรุ่นเก่าที่ไม่ส่งมาก็ยังใช้ได้)",
      srv.check_bridge_protocol({}) is None and srv.check_bridge_protocol(None) is None)
warn = srv.check_bridge_protocol({"protocol": 0, "bridge": "0.9.0"})
check("โปรโตคอลไม่ตรง → เตือน", warn is not None and "v0" in warn, str(warn))
check("คำเตือนบอกสาเหตุที่พบบ่อย (add-on เก่า)", "add-on" in (warn or ""), str(warn))
check("คำเตือนบอกวิธีแก้ที่ทำได้ทันที", "--install-addon" in (warn or ""), str(warn))

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
sys.exit(0)
