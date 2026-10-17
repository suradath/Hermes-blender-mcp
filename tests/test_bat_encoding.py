#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_bat_encoding.py — กันไม่ให้สคริปต์ Windows แสดงภาษาไทยเป็นตัวประหลาด

ปัญหาจริงที่เจอ: `install-windows.bat` แสดงภาษาไทยเป็นตัวอ่านไม่ออกบน cmd.exe
เพราะ cmd เขียนข้อความ `echo` เป็น "ไบต์ดิบ" ตาม codepage ของหน้าต่าง
(ไฟล์เป็น UTF-8 แต่หน้าต่างเป็น CP874/CP437) — ต่างจาก Python ที่ใช้ API แบบกว้าง
จึงพิมพ์ไทยได้ถูกเสมอ

เงื่อนไขที่ต้องคงไว้:
  1. ไฟล์ .bat/.cmd ต้องเป็น UTF-8 **ไม่มี BOM** (BOM ทำให้ cmd อ่านบรรทัดแรกพัง)
  2. ต้องมี `chcp 65001` และต้องอยู่ **ก่อน** บรรทัด `echo` แรก
  3. บรรทัด `echo` ที่มีอักษรนอก ASCII ต้องอยู่หลัง `chcp 65001` แล้วเท่านั้น
  4. ไฟล์ต้องถอดรหัสเป็น UTF-8 ได้ (ไม่ใช่ ANSI/TIS-620 เก่า)
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

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


BATS = ["install-windows.bat", "run-hermes-blender-mcp.bat"]


section("[1] มีไฟล์ครบ")
for name in BATS:
    check(f"มี {name}", (ROOT / name).is_file(), str(ROOT / name))


section("[2] ไม่มี BOM · ถอดรหัส UTF-8 ได้")
for name in BATS:
    p = ROOT / name
    if not p.is_file():
        continue
    raw = p.read_bytes()
    check(f"{name} ไม่มี BOM", not raw.startswith(b"\xef\xbb\xbf"),
          "มี UTF-8 BOM — cmd จะเห็นเป็นตัวอักษรขยะหน้า @echo แล้วพัง")
    try:
        p.read_text(encoding="utf-8")
        check(f"{name} เป็น UTF-8 ที่ถูกต้อง", True)
    except UnicodeDecodeError as exc:
        check(f"{name} เป็น UTF-8 ที่ถูกต้อง", False, str(exc))


section("[3] chcp 65001 มาก่อน echo แรก")
for name in BATS:
    p = ROOT / name
    if not p.is_file():
        continue
    lines = p.read_text(encoding="utf-8").splitlines()
    chcp = [i for i, l in enumerate(lines) if l.strip().lower().startswith("chcp 65001")]
    echo = [i for i, l in enumerate(lines) if l.strip().lower().startswith("echo")]
    check(f"{name} มี chcp 65001", bool(chcp),
          "ไม่มี chcp 65001 — ภาษาไทยใน echo จะกลายเป็นตัวประหลาด")
    if chcp and echo:
        check(f"{name} chcp อยู่ก่อน echo แรก", chcp[0] < echo[0],
              f"chcp บรรทัด {chcp[0] + 1} · echo แรกบรรทัด {echo[0] + 1}")
    check(f"{name} เริ่มด้วย @echo off",
          bool(lines) and lines[0].strip().lower() == "@echo off",
          lines[0] if lines else "(ว่าง)")


section("[4] echo ที่มีภาษาไทยต้องอยู่หลัง chcp")
for name in BATS:
    p = ROOT / name
    if not p.is_file():
        continue
    lines = p.read_text(encoding="utf-8").splitlines()
    chcp_line = next((i for i, l in enumerate(lines)
                      if l.strip().lower().startswith("chcp 65001")), 10 ** 6)
    bad = [(i + 1, l.strip()[:48]) for i, l in enumerate(lines)
           if l.strip().lower().startswith("echo")
           and any(ord(c) > 127 for c in l)
           and i < chcp_line]
    check(f"{name} ไม่มี echo ภาษาไทยก่อน chcp", not bad, str(bad[:3]))

section("[5] ข้อความ echo ขั้นตอนสำคัญเป็นภาษาอังกฤษ (อ่านได้ทุกเครื่อง)")
for name in BATS:
    p = ROOT / name
    if not p.is_file():
        continue
    text = p.read_text(encoding="utf-8")
    # ทุกข้อความ [1/4] [2/4] ... ต้องเป็น ASCII ล้วน (เป็นข้อความบอกความคืบหน้า)
    steps = [l.strip() for l in text.splitlines() if "[1/4]" in l or "[2/4]" in l
             or "[3/4]" in l or "[4/4]" in l]
    check(f"{name} บรรทัดความคืบหน้าเป็น ASCII", all(l.isascii() for l in steps), str(steps))


print()
if failed:
    print(f"❌ ล้มเหลว {len(failed)} รายการ")
    for f in failed:
        print(f"   • {f}")
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ")
