#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_docs_links.py — ตรวจว่าลิงก์ในเอกสารชี้ไปที่ไฟล์ที่มีจริง

ลิงก์เสียคือปัญหาที่พบบ่อยที่สุดของรีโปที่เพิ่งเปิดสาธารณะ และเป็นสิ่งที่คนเห็น
ก่อนอย่างอื่น (กดแล้ว 404) — เทสต์นี้จึงควรอยู่ใน CI

ตรวจ:
  - ลิงก์แบบสัมพัทธ์ (ไฟล์ในรีโป) ต้องมีไฟล์นั้นจริง
  - anchor (#หัวข้อ) ที่อ้างถึงภายในไฟล์เดียวกัน ต้องมีหัวข้อนั้นจริง
  - ไฟล์ที่เอกสารอ้างว่า "มีอยู่" (เช่น INSTALL.md ที่ README ลิงก์) ต้องมีจริง
"""

from __future__ import annotations

import pathlib
import re
import sys
import unicodedata

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


def slug(text: str) -> str:
    """ทำหัวข้อให้เป็น anchor แบบที่ GitHub สร้าง (ใช้ตรวจลิงก์ในไฟล์)

    GitHub: ตัวพิมพ์เล็ก ตัดอักขระพิเศษ เว้นวรรค→'-' เก็บอักษรไทยไว้
    """
    s = text.strip().lower()
    s = re.sub(r"[^\w\s\-\u0e00-\u0e7f]", "", s, flags=re.UNICODE)
    s = s.replace(" ", "-")
    return unicodedata.normalize("NFC", s)


DOCS = sorted(p for p in ROOT.glob("*.md")) + sorted(ROOT.glob("docs/*.md"))
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")

section("[1] เอกสารที่ต้องมีสำหรับรีโปสาธารณะ")
for name, why in (("README.md", "หน้าหลักของรีโป"),
                  ("INSTALL.md", "คู่มือติดตั้ง (อังกฤษ)"),
                  ("INSTALL.th.md", "คู่มือติดตั้ง (ไทย)"),
                  ("LICENSE", "สัญญาอนุญาต — รีโปสาธารณะควรมี"),
                  (".gitattributes", "กันปัญหา CRLF/LF ข้ามระบบ"),
                  (".github/workflows/tests.yml", "รันเทสต์อัตโนมัติบน GitHub"),
                  ("tools/build_addon_zip.py", "สร้าง zip ติดตั้ง add-on")):
    f = ROOT / name
    check(f"มี {name} ({why})", f.is_file(), str(f))

section("[2] ทุกลิงก์ในเอกสารชี้ไปที่มีจริง")
total_links = 0
for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    headings = [slug(m.group(2)) for m in re.finditer(r"^(#{1,6})\s+(.*)$", text, re.M)]
    for m in MD_LINK.finditer(text):
        label, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        total_links += 1
        rel, _, anchor = target.partition("#")
        # ลิงก์ภายในไฟล์เดียวกัน
        if not rel:
            check(f"{doc.name}: #{anchor} ({label[:28]})", anchor in headings,
                  f"ไม่พบหัวข้อนี้ (มี: {headings[:4]}…)")
            continue
        dest = (doc.parent / rel).resolve()
        check(f"{doc.name} → {rel}", dest.exists(), f"ไม่พบไฟล์ {dest}")
        # ถ้าชี้ไป .md ต้องมี anchor ด้วย (ถ้าระบุ)
        if anchor and dest.suffix == ".md" and dest.is_file():
            sub = [slug(x.group(2)) for x in
                   re.finditer(r"^(#{1,6})\s+(.*)$", dest.read_text(encoding="utf-8"), re.M)]
            check(f"{dest.name}: #{anchor}", anchor in sub, f"ไม่พบหัวข้อใน {dest.name}")

check("พบลิงก์ภายในให้ตรวจมากพอ (!= 0)", total_links > 10, f"พบ {total_links}")

section("[3] ลิงก์ที่ README อ้างว่าสำคัญต้องมีจริง")
readme = (ROOT / "README.md").read_text(encoding="utf-8")
for must in ("INSTALL.th.md", "INSTALL.md", "LICENSE", "docs/02-Hermes-config.md",
             "docs/01-ติดตั้ง-Windows11.md", ".github/workflows/tests.yml",
             "tools/build_addon_zip.py"):
    check(f"README อ้างถึง {must}", must in readme, "ไม่มีใน README")
    check(f"ไฟล์ที่อ้างมีจริง: {must}", (ROOT / must).exists(), must)

section("[4] คู่มือสองภาษาต้องพูดเรื่องเดียวกัน")
th = (ROOT / "INSTALL.th.md").read_text(encoding="utf-8")
en = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
# เทียบแบบไม่สนตัวพิมพ์ — เอกสารมักขึ้นต้นประโยคด้วยตัวใหญ่
for topic, th_kw, en_kw in (("คำเตือน --args ท้ายสุด", "--args", "--args"),
                            ("แพ็กเกจ mcp ฝั่ง Hermes", "uv pip install", "uv pip install"),
                            ("พอร์ต 9876", "9876", "9876"),
                            ("ห้ามเปิดพอร์ตออกเครือข่าย", "ห้ามเปิด", "never expose"),
                            ("วิธีถอนการติดตั้ง", "ถอนการติดตั้ง", "Uninstall"),
                            ("ตารางแก้ปัญหา", "แก้ปัญหา", "Troubleshooting")):
    check(f"ไทยมีเรื่อง «{topic}»", th_kw.lower() in th.lower(), th_kw)
    check(f"อังกฤษมีเรื่อง «{topic}»", en_kw.lower() in en.lower(), en_kw)

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ (ตรวจ {total_links} ลิงก์ใน {len(DOCS)} ไฟล์)")
sys.exit(0)
