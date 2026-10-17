# บันทึกการเปลี่ยนแปลง (Changelog)

ทุกการเปลี่ยนแปลงที่สำคัญของโปรเจกต์นี้จะบันทึกไว้ในไฟล์นี้

รูปแบบอ้างอิง [Keep a Changelog](https://keepachangelog.com/th/1.1.0/)
· เวอร์ชันอ้างอิง [Semantic Versioning](https://semver.org/lang/th/)
· หัวข้อใช้คำไทยคู่กับคำอังกฤษ เพื่อให้คนไทยอ่านง่ายและเครื่องมือ parse ได้

---

## [Unreleased]

### เพิ่ม (Added)

_ยังไม่มี_

### เปลี่ยน (Changed)

_ยังไม่มี_

### แก้ไข (Fixed)

_ยังไม่มี_

> 💡 เมื่อเพิ่มอะไร ให้ใส่บรรทัดใต้หัวข้อที่ถูกต้องใน `[Unreleased]` ก่อน — **อย่าตั้งเลขเวอร์ชันเอง**
> ผู้ดูแลจะย้ายไปยังเวอร์ชันใหม่ตอนปล่อย (ดู [CONTRIBUTING §8](CONTRIBUTING.md))

---

## [1.0.0] - 2026-10-17

เวอร์ชันแรก — MCP server ที่ให้ AI (Hermes Agent / Claude Desktop / ไคลเอนต์ MCP ใด ๆ)
อ่านและสั่งงาน **Blender 5.2 LTS** ผ่าน `bpy` ได้จากในแชท

### เพิ่ม (Added)

**MCP server** — `blender_mcp_server.py` (`5,599` บรรทัดทั้งโปรเจกต์)
- สื่อสารผ่าน **stdio** ด้วย MCP Python SDK ทางการ (`mcp>=2.0,<3` · ทดสอบกับ 2.3.0)
- เปิด/ปิด Blender ให้เองอัตโนมัติ (โหมด `--background` เป็นค่าปริยาย) หรือ `--gui`
- ต่อกับ Blender ที่เปิดค้างอยู่ได้ด้วย `--attach host:port --token …`
- ตัวเลือก: `--blend-file`, `--blender`, `--timeout`, `--check`, `--list-tools`, `--selftest`
- ค้นหา Blender ให้เองบน Windows/Linux/macOS และ**บอกที่มาของคำตอบ** (เจอจาก PATH / จากตัวแปร / จากที่มาตรฐาน)

**เครื่องมือ 8 ตัว**

| เครื่องมือ | ทำอะไร |
|---|---|
| `get_scene_hierarchy` | อ่านฉาก: คอลเลกชัน + วัตถุ + transform + จำนวนจุดยอด + ตัวกรองชื่อ |
| `add_primitive_mesh` | สร้าง 10 รูปทรง (cube/sphere/cylinder/plane/cone/torus/monkey/circle/grid/ico_sphere) |
| `modify_object_transform` | ขยับ/หมุน/ย่อขยาย (แบบสัมบูรณ์หรือสัมพัทธ์) |
| `execute_blender_script` | รันโค้ด `bpy` ดิบ พร้อมด่านตรวจ |
| `get_object_details` | รายละเอียดวัตถุชิ้นเดียว (matrix_world, modifiers, materials, custom props) |
| `delete_object` | ลบวัตถุ (มีสลัก `confirm` กันลบพลาด) |
| `set_object_material` | ใส่วัสดุ Principled BSDF |
| `save_blend_file` | บันทึกไฟล์ `.blend` |

**ทรัพยากร 2 ตัว** — `blender://file/metadata` (ที่อยู่ไฟล์ · render engine · เฟรม ·
ความละเอียด · จำนวนของในไฟล์) และ `blender://scene/hierarchy`

**สะพานใน Blender** — `blender_bridge.py` (ใช้แค่ stdlib)
- เรียก `bpy` **บน main thread เท่านั้น** (bpy ไม่ thread-safe)
- สองโหมด: `main` (บล็อกบน main thread สำหรับ `blender -b` — เพราะ `bpy.app.timers`
  **ไม่ทำงาน** ในโหมด background) และ `timer` (คิวงาน + timer สำหรับโหมดมีหน้าต่าง)
- รับคำสั่งทางซ็อกเก็ต `127.0.0.1` พร้อม token สุ่มทุกครั้ง

**add-on ของ Blender** — `blender_addon/__init__.py`
- แผงใน `View3D > Sidebar (N) > Blender MCP` · เริ่ม/หยุดสะพาน · แสดงพอร์ต+token
- ใช้ token แบบสุ่มและเก็บไว้ในไฟล์ `.blend` · แก้พอร์ตได้ (ค่าปริยาย `9876`)

**การติดตั้งและเอกสาร**
- `install-windows.bat` — ติดตั้งครบในคำสั่งเดียว (venv + แพ็กเกจ + ตรวจเจอ Blender)
- `run-blender-mcp.bat` / `.sh` — ตัวเปิดเซิร์ฟเวอร์และคำสั่งตรวจวินิจฉัย
- `tools/build_addon_zip.py` — สร้าง zip สำหรับ `Install from Disk` ใน Blender
  (อ่านเลขเวอร์ชันจาก `bl_info` ตั้งชื่อไฟล์เอง และตรวจโครงสร้างก่อนคืนค่า)
- เอกสาร: `README.md` · `INSTALL.th.md` · `INSTALL.md` · `docs/01-ติดตั้ง-Windows11.md`
  · `docs/02-Hermes-config.md`

**การทดสอบและ CI**
- **329 ข้อ ใน 5 ชุด** ทดสอบด้วยของจริงทุกชั้นยกเว้นตัว Blender (ใช้ `tests/fake_bpy.py`)
- `test_mcp_e2e.py` ขับด้วย **MCP client ทางการ** ผ่าน stdio จริง ครบวงจร
- GitHub Actions รันบน Python 3.10 + 3.12 พร้อมตรวจว่า **stdout ว่าง 0 ไบต์** ตอนสตาร์ต

### เปลี่ยน (Changed)

- ตั้งค่าปริยายของสะพานเป็น **พอร์ตสุ่ม + token สุ่ม** (โหมดที่เซิร์ฟเวอร์เปิด Blender เอง)
  เพื่อไม่ให้ชนกับอะไรในเครื่องและไม่ต้องตั้งค่าอะไรเลย — โหมด add-on ยังใช้ `9876` ตามธรรมเนียม
- หน่วยหมุนที่ขอบเครื่องมือเป็น **องศา** (แปลงเป็นเรเดียนภายใน) เพราะ AI ถนัดองศา

### ความปลอดภัย (Security)

- `execute_blender_script` มีด่านตรวจ **ก่อนรัน** ด้วย AST: ห้าม `import` โมดูลอันตราย
  (`os`, `sys`, `subprocess`, `socket`, `ctypes`, `importlib`, `pickle`, `shutil`, `pathlib` …)
  · ห้ามเรียก `open()`/`eval()`/`exec()`/`compile()`/`__import__`/`getattr` … ·
  ห้ามเข้าถึง attribute `__xx__` (ทางหลบหนีคลาสสิก) · ห้าม `bpy.ops.wm.quit_blender`
  และ operator ที่ทำลายงาน · ตั้ง `allow_unsafe=true` เพื่อข้ามด่านได้
- ⚠️ **ด่านนี้คือ "ราวกันตก" ไม่ใช่ sandbox** — โค้ดที่ผ่านด่านยังแก้ฉากทั้งหมดได้
  (ระบุไว้ชัดในคำอธิบายเครื่องมือ เอกสาร และข้อความ error)
- สะพานรับฟังเฉพาะ `127.0.0.1` + token สุ่ม · **ห้ามเปิดพอร์ตออกเครือข่าย** (ไม่เข้ารหัส)

### บันทึกการพัฒนา (Notes)

บันทึกไว้เพราะเป็นกับดักที่คนอื่นจะเจอเหมือนกัน — บั๊กทั้ง 4 ตัวนี้ถูกจับได้ **ก่อน** ปล่อย
เวอร์ชันแรก โดยชุดทดสอบ ไม่ใช่พบในของที่ปล่อยออกไป

| # | อาการ | ต้นเหตุจริง |
|---|---|---|
| 1 | ทุกการเชื่อมต่อถูกปฏิเสธเงียบ ๆ → ไคลเอนต์วนลอง 90 วินาทีแล้วค้าง | `socket.socket` นิยาม `__slots__` → เก็บไฟล์เป็น attribute ไม่ได้ แล้ว `except` กวาดความผิดพลาดทิ้ง |
| 2 | AI เห็นแค่ `Error executing tool X` ไม่รู้สาเหตุ | SDK **กลืนข้อความ** ของ exception ธรรมดา — ต้องโยน `ToolError` ของ SDK |
| 3 | `allow_unsafe=true` ยังถูกบล็อก `import os` | ด่านอยู่ **สองที่** (ตรวจ AST + `__import__` ที่ถูกแทน) แต่ปลดล็อกแค่ที่เดียว |
| 4 | เทสต์หา `bpy.data.objects["ชื่อใหม่"]` ไม่เจอ | `bpy` ปลอมไม่ได้ย้ายคีย์ให้เหมือนของจริง → เทสต์ตัดสินผิด |

**ยืนยันแล้ว**
- เชื่อมกับ **Hermes Agent ตัวจริง** ได้: `hermes mcp add` → `✓ Connected! Found 8 tool(s)`
  · `hermes mcp test` → `✓ Connected (1950ms) · ✓ Tools discovered: 8`
- stdout ว่าง 0 ไบต์ตอนสตาร์ต (ท่อ JSON-RPC สะอาด)
- ชุดทดสอบ 329 ข้อ ผ่านหมด

**ยังไม่ได้ยืนยัน**
- การเปิด/ปิด **Blender จริง** และ `bpy.app.timers` ของจริง (เครื่องที่พัฒนาไม่มี Blender)
  → มี `--selftest` ให้ยืนยันในคำสั่งเดียวบนเครื่องผู้ใช้
- workflow CI: YAML ตรวจแล้วว่าถูกต้องและรันขั้นต่าง ๆ บนเชลล์แบบไม่โต้ตอบผ่าน
  แต่ **ยังไม่เคยรันบน GitHub Actions** — ครั้งแรกที่ push จะรู้ผล

---

<!--
เทมเพลตสำหรับเวอร์ชันถัดไป — คัดลอกแล้วแก้

## [1.1.0] - YYYY-MM-DD

### เพิ่ม (Added)
- …

### เปลี่ยน (Changed)
- …

### แก้ไข (Fixed)
- …

### ความปลอดภัย (Security)
- …
-->

[Unreleased]: https://github.com/OWNER/blender-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/OWNER/blender-mcp/releases/tag/v1.0.0
