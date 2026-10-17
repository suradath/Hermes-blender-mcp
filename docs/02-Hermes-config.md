# 02 — ต่อ Hermes Blender MCP เข้ากับ Hermes Agent

คู่มือนี้เขียนจาก **คำสั่งจริงที่รันและได้ผลจริง** บนเครื่องนี้ (ไม่ใช่จากความจำ)
Hermes มีคำสั่งจัดการ MCP ในตัว — ไม่ต้องแก้ YAML เอง

---

## ✅ ตรวจก่อน: Hermes ต้องมีแพ็กเกจ `mcp` เสียก่อน

⚠️ **กับดักที่พบบ่อยที่สุด** — ถ้า Python ของ Hermes ไม่มีแพ็กเกจ `mcp`
Hermes จะ **ปิดความสามารถ MCP เงียบ ๆ** (ไม่มี error ให้เห็น แค่ไม่มีเครื่องมือขึ้นมา)

```bash
# ดูว่า Hermes ใช้ Python ตัวไหน
hermes --help >/dev/null && python3 -c "import sys; print(sys.executable)"
```

ถ้า `import mcp` ล้มเหลว ให้ติดตั้งด้วย `uv` ที่มากับ Hermes:

```bash
# Linux / macOS
~/.hermes/bin/uv pip install --python "$(which python3)" mcp

# Windows (PowerShell) — ปรับพาธให้ตรงกับเครื่อง
& "$env:USERPROFILE\.hermes\bin\uv.exe" pip install --python (Get-Command python).Source mcp
```

ตรวจว่าได้แล้ว:

```bash
python3 -c "import mcp; print('ok')"
```

---

## วิธีที่ 1 (แนะนำ) — ใช้คำสั่งของ Hermes

### ก) โหมดไม่มีหน้าต่าง (Hermes เปิด Blender ให้เอง)

```bash
hermes mcp add blender \
  --command "C:\Hermes-blender-mcp\.venv\Scripts\python.exe" \
  --connect-timeout 120 \
  --args C:\Hermes-blender-mcp\blender_mcp_server.py
```

Linux / macOS:

```bash
hermes mcp add blender \
  --command "/path/to/Hermes-blender-mcp/.venv/bin/python" \
  --connect-timeout 120 \
  --args /path/to/Hermes-blender-mcp/blender_mcp_server.py
```

### ข) ระบุไฟล์ `.blend` ที่จะเปิด

```bash
hermes mcp add blender --command "..." --connect-timeout 120 \
  --args blender_mcp_server.py --blend-file "C:\งาน\บ้าน.blend"
```

### ค) โหมดมีหน้าต่าง (attach ไปที่ add-on ที่กำลังรัน)

```bash
hermes mcp add blender --command "..." --connect-timeout 60 \
  --args blender_mcp_server.py --attach 127.0.0.1:9876 --token "วาง_TOKEN_จากแผงใน Blender"
```

### ⚠️ บทเรียนจริง: `--args` ต้องอยู่ **ท้ายสุดเสมอ**

รอบแรกที่ทดสอบ ใส่ `--connect-timeout` ต่อจาก `--args` → มันถูกกลืนเป็น
**อาร์กิวเมนต์ของเซิร์ฟเวอร์** → เซิร์ฟเวอร์ปฏิเสธและออกทันที → Hermes รายงานแค่

```
✗ Failed to connect: Connection closed
```

ซึ่งชี้ทางผิดไปไกล (ดูเหมือนปัญหาที่โปรแกรม ไม่ใช่ที่ลำดับอาร์กิวเมนต์)
**ให้วาง `--connect-timeout` ไว้ก่อน `--args`** แล้วทุกอย่างจบ

### ผลลัพธ์ที่ควรเห็น (คัดจากของจริง)

```
  Connecting to 'blender'...

  ✓ Connected! Found 8 tool(s) from 'blender':

    get_scene_hierarchy                      Read the active scene: collection tree, every object with it...
    add_primitive_mesh                       Add a primitive mesh to the scene. primitive is one of: cube...
    modify_object_transform                  Move, rotate or resize an existing object by name. Pass only...
    get_object_details                       Full details for one object: world matrix, dimensions, rotat...
    delete_object                            Delete an object by name. The first call only reports what w...
    set_object_material                      Give a mesh object a simple Principled BSDF material. color ...
    save_blend_file                          Save the current .blend. Without filepath it saves in place ...
    execute_blender_script                   Run raw bpy Python inside Blender and return stdout, the val...

  Enable all 8 tools? [Y/n/select]:
  ✓ Saved 'blender' to ~/.hermes/config.yaml (8/8 tools enabled)
  Start a new session to use these tools, or run /reload-mcp to load them into open sessions.
```

### คำสั่งที่ใช้ตรวจทีหลัง

```bash
hermes mcp list          # ดูรายการทั้งหมด + สถานะ
hermes mcp test blender  # ทดสอบเชื่อมต่อ + นับเครื่องมือ
hermes mcp configure blender   # เลือกเปิด/ปิดเครื่องมือทีละตัว
hermes mcp remove blender      # เอาออก
```

ผลของ `hermes mcp test blender` (ของจริง):

```
  Testing 'blender'...
  Transport: stdio → C:\Hermes-blender-mcp\.venv\Scripts\python.exe
  Auth: none
  ✓ Connected (1950ms)
  ✓ Tools discovered: 8
```

---

## วิธีที่ 2 — แก้ `~/.hermes/config.yaml` เอง

Hermes เขียนรูปแบบนี้จริง (คัดจากไฟล์หลัง `hermes mcp add`):

```yaml
mcp_servers:
  blender:
    command: C:\Hermes-blender-mcp\.venv\Scripts\python.exe
    args:
      - C:\Hermes-blender-mcp\blender_mcp_server.py
      - --blend-file
      - C:\งาน\บ้าน.blend
    connect_timeout: 120.0
    enabled: true
    timeout: 300            # เพิ่มเองได้ — ค่าปริยาย 120 อาจสั้นไปสำหรับงาน 3D
```

| คีย์ | ความหมาย | ค่าที่แนะนำสำหรับ Blender |
|---|---|---|
| `command` | โปรแกรมที่จะรัน | Python ของ **venv โปรเจกต์** (ไม่ใช่ของ Blender) |
| `args` | อาร์กิวเมนต์ | พาธ `blender_mcp_server.py` + ตัวเลือกอื่น |
| `connect_timeout` | เวลารอเชื่อมต่อครั้งแรก | **120** (Blender ใช้เวลาหลายวินาทีเปิดตัว) |
| `timeout` | เวลารอต่อหนึ่งคำสั่ง | **300** (สคริปต์ 3D ใช้เวลาได้) |
| `enabled` | เปิดใช้ | `true` |
| `env` | ตัวแปรสภาพแวดล้อมเพิ่มเติม | ปกติไม่ต้องใส่ (ดูหัวข้อถัดไป) |

### เรื่องตัวแปรสภาพแวดล้อม (สำคัญบน Windows)

Hermes ส่งตัวแปรสภาพแวดล้อมแบบ **กรองแล้ว** ให้โปรเซสลูก:
เฉพาะ `PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TERM`, `SHELL`, `TMPDIR`, `XDG_*`

⇒ จึง**ไม่มี** `PROGRAMFILES` / `LOCALAPPDATA` ให้ใช้ค้นหา Blender
โค้ดนี้มีค่าเริ่มต้นมาตรฐานเป็นทางถอยอยู่แล้ว (`C:\Program Files`,
`%USERPROFILE%\AppData\Local\Programs\Blender Foundation`) จึงมักไม่ต้องส่งอะไรเพิ่ม
แต่ถ้า Blender ติดตั้งไว้ที่แปลก ๆ ให้ระบุตรง ๆ ซึ่งแน่นอนที่สุด:

```yaml
    args:
      - C:\Hermes-blender-mcp\blender_mcp_server.py
      - --blender
      - D:\Apps\Blender 5.2\blender.exe
```

หรือส่งตัวแปรให้ก็ได้:

```yaml
    env:
      PROGRAMFILES: "C:\\Program Files"
      LOCALAPPDATA: "C:\\Users\\Mikky\\AppData\\Local"
```

### หมายเหตุ: รูปแบบ JSON `mcpServers` ของไคลเอนต์อื่น

Claude Desktop และไคลเอนต์อื่นใช้รูปแบบ JSON — **Hermes ไม่ได้อ่านไฟล์นี้**
(ของ Hermes อยู่ที่ `config.yaml`) แต่ถ้าต้องการรูปแบบมาตรฐาน:

```json
{
  "mcpServers": {
    "blender": {
      "command": "C:\\Hermes-blender-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Hermes-blender-mcp\\blender_mcp_server.py"],
      "env": {}
    }
  }
}
```

---

## หลังติดตั้ง: เรียกใช้จริง

1. **โหลดเครื่องมือ**: เริ่มเซสชันใหม่ หรือสั่ง `/reload-mcp` ในเซสชันที่เปิดอยู่
2. ชื่อเครื่องมือใน Hermes จะขึ้นต้นด้วย `mcp_blender_` เช่น

```
mcp_blender_get_scene_hierarchy
mcp_blender_add_primitive_mesh
mcp_blender_modify_object_transform
mcp_blender_execute_blender_script
mcp_blender_get_object_details
mcp_blender_delete_object
mcp_blender_set_object_material
mcp_blender_save_blend_file
```

3. ลองสั่งเป็นภาษาธรรมชาติ:

> "ใช้ Blender สร้างลูกบาศก์ที่ (0,0,3) ย่อเป็นครึ่งหนึ่ง ใส่สีแดง แล้วบอกว่าฉากมีอะไรบ้าง"

Hermes จะเรียก `get_scene_hierarchy` → `add_primitive_mesh` → `modify_object_transform`
→ `set_object_material` ตามลำดับเอง

---

## แก้ปัญหาเฉพาะของการเชื่อมต่อ

| อาการ | สาเหตุ | แก้ |
|---|---|---|
| ไม่มีเครื่องมือ `mcp_blender_*` ขึ้นมาเลย | Python ของ Hermes ไม่มี `mcp` | ติดตั้งตามหัวข้อแรกด้านบน แล้วรีสตาร์ต |
| `✗ Failed to connect: Connection closed` | มักเป็น `--args` ไม่ได้อยู่ท้ายสุด (ตัวเลือกของ Hermes ถูกกลืนไปเป็นอาร์กิวเมนต์) | ย้าย `--connect-timeout` ไปก่อน `--args` |
| เชื่อมต่อไม่ได้ ทั้งที่รันเองได้ | `connect_timeout` สั้นเกินไป | ตั้ง 120 แล้ว `hermes mcp test blender` |
| ต่อได้แต่เรียกแล้ว timeout | งานใช้เวลานาน (สคริปต์/เรนเดอร์) | เพิ่ม `timeout: 300` |
| เพิ่มแล้วแต่ Hermes ยังไม่เห็น | ยังไม่ได้โหลด | เริ่มเซสชันใหม่ หรือ `/reload-mcp` |
| Hermes พยายามเปิด Blender ทุกครั้ง | ต้องการโหมด attach | ใส่ `--attach 127.0.0.1:9876 --token ...` |
