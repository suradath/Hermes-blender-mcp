# Hermes Blender MCP — ให้ Hermes สั่งงาน Blender 5.2 ได้

MCP Server (stdio) ที่เชื่อม **Hermes Agent** เข้ากับ **Blender 5.2 LTS** ผ่าน `bpy`
ให้ AI อ่านฉาก สร้าง/ขยับวัตถุ ใส่สี และรันสคริปต์ได้จริงจากในแชท

> 🎯 **สถานะ:** ทดสอบอัตโนมัติผ่าน **756 ข้อ (10 ชุด)** + **ยืนยันกับ Hermes ตัวจริงแล้ว**
> (`hermes mcp add` → เชื่อมต่อได้ เห็นทั้ง 12 เครื่องมือ)
> ✅ **ทดสอบกับ Blender จริงแล้ว** — Windows 11 + Blender 5.2.2 (`--selftest` ผ่านครบหลังแก้ v1.0.1)
> เครื่องที่ใช้พัฒนาไม่มี Blender จึงพึ่งเทสต์จำลองเป็นหลัก — รายละเอียดใน
> [ทดสอบอะไรแล้ว / ยังไม่ได้ทดสอบอะไร](#ทดสอบอะไรแล้ว--ยังไม่ได้ทดสอบอะไร)

> 📖 **ติดตั้ง:** [คู่มือภาษาไทย (INSTALL.th.md)](INSTALL.th.md) ·
> [English (INSTALL.md)](INSTALL.md) — ครอบคลุม Windows 11, Linux และ macOS
> 🤝 **ร่วมพัฒนา:** [CONTRIBUTING.md](CONTRIBUTING.md) · 📋 **ประวัติเวอร์ชัน:** [CHANGELOG.md](CHANGELOG.md)
> ⚖️ สัญญาอนุญาต [MIT](LICENSE) (เปลี่ยนได้ตามต้องการ)

![บ้านทรงไทยโพลิกอนที่สร้างจากเรขาคณิตของโปรเจกต์](docs/images/05-thai-house-3q.png)

*🏠 **บ้านทรงไทยโพลิกอน** — 88 ชิ้น สร้างจากเรขาคณิตจริง (ไม่ได้ปั้นมือ · ไม่ได้ใช้ภาพจาก AI)
เสายกพื้น · หลังคาซ้อนชั้นชัน 40.6° · หน้าบัน · ป้านลม · ช่อฟ้าโค้ง · ระเบียง · บันได
— [ดูในคู่มือ §10](docs/03-สร้างตัวละครจากรูป.md#10-ตัวอย่างที่-2-บ้านทรงไทยสไตล์โพลิกอน)*

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
:: 1) วางโฟลเดอร์โปรเจกต์ไว้ที่ไหนก็ได้ เช่น C:\Hermes-blender-mcp
::    แล้วดับเบิลคลิก (หรือรันใน cmd):
C:\Hermes-blender-mcp\install-windows.bat
```

สคริปต์จะทำให้ทั้งหมด: หา Python → สร้าง `.venv` → ติดตั้ง `mcp` → **ตรวจว่าเจอ Blender ไหม**
→ พิมพ์ค่า config ให้คัดลอก

ถ้าขั้นสุดท้ายบอกว่า **"หา Blender ไม่เจอ"** ให้ระบุเอง:

```bat
C:\Hermes-blender-mcp\.venv\Scripts\python.exe C:\Hermes-blender-mcp\blender_mcp_server.py ^
  --check --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

### 🐧 Linux / 🍎 macOS

```bash
cd /path/to/Hermes-blender-mcp
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python blender_mcp_server.py --check
```

`--check` ต้องขึ้นแบบนี้:

```
Blender: /usr/bin/blender (เจอใน PATH)
สคริปต์สะพาน: /path/to/Hermes-blender-mcp/blender_bridge.py ✅
```

### ✅ ทดสอบครั้งแรก (แนะนำอย่างยิ่ง)

```bat
run-hermes-blender-mcp.bat --selftest      :: Windows
./run-hermes-blender-mcp.sh --selftest     :: Linux/macOS
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
  --command "C:\Hermes-blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 120 `
  --args C:\Hermes-blender-mcp\blender_mcp_server.py
```

```bash
# Linux / macOS
hermes mcp add blender \
  --command "/path/to/Hermes-blender-mcp/.venv/bin/python" \
  --connect-timeout 120 \
  --args /path/to/Hermes-blender-mcp/blender_mcp_server.py
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
  --args C:\Hermes-blender-mcp\blender_mcp_server.py --blend-file "C:\งาน\บ้าน.blend"
```

### วิธีที่ 2 — แก้ `~/.hermes/config.yaml` เอง

รูปแบบนี้คือสิ่งที่ Hermes เขียนจริง (คัดจากไฟล์หลังรัน `hermes mcp add`):

```yaml
mcp_servers:
  blender:
    command: C:\Hermes-blender-mcp\.venv\Scripts\python.exe
    args:
      - C:\Hermes-blender-mcp\blender_mcp_server.py
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

## 5. เครื่องมือทั้งหมด (12) + ทรัพยากร (2)

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
| **`get_viewport_screenshot`** | **เรนเดอร์ภาพให้ AI "เห็น" ฉาก — คืนเป็นรูปจริง + ข้อมูลกำกับ** | `filepath`, `width`, `height`, `mode` (auto/render/viewport), `camera` |

| **`search_polyhaven`** | **ค้นคลัง CC0 ของฟรี (HDRI/เท็กซ์เจอร์/โมเดล) — ไม่ต้องใช้คีย์** | `query`, `asset_type` (hdris/textures/models), `categories`, `limit` |
| **`get_polyhaven_info`** | **ดูว่าของชิ้นนั้นมีรูปแบบ/ความละเอียดอะไร ก่อนโหลด** | `asset_id` |
| **`download_polyhaven_asset`** | **โหลดของ + ไฟล์เท็กซ์เจอร์ที่ต้องใช้ แล้วใส่เข้าฉากให้เลย** | `asset_id`, `kind`, `resolution`, `apply`, `target_dir`, `max_mb`, `texture_map` |

> 🆓 **คลังของฟรีที่ไม่ต้องใช้คีย์** — [Poly Haven](https://polyhaven.com) เป็น **CC0 (public domain)**
> ใช้เชิงพาณิชย์ได้ ไม่ต้องอ้างอิงที่มา ไม่ต้องสมัคร ไม่ต้องมี API key · มีทั้ง HDRI สำหรับให้แสง
> แผนที่พื้นผิว PBR และโมเดลสำเร็จรูป (เก้าอี้/ถัง/ต้นไม้…)
> · `download_…` ดึง **ไฟล์เท็กซ์เจอร์ที่ต้องใช้คู่กัน** มาด้วย และวางตามพาธสัมพัทธ์เดิม
> เพื่อให้โมเดลอ้างถึงได้ · ไฟล์ถูกแคชไว้ เรียกซ้ำไม่โหลดใหม่
> · เลือก `resolution` ต่ำ (`1k`/`2k`) ก่อนเสมอ — 4k ขึ้นไปไฟล์ละหลายร้อย MB (มี `max_mb` กันพลาด)
> · ทดสอบกับ API จริงในชุดทดสอบ (ข้ามเองถ้าเครือข่ายไม่พร้อม — ซื่อสัตย์กว่าแอบผ่าน)

> 🧍 **สร้างตัวละคร 3D จากรูปที่แนบมาได้ไหม?** ได้ — แต่ต้องเข้าใจขอบเขต:
> Hermes ดูรูป → ประเมินสัดส่วน/สี → สร้าง **blockout** ลงฉาก → ถ่ายภาพกลับมาดู → ปรับวนซ้ำ
> (ดู [คู่มือ](docs/03-สร้างตัวละครจากรูป.md) · [ตัวอย่างที่รันได้](examples/character_blockout.py))
> ส่วน **ปั้นละเอียดจากรูปอัตโนมัติ (image-to-3D) ไม่มีในตัว** เพราะต้องใช้บริการภายนอกที่มีคีย์
> — โปรเจกต์นี้เลือกไม่ผูกกับคีย์ เอกสารจึงบอกตรง ๆ ว่าอะไรทำได้/ทำไม่ได้

![เทียบรูปต้นแบบกับโมเดลที่สร้างจากเรขาคณิตเอง](docs/images/04-compare.png)

*ซ้าย = รูปต้นแบบ · กลาง/ขวา = โมเดล 27 ชิ้นที่สร้างจากเรขาคณิตของโปรเจกต์
(เรนเดอร์ด้วย `tools/render_flat.py` · ยังไม่ได้ใช้ Blender) —
รายละเอียดอยู่ใน [คู่มือ §7–§8](docs/03-สร้างตัวละครจากรูป.md)*

🏠 **ตัวอย่างที่ 2 — สถาปัตยกรรม:** [`tools/thai_house_builder.py`](tools/thai_house_builder.py)
สร้าง **บ้านทรงไทยโพลิกอน** 88 ชิ้น (เสายกพื้น · หลังคาช้อน 2 ชั้นชัน 40.6° · หน้าบัน ·
ป้านลม · ช่อฟ้าโค้ง · ระเบียง · บันได) ทุกชิ้นปิดสนิท — ดู [คู่มือ §10](docs/03-สร้างตัวละครจากรูป.md#10-ตัวอย่างที่-2-บ้านทรงไทยสไตล์โพลิกอน)
· ตัวอย่างเพิ่มเติม: 🌳 ต้นไม้ [`tree_builder.py`](tools/tree_builder.py) · 🐕 สุนัข [`dog_builder.py`](tools/dog_builder.py)
— ดู [คู่มือ §11](docs/03-สร้างตัวละครจากรูป.md#11-ตัวอย่างที่-34-ต้นไม้-และ-สุนัข-แยกไฟล์)
· 🏘️ ภาพหมู่ทั้งฉาก [`scene_builder.py`](tools/scene_builder.py) — [คู่มือ §12](docs/03-สร้างตัวละครจากรูป.md#12-ภาพหมู่-ประกอบทุกอย่างเป็นฉากเดียว)

> 🖼️ **AI เห็นภาพได้** — `get_viewport_screenshot` ส่งกลับเป็น **content block ชนิด `image`**
> ไม่ใช่แค่ชื่อไฟล์ พร้อมบล็อกข้อความบอกโหมด/กล้อง/ความละเอียด/เวลา
> โหมด `render` ใช้ได้ทุกที่รวมถึง `-b` (เรนเดอร์จากกล้อง) · โหมด `viewport` ต้องมีหน้าต่าง Blender
> ค่าตั้งการเรนเดอร์ของผู้ใช้ถูก**คืนกลับเสมอ**หลังถ่ายภาพ · ไฟล์ปริยายอยู่ในโฟลเดอร์ชั่วคราว

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
| เครื่องมือขึ้นแต่เรียกแล้วเงียบ | ดูบันทึกที่ `/tmp/Hermes-blender-mcp/server-*.log` (Windows: `%TEMP%\Hermes-blender-mcp\`) |
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
| `test_addon_structure.py` | โครง add-on + ตัวสร้าง zip + การเปิดสะพานอัตโนมัติ | 56 |
| `test_docs_links.py` | ลิงก์/anchor ทุกไฟล์ · เอกสาร 2 ภาษาตรงกัน · **ไม่มีอักษรต่างชาติหลุด** · การเทียบโครงการอื่น · **รูปประกอบมีจริงและเป็น PNG ที่สมบูรณ์** | 143 |
| `test_example_character.py` | **ตัวอย่างสร้างตัวละคร**: ผ่านด่านความปลอดภัย · รันจริงในฉากจำลอง · **สัดส่วนที่ให้ไปถูกใช้จริง** · **ตัวละครจากรูปจริง (T-pose) เทียบกับที่วัดจากพิกเซล** · เอกสารซื่อสัตย์ | 68 |
| `test_scene.py` | **ฉากภาพหมู่**: เมชยังสมบูรณ์หลังย้าย/หมุน/ย่อ · ทุกชิ้นยืนบนพื้น · **ไม่มีของทับกัน (AABB ทุกคู่)** · อยู่ในขอบแผ่นดิน · แผ่นดินแผ่นเดียว | 35 |
| `test_tree_dog.py` | **ต้นไม้ + สุนัข**: เสา/ขาแตะพื้น · พุ่มซ้อนลำต้น · กิ่งยื่นพ้น · หัว-ปาก-จมูกเรียงถูก · **ตาพ้นความกว้างปาก** · สมมาตร | 47 |
| `test_thai_house.py` | **บ้านทรงไทย**: ทุกชิ้นปิดสนิท · **ระดับชั้นต่อกันจริง** (เสา→พื้น→ฝา→หลังคา→สัน) · ช่อฟ้านั่งบนสันและโค้งจริง · หลังคาชัน ≥ 35° · บันไดไล่ถึงพื้น · ราวไม่ทับบันได (AABB) | 65 |
| `test_mesh_lib.py` | **เมชละเอียด**: ทุกชิ้นปิดสนิท/ออยเลอร์ = 2/ปริมาตรตรงสูตร · สัดส่วนตรงกับที่วัดจากรูป · ขา-เท้าไม่ทับกัน · มือไม่ใหญ่กว่าแขน · `.obj` อ่านได้ · สคริปต์ฝั่ง Blender ผ่านด่าน | 67 |
| `test_server_utils.py` | ค้นหา Blender (รวม Hermes กรอง env) · CLI · **อดทนต่ออาร์กิวเมนต์แปลก** · **ติดตั้ง add-on ให้เอง** · ตรวจโปรโตคอล | 58 |
| `test_bridge_logic.py` | ตรรกะทุกเครื่องมือ + ด่านความปลอดภัย + การถ่ายภาพ + **คลัง Poly Haven (จำลองเครือข่าย)** + **ยิง API จริง** | 161 |
| `test_mcp_e2e.py` | **ครบวงจรจริง**: MCP client ทางการ ⇄ เซิร์ฟเวอร์ ⇄ สะพาน (รวม**รูปส่งถึงไคลเอนต์จริง**) | 56 |

**รวม 756 ข้อ** ทดสอบด้วยของจริงทุกชั้น ยกเว้นตัว Blender (ใช้ `tests/fake_bpy.py`)

### ทดสอบอะไรแล้ว / ยังไม่ได้ทดสอบอะไร

| | สถานะ |
|---|---|
| ⭐ **รันบน Blender จริง** — Windows 11 + Blender 5.2.2 · `--selftest` รอบแรก (v1.0.0) **ผ่าน 8/9** และจับบั๊ก `Collection.parent` ได้จริง → แก้ใน v1.0.1 (รอตรวจซ้ำบนเครื่องนั้น) | ✅ **ยืนยันบางส่วน** |
| ⭐ **Hermes ตัวจริงเชื่อมต่อได้** — `hermes mcp add` → `✓ Connected! Found 12 tool(s)` · `hermes mcp test` → `✓ Connected (1950ms) · ✓ Tools discovered: 12` | ✅ **ยืนยันแล้ว** (ด้วยสะพานจำลอง เพราะเครื่องนี้ไม่มี Blender) |
| สื่อสาร MCP (handshake, tool list, สคีมา, เรียกใช้, resource, error) | ✅ ทดสอบด้วย MCP client ทางการ (56 ข้อ) |
| ลิงก์ในเอกสารไม่เสีย (ปัญหาที่พบบ่อยสุดของรีโปสาธารณะ) | ✅ ตรวจทุก push — 56 ลิงก์ใน 8 ไฟล์ |
| โปรโตคอลสะพาน (token, JSON บรรทัดละคำขอ, ข้อผิดพลาด, ตอบไม่ถูกต้อง) | ✅ ทดสอบผ่านซ็อกเก็ตจริง |
| ตรรกะ bpy ทุกเครื่องมือ (สร้าง/ขยับ/ลบ/วัสดุ/รันสคริปต์/ด่านตรวจ/คลังของฟรี) | ✅ ทดสอบกับ `bpy` ปลอมที่เลียนแบบของจริง (161 ข้อ) |
| stdout สะอาด (ไม่มีอะไรเลอะท่อ JSON-RPC) | ✅ ยืนยัน 0 ไบต์ |
| **การเปิด/ปิด Blender จริง** (โดยเฉพาะบน Windows 11) | ❌ **ต้องมี Blender** → ใช้ `--selftest` ยืนยัน |
| **การเรนเดอร์ · UI · `bpy.app.timers` ของจริง** | ❌ **ต้องมี Blender** |
| **การยิง API จริงของ Poly Haven** | ✅ ทดสอบแล้ว (ค้น "chair" เจอจริง) — ข้ามเองถ้าเครือข่ายไม่พร้อม |

> เครื่องที่พัฒนาไม่มี Blender ติดตั้ง จึงทดสอบได้ถึงชั้น "โปรโตคอล + ตรรกะ + การเชื่อมกับ Hermes"
> ส่วนชั้น `bpy` ตรวจด้วย `--selftest` บนเครื่องที่มี Blender — รอบแรก (v1.0.0) จับบั๊กได้ 1 ตัว
> (`Collection` ไม่มี `.parent`) ซึ่งเทสต์จำลองมองไม่เห็นเพราะ `fake_bpy` เติม attribute นี้ให้เอง
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
Hermes-blender-mcp/
├── README.md                 ← ภาพรวมสถาปัตยกรรม + เครื่องมือ + บทเรียน
├── INSTALL.md                ← คู่มือติดตั้ง (อังกฤษ)
├── INSTALL.th.md             ← คู่มือติดตั้ง (ไทย)
├── CONTRIBUTING.md           ← วิธีร่วมพัฒนา (กฎที่โปรเจกต์บังคับ · สูตรเพิ่มเครื่องมือ)
├── CHANGELOG.md              ← บันทึกการเปลี่ยนแปลงทุกรุ่น
├── LICENSE                   ← MIT
├── blender_mcp_server.py     ← MCP server (รันด้วย Python ของเครื่อง · stdio)
├── blender_bridge.py         ← รันใน Blender (stdlib ล้วน · bpy บน main thread)
├── blender_addon/__init__.py ← add-on สำหรับโหมดมีหน้าต่าง (timer mode)
├── requirements.txt
├── install-windows.bat       ← ติดตั้งอัตโนมัติ (Windows 11)
├── run-hermes-blender-mcp.bat/.sh   ← ตัวเปิดเซิร์ฟเวอร์ / --check / --selftest
├── tools/
│   ├── build_addon_zip.py    ← สร้าง zip สำหรับติดตั้ง add-on (Install from Disk)
│   ├── preview_blockout.py   ← วาดผัง blockout เทียบรูปต้นแบบ (ต้องมี Pillow · dev-only)
│   ├── mesh_lib.py           ← เครื่องยนต์เมช (ลบมุม/แท่งสอบ/ตรวจความสมบูรณ์) stdlib ล้วน
│   ├── character_builder.py  ← ประกอบตัวละครละเอียด 27 ชิ้น → .obj/.mtl
│   ├── thai_house_builder.py ← บ้านทรงไทยโพลิกอน 88 ชิ้น (หลังคาช้อน · ช่อฟ้าโค้ง · ระเบียง · บันได)
│   ├── tree_builder.py       ← ต้นไม้โพลิกอน (โคนบาน · กิ่ง · พุ่ม 9 ก้อน)
│   ├── dog_builder.py        ← สุนัขโพลิกอน (4 ขา · ปากเรียว · หู · หาง · ปลอกคอ)
│   └── scene_builder.py      ← ประกอบทุกอย่างเป็นฉากเดียว (ภาพหมู่) → .obj + เรนเดอร์
│   └── render_flat.py        ← เรนเดอร์ระนาบสีเรียบเอง (Pillow · dev-only)
├── examples/
│   ├── character_blockout.py ← ตัวอย่างสร้างตัวละคร 3D จากสเปกที่ AI อ่านจากรูป
│   └── detail_character_in_blender.py ← นำเข้า .obj + Bevel/Subdiv/Smooth ใน Blender
├── docs/
│   ├── images/               ← รูปประกอบในคู่มือ (ภาพเทียบต้นแบบ/โมเดล/ผัง blockout)
│   ├── 01-ติดตั้ง-Windows11.md
│   ├── 02-Hermes-config.md
│   ├── 03-สร้างตัวละครจากรูป.md
│   └── 04-GitHub-repo-setup.md ← ข้อความ Description/Topics พร้อมใช้ตอน publish ← ตอบคำถาม "แนบรูปแล้วสร้างตามแบบได้ไหม"
├── .github/workflows/tests.yml ← รันชุดทดสอบบน GitHub อัตโนมัติ
├── .gitattributes            ← บังคับ CRLF/LF ให้ .bat/.sh ไม่พังข้ามระบบ
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

## 10.1 การพัฒนา (Contributing)

```bash
bash tests/run_all.sh                      # ชุดทดสอบทั้งหมด (ไม่ต้องมี Blender)
python tools/build_addon_zip.py            # สร้าง zip ของ add-on
python blender_mcp_server.py --list-tools  # ดูรายการเครื่องมือ
```

ทุก push จะรันชุดทดสอบบน GitHub อัตโนมัติ
([`.github/workflows/tests.yml`](.github/workflows/tests.yml)) ทั้ง Python 3.10 และ 3.12
พร้อมตรวจว่า stdout ว่างตอนสตาร์ต (กันท่อ JSON-RPC ถูกทำให้สกปรกโดยไม่ตั้งใจ)

> 💡 หลังอัปขึ้น GitHub แล้ว ใส่ป้ายสถานะใน README ได้ด้วยบรรทัดนี้ (แทนที่ `<OWNER>/<REPO>`):
> `[![tests](https://github.com/<OWNER>/<REPO>/actions/workflows/tests.yml/badge.svg)](https://github.com/<OWNER>/<REPO>/actions/workflows/tests.yml)`

---

## 11. เปรียบเทียบกับโครงการอื่นในระบบนิเวศ (ควรใช้อันไหน)

> 🔍 ตรวจเมื่อ **17 ต.ค. 2026** จากข้อมูลจริง (จำนวนดาวจากหน้ารีโป · `pyproject.toml` ·
> ซอร์ส `addon.py` · สถานะ issue/PR) — **ยังไม่ได้รันของใครเลย** เพราะเครื่องที่พัฒนาไม่มี
> Blender ติดตั้ง ตัวเลขและสถานะด้านล่างจึงเป็น "สิ่งที่อ่านจากต้นทาง" ไม่ใช่ผลทดลอง

### 🏆 ตัวที่คนใช้มากที่สุด: `ahujasid/mcp-for-blender`

| ข้อมูล | ค่า |
|---|---|
| ดาว / fork | **31,125★ · 2,843 forks** |
| สัญญาอนุญาต | MIT · เวอร์ชัน 2.1.9 · หน้าเว็บ [mcp-for-blender.com](https://www.mcp-for-blender.com/) |
| ชื่อเดิม | `ahujasid/Hermes-blender-mcp` (เปลี่ยนชื่อแล้ว — ลิงก์เก่าจะ redirect) |
| ติดตั้ง | `uvx mcp-for-blender` + ติดตั้ง add-on ใน Blender |
| MCP SDK | **ตรึง `mcp>=1.26.0,<2`** และใช้ `from mcp.server.fastmcp import FastMCP` |

**ของเขาที่เรานำมาพัฒนาแล้ว** (ดูรายการในหัวข้อ "สิ่งที่ได้เรียนรู้" ท้ายหัวข้อนี้):
ส่งภาพหน้าจอ viewport กลับให้ AI ดู ✅ · add-on เปิดสะพานเองอัตโนมัติ ✅ ·
ติดตั้ง add-on ให้เอง ✅ · ตรวจเวอร์ชันโปรโตคอล ✅ · อดทนต่ออาร์กิวเมนต์แปลก ✅

**ของเขาที่ยังดีกว่าอยู่:** คลังโมเดล (Poly Haven / Poly Pizza) ·
สร้างโมเดล 3D ช่วย AI ·
ตรวจเวอร์ชันโปรโตคอลระหว่าง add-on กับเซิร์ฟเวอร์ · telemetry · บันทึกว่าผู้ใช้แก้ไขอะไรไป ·
มี safe mode (`validate_code`) · ชุมชนใหญ่ (52 issue เปิด — มีคนตอบ)

**ข้อควรระวังที่ตรวจพบ**
- ⚠️ **โหมดไม่มีหน้าต่าง (`blender -b`) ยังมีปัญหาค้าง** — [issue #251](https://github.com/ahujasid/mcp-for-blender/issues/251)
  ("`bpy.app.timers` ไม่ทำงาน → ทุกคำสั่งค้าง") และ PR ที่เสนอแก้ **ยังเปิดอยู่ ไม่ได้ merge**
  ณ วันที่ตรวจ
- ⚠️ ตรึง `mcp<2` เพราะใช้ API v1 ที่ mcp 2.x ตัดออกแล้ว → ถ้ารันเซิร์ฟเวอร์ของเขา
  บน Python ที่มี `mcp 2.x` (เช่น env ของ Hermes) จะพัง ต้องปล่อยให้ `uvx` สร้าง env แยกให้
- ⚠️ พอร์ตคงที่ (`9876`) ไม่มี token สุ่มแบบโปรเจกต์นี้

### 📋 ทางเลือกอื่นในระบบนิเวศ

GitHub มี **508 รีโป** ที่เกี่ยวกับ "blender mcp" — ส่วนใหญ่เป็น clone/ฟอร์กของตัวข้างบน
ที่อ้างจำนวนเครื่องมือสูง ๆ ควรอ่านซอร์สก่อนเชื่อตัวเลข

| รีโป | ดาว | สัญญาอนุญาต | จุดที่อ้าง |
|---|---:|---|---|
| `RFingAdam/mcp-blender` | 24★ | AGPL-3.0 | 218 เครื่องมือ + MSFS |
| `carlosh7/Hermes-blender-mcp` | — | — | "ครบที่สุด 223 เครื่องมือ" |
| `6xvl/Hermes-blender-mcp` | — | — | ~270 เครื่องมือ |
| `jenkinsm13/better-Hermes-blender-mcp` | — | — | ระบุ "Blender 5" + agents/skills |

> 🚩 **สัญญาณเตือน:** รีโปที่อ้าง "N เครื่องมือ" แต่ดาว 0–2 หลัก มักเป็น fork ที่เปลี่ยนชื่อ
> หรือสร้างด้วย AI — ให้ดูว่ามีเทสต์ไหม มี commit ต่อเนื่องไหม และอ่านโค้ดจริงก่อนติดตั้ง

### 🧠 สกิลใน Hermes Skills Hub (คนละชนิดกับ MCP)

ค้นใน Hub ของ Hermes แล้วพบ **3 สกิลชื่อ "blender"** ทั้งหมด **trust = community**
(ไม่ได้ผ่านการตรวจจาก Nous):

| สกิล | ที่มา | เป็นอะไร |
|---|---|---|
| `skills-sh/monumentalsystems/atlas-agent-teams/blender` | skills.sh | ความรู้เรื่อง UI/ลำดับงานของ Blender |
| `clawhub/blender` | clawhub | "หลีกเลี่ยงข้อผิดพลาดที่พบบ่อย" (transform, modifier) |
| `skills-sh/sfkislev/flue/blender` | skills.sh | ความรู้ทั่วไป |

> ⚠️ **สำคัญ: สกิลกับ MCP คนละหน้าที่** — สกิลคือ "ความรู้" (บอก AI ว่า Blender ทำงานยังไง)
> แต่ **สั่ง Blender ไม่ได้** ส่วน MCP (โปรเจกต์นี้ หรือตัว 31k★) คือ "ลงมือทำ"
> ⇒ ใช้คู่กันได้ และ **แค็ตตาล็อก MCP ที่ Nous รับรองยังไม่มี Blender** (ตรวจแล้ว)
> (ยังไม่ได้ประเมินคุณภาพของ 3 สกิลนั้น — ตรวจแค่ว่ามีอยู่จริงและ trust เป็น community)

### ✅ สรุป: เลือกอันไหน

| ถ้าคุณต้องการ… | ใช้ |
|---|---|
| ฟีเจอร์เยอะ (คลังโมเดล · สร้างโมเดล 3D · ถ่ายภาพ viewport) + ชุมชนใหญ่ช่วยตอบปัญหา | **`ahujasid/mcp-for-blender`** (31k★) |
| **รันแบบไม่มีหน้าต่าง/บนเซิร์ฟเวอร์** (headless-first) เป็นหลัก | **โปรเจกต์นี้** (ออกแบบมาเพื่อ `blender -b` — โหมด `main` บล็อกบน main thread) |
| ไม่ต้องติดตั้ง add-on และไม่ต้อง `pip install` อะไรลง Blender เลย | **โปรเจกต์นี้** (สะพานใช้ stdlib ล้วน) |
| ใช้ `mcp 2.x` (`MCPServer`) | **โปรเจกต์นี้** |
| โค้ดเล็กพออ่านจบ + เทสต์เป็นสัญญา (399 ข้อ) + เอกสารไทย | **โปรเจกต์นี้** |
| ให้ AI "รู้" ศัพท์และขั้นตอนของ Blender | ติดสกิลจาก Skills Hub เสริม (trust: community) |

### 🙏 สิ่งที่ได้เรียนรู้จากตัว 31k★ (และนำมาแก้ในโปรเจกต์นี้)

- เขาใช้ `parse_known_args` **โดยตั้งใจ** เพราะไคลเอนต์ MCP มักเติมอาร์กิวเมนต์ของตัวเอง
  ต่อท้ายบรรทัดคำสั่ง → **เราเปลี่ยนตามแล้ว** (เดิมออกทันที ทำให้ `hermes mcp add` ขึ้น
  `Connection closed` ที่หาสาเหตุยาก) ตอนนี้ข้ามพร้อมบันทึกเตือน
- เขาแก้ปัญหา "add-on เปิดสะพานให้เอง" ด้วย `bpy.app.timers` ตอนโหลดไฟล์ —
  **เรานำมาใช้แล้ว** (พร้อมด่าน `bpy.app.background` เพื่อไม่ให้โหมด `-b` ค้างแบบ issue #251)
- **ส่งรูปให้ AI ดู** — เราทำตามแล้ว (`get_viewport_screenshot`) โดยเลือกโหมด `render`
  เป็นปริยาย เพื่อให้ใช้ได้ทั้ง GUI และ `-b` (ของเขาถ่าย viewport ซึ่งต้องมีหน้าต่าง)
- **ติดตั้ง add-on ให้เอง** — ของเขามี CLI จัดการ add-on เราก็มี `--install-addon` แล้ว
- **ตรวจเวอร์ชันระหว่าง add-on กับเซิร์ฟเวอร์** — นำมาใช้เป็น `check_bridge_protocol()`
  พร้อมข้อความบอกวิธีแก้ (`--install-addon --force`)
- **ยังไม่นำมา** (พร้อมเหตุผล): คลังโมเดล Poly Haven/Poly Pizza และสร้างโมเดลด้วย AI
  ต้องพึ่ง API ภายนอก/คีย์ และทำให้สะพานเลิกเป็น stdlib ล้วน · telemetry เราไม่ต้องการ
  (ส่งข้อมูลออกโดยไม่จำเป็น) · การบันทึกว่าผู้ใช้แก้อะไรไป ยังซับซ้อนเกินความจำเป็นตอนนี้
- การมีหน้าเว็บเอกสาร + ชื่อแพ็กเกจที่ติดตั้งด้วย `uvx` บรรทัดเดียว ลดแรงต้านของผู้ใช้ได้มาก

---

## 12. อ้างอิง

- Blender 5.2 LTS — ออก 14 กรกฎาคม 2026 (ซ่อมล่าสุด 5.2.2, 15 ก.ย. 2026) · `<https://developer.blender.org/docs/release_notes/5.2/>`
- MCP Python SDK 2.x — `FastMCP` เปลี่ยนชื่อเป็น `MCPServer` · `<https://py.sdk.modelcontextprotocol.io/v2/migration/>`
- เหตุผลเรื่อง `bpy.app.timers` ไม่ทำงานในโหมด `-b` — [issue #251](https://github.com/ahujasid/mcp-for-blender/issues/251) และ [PR #252](https://github.com/ahujasid/mcp-for-blender/pull/252) (ยังเปิดอยู่ ณ 17 ต.ค. 2026)
- โครงการที่คนใช้มากที่สุดในระบบนิเวศ — [`ahujasid/mcp-for-blender`](https://github.com/ahujasid/mcp-for-blender) (31,125★)
