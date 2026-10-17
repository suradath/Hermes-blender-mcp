# การร่วมพัฒนา (Contributing)

ขอบคุณที่สนใจช่วยพัฒนาค่ะ/ครับ 💖 โปรเจกต์นี้เป็นเครื่องมือของ **โรงเรียนลำปลายมาศ**
ที่ตั้งใจให้คนอื่นนำไปใช้และต่อยอดได้

> 🇬🇧 **In short (English):** set up with `python -m venv .venv && pip install -r requirements.txt`,
> run `bash tests/run_all.sh` (5 suites, 343 checks — **no Blender needed**), keep the
> rules in [§4](#4-กฎที่โปรเจกต์นี้บังคับ-และทำไม) (never write to stdout,
> never call `bpy` off the main thread, errors must be Thai and wrapped in `ToolError`,
> rotation is in degrees, docs must stay in two-language parity), and open one
> pull request per logical change. Contributions welcome in Thai or English.

**สารบัญ**

- [1. ช่วยอะไรได้บ้าง](#1-ช่วยอะไรได้บ้าง-what-we-need)
- [2. เตรียมเครื่อง](#2-เตรียมเครื่อง-setup)
- [3. รันทดสอบ](#3-รันทดสอบ-running-the-tests)
- [4. กฎที่โปรเจกต์นี้บังคับ (และทำไม)](#4-กฎที่โปรเจกต์นี้บังคับ-และทำไม)
- [5. วิธีเพิ่มเครื่องมือใหม่ 1 ตัว](#5-วิธีเพิ่มเครื่องมือใหม่-1-ตัว-adding-a-tool)
- [6. ทดสอบโดยไม่มี Blender](#6-ทดสอบโดยไม่มี-blender-testing-without-blender)
- [7. แนวการเขียนโค้ด](#7-แนวการเขียนโค้ด-code-style)
- [8. commit และ pull request](#8-commit-และ-pull-request)
- [9. รายงานบั๊ก](#9-รายงานบั๊ก-reporting-bugs)
- [10. เรื่องความปลอดภัย](#10-เรื่องความปลอดภัย-security)

---

## 1. ช่วยอะไรได้บ้าง (What we need)

| อยากได้ | หมายเหตุ |
|---|---|
| 🐛 **รายงานบั๊ก** | มีค่ามากที่สุดโดยเฉพาะจาก**เครื่องที่มี Blender จริง** — เครื่องที่พัฒนาโปรเจกต์นี้ไม่มี Blender ติดตั้ง (ดู [§9](#9-รายงานบั๊ก-reporting-bugs)) |
| 🔧 **เครื่องมือ MCP เพิ่ม** | เช่น เรนเดอร์, จัดการ scene, งาน material ขั้นสูง — ดูสูตรใน [§5](#5-วิธีเพิ่มเครื่องมือใหม่-1-ตัว-adding-a-tool) |
| 🌏 **ตรวจคู่มือ** | ลองทำตาม `INSTALL.md` / `INSTALL.th.md` บนเครื่องคุณ แล้วแก้จุดที่สะดุด |
| 🧪 **ขยายเทสต์** | โดยเฉพาะกรณีที่ `bpy` ปลอมยังไม่เหมือนของจริง |
| 🇬🇧 **แปลเอกสาร** | คู่มือสองภาษาต้องตรงกัน (มีเทสต์บังคับ — ดู [§4](#4-กฎที่โปรเจกต์นี้บังคับ-และทำไม)) |

**ไม่รับ:** การทำให้ `execute_blender_script` ดูเหมือน "ปลอดภัยจริง"
หรือการเปิดพอร์ตสะพานออกเครือข่าย — ดูเหตุผลใน [§10](#10-เรื่องความปลอดภัย-security)

---

## 2. เตรียมเครื่อง (Setup)

ต้องมี Python 3.10 ขึ้นไป (ไม่ต้องมี Blender ก็พัฒนาได้)

```bash
git clone https://github.com/<OWNER>/blender-mcp.git
cd blender-mcp
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt     # Windows: .\.venv\Scripts\python.exe -m pip ...

# ตรวจว่าโปรแกรมทำงาน (บนเครื่องที่ไม่มี Blender จะบอกว่า "หาไม่เจอ" — ปกติ)
./.venv/bin/python blender_mcp_server.py --list-tools
```

บนเครื่องที่มี Blender จะรันตรวจเต็มรูปแบบได้:

```bash
./run-blender-mcp.sh --check      # เจอ Blender ไหม
./run-blender-mcp.sh --selftest   # เปิด Blender จริง ไล่เรียกทุกเครื่องมือ
```

---

## 3. รันทดสอบ (Running the tests)

```bash
bash tests/run_all.sh
```

ต้องผ่านทั้ง **5 ชุด (343 ข้อ)** ก่อนเปิด pull request:

| ชุด | ตรวจอะไร |
|---|---|
| `test_addon_structure.py` | โครง add-on ตามที่ Blender ต้องการ + ตัวสร้าง zip |
| `test_docs_links.py` | ลิงก์ · คู่มือสองภาษาตรงกัน · อักษรต่างชาติหลุด · การเทียบโครงการอื่น |
| `test_server_utils.py` | ค้นหา Blender · CLI · อดทนต่ออาร์กิวเมนต์แปลก · การส่งพารามิเตอร์ |
| `test_bridge_logic.py` | ตรรกะทุกเครื่องมือ + ด่านความปลอดภัย (ใช้ `bpy` ปลอม) |
| `test_mcp_e2e.py` | MCP client ทางการ ⇄ เซิร์ฟเวอร์ ⇄ สะพาน (ครบวงจร) |

---

## 4. กฎที่โปรเจกต์นี้บังคับ (และทำไม)

สิบข้อนี้ไม่ใช่ความชอบส่วนตัว — **ทุกข้อเคยเกิดบั๊กจริงมาแล้ว** และมีเทสต์ล็อกไว้

| # | กฎ | ทำไม (ของจริงที่เคยเกิด) |
|---|---|---|
| 1 | **ห้ามเขียนอะไรลง `stdout`** ใน `blender_mcp_server.py` / `blender_bridge.py` — ใช้ `log()` ที่เขียนลง stderr | stdout เป็นท่อ JSON-RPC ของ MCP ถ้ามีข้อความปน ไคลเอนต์อ่านไม่รู้เรื่อง · CI ตรวจว่าต้อง **0 ไบต์** |
| 2 | **ห้ามเรียก `bpy` จาก thread อื่น** — ส่งงานผ่านคิวให้ main thread เท่านั้น | `bpy` ไม่ thread-safe เรียกผิด thread = **hard crash ไม่ใช่ exception** |
| 3 | **ข้อผิดพลาดต้องเป็นภาษาไทยและห่อด้วย `ToolError`** (`mcp.server.mcpserver.exceptions`) | ถ้าปล่อย exception ธรรมดา SDK จะ **กลืนข้อความ** เหลือแค่ `Error executing tool X` → AI มืดแปดด้าน |
| 4 | **หน่วยหมุนเป็น "องศา"** ที่ขอบเครื่องมือ แปลงเป็นเรเดียนภายใน | AI ถนัดองศา · เคยส่งเรเดียนตรง ๆ แล้วหมุนผิด 57 เท่า |
| 5 | **ห้ามให้เทสต์หรือเครื่องมือเขียนทับไฟล์จริงของผู้ใช้** — ใช้ `tempfile` + `os.chdir()` หรือพารามิเตอร์ `--out` | เคยมีเทสต์เขียนทับ `config.json` จริงของผู้ใช้ |
| 6 | **ด่านความปลอดภัยต้องบังคับที่เดียว** — เพิ่มกฎใน `scan_code()` **และ** ชุด `__builtins__` ที่จำกัด | เคยมีด่าน 2 ที่ แต่ `allow_unsafe=true` ปลดล็อกแค่ที่เดียว → ยังถูกบล็อกอยู่ |
| 7 | **ห้ามเรียกว่า "sandbox"** — ใช้คำว่า "ราวกันตก/guardrail" และคงข้อความเตือนไว้ | โค้ด `bpy` ที่ผ่านด่านยังลบทั้งฉากได้ การอ้างเกินจริงคือการโกหกผู้ใช้ |
| 8 | **เอกสารสองภาษาต้องตรงกัน** และลิงก์ต้องไม่เสีย | เอกสารสองชุดจะเพี้ยนทันทีที่แก้ข้างเดียว — `test_docs_links.py` บังคับ |
| 9 | **ห้ามลิงก์ไป anchor ที่มีอีโมจิ/เครื่องหมายผสม** — ลิงก์ไปที่ *ไฟล์* แล้วบอกเลขข้อในข้อความ | renderer แต่ละตัว slugify ต่างกัน → ลิงก์พังแบบหาไม่เจอสาเหตุ |
| 10 | **ตัวเลขในเอกสารต้องตรงกับความจริง** (จำนวนเทสต์, บรรทัด, เวอร์ชัน) | เอกสารที่อ้างเลขเก่าทำให้คนอ่านเชื่อผิด |

---

## 5. วิธีเพิ่มเครื่องมือใหม่ 1 ตัว (Adding a tool)

ตัวอย่าง: เพิ่มเครื่องมือ `set_object_visibility`

### ขั้น 1 — เขียนตรรกะใน `blender_bridge.py`

```python
@tool(
    "set_object_visibility",
    "Show or hide an object by name. Use hide_viewport to also hide it in the "
    "viewport, and hide_render for renders only.",          # ← อธิบายเป็นอังกฤษ (AI อ่าน)
)
def set_object_visibility(name: str, hide_render: bool = False,
                          hide_viewport: bool = False) -> dict:
    obj = _find_object(name)                                # ← ใช้ตัวช่วยเดิม (ข้อความไทยดีอยู่แล้ว)
    if obj.type == "CAMERA" and hide_render:
        raise ToolError("ซ่อนกล้องจากการเรนเดอร์ไม่ได้ — ต้องมีกล้องอย่างน้อยหนึ่งตัว")
    obj.hide_render = bool(hide_render)
    return {"name": obj.name, "hide_render": bool(obj.hide_render)}
```

ไม่ต้องลงทะเบียนที่ไหนอีก — `list_tools` อ่านจาก `_TOOLS` ให้เอง

### ขั้น 2 — เพิ่มตัวห่อใน `blender_mcp_server.py`

```python
    @srv.tool()
    async def set_object_visibility(name: str, hide_render: bool = False,
                                    hide_viewport: bool = False) -> dict:
        """Show or hide an object by name. hide_viewport hides it in the viewport,
        hide_render hides it from renders only."""
        return await _run(lambda: rt.call("set_object_visibility", name=name,
                                          hide_render=hide_render,
                                          hide_viewport=hide_viewport))
```

> `_run()` แปลง `BridgeError` → `ToolError` ให้แล้ว (กฎข้อ 3) และย้ายงานบล็อกออกจาก event loop

### ขั้น 3 — เพิ่มเทสต์ (ห้ามข้าม)

- `tests/test_bridge_logic.py` — เพิ่มส่วนทดสอบตรรกะ (ใช้ `bpy` ปลอม)
- `tests/test_mcp_e2e.py` — เพิ่มการเรียกจริงในขั้น [3]
- ⚠️ **อัปเดตจำนวนเครื่องมือที่เทสต์ล็อกไว้** — ทั้งสองไฟล์มีข้อตรวจแบบ
  `len(names) == 8` ให้แก้เป็นจำนวนใหม่ (นี่คือจุดที่คนลืมบ่อยที่สุด)
- ถ้าเครื่องมือใหม่ใช้ API ของ `bpy` ที่ `tests/fake_bpy.py` ยังไม่มี → เพิ่มในของปลอมด้วย
  (ให้เหมือนของจริงที่สุด เช่น ถ้าเปลี่ยนชื่อวัตถุ ต้องย้ายคีย์ในคอลเลกชันให้ด้วย)

### ขั้น 4 — อัปเดตเอกสาร

| ไฟล์ | แก้อะไร |
|---|---|
| `README.md` §5 | เพิ่มแถวในตารางเครื่องมือ |
| `INSTALL.md` §7 | เพิ่มชื่อ `mcp_blender_...` ในรายการ |
| `INSTALL.th.md` §7 | เหมือนกัน (ต้องตรงกัน — กฎข้อ 8) |
| `CHANGELOG.md` | เพิ่มบรรทัดใต้ `[Unreleased]` → `### เพิ่ม (Added)` |

### ขั้น 5 — รันทุกอย่าง

```bash
bash tests/run_all.sh
python tools/build_addon_zip.py    # ถ้าแก้ไฟล์ใน blender_addon/ หรือ blender_bridge.py
```

---

## 6. ทดสอบโดยไม่มี Blender (Testing without Blender)

`tests/fake_bpy.py` เลียนแบบ `bpy` พอให้ทดสอบตรรกะได้บนเครื่องเปล่า
**หลักการสำคัญ: ของปลอมต้องเหมือนของจริงในจุดที่เทสต์ตัดสิน** เช่น

- `data.objects["ชื่อใหม่"]` **ต้องเจอทันที**หลังตั้งชื่อวัตถุใหม่ (ของจริงย้ายคีย์ให้)
- `collection.objects` ต้องมี `.link()` / `.unlink()`
- operator ต้อง **บันทึกอาร์กิวเมนต์ที่ถูกเรียก** เพื่อให้เทสต์ตรวจได้ (เช่นยืนยันว่าแปลงเป็นเรเดียนจริง)

ของปลอมที่เพี้ยนจะทำให้เทสต์ผ่าน/ไม่ผ่านด้วยเหตุผลที่ไม่จริง — เคยเกิดขึ้นแล้ว 1 ครั้ง
(ดูหัวข้อ "บทเรียน" ใน `README.md` §9)

---

## 7. แนวการเขียนโค้ด (Code style)

- **คอมเมนต์/ข้อความผู้ใช้ = ภาษาไทย** · **คำอธิบายเครื่องมือ (docstring ที่ AI อ่าน) = อังกฤษ**
- คอมเมนต์ควรอธิบาย **"ทำไม"** ไม่ใช่ "ทำอะไร" — ตัวอย่างที่ดีคือหัว `blender_bridge.py`
- ใช้ type hint ทุกฟังก์ชันใหม่ · คืนค่าเป็น dict ที่ `json.dumps` ได้เสมอ
- **ห้ามมีอักษรต่างชาติหลุด** (ซีริลลิก/กรีก/จีน/เกาหลี) — ตรวจได้ด้วยสคริปต์สแกนในรีโป
  (อีโมจิและเครื่องหมายวรรคตอนใช้ได้)
- ห้ามพึ่งพาไลบรารีภายนอกใน `blender_bridge.py` — **ต้องใช้แค่ stdlib** เพราะรันใน Blender

---

## 8. commit และ pull request

- **หนึ่ง pull request = หนึ่งเรื่อง** (อย่ารวมแก้บั๊ก + เพิ่มฟีเจอร์ + จัดฟอร์แมต)
- ข้อความ commit: บรรทัดแรกเป็น**ประโยคคำสั่งภาษาไทย** แล้วเว้นบรรทัด อธิบาย **"ทำไม"
  และหลักฐานว่าผ่าน** (ตัวอย่างที่ดีดูได้จาก `git log`)
- ระบุใน PR description: **รันอะไรมาบ้าง** และ **ยังไม่ได้ยืนยันอะไร**
  (เช่น "ทดสอบด้วย `bpy` ปลอม — ยังไม่ได้ลองกับ Blender จริง")
- อย่าเพิ่งอัปเดต `CHANGELOG.md` version — ผู้ดูแลจะตัดเวอร์ชันเอง
  (ใส่บรรทัดใน `[Unreleased]` ได้)

---

## 9. รายงานบั๊ก (Reporting bugs)

**เครื่องที่พัฒนาโปรเจกต์นี้ไม่มี Blender ติดตั้ง** — รายงานจากเครื่องที่มี Blender
จึงมีค่ามาก ขอข้อมูลนี้เพื่อให้ตามได้เร็ว:

1. ผลของ `python blender_mcp_server.py --check`
2. เวอร์ชัน Blender (`blender --version`) และระบบปฏิบัติการ
3. **ข้อความ error ตรงตัว** (คัดลอกทั้งบรรทัด ไม่ต้องแปล)
4. บันทึกท้าย ๆ: `%TEMP%\blender-mcp\server-*.log` หรือ `/tmp/blender-mcp/server-*.log`
5. ขั้นตอนที่ทำก่อนเจอปัญหา (คำสั่ง/คำสั่งของ AI ที่ใช้)

> ⚠️ ถ้าเป็น "หา Blender ไม่เจอ" ให้ลอง `--blender "<พาธเต็ม>"` ก่อน —
> โปรแกรมที่เปิดโปรเซสลูกมักถูกส่งตัวแปรสภาพแวดล้อมแบบกรอง (ไม่มี `PROGRAMFILES`/`LOCALAPPDATA`)

---

## 10. เรื่องความปลอดภัย (Security)

- **`execute_blender_script` ไม่ใช่ sandbox** และจะไม่ถูกทำให้ดูเหมือนเป็น —
  มันคือราวกันตกสำหรับความผิดพลาดที่สุจริต โค้ดที่ผ่านด่านยังแก้ฉากทั้งหมดได้
  ถ้าจะเสนอปรับด่าน **อย่าลดความชัดเจนของคำเตือน**
- พอร์ตของสะพานรับฟังเฉพาะ `127.0.0.1` และมี token สุ่ม — **ห้ามเสนอให้เปิดออกเครือข่าย**
  (โปรโตคอลไม่เข้ารหัส ใครต่อได้ก็สั่ง Blender ได้)
- ถ้าพบช่องโหว่ที่ทำให้ **ข้ามด่านได้โดยไม่ตั้งใจ** ให้เปิด issue แยก
  อย่าใส่รายละเอียดการโจมตีใน issue สาธารณะ

---

## สัญญาอนุญาต

การส่ง pull request ถือว่าคุณยินยอมให้เผยแพร่ผลงานนั้นภายใต้
[สัญญาอนุญาต MIT](LICENSE) ของโปรเจกต์นี้
