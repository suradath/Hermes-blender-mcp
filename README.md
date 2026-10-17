# LPM Blender MCP — ให้ Hermes สั่งงาน Blender 5.2 ได้

MCP Server (stdio) ที่เชื่อม **Hermes Agent** เข้ากับ **Blender 5.2 LTS** ผ่าน `bpy`
ให้ AI อ่านฉาก สร้าง/ขยับวัตถุ ใส่สี และรันสคริปต์ได้จริงจากในแชท

> 🎯 **สถานะ:** ทดสอบอัตโนมัติผ่าน **214 ข้อ (4 ชุด)** + **ยืนยันกับ Hermes ตัวจริงแล้ว**
> (`hermes mcp add` → เชื่อมต่อได้ เห็นทั้ง 8 เครื่องมือ)
> ⏳ **ยังไม่ได้ทดสอบกับ Blender จริง** — เครื่องที่พัฒนาไม่มี Blender ติดตั้ง
> (ดูหัวข้อ [ทดสอบอะไรแล้ว / ยังไม่ได้ทดสอบอะไร](#ทดสอบอะไรแล้ว--ยังไม่ได้ทดสอบอะไร))

---

## 1. ภาพรวมสถาปัตยกรรม (อ่านก่อนใช้งาน)

```
   Hermes Agent
        │  stdio (JSON-RPC)
        ▼
  blender_mcp_server.py          ← Python ของ "เครื่อง" · ใช้ mcp SDK ทางการ
        │  ├─ เปิด Blender ให้เอง (โหมด -b)
        │  └─ ซ็อกเก็ต 127.0.0.1:<พอร์ตสุ่ม> + token
        ▼
  blender_bridge.py              ← รัน "อยู่ข้างใน Blender" · stdlib ล้วน
        │  เรียก bpy บน MAIN THREAD เท่านั้น
        ▼
   Blender 5.2  (.blend ของคุณ)
```

### ทำไมต้องแยกเป็นสองโปรเซส

**เหตุผลที่ 1 — stdout ของ Blender สกปรก**
MCP สื่อสารผ่าน stdio แต่ `blender -b` พ่นข้อความต้อนรับ/บันทึกของตัวเองลง **stdout**
ตั้งแต่ก่อนสคริปต์จะได้รัน ถ้าให้ MCP server รันใน Blender เอง ไคลเอนต์จะอ่านเจอขยะ
ก่อน JSON แรก → พังทันที (ไฟล์นี้จึงยืนยันได้ว่า **stdout ว่าง 0 ไบต์** ตอนสตาร์ต)
สะพานจึงใช้ **ซ็อกเก็ต** และปล่อยให้ stdout ของ Blender เป็นแค่บันทึก

**เหตุผลที่ 2 — bpy ไม่ thread-safe**
เอกสารและรายงานบั๊กของชุมชนยืนยันตรงกัน: เรียก `bpy` จาก thread อื่นได้ **hard crash
ไม่ใช่ exception** และ **`bpy.app.timers` ไม่ทำงานในโหมด `blender -b`** ด้วย
(มี PR จริงที่แก้เรื่องนี้ — เซิร์ฟเวอร์ที่พึ่ง timer จะค้างทุกคำสั่งในโหมด headless)

การออกแบบจึงแยกเป็นสองโหมดตามที่ bpy บังคับ:

| โหมด | ใช้เมื่อ | กลไก | ไฟล์ |
|---|---|---|---|
| **main** | `blender -b` (ไม่มีหน้าต่าง) — ค่าปริยาย | วนรับงาน**บน main thread** แบบบล็อก | ไม่ต้องใช้ add-on |
| **timer** | Blender ที่เปิดหน้าต่างอยู่ | รับงานใน thread แยก → ส่งให้ main thread ผ่าน `bpy.app.timers` | `blender_addon/` |

**เหตุผลที่ 3 — ไม่ต้อง pip install อะไรลง Blender เลย**
`blender_bridge.py` ใช้แค่ stdlib ⇒ บน Windows **ไม่ต้องสิทธิ์ผู้ดูแลระบบ**
และไม่ต้องกังวลว่า wheel ที่คอมไพล์แล้ว (เช่น `pydantic-core`) จะตรงรุ่น Python
ของ Blender หรือไม่ (Blender พา Python ของตัวเองมา)

---

## 2. สิ่งที่ต้องมี

| | ต้องการ |
|---|---|
| Blender | **5.2 LTS** (ออก 14 ก.ค. 2026 · ซ่อมล่าสุด 5.2.2) — ใช้ได้ตั้งแต่ 4.0 ขึ้นไป |
| Python | 3.10 ขึ้นไป (ทดสอบกับ 3.12 / 3.14) — **เป็น Python ของเครื่อง ไม่ใช่ของ Blender** |
| แพ็กเกจ | `mcp>=2.0,<3` (ทดสอบกับ **2.3.0**) |
| Hermes Agent | มี MCP client ในตัวอยู่แล้ว — แค่ใส่ค่าใน `~/.hermes/config.yaml` |

> ⚠️ **mcp 2.x เปลี่ยนชื่อ `FastMCP` → `MCPServer`** โค้ดนี้ใช้ API ของ 2.x
> ถ้าติดตั้ง `mcp<2` จะใช้ไม่ได้ (และโค้ดที่เขียนตามตัวอย่างเก่า ๆ บนอินเทอร์เน็ตจะพัง)

---

## 3. ติดตั้ง

### 🪟 Windows 11 (แนะนำ)

```bat
:: 1) วางโฟลเดอร์โปรเจกต์ไว้ที่ไหนก็ได้ เช่น C:\blender-mcp
::    แล้วดับเบิลคลิก (หรือรันใน cmd):
C:\blender-mcp\install-windows.bat
```

สคริปต์จะทำให้ทั้งหมด: หา Python → สร้าง `.venv` → ติดตั้ง `mcp` → **ตรวจว่าเจอ Blender ไหม**
→ พิมพ์ค่า config ให้คัดลอก

ถ้าขั้นสุดท้ายบอกว่า **"หา Blender ไม่เจอ"** ให้ระบุเอง:

```bat
C:\blender-mcp\.venv\Scripts\python.exe C:\blender-mcp\blender_mcp_server.py ^
  --check --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

### 🐧 Linux / 🍎 macOS

```bash
cd /path/to/blender-mcp
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python blender_mcp_server.py --check
```

`--check` ต้องขึ้นแบบนี้:

```
Blender: /usr/bin/blender (เจอใน PATH)
สคริปต์สะพาน: /path/to/blender-mcp/blender_bridge.py ✅
```

### ✅ ทดสอบครั้งแรก (แนะนำอย่างยิ่ง)

```bat
run-blender-mcp.bat --selftest      :: Windows
./run-blender-mcp.sh --selftest     :: Linux/macOS
```

คำสั่งนี้จะเปิด Blender จริง แล้วไล่เรียกทุกเครื่องมือให้ดูผลทีละตัว
(สร้างลูกบาศก์ → ขยับ → ใส่สี → รันสคริปต์ → ลบ) ถ้าผ่านหมด = พร้อมใช้

> `--selftest` จะ**เปิด Blender ขึ้นมาจริง**และปิดให้เองเมื่อจบ — ไม่แตะไฟล์ `.blend` ของคุณ
> (ใช้ `--factory-startup` = ฉากเริ่มต้น ไม่โหลดไฟล์เดิม)

---

## 4. ต่อเข้ากับ Hermes Agent

### ⚠️ ตรวจก่อน (กับดักที่พบบ่อยที่สุด)

Hermes ต้องมีแพ็กเกจ `mcp` ใน **Python ของตัวเอง** ไม่งั้นมันจะ
**ปิดความสามารถ MCP เงียบ ๆ** — ไม่มี error ให้เห็น แค่ไม่มีเครื่องมือขึ้นมา

```bash
python3 -c "import mcp; print('ok')"     # ถ้าล้มเหลว ต้องติดตั้ง
~/.hermes/bin/uv pip install --python "$(which python3)" mcp
```

### วิธีที่ 1 (แนะนำ) — คำสั่งเดียวจบ

Hermes มีตัวจัดการ MCP ในตัว ใช้ `hermes mcp add` แล้วมันจะเชื่อมต่อและ
**ตรวจหาเครื่องมือให้เลย**:

```powershell
# Windows 11 (PowerShell) — ⚠️ --args ต้องอยู่ "ท้ายสุด" เสมอ
hermes mcp add blender `
  --command "C:\blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 120 `
  --args C:\blender-mcp\blender_mcp_server.py
```

```bash
# Linux / macOS
hermes mcp add blender \
  --command "/path/to/blender-mcp/.venv/bin/python" \
  --connect-timeout 120 \
  --args /path/to/blender-mcp/blender_mcp_server.py
```

ผลลัพธ์ที่ได้จริง (คัดจากเครื่องที่ทดสอบ):

```
  Connecting to 'blender'...

  ✓ Connected! Found 8 tool(s) from 'blender':

    get_scene_hierarchy                      Read the active scene: collection tree, ...
    add_primitive_mesh                       Add a primitive mesh to the scene. ...
    modify_object_transform                  Move, rotate or resize an existing object ...
    get_object_details                       Full details for one object: world matrix, ...
    delete_object                            Delete an object by name. ...
    set_object_material                      Give a mesh object a simple Principled BSDF ...
    save_blend_file                          Save the current .blend. ...
    execute_blender_script                   Run raw bpy Python inside Blender ...

  Enable all 8 tools? [Y/n/select]:
  ✓ Saved 'blender' to ~/.hermes/config.yaml (8/8 tools enabled)
  Start a new session to use these tools, or run /reload-mcp to load them into open sessions.
```

ตรวจทีหลังด้วย:

```bash
hermes mcp list          # ดูรายการ + สถานะ
hermes mcp test blender  # → ✓ Connected (1950ms) · ✓ Tools discovered: 8
hermes mcp remove blender
```

### ⚠️ บทเรียนจริง: `--args` ต้องอยู่ท้ายสุด

รอบแรกที่ทดสอบ ใส่ `--connect-timeout` ต่อจาก `--args` → มันถูกกลืนเป็น
**อาร์กิวเมนต์ของเซิร์ฟเวอร์** → เซิร์ฟเวอร์ออกทันที → Hermes รายงานแค่
`✗ Failed to connect: Connection closed` ซึ่งชี้ทางผิดไปไกล
**วาง `--connect-timeout` ไว้ก่อน `--args`**

### เปิดไฟล์ `.blend` ของคุณตั้งแต่ต้น

```powershell
hermes mcp add blender --command "..." --connect-timeout 120 `
  --args C:\blender-mcp\blender_mcp_server.py --blend-file "C:\งาน\บ้าน.blend"
```

### วิธีที่ 2 — แก้ `~/.hermes/config.yaml` เอง

รูปแบบนี้คือสิ่งที่ Hermes เขียนจริง (คัดจากไฟล์หลังรัน `hermes mcp add`):

```yaml
mcp_servers:
  blender:
    command: C:\blender-mcp\.venv\Scripts\python.exe
    args:
      - C:\blender-mcp\blender_mcp_server.py
    connect_timeout: 120.0
    enabled: true
    timeout: 300            # เพิ่มเอง — งาน 3D ใช้เวลาได้ (ค่าปริยาย 120)
```

| คีย์ | ค่าที่แนะนำ | เพราะ |
|---|---|---|
| `connect_timeout` | **120** | Blender ใช้เวลาหลายวินาทีเปิดตัว |
| `timeout` | **300** | สคริปต์/เรนเดอร์ใช้เวลาได้ |
| `env` | ปกติไม่ต้องใส่ | Hermes กรอง env — โค้ดมีค่าเริ่มต้นมาตรฐานเป็นทางถอยแล้ว |

> 📄 **รายละเอียดเต็ม** (รวมเรื่องตัวแปรสภาพแวดล้อมที่ Hermes กรอง,
> รูปแบบ JSON `mcpServers` สำหรับไคลเอนต์อื่น, และตารางแก้ปัญหา)
> อยู่ใน [`docs/02-Hermes-config.md`](docs/02-Hermes-config.md)

### 🅱️ โหมดมีหน้าต่าง (attach) — เห็นภาพขณะ AI ทำ

ติดตั้ง add-on (ดู [`docs/01-ติดตั้ง-Windows11.md`](docs/01-ติดตั้ง-Windows11.md)
หัวข้อสุดท้าย) → กด **"เริ่มสะพาน"** ในแผง `View3D > Sidebar (N) > Blender MCP`
→ แล้วสั่ง Hermes ให้ใช้ `--attach`:

```bash
hermes mcp add blender --command "..." --connect-timeout 60 \
  --args blender_mcp_server.py --attach 127.0.0.1:9876 --token "วาง_TOKEN_จากแผง"
```

### ✔️ เรียกใช้จริง

เริ่มเซสชันใหม่ (หรือ `/reload-mcp`) แล้วเครื่องมือจะขึ้นชื่อว่า
`mcp_blender_get_scene_hierarchy`, `mcp_blender_add_primitive_mesh`, … (8 ตัว)

ลองสั่งเป็นภาษาธรรมชาติ:

> "ใช้ Blender สร้างลูกบาศก์ที่ (0,0,3) ย่อครึ่งหนึ่ง ใส่สีแดง แล้วบอกว่าฉากมีอะไรบ้าง"

---

## 5. เครื่องมือทั้งหมด (8) + ทรัพยากร (2)

### เครื่องมือ

| เครื่องมือ | ทำอะไร | พารามิเตอร์สำคัญ |
|---|---|---|
| `get_scene_hierarchy` | อ่านฉากทั้งหมด: คอลเลกชัน + วัตถุ + transform + จำนวนจุดยอด | `include_hidden`, `name_filter`, `max_objects` |
| `add_primitive_mesh` | สร้างรูปทรงพื้นฐาน | `primitive` (cube/sphere/cylinder/plane/cone/torus/monkey/circle/grid/ico_sphere), `name`, `location`, `rotation`(องศา), `scale`, `radius`, `size`, `collection` |
| `modify_object_transform` | ขยับ/หมุน/ย่อขยายวัตถุตามชื่อ | `name`, `location`, `rotation`(องศา), `scale`, `relative`, `rotation_mode` |
| `execute_blender_script` | รันโค้ด `bpy` ดิบ (มีด่านตรวจ) | `code`, `allow_unsafe`, `return_variables` |
| `get_object_details` | รายละเอียดวัตถุชิ้นเดียว (matrix_world, modifiers, materials, custom props) | `name` |
| `delete_object` | ลบวัตถุ (มีสลักกันลบพลาด) | `name`, `confirm` |
| `set_object_material` | ใส่วัสดุ Principled BSDF สีง่าย ๆ | `name`, `color`, `metallic`, `roughness`, `alpha` |
| `save_blend_file` | บันทึกไฟล์ `.blend` | `filepath` |

### ทรัพยากร

| URI | เนื้อหา |
|---|---|
| `blender://file/metadata` | ที่อยู่ไฟล์ · render engine · เฟรมปัจจุบัน/ช่วง · ความละเอียด · จำนวนของในไฟล์ |
| `blender://scene/hierarchy` | ลำดับชั้นของฉากทั้งก้อน (JSON) |

> **หน่วยหมุนเป็น "องศา"** ในทุกเครื่องมือ (AI ถนัดองศา) แต่ `bpy` เก็บเป็นเรเดียน —
> โค้ดแปลงให้แล้ว และเทสต์ล็อกไว้ว่าต้องแปลงจริง

---

## 6. ⚠️ ความปลอดภัยของ `execute_blender_script` — อ่านตรงนี้

**มันคือ "ราวกันตก" ไม่ใช่ "กรงขัง"** — พูดตรง ๆ ว่า:

✅ **ด่านที่กันได้จริง** (ตรวจก่อนรันด้วย AST ไม่ใช่จับสตริง):

| กันอะไร | ตัวอย่างที่ถูกปฏิเสธ |
|---|---|
| import โมดูลอันตราย | `import os`, `subprocess`, `sys`, `socket`, `ctypes`, `importlib`, `pickle`, `shutil`, `pathlib` … |
| ฟังก์ชันในตัวอันตราย | `open()`, `eval()`, `exec()`, `compile()`, `__import__`, `getattr/setattr`, `globals/locals` … |
| ทางหลบหนีคลาสสิก | `(1).__class__.__bases__[0].__subclasses__()` (ห้าม attribute `__xx__`) |
| operator ที่ทำลายงาน | `bpy.ops.wm.quit_blender` (ปิด Blender ทิ้งงาน), `wm.read_homefile`, `wm.read_factory_settings` |

⚠️ **สิ่งที่ "กันไม่ได้"** — และเราไม่แอบอ้างว่ากันได้:
นี่ไม่ใช่ sandbox ระดับ OS กระบวนการนี้รันด้วยสิทธิ์เดียวกับ Blender ของคุณ
โค้ดที่ผ่านด่านยัง**แก้ฉากทั้งหมดได้ ลบวัตถุได้ บันทึกทับไฟล์ได้**
ถ้าไม่ไว้ใจผู้สั่ง **อย่าเปิด `allow_unsafe=true`** และ **บันทึกไฟล์ก่อน** ให้เป็นนิสัย

การออกแบบที่ลดความเสี่ยง: `delete_object` มีสลัก `confirm=false` เป็นค่าปริยาย ·
`save_blend_file` ไม่บันทึกทับเองถ้าไม่ได้สั่ง · และทุกข้อความ error เป็นภาษาไทยที่ AI อ่านรู้เรื่อง

---

## 7. แก้ปัญหา

| อาการ | สาเหตุ / ทางแก้ |
|---|---|
| `หา Blender ไม่เจอ` | ใช้ `--blender "พาธเต็ม"` หรือตั้ง `BLENDER_EXE` (Hermes กรอง env ออก — ส่งผ่าน `env:` ใน config ด้วยก็ได้) |
| `Blender ไม่พร้อมภายใน 90 วินาที` | เปิดเองเพื่อดูข้อผิดพลาดจริง: `blender -b --python blender_bridge.py -- --port 0 --selftest` แล้วดูบันทึกท้าย ๆ ที่เซิร์ฟเวอร์แนบมาให้ |
| Hermes ขึ้น "Failed to connect to MCP server 'blender'" | `connect_timeout` สั้นเกินไป — ตั้งเป็น 120 (Blender ใช้เวลาหลายวินาที) |
| เครื่องมือขึ้นแต่เรียกแล้วเงียบ | ดูบันทึกที่ `/tmp/blender-mcp/server-*.log` (Windows: `%TEMP%\blender-mcp\`) |
| `ต่อสะพานไม่สำเร็จ` | โหมด attach: ตรวจว่าใน Blender กด "เริ่มสะพาน" แล้ว และ token ตรงกัน |
| คำสั่งถูกปฏิเสธด้วยข้อความ "ฝ่าด่านความปลอดภัย" | เป็นไปตามการออกแบบ — ถ้าตั้งใจจริงส่ง `allow_unsafe=true` |
| งานค้างนาน (เช่น ลูปยาว/เรนเดอร์) | หมดเวลาตาม `timeout` — **Blender ไม่ถูกสั่งหยุดกลางคัน** (bpy หยุดกลางคันไม่ได้) จะทำงานต่อจนจบ |
| รันแล้วไม่มีอะไรเกิดขึ้นในหน้าต่าง cmd | ปกติ — มันรอคำสั่ง JSON-RPC ทาง stdin ให้ Hermes เรียก |

---

## 8. ทดสอบ

```bash
bash tests/run_all.sh
```

| ชุดทดสอบ | ตรวจอะไร | จำนวน |
|---|---|---|
| `test_addon_structure.py` | โครง add-on ตามที่ Blender ต้องการ + ลง timer บน main thread | 34 |
| `test_server_utils.py` | ค้นหา Blender (รวมกรณี Hermes กรอง env) · CLI · ตัดพารามิเตอร์ None | 33 |
| `test_bridge_logic.py` | ตรรกะทุกเครื่องมือ + ด่านความปลอดภัย (ใช้ `bpy` ปลอม) | 103 |
| `test_mcp_e2e.py` | **ครบวงจรจริง**: MCP client ทางการ ⇄ เซิร์ฟเวอร์ ⇄ สะพาน | 44 |

**รวม 214 ข้อ** ทดสอบด้วยของจริงทุกชั้น ยกเว้นตัว Blender (ใช้ `tests/fake_bpy.py`)

### ทดสอบอะไรแล้ว / ยังไม่ได้ทดสอบอะไร

| | สถานะ |
|---|---|
| ⭐ **Hermes ตัวจริงเชื่อมต่อได้** — `hermes mcp add` → `✓ Connected! Found 8 tool(s)` · `hermes mcp test` → `✓ Connected (1950ms) · ✓ Tools discovered: 8` | ✅ **ยืนยันแล้ว** (ด้วยสะพานจำลอง เพราะเครื่องนี้ไม่มี Blender) |
| สื่อสาร MCP (handshake, tool list, สคีมา, เรียกใช้, resource, error) | ✅ ทดสอบด้วย MCP client ทางการ (44 ข้อ) |
| โปรโตคอลสะพาน (token, JSON บรรทัดละคำขอ, ข้อผิดพลาด, ตอบไม่ถูกต้อง) | ✅ ทดสอบผ่านซ็อกเก็ตจริง |
| ตรรกะ bpy ทุกเครื่องมือ (สร้าง/ขยับ/ลบ/วัสดุ/รันสคริปต์/ด่านตรวจ) | ✅ ทดสอบกับ `bpy` ปลอมที่เลียนแบบของจริง (103 ข้อ) |
| stdout สะอาด (ไม่มีอะไรเลอะท่อ JSON-RPC) | ✅ ยืนยัน 0 ไบต์ |
| **การเปิด/ปิด Blender จริง** (โดยเฉพาะบน Windows 11) | ❌ **ต้องมี Blender** → ใช้ `--selftest` ยืนยัน |
| **การเรนเดอร์ · UI · `bpy.app.timers` ของจริง** | ❌ **ต้องมี Blender** |

> เครื่องที่พัฒนาไม่มี Blender ติดตั้ง จึงทดสอบได้ถึงชั้น "โปรโตคอล + ตรรกะ + การเชื่อมกับ Hermes"
> ส่วนชั้น Blender จริงใช้ `--selftest` ยืนยันได้ในคำสั่งเดียว (ดู [`docs/01`](docs/01-ติดตั้ง-Windows11.md) ขั้นที่ 3)

---

## 9. บทเรียนจากการพัฒนา (บั๊กจริงที่เทสต์จับได้)

บันทึกไว้เพราะเป็นกับดักที่คนอื่นจะเจอเหมือนกัน — ไม่ใช่รายงานความสำเร็จ

| # | บั๊ก | อาการที่เห็น | ต้นเหตุจริง |
|---|---|---|---|
| 1 | `conn._bridge_file = f` ในสะพาน | **ทุกการเชื่อมต่อถูกปฏิเสธเงียบ ๆ** → MCP server วนลอง 90 วินาทีแล้วค้าง | `socket.socket` นิยาม `__slots__` → กำหนด attribute ใหม่ไม่ได้ แล้ว `except` กวาดความผิดพลาดทิ้ง |
| 2 | ปล่อย exception ธรรมดาในเครื่องมือ | AI เห็นแค่ `Error executing tool X` **ไม่รู้ว่าทำไมผิด** | SDK **กลืนข้อความ** ของ exception ต้องโยน `mcp.server.mcpserver.exceptions.ToolError` เท่านั้นจึงจะถึงไคลเอนต์ |
| 3 | `allow_unsafe=true` | ยังถูกบล็อก `import os` อยู่ดี | ด่านอยู่ **สองที่** (ตรวจ AST + `__import__` ที่ถูกแทน) แต่ปลดล็อกแค่ที่เดียว |
| 4 | `bpy` ปลอม: เปลี่ยนชื่อวัตถุแล้วคีย์ไม่ย้าย | เทสต์หา `bpy.data.objects["ชื่อใหม่"]` ไม่เจอ | ของจริงย้ายคีย์ให้ — ของปลอมต้องทำเหมือนกัน ไม่งั้นเทสต์ตัดสินผิด |

> 📌 ข้อ 2 สำคัญที่สุดต่อประสบการณ์ใช้งาน: ถ้าไม่แก้ AI จะเดาสาเหตุผิดไปเรื่อย ๆ
> เพราะไม่มีข้อมูลอะไรเลย และข้อ 1 คือกรณีที่ "เทสต์ผ่านแต่ของจริงพัง" ถ้าไม่ทดสอบแบบ end-to-end

---

## 10. แผนผังไฟล์

```
blender-mcp/
├── blender_mcp_server.py     ← MCP server (รันด้วย Python ของเครื่อง · stdio)
├── blender_bridge.py         ← รันใน Blender (stdlib ล้วน · bpy บน main thread)
├── blender_addon/__init__.py ← add-on สำหรับโหมดมีหน้าต่าง (timer mode)
├── requirements.txt
├── install-windows.bat       ← ติดตั้งอัตโนมัติ (Windows 11)
├── run-blender-mcp.bat/.sh   ← ตัวเปิดเซิร์ฟเวอร์ / --check / --selftest
├── tests/
│   ├── run_all.sh            ← รันทุกชุด
│   ├── fake_bpy.py           ← bpy ปลอมสำหรับทดสอบ
│   ├── bridge_host.py        ← เปิดสะพานตัวจริงเพื่อทดสอบ e2e
│   ├── test_addon_structure.py · test_server_utils.py
│   ├── test_bridge_logic.py  · test_mcp_e2e.py
└── docs/
    ├── 01-ติดตั้ง-Windows11.md
    └── 02-Hermes-config.md
```

## 11. อ้างอิง

- Blender 5.2 LTS — ออก 14 กรกฎาคม 2026 (ซ่อมล่าสุด 5.2.2, 15 ก.ย. 2026) · `<https://developer.blender.org/docs/release_notes/5.2/>`
- MCP Python SDK 2.x — `FastMCP` เปลี่ยนชื่อเป็น `MCPServer` · `<https://py.sdk.modelcontextprotocol.io/v2/migration/>`
- เหตุผลเรื่อง `bpy.app.timers` ไม่ทำงานในโหมด `-b` — PR ของ `ahujasid/blender-mcp` #252
