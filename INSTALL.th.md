# คู่มือติดตั้ง (ฉบับภาษาไทย)

คู่มือนี้ติดตั้ง **Hermes Blender MCP** — MCP server ที่ให้ AI (Hermes Agent,
Claude Desktop หรือไคลเอนต์ MCP ใด ๆ) อ่านและสั่งงาน **Blender 5.2** ผ่าน `bpy`

> 🇬🇧 English version: **[INSTALL.md](INSTALL.md)**

มี **สองส่วนที่ติดตั้งได้** — ปกติใช้แค่ส่วนแรก

| # | ส่วน | จำเป็นไหม | คืออะไร |
|---|---|---|---|
| 1 | **MCP server** (`blender_mcp_server.py` + `blender_bridge.py`) | ✅ จำเป็น | รันด้วย Python ของเครื่อง แล้วเปิด Blender ให้เอง |
| 2 | **Add-on ของ Blender** (`blender_mcp_bridge`) | ไม่บังคับ | ใช้เมื่ออยากสั่งงาน Blender ที่ **เปิดหน้าต่างค้างไว้อยู่แล้ว** |

**สารบัญ**

- [1. สิ่งที่ต้องมี](#1-สิ่งที่ต้องมี)
- [2. ดาวน์โหลดโค้ด](#2-ดาวน์โหลดโค้ด)
- [3. ติดตั้ง MCP server](#3-ติดตั้ง-mcp-server)
- [4. ตรวจว่าติดตั้งสำเร็จ](#4-ตรวจว่าติดตั้งสำเร็จ)
- [5. เชื่อมกับไคลเอนต์ AI](#5-เชื่อมกับไคลเอนต์-ai)
- [6. (ไม่บังคับ) ติดตั้ง add-on ของ Blender](#6-ไม่บังคับ-ติดตั้ง-add-on-ของ-blender)
- [7. วิธีใช้งาน](#7-วิธีใช้งาน)
- [8. ถอนการติดตั้ง](#8-ถอนการติดตั้ง)
- [9. แก้ปัญหา](#9-แก้ปัญหา)

---

## 1. สิ่งที่ต้องมี

| | ต้องมี | หมายเหตุ |
|---|---|---|
| Blender | **5.2 LTS** (ใช้ได้ตั้งแต่ 4.0) | 5.2 LTS ออกเมื่อ 14 ก.ค. 2026 |
| Python | **3.10** ขึ้นไป | Python **ของเครื่อง** — ไม่ใช่ของ Blender |
| แพ็กเกจ | `mcp>=2.0,<3` | ติดตั้งให้อัตโนมัติในข้อ 3 |
| ไคลเอนต์ AI | Hermes Agent / Claude Desktop / อื่น ๆ | ฝั่งไคลเอนต์ก็ต้องมีแพ็กเกจ `mcp` (ดูข้อ 5) |

> ⚠️ **อย่าพยายามติดตั้งแพ็กเกจ `mcp` ลง Python ของ Blender**
> ตัวสะพานที่รันใน Blender ใช้ **แค่ stdlib** — ตั้งใจออกแบบไว้แบบนั้น
> จึงไม่ต้องติดตั้งอะไรลง Blender เลย (บน Windows ก็ไม่ต้องสิทธิ์ผู้ดูแลระบบ)

---

## 2. ดาวน์โหลดโค้ด

```bash
git clone https://github.com/<ชื่อคุณ>/Hermes-blender-mcp.git
cd Hermes-blender-mcp
```

ไม่มี git? ดาวน์โหลด ZIP จากหน้ารีโปแล้วแตกไฟล์ก็ได้

---

## 3. ติดตั้ง MCP server

### 🪟 Windows 11 (PowerShell)

วิธีง่าย — ดับเบิลคลิกหรือรันไฟล์เดียวจบ (สร้าง venv + ติดตั้ง + ตรวจเจอ Blender):

```powershell
cd C:\path\to\Hermes-blender-mcp
.\install-windows.bat
```

หรือทำเองทีละคำสั่ง:

```powershell
cd C:\path\to\Hermes-blender-mcp
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe blender_mcp_server.py --check
```

### 🐧 Linux / 🍎 macOS

```bash
cd /path/to/Hermes-blender-mcp
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python blender_mcp_server.py --check
```

ผลของ `--check` ที่ถูกต้อง:

```
Blender: /usr/bin/blender (เจอใน PATH)
สคริปต์สะพาน: /path/to/Hermes-blender-mcp/blender_bridge.py ✅
```

ถ้าขึ้น **"หา Blender ไม่เจอ"** ให้ระบุพาธเอง:

```powershell
# Windows
.\.venv\Scripts\python.exe blender_mcp_server.py --check `
  --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

```bash
# Linux / macOS
./.venv/bin/python blender_mcp_server.py --check --blender /usr/bin/blender
```

หรือตั้งตัวแปรสภาพแวดล้อม `BLENDER_EXE` ไว้ครั้งเดียวก็ได้

---

## 4. ตรวจว่าติดตั้งสำเร็จ

ขั้นนี้คือขั้นที่ **พิสูจน์ว่าใช้ได้จริง** — มันจะเปิด Blender ขึ้นมาจริง
แล้วไล่เรียกทุกเครื่องมือให้ดูผลทีละตัว (ใช้ฉากเริ่มต้น ไม่แตะไฟล์งานของคุณ):

```powershell
# Windows
run-hermes-blender-mcp.bat --selftest
```

```bash
# Linux / macOS
./run-hermes-blender-mcp.sh --selftest
```

ควรเห็น:

```
── ตรวจการติดตั้ง (selftest) ──
✅ ต่อได้ · Blender 5.2.2
✅ get_scene_hierarchy: {"scene": {"name": "Scene", ...
✅ add_primitive_mesh: {"created": "LPM_Test", ...
✅ modify_object_transform: {"name": "LPM_Test", ...
✅ set_object_material: {"material": "LPM_0.9_0.2_0.2", ...
✅ get_object_details: {"name": "LPM_Test", ...
✅ execute_blender_script: {"ok": true, ...}
✅ delete_object: {"deleted": true, ...
✅ resource file_metadata: {"filepath": "", ...
── จบ ──
```

> ครั้งแรกจะใช้เวลา 10–30 วินาที (Blender ต้องเปิดตัว) และอาจมีหน้าต่าง Blender แวบขึ้นมา — ปกติ

**รันชุดทดสอบ** (ไม่ต้องมี Blender, 200+ ข้อ):

```bash
bash tests/run_all.sh
```

---

## 5. เชื่อมกับไคลเอนต์ AI

### Hermes Agent (ทางที่แนะนำ)

Hermes มีตัวจัดการ MCP ในตัว — เชื่อมต่อ ค้นหาเครื่องมือ และเขียน config ให้เลย:

```powershell
# Windows (PowerShell)
hermes mcp add blender `
  --command "C:\path\to\Hermes-blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 120 `
  --args C:\path\to\Hermes-blender-mcp\blender_mcp_server.py
```

```bash
# Linux / macOS
hermes mcp add blender \
  --command "/path/to/Hermes-blender-mcp/.venv/bin/python" \
  --connect-timeout 120 \
  --args /path/to/Hermes-blender-mcp/blender_mcp_server.py
```

> ⚠️ **`--args` ต้องอยู่ท้ายสุดเสมอ** อะไรที่พิมพ์ต่อจาก `--args` จะถูกส่งเป็น
> อาร์กิวเมนต์ของเซิร์ฟเวอร์ → เซิร์ฟเวอร์ออกทันที → Hermes รายงานแค่
> `Failed to connect: Connection closed` ซึ่งหาสาเหตุยากมาก
> **ให้วางตัวเลือกของ Hermes ไว้ *ก่อน* `--args`**

> ⚠️ **Python ของ Hermes ต้องมีแพ็กเกจ `mcp`** ไม่งั้นมันจะปิดความสามารถ MCP
> **เงียบ ๆ** (ไม่มีเครื่องมือขึ้นมา ไม่มี error) — ติดตั้งด้วย `uv` ที่มากับ Hermes:
>
> ```bash
> ~/.hermes/bin/uv pip install --python "$(which python3)" mcp
> ```

ผลลัพธ์ที่ถูกต้อง:

```
  Connecting to 'blender'...
  ✓ Connected! Found 12 tool(s) from 'blender':
    get_scene_hierarchy · add_primitive_mesh · modify_object_transform · …
  Enable all 12 tools? [Y/n/select]: Y
  ✓ Saved 'blender' to ~/.hermes/config.yaml (12/12 tools enabled)
```

ตรวจทีหลังด้วย:

```bash
hermes mcp list          # ดูสถานะ
hermes mcp test blender  # → ✓ Connected · ✓ Tools discovered: 8
```

แล้ว **เริ่มเซสชันใหม่** (หรือสั่ง `/reload-mcp`) เพื่อโหลดเครื่องมือ

### ตั้งค่าเองด้วยไฟล์ (Hermes)

แก้ `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  blender:
    command: C:\path\to\Hermes-blender-mcp\.venv\Scripts\python.exe
    args:
      - C:\path\to\Hermes-blender-mcp\blender_mcp_server.py
    connect_timeout: 120.0
    enabled: true
    timeout: 300            # งาน 3D ใช้เวลาได้ (ค่าปริยาย 120)
```

### ไคลเอนต์อื่น (Claude Desktop ฯลฯ)

```json
{
  "mcpServers": {
    "blender": {
      "command": "C:\\path\\to\\Hermes-blender-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\Hermes-blender-mcp\\blender_mcp_server.py"]
    }
  }
}
```

### ตัวเลือกที่มีประโยชน์ของเซิร์ฟเวอร์

| ตัวเลือก | ใช้เมื่อไร |
|---|---|
| `--blend-file "C:\งาน\บ้าน.blend"` | เปิดไฟล์นี้ตั้งแต่เริ่ม (แทนฉากเริ่มต้น) |
| `--blender /path/to/blender.exe` | Blender ไม่อยู่ใน `PATH` หรืออยู่ที่แปลก |
| `--timeout 300` | สคริปต์ยาวหรือเรนเดอร์ |
| `--gui` | เปิด Blender **พร้อมหน้าต่าง** (ใช้โหมด timer) |
| `--attach 127.0.0.1:9876 --token …` | ต่อกับ Blender ที่เปิดค้างอยู่ (ดูข้อ 6) |
| `--check` · `--list-tools` · `--selftest` | ตรวจวินิจฉัย |

### 5.1 อยากเห็น AI ทำงานในหน้าต่าง Blender (โหมดเห็นสด)

ค่าปริยายคือ headless: AI สร้างของจริง แต่มองไม่เห็น (ได้แค่ภาพจาก
`get_viewport_screenshot`) — ถ้าอยากดูของโผล่ทีละชิ้น มี 2 ทาง **เลือกทางเดียว**

**ทางที่ 1 (ง่ายสุด) — `--gui` · ไม่ต้องติดตั้ง add-on**

```yaml
mcp_servers:
  blender:
    command: C:\Hermes-blender-mcp\.venv\Scripts\python.exe
    args:
      - C:\Hermes-blender-mcp\blender_mcp_server.py
      - --gui
    connect_timeout: 120.0
    timeout: 300
    enabled: true
```

- ครั้งแรกที่ AI เรียกเครื่องมือ → **หน้าต่าง Blender เปิดขึ้นมาเอง** แล้วของจะโผล่สด ๆ
- ⚠️ `- --gui` ต้องขึ้น **บรรทัดใหม่** ห้ามต่อท้ายบรรทัด path (args จะกลายเป็นค่าเดียว
  `...blender_mcp_server.py- --gui` แล้ว `--gui` ไม่ทำงาน)
- ⚠️ `--gui` **เปิด Blender ใหม่** ไม่ได้ใช้หน้าต่างที่คุณเปิดค้างไว้
- ตรวจโหมดนี้ได้โดยไม่ต้องผ่าน Hermes:

```bat
run-hermes-blender-mcp.bat --selftest --gui
```
✅ ควรเห็น `timer เต้นปกติ (tick 1)` แล้ว `พร้อมใช้งาน · Blender 5.2.2`

**ทางที่ 2 — add-on + `--attach` · ใช้หน้าต่างที่คุณเปิดอยู่** (ขั้นตอนในข้อ 6)
ไม่มี Blender เปิด/ปิดเลย ✅ เหมาะกับงานที่ใช้ไฟล์ `.blend` เดิม ✅

> 🩺 **ของไม่โผล่ในหน้าต่าง?** กด **`Home`** (Frame All) หรือ **`Numpad 0`** (มุมมองกล้อง)
> ⚠️ ถ้าเปิดหน้าต่างเองไว้แล้วยังใช้ `--gui` จะมี **Blender 2 ตัว** — ของจะไปอยู่ในตัวที่ AI เปิด

---

## 6. (ไม่บังคับ) ติดตั้ง add-on ของ Blender

**ไม่จำเป็น** ถ้าไม่ได้อยากให้ AI ทำงานบน Blender ที่เปิดหน้าต่างค้างไว้ (เพื่อดูภาพขณะทำ)

### 6ก. ติดตั้งด้วยคำสั่งเดียว (แนะนำ)

เซิร์ฟเวอร์คัดลอก add-on ไปไว้ในโฟลเดอร์ของ Blender ให้เอง:

```powershell
.\.venv\Scripts\python.exe blender_mcp_server.py --install-addon --dry-run  # ดูปลายทางก่อน
.\.venv\Scripts\python.exe blender_mcp_server.py --install-addon            # ติดตั้งจริง
.\.venv\Scripts\python.exe blender_mcp_server.py --install-addon --force    # เขียนทับของเก่า
.\.venv\Scripts\python.exe blender_mcp_server.py --uninstall-addon          # ถอนออก
```

มันหาทุกเวอร์ชันของ Blender ที่คุณมี (Windows / macOS / Linux) แล้วบอกว่าคัดลอกไปที่ไหน
· `--check` ก็รายงานสถานะ add-on ให้ด้วย

### 6ข. หรือสร้างไฟล์ .zip เอง

```powershell
.\.venv\Scripts\python.exe tools\build_addon_zip.py
```

ได้ไฟล์ `dist\blender_mcp_bridge-<เวอร์ชัน>.zip` — เหมาะกับแนบใน GitHub Releases

### 6ค. เปิดใช้ใน Blender

1. เปิด Blender → `Edit > Preferences > Add-ons`
2. กดลูกศร **▼** (มุมขวาบน) → **Install from Disk…**
3. เลือกไฟล์ `blender_mcp_bridge-<เวอร์ชัน>.zip` (เช่น `-1.0.9.zip`)
4. ติ๊กถูกที่ **"Hermes Blender MCP Bridge"**

### 6ง. เริ่มสะพาน

1. ในมุมมอง 3D กด **`N`** → เปิดแท็บ **"Blender MCP"**
2. กด **"เริ่มสะพาน (Start bridge)"** — แผงจะแสดง `host:port` (ค่าปริยาย
   `127.0.0.1:9876`) และ token
3. กด **"คัดลอกคำสั่งเชื่อมต่อ"**

### 6จ. ใช้งานประจำวัน (plug-in)

**ปกติไม่ต้องกดอะไรเลย** — add-on เริ่มสะพานให้อัตโนมัติเมื่อโหลดไฟล์ `.blend`
(ถ้าอยากปิดพฤติกรรมนี้ เปิดแผงแล้วปิด "เริ่มสะพานอัตโนมัติ")

1. เปิด Blender ตามปกติ → เปิดไฟล์งานของคุณ
2. กด **`N`** → แท็บ **"Blender MCP"** → ดูสถานะ:
   - **"สะพานทำงานอยู่"** + `host:port` (ปริยาย `127.0.0.1:9876`) + token
   - ถ้ายังไม่ทำงาน → กด **"เริ่มสะพาน"**
3. คัดลอก token ไปใส่ใน config ของ Hermes (ครั้งเดียว — token คงอยู่จนกว่าจะกด
   **"สร้าง token ใหม่"**)

```yaml
    args:
      - C:\Hermes-blender-mcp\blender_mcp_server.py
      - --attach
      - 127.0.0.1:9876
      - --token
      - "<token จากแผง>"
```

4. รีสตาร์ต Hermes → สั่งงาน → **เห็นของโผล่ในหน้าต่างที่คุณเปิดอยู่** ✅

**ปุ่มในแผง**

| ปุ่ม | ใช้เมื่อไร |
|---|---|
| เริ่มสะพาน / หยุดสะพาน | เปิด-ปิดตัวรับคำสั่งใน Blender ตัวนี้ |
| สร้าง token ใหม่ | เมื่อสงสัยว่า token รั่ว (ต้องอัปเดต config ของ Hermes ตาม) |
| คัดลอกคำสั่งเชื่อมต่อ | ก็อปบรรทัด `--attach ... --token ...` ไปวางใน config ได้เลย |

**ข้อควรระวัง**

- ปิด Blender = สะพานหยุด → Hermes ต่อไม่ได้ (เปิดใหม่แล้ว add-on จะเริ่มให้เอง)
- ถ้าเปิด Blender **หลายหน้าต่าง** ทุกตัวจะแย่งพอร์ต 9876 → ตั้งพอร์ตต่างกันในแผง
- `--attach` กับ `--gui` ใช้พร้อมกันไม่ได้ (เลือกอย่างเดียว)
- พอร์ตของสะพานฟังเฉพาะ `127.0.0.1` — **ห้ามเปิดออกเครือข่าย** เพราะไม่ได้เข้ารหัส
  ใครต่อได้ก็สั่ง Blender ของคุณได้

## 7. วิธีใช้งาน

ชื่อเครื่องมือจะขึ้นต้นด้วยคำนำหน้าของไคลเอนต์ เช่นใน Hermes:

```
mcp_blender_get_scene_hierarchy     mcp_blender_get_object_details
mcp_blender_add_primitive_mesh      mcp_blender_delete_object
mcp_blender_modify_object_transform mcp_blender_set_object_material
mcp_blender_execute_blender_script  mcp_blender_save_blend_file
mcp_blender_get_viewport_screenshot
```

และมี 2 ทรัพยากร: `blender://file/metadata`, `blender://scene/hierarchy`

ลองสั่งเป็นภาษาธรรมชาติ:

> "ดูว่าในฉาก Blender มีอะไรบ้าง แล้วสร้างลูกบาศก์สีแดงที่ (0, 0, 3) ย่อเหลือครึ่งหนึ่ง"

> "สร้างทรงกลม 3 ลูกเรียงกัน ห่างกัน 2 หน่วย ใส่สีคนละสี"

> "บันทึกไฟล์ปัจจุบันเป็น `C:\งาน\layout.blend`"

**สองเรื่องที่ควรรู้**

- **หน่วยหมุนเป็น "องศา"** ในทุกเครื่องมือ (`bpy` เก็บเป็นเรเดียน — โค้ดแปลงให้แล้ว)
- `execute_blender_script` รันโค้ด `bpy` ดิบ โดยมีด่านกัน `import os`/`subprocess`,
  `open()`, `eval()`, การเข้าถึง dunder และ operator ที่ทำลายงานอย่าง
  `bpy.ops.wm.quit_blender` — ตั้ง `allow_unsafe=true` เพื่อข้ามด่านได้
  **มันคือ "ราวกันตก ไม่ใช่กรงขัง"** — อ่านรายละเอียดใน
  [README](README.md) (ข้อ 6)

---

## 8. ถอนการติดตั้ง

```bash
hermes mcp remove blender        # หรือลบบรรทัดใน config.yaml เอง
```

แล้วลบโฟลเดอร์โปรเจกต์ทิ้ง (`.venv` อยู่ข้างใน)
ถ้าติดตั้ง add-on: Blender → `Edit > Preferences > Add-ons` → เอาติ๊กออก → **Remove**
แล้วลบโฟลเดอร์ `blender_mcp_bridge` ในโฟลเดอร์ addons

ไม่มีอะไรถูกเขียนไว้นอกโฟลเดอร์โปรเจกต์ นอกจากโฟลเดอร์ add-on
และไฟล์บันทึกในโฟลเดอร์ชั่วคราว (`%TEMP%\Hermes-blender-mcp\` หรือ `/tmp/Hermes-blender-mcp/`)

---

## 9. แก้ปัญหา

| อาการ | สาเหตุ / ทางแก้ |
|---|---|
| `หา Blender ไม่เจอ` | ระบุ `--blender "<พาธเต็ม>"` หรือตั้ง `BLENDER_EXE` — **หมายเหตุ:** โปรแกรมที่เปิดโปรเซสลูก (รวม Hermes) จะส่งตัวแปรสภาพแวดล้อมแบบ **กรองแล้ว** เท่านั้น (`PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`, `XDG_*`) จึงมักไม่มี `PROGRAMFILES`/`LOCALAPPDATA` → ระบุพาธตรง ๆ ชัวร์ที่สุด |
| `Blender ไม่พร้อมภายใน 90 วินาที` | อาจมีกล่องข้อความของ Blender ค้างอยู่ตอนเปิด หรือเครื่องช้า — ข้อความ error จะแนบบันทึกท้าย ๆ ของ Blender มาให้ · ลองรันเองดู: `blender -b --python blender_bridge.py -- --port 0 --selftest` |
| `Failed to connect: Connection closed` | เกือบทุกครั้งคือ `--args` ไม่ได้อยู่ท้ายสุด (ดูข้อ 5) หรือเซิร์ฟเวอร์ล้มตอนเริ่ม — ทดสอบเองด้วยการป้อน JSON `initialize` ทาง stdin |
| Hermes ไม่เห็นเครื่องมือเลย | Python ของ Hermes ไม่มีแพ็กเกจ `mcp` (ปิดเงียบ ๆ) หรือเพิ่มเซิร์ฟเวอร์หลังเซสชันเริ่ม → เริ่มเซสชันใหม่ หรือ `/reload-mcp` |
| เรียกเครื่องมือแล้วหมดเวลา | เพิ่ม `timeout` ใน config / `--timeout` — **Blender ถูกสั่งหยุดกลางคันไม่ได้** ลูปยาวหรือเรนเดอร์จะทำต่อจนจบ |
| add-on ขึ้นแต่บอกหาสะพานไม่เจอ | สองไฟล์ไม่ได้อยู่โฟลเดอร์เดียวกัน — ดูข้อ 6ค ใหม่ หรือตั้ง `BLENDER_MCP_DIR` |
| ขึ้น "ถูกปฏิเสธเพราะฝ่าด่านความปลอดภัย" | เป็นไปตามการออกแบบ — ถ้าตั้งใจจริงส่ง `allow_unsafe=true` |
| ดูบันทึก | `%TEMP%\Hermes-blender-mcp\server-*.log` (Windows) หรือ `/tmp/Hermes-blender-mcp/server-*.log` |
| **ภาษาไทยในหน้าต่าง cmd เป็นตัวอ่านไม่ออก** | cmd เขียนข้อความ `echo` ตาม codepage ของหน้าต่าง (ไฟล์เป็น UTF-8 แต่หน้าต่างเป็น CP874/CP437) — สคริปต์ `.bat` ของเราตั้ง `chcp 65001` ให้แล้ว ถ้าแก้เองในไฟล์ ให้วาง `chcp 65001 >nul 2>&1` **ก่อน** บรรทัด `echo` ที่มีภาษาไทย และ **ห้ามบันทึกเป็น UTF-8 มี BOM** (BOM ทำให้ cmd พังบรรทัดแรก) · ถ้าฟอนต์ของหน้าต่างไม่มีตัวอักษรไทย ให้ใช้ Windows Terminal หรืออ่านข้อความภาษาอังกฤษคู่กันที่พิมพ์ไว้ |

ยังไม่หาย? เปิด issue พร้อมแนบบันทึกท้าย ๆ และผลของ
`python blender_mcp_server.py --check`

---

## สำหรับผู้ดูแลรีโป — การปล่อยเวอร์ชัน

เพื่อให้ผู้ใช้ไม่ต้องมี Python ก็ติดตั้ง add-on ได้:

```bash
python tools/build_addon_zip.py
# แนบ dist/blender_mcp_bridge-<เวอร์ชัน>.zip ไว้ใน GitHub Releases
```

แล้วในคู่มือก็เขียนได้ว่า "ดาวน์โหลด `.zip` จาก Releases → Install from Disk"
ก่อนสร้างให้เพิ่ม `bl_info["version"]` ใน `blender_addon/__init__.py` —
ชื่อไฟล์ zip จะตั้งตามเวอร์ชันนั้นอัตโนมัติ
