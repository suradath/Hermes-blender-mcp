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
                  ("CONTRIBUTING.md", "วิธีร่วมพัฒนา"),
                  ("CHANGELOG.md", "บันทึกการเปลี่ยนแปลง"),
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

section("[2.1] เอกสารที่รีโปสาธารณะควรอ้างถึงกัน")
readme_now = (ROOT / "README.md").read_text(encoding="utf-8")
for must in ("CONTRIBUTING.md", "CHANGELOG.md"):
    check(f"README ลิงก์ไปที่ {must}", must in readme_now, "ไม่มีใน README")
# CHANGELOG ต้องอ้างถึง Keep a Changelog และชี้วิธีเพิ่มรายการ
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
check("CHANGELOG อ้างอิงรูปแบบ Keep a Changelog", "Keep a Changelog" in changelog)
check("CHANGELOG มีหัวข้อ [Unreleased] ให้คนอื่นเติม", "## [Unreleased]" in changelog)
check("CHANGELOG อธิบายวิธีเพิ่มรายการ (ห้ามตั้งเลขเวอร์ชันเอง)",
      "อย่าตั้งเลขเวอร์ชัน" in changelog, "ต้องบอกว่าผู้ดูแลตัดเวอร์ชันเอง")
contrib = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
for topic, kw in (("วิธีรันเทสต์", "run_all.sh"),
                  ("กฎ stdout ห้ามสกปรก", "stdout"),
                  ("ห้ามเรียก bpy ข้ามเธรด", "thread"),
                  ("ต้องห่อ error ด้วย ToolError", "ToolError"),
                  ("สูตรเพิ่มเครื่องมือใหม่", "@srv.tool"),
                  ("แก้จำนวนเครื่องมือในเทสต์ด้วย", "len(names) =="),
                  ("รายงานบั๊ก", "รายงานบั๊ก"),
                  ("ความปลอดภัย/ไม่ใช่ sandbox", "sandbox")):
    check(f"CONTRIBUTING สอนเรื่อง «{topic}»", kw in contrib, kw)

section("[2.2] README ต้องมีการเทียบกับโครงการอื่นอย่างซื่อสัตย์")

# บทเรียน: การแนะนำโครงการอื่นต้องมาจากข้อมูลจริงและบอกข้อจำกัดของตัวเอง ไม่ใช่โฆษณา
for kw, why in (
        ("ahujasid/mcp-for-blender", "ต้องอ้างถึงตัวที่คนใช้มากที่สุด (ตรวจจากข้อมูลจริง)"),
        ("31,125", "ต้องมีตัวเลขดาวที่ตรวจมา ไม่ใช่พูดลอย ๆ"),
        ("ยังไม่ได้รันของใครเลย", "ต้องบอกตรง ๆ ว่ายังไม่ได้ทดลองรันของเขา"),
        ("เลือกอันไหน", "ต้องมีคำแนะนำว่าเมื่อไรควรใช้อันไหน"),
        ("คนละหน้าที่", "ต้องแยกให้ชัดว่าสกิล (ความรู้) ต่างจาก MCP (ลงมือทำ)"),
        ("issues/251", "ต้องอ้างหลักฐานของข้อจำกัดที่ตรวจพบ"),
):
    check(f"README มี «{kw}»", kw in readme_now, why)

check("README บอกว่าเราเรียนอะไรจากเขาและนำมาแก้",
      "ได้เรียนรู้จากตัว" in readme_now or "parse_known_args" in readme_now,
      "การเทียบควรนำไปสู่การปรับปรุง ไม่ใช่แค่เปรียบเทียบ")

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

section("[5] ไม่มีอักษรต่างชาติหลุด (บทเรียนจริง: เคยหลุด 2 ครั้ง)")

# อักษรที่ *ไม่ควร* ปรากฏ: ไทย (0E00-0E7F) และละตินพื้นฐาน/อีโมจิ/เครื่องหมายวรรคตอน = ผ่าน
FOREIGN_BLOCKS = [
    (0x00C0, 0x024F, "ละตินมีเครื่องหมายกำกับ U+00C0–U+024F"),
    (0x0370, 0x03FF, "กรีก"),
    (0x0400, 0x04FF, "ซีริลลิก"),
    (0x0530, 0x058F, "อาร์เมเนีย"),
    (0x0590, 0x05FF, "ฮีบรู"),
    (0x0600, 0x06FF, "อาหรับ"),
    (0x3040, 0x30FF, "ญี่ปุ่น"),
    (0x4E00, 0x9FFF, "จีน"),
    (0xAC00, 0xD7AF, "เกาหลี"),
]
ALLOWED_CHARS = {"\u00d7", "\u00f7"}   # × ÷ (อยู่ในช่วงละตินแต่เป็นสัญลักษณ์คณิต)
SUFFIXES = {".py", ".md", ".txt", ".bat", ".sh", ".yml", ".yaml", ".json"}
SKIP = {".venv", "dist", "__pycache__", ".git", "node_modules"}

offenders: list[tuple[pathlib.Path, int, str, str]] = []
scanned = 0
for f in sorted(ROOT.rglob("*")):
    if not f.is_file() or f.suffix not in SUFFIXES:
        continue
    if any(part in SKIP for part in f.parts):
        continue
    scanned += 1
    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for ch in line:
            if ch in ALLOWED_CHARS:
                continue
            o = ord(ch)
            for lo, hi, name in FOREIGN_BLOCKS:
                if lo <= o <= hi:
                    offenders.append((f.relative_to(ROOT), i, ch, name))
                    break

check("สแกนไฟล์ข้อความครบ (!= 0)", scanned > 10, f"สแกน {scanned} ไฟล์")
check("ไม่มีอักษรต่างชาติหลุดเลย (ไทย/ละติน/อีโมจิ ผ่าน)",
      not offenders,
      "; ".join(f"{f}:{i} {c!r} ({n})" for f, i, c, n in offenders[:5]))

section("[6] รูปภาพที่เอกสารอ้างถึง ต้องมีจริงและเป็น PNG ที่สมบูรณ์")

IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
imgs = []
for doc in DOCS:
    for alt, target in IMG.findall(doc.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://")):
            continue
        imgs.append((doc, alt, target, (doc.parent / target).resolve()))

check("เอกสารมีรูปประกอบ (!= 0)", len(imgs) > 0, f"พบ {len(imgs)} รูป")
check("ทุกรูปมีคำบรรยาย alt (ช่วยคนตาบอด/ตอนโหลดช้า)",
      all(a.strip() for _d, a, _t, _p in imgs),
      str([(_d.name, t_) for _d, a, t_, _p in imgs if not a.strip()]))
missing = [(str(d.relative_to(ROOT)), tgt) for d, _a, tgt, path in imgs if not path.is_file()]
check("ทุกรูปที่อ้างถึงมีไฟล์จริงในรีโป", not missing, str(missing[:5]))
bad = []
for _d, _a, tgt, path in imgs:
    if not path.is_file():
        continue
    head = path.read_bytes()[:8]
    if head != b"\x89PNG\r\n\x1a\n":
        bad.append((tgt, "ไม่ใช่ PNG"))
    elif path.stat().st_size < 500:
        bad.append((tgt, f"เล็กผิดปกติ {path.stat().st_size} ไบต์"))
check("ทุกรูปเป็นไฟล์ PNG จริงและไม่ว่าง", not bad, str(bad[:5]))
check("รูปทั้งหมดอยู่ในโฟลเดอร์ของรีโป (ไม่ลิงก์ไปเครื่องใคร)",
      all(str(path).startswith(str(ROOT)) for *_x, path in imgs), "ต้องเป็นพาธสัมพัทธ์ในรีโป")

print()
print("=" * 70)
if failed:
    print(f"❌ ล้มเหลว {len(failed)} จากทั้งหมด {passed + len(failed)}")
    for f in failed:
        print("   • " + f)
    sys.exit(1)
print(f"✅ ผ่านทั้งหมด {passed} รายการ (ตรวจ {total_links} ลิงก์ใน {len(DOCS)} ไฟล์)")
sys.exit(0)
