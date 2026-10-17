#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_mcp_e2e.py — ทดสอบครบวงจร: Hermes/MCP client ⇄ MCP server ⇄ สะพาน

ทดสอบด้วยของจริงทุกชั้น ยกเว้น "ตัว Blender" (ใช้ bpy ปลอม):
  1. สะพานตัวจริง (blender_bridge.serve_blocking) รับ-ส่งทางซ็อกเก็ต
  2. MCP server ตัวจริง (blender_mcp_server.py) พูด stdio
  3. MCP client ตัวจริงจาก SDK ทางการ (stdio_client + ClientSession)

รัน: <venv>/bin/python tests/test_mcp_e2e.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
TOKEN = "test-token-ท-ทดสอบ-1234"

passed = 0
failed: list[str] = []
notes: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed
    if cond:
        passed += 1
    else:
        failed.append(f"{name} — {detail}" if detail else name)


def section(t: str) -> None:
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


# --------------------------------------------------------------- เปิดสะพาน
class FakeBlender:
    """เปิด bridge_host.py (สะพานจริง + bpy ปลอม) แล้วรอจนมันบอกพอร์ต"""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self.lines: list[str] = []

    def start(self, timeout: float = 30.0) -> int:
        self.proc = subprocess.Popen(
            [PY, str(HERE / "bridge_host.py"), "--port", "0", "--token", TOKEN,
             "--mode", "main", "--host", "127.0.0.1"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1, cwd=str(ROOT))
        ready = threading.Event()

        def reader():
            assert self.proc and self.proc.stdout
            for raw in self.proc.stdout:
                line = raw.rstrip("\n")
                self.lines.append(line)
                if line.strip().startswith("{"):
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("bridge_ready"):
                        self.port = int(obj["port"])
                        ready.set()

        threading.Thread(target=reader, daemon=True).start()
        if not ready.wait(timeout):
            raise RuntimeError("สะพานไม่พร้อม: " + "\n".join(self.lines[-10:]))
        return self.port

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()


def _payload(res) -> dict:
    """ดึงผลลัพธ์เป็น dict — SDK อาจส่งมาเป็น structured content หรือเป็นข้อความ JSON

    ⚠️ แกะคีย์ "result" ออกเฉพาะเมื่อมันเป็นตัวห่อ (มีคีย์เดียว) เท่านั้น
    เพราะเครื่องมือของเราเองก็มีคีย์ชื่อ "result" อยู่ในผลลัพธ์
    (เจอบั๊กนี้จริงตอนเทสต์ e2e ครั้งแรก: ได้ int 5 แทนที่จะได้ dict)
    """
    sc = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    if isinstance(sc, dict) and sc:
        if len(sc) == 1 and "result" in sc:
            return sc["result"]
        return sc
    for block in getattr(res, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return {"_text": text}
        if isinstance(obj, dict) and len(obj) == 1 and "result" in obj:
            return obj["result"]
        return obj if isinstance(obj, dict) else {"_value": obj}
    return {}


def A(obj, *names, default=None):
    """อ่าน attribute จากโมเดลของ SDK — รองรับทั้งชื่อแบบ python และ alias"""
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    try:
        d = obj.model_dump(by_alias=True)
        for n in names:
            if n in d:
                return d[n]
    except Exception:
        pass
    return default


def _is_error(res) -> bool:
    return bool(getattr(res, "is_error", None) or getattr(res, "isError", None))


def _text(res) -> str:
    out = []
    for block in getattr(res, "content", []) or []:
        out.append(getattr(block, "text", "") or "")
    if not out:
        out.append(json.dumps(getattr(res, "structured_content", None), ensure_ascii=False))
    return " ".join(out)


async def main() -> int:
    blender = FakeBlender()
    port = blender.start()
    notes.append(f"สะพานพร้อมที่พอร์ต {port}")

    server_log = pathlib.Path("/tmp/blender_mcp_e2e_server.log")
    params = StdioServerParameters(
        command=PY,
        args=[str(ROOT / "blender_mcp_server.py"),
              "--attach", f"127.0.0.1:{port}", "--token", TOKEN,
              "--log-file", str(server_log), "--timeout", "30"],
        cwd=str(ROOT),
    )

    try:
        with open(os.devnull, "w") as devnull:
            async with stdio_client(params, errlog=devnull) as (read, write):
                async with ClientSession(read, write) as session:

                    # ------------------------------------------------ [1]
                    section("[1] จับมือ (initialize) กับ MCP server")
                    init = await session.initialize()
                    si = A(init, "server_info", "serverInfo")
                    check("เซิร์ฟเวอร์บอกชื่อตัวเองว่า 'blender'",
                          "blender" in str(si.name), str(si))
                    check("บอกเวอร์ชัน", bool(si.version), str(si))
                    check("บอกความสามารถด้าน tools", A(init.capabilities, "tools") is not None)
                    check("บอกความสามารถด้าน resources",
                          A(init.capabilities, "resources") is not None)

                    # ------------------------------------------------ [2]
                    section("[2] ค้นหาเครื่องมือ (tools/list)")
                    tl = await session.list_tools()
                    names = [t.name for t in tl.tools]
                    expect = ["get_scene_hierarchy", "add_primitive_mesh",
                              "modify_object_transform", "execute_blender_script",
                              "get_object_details", "delete_object",
                              "set_object_material", "save_blend_file"]
                    check("มีเครื่องมือครบ 8 ตัว", len(names) == 8, str(names))
                    for want in expect:
                        check(f"มีเครื่องมือ {want}", want in names, str(names))

                    schemas = {t.name: (A(t, "input_schema", "inputSchema") or {}) for t in tl.tools}
                    props = schemas["add_primitive_mesh"].get("properties", {})
                    check("สคีมาของ add_primitive_mesh มี primitive/location/rotation/scale",
                          {"primitive", "location", "rotation", "scale"} <= set(props),
                          str(sorted(props)))
                    check("สคีมาบอกชนิด array ของ location",
                          (props.get("location") or {}).get("type", "").endswith("array")
                          or "anyOf" in (props.get("location") or {}),
                          str(props.get("location")))
                    desc = {t.name: (t.description or "") for t in tl.tools}
                    check("ทุกเครื่องมือมีคำอธิบายให้ AI อ่าน",
                          all(desc.values()), str({k: len(v) for k, v in desc.items()}))
                    check("คำอธิบายเตือนเรื่ององศา/เรเดียน",
                          "DEGREES" in desc.get("modify_object_transform", ""),
                          "สำคัญ: กัน AI ส่งเรเดียนผิดหน่วย")
                    check("คำอธิบายบอกว่า execute_blender_script ไม่ใช่ sandbox",
                          "NOT a sandbox" in desc.get("execute_blender_script", ""))

                    # ------------------------------------------------ [3]
                    section("[3] เรียกเครื่องมือจริงผ่าน MCP")
                    r = await session.call_tool("get_scene_hierarchy", {})
                    data = _payload(r)
                    check("get_scene_hierarchy ทำงาน", bool(data.get("objects")), str(data)[:150])
                    check("เห็นวัตถุตั้งต้นของ Blender",
                          "Cube" in [o["name"] for o in data.get("objects", [])],
                          str([o.get("name") for o in data.get("objects", [])]))
                    check("บอกเวอร์ชัน Blender 5.2 ผ่านสาย MCP",
                          data.get("blender_version") == "5.2.0", str(data.get("blender_version")))

                    r = await session.call_tool("add_primitive_mesh", {
                        "primitive": "cylinder", "name": "LPM_E2E",
                        "location": [1, 2, 3], "rotation": [90, 0, 0], "scale": [1, 1, 2]})
                    d = _payload(r)
                    check("สร้างรูปทรงผ่าน MCP ได้", d.get("created") == "LPM_E2E", str(d)[:150])
                    check("ตำแหน่งที่ได้ตรงกับที่สั่ง", d.get("location") == [1.0, 2.0, 3.0], str(d))

                    r = await session.call_tool("modify_object_transform", {
                        "name": "LPM_E2E", "location": [9, 9, 9], "rotation": [45, 0, 0]})
                    d = _payload(r)
                    check("ขยับวัตถุผ่าน MCP ได้", d.get("location") == [9.0, 9.0, 9.0], str(d)[:150])
                    check("หมุน: คืนค่าเป็นองศาให้ AI อ่านง่าย",
                          d.get("rotation_euler_deg", [None])[0] == 45.0, str(d.get("rotation_euler_deg")))

                    r = await session.call_tool("set_object_material",
                                                {"name": "LPM_E2E", "color": [0.9, 0.2, 0.2]})
                    d = _payload(r)
                    check("ใส่วัสดุผ่าน MCP ได้", str(d.get("material", "")).startswith("LPM_"), str(d)[:150])

                    r = await session.call_tool("get_object_details", {"name": "LPM_E2E"})
                    d = _payload(r)
                    check("อ่านรายละเอียดวัตถุผ่าน MCP ได้",
                          d.get("name") == "LPM_E2E" and "matrix_world" in d, str(d)[:150])

                    r = await session.call_tool("execute_blender_script",
                                                {"code": "import bpy\nresult = len(bpy.data.objects)"})
                    d = _payload(r)
                    check("รันสคริปต์ผ่าน MCP ได้", d.get("ok") is True and d.get("result") == 5,
                          str(d)[:180])
                    check("คืนค่า stdout กลับมาด้วย", "stdout" in d)

                    r = await session.call_tool("execute_blender_script",
                                                {"code": "import os\nresult = os.getcwd()"})
                    check("สคริปต์ที่ฝ่าด่านถูกปฏิเสธ (ไม่ใช่รันเงียบ ๆ)",
                          _is_error(r) or _payload(r).get("ok") is False, _text(r)[:150])
                    check("ข้อความปฏิเสธบอกสาเหตุเป็นภาษาไทย",
                          "ห้าม import 'os'" in _text(r), _text(r)[:180])

                    r = await session.call_tool("delete_object", {"name": "LPM_E2E"})
                    check("ลบแบบมีสลักกันพลาด (ยังไม่ลบ)", _payload(r).get("deleted") is False,
                          _text(r)[:150])
                    r = await session.call_tool("delete_object",
                                                {"name": "LPM_E2E", "confirm": True})
                    check("ยืนยันแล้วลบจริง", _payload(r).get("deleted") is True, _text(r)[:150])

                    # ------------------------------------------------ [4]
                    section("[4] ข้อผิดพลาดต้องไม่ทำให้ทั้งระบบล้ม")
                    r = await session.call_tool("modify_object_transform",
                                                {"name": "ไม่มีวัตถุนี้"})
                    check("เรียกเครื่องมือกับวัตถุที่ไม่มี → รายงาน error",
                          _is_error(r) or "ไม่พบวัตถุ" in _text(r), _text(r)[:150])
                    r = await session.call_tool("get_scene_hierarchy", {})
                    check("หลัง error ยังใช้งานต่อได้ทันที",
                          bool(_payload(r).get("objects")), _text(r)[:150])

                    # ------------------------------------------------ [5]
                    section("[5] ทรัพยากร (resources)")
                    rl = await session.list_resources()
                    uris = [str(x.uri) for x in rl.resources]
                    check("มี resource ของไฟล์ .blend", "blender://file/metadata" in uris, str(uris))
                    check("มี resource ของลำดับชั้นฉาก", "blender://scene/hierarchy" in uris, str(uris))

                    r = await session.read_resource("blender://file/metadata")
                    body = "".join(getattr(c, "text", "") for c in r.contents)
                    meta = json.loads(body)
                    check("อ่าน metadata ได้และเป็น JSON", isinstance(meta, dict), body[:150])
                    check("metadata มีที่อยู่ไฟล์", "filepath" in meta, str(list(meta)))
                    check("metadata มี engine ที่ใช้เรนเดอร์", "render_engine" in meta, str(list(meta)))
                    check("metadata มีเฟรมปัจจุบัน", meta.get("frame", {}).get("current") == 1,
                          str(meta.get("frame")))
                    check("metadata นับจำนวนของในไฟล์", "counts" in meta and "objects" in meta["counts"])

                    r = await session.read_resource("blender://scene/hierarchy")
                    body = "".join(getattr(c, "text", "") for c in r.contents)
                    hier = json.loads(body)
                    check("อ่านลำดับชั้นฉากผ่าน resource ได้",
                          "Cube" in [o["name"] for o in hier.get("objects", [])], body[:150])

                    # ------------------------------------------------ [6]
                    section("[6] ยังไม่มี Blender ก็ต้องบอกให้รู้ ไม่ใช่ค้าง")
                    check("สะพานยังทำงานอยู่หลังทดสอบทั้งหมด",
                          blender.proc is not None and blender.proc.poll() is None)
    finally:
        blender.stop()
        time.sleep(0.2)

    section("สรุป")
    for n in notes:
        print("  •", n)
    if server_log.is_file() and failed:
        tail = server_log.read_text(encoding="utf-8").strip().splitlines()[-12:]
        print("\n── บันทึกท้าย ๆ ของ MCP server ──")
        for line in tail:
            print("   ", line)

    print()
    print("=" * 72)
    if failed:
        print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
        for f in failed:
            print("   • " + f)
        return 1
    print(f"✅ ผ่านทั้งหมด {passed} รายการ")
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))
