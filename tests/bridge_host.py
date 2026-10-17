#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bridge_host.py — เปิด "สะพาน" ตัวจริง (blender_bridge.serve_blocking) บนเครื่องนี้
โดยใช้ bpy ปลอม — เพื่อทดสอบว่า MCP server คุยกับสะพานได้จริงแบบ end-to-end

ใช้โดย tests/test_mcp_e2e.py เท่านั้น (บนเครื่องจริงจะใช้ Blender เป็นเจ้าบ้าน)
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import fake_bpy  # noqa: E402

sys.modules["bpy"] = fake_bpy   # ต้องฉีดก่อน import bridge

import blender_bridge as br  # noqa: E402

if __name__ == "__main__":
    # ตั้งฉากเริ่มต้นเหมือน Blender เปิดไฟล์ใหม่ (Camera/Light/Cube + คอลเลกชันซ้อน)
    # ไม่ทำแบบนี้ฉากจะว่างเปล่า แล้วเทสต์จะผ่าน/ไม่ผ่านด้วยเหตุผลที่ไม่จริง
    fake_bpy.reset()
    # ส่งต่ออาร์กิวเมนต์ทั้งหมดให้ bridge (--port/--token/--host/--mode)
    sys.exit(br.main(sys.argv[1:]))
