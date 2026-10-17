# 01 — ติดตั้งบน Windows 11 (ทีละขั้น)

คู่มือนี้สำหรับ **Windows 11** โดยเฉพาะ ทุกคำสั่งคัดลอกวางได้เลย
(ปรับพาธ `C:\Hermes-blender-mcp` ให้ตรงกับที่คุณวางโฟลเดอร์)

---

## ขั้นที่ 0 — สิ่งที่ต้องมี

| ต้องมี | ตรวจยังไง | ถ้าไม่มี |
|---|---|---|
| **Blender 5.2 LTS** | เปิด Blender แล้วดูมุมขวาล่าง | โหลดที่ <https://www.blender.org/download/> (รุ่น 5.2.2 ขึ้นไป) |
| **Python 3.10+** | เปิด PowerShell พิมพ์ `python --version` | โหลดจาก <https://www.python.org/downloads/> — **ติ๊ก "Add python.exe to PATH"** ตอนติดตั้ง |
| **Hermes Agent** | พิมพ์ `hermes --help` | ติดตั้ง Hermes ก่อน |

---

## ขั้นที่ 1 — หาที่อยู่ของ Blender

เปิด PowerShell แล้วรัน:

```powershell
Get-ChildItem "C:\Program Files\Blender Foundation" -Directory |
  Select-Object -ExpandProperty FullName
```

จะได้ผลประมาณนี้ — จดพาธไว้ใช้ทีหลัง:

```
C:\Program Files\Blender Foundation\Blender 5.2
```

พาธเต็มของโปรแกรมคือ `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`

> 💡 ถ้าติดตั้งแบบ portable/Steam พาธจะต่างออกไป — หาไฟล์ `blender.exe` เองได้เลย

---

## ขั้นที่ 2 — ติดตั้งโปรแกรม (คำสั่งเดียว)

วางโฟลเดอร์โปรเจกต์ไว้ที่ `C:\Hermes-blender-mcp` แล้วเปิด PowerShell:

```powershell
cd C:\Hermes-blender-mcp
.\install-windows.bat
```

สคริปต์จะทำให้ทั้งหมดนี้:

1. หา Python ของเครื่อง
2. สร้าง virtual environment ที่ `.venv` (แยกจาก Python ของ Blender โดยสิ้นเชิง)
3. ติดตั้ง `mcp` (MCP Python SDK)
4. **ตรวจว่าเจอ Blender ไหม**
5. พิมพ์ค่า config ให้คัดลอก

### ถ้าขั้นที่ 4 บอกว่า "หา Blender ไม่เจอ"

ระบุพาธเอง:

```powershell
C:\Hermes-blender-mcp\.venv\Scripts\python.exe C:\Hermes-blender-mcp\blender_mcp_server.py `
  --check --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

ควรได้:

```
Blender: C:\Program Files\Blender Foundation\Blender 5.2\blender.exe (ระบุเองจาก --blender)
สคริปต์สะพาน: C:\Hermes-blender-mcp\blender_bridge.py ✅
```

---

## ขั้นที่ 3 — ทดสอบว่าใช้งานได้จริง

```powershell
C:\Hermes-blender-mcp\run-hermes-blender-mcp.bat --selftest
```

คำสั่งนี้จะ **เปิด Blender จริง** แล้วไล่เรียกทุกเครื่องมือให้ดูผลทีละตัว:

```
── ตรวจการติดตั้ง (selftest) ──
✅ ต่อได้ · Blender 5.2.2
✅ get_scene_hierarchy: {"scene": {"name": "Scene", ...
✅ add_primitive_mesh: {"created": "LPM_Test", ...
✅ modify_object_transform: {"name": "LPM_Test", ...
✅ set_object_material: {"material": "LPM_0.9_0.2_0.2", ...
✅ get_object_details: {"name": "LPM_Test", ...
✅ execute_blender_script: {"ok": true, "stdout": "", ..., "result": 42}
✅ delete_object: {"deleted": true, ...
✅ resource file_metadata: {"filepath": "", ...
── จบ ──
```

ผ่านหมด = พร้อมใช้งาน 🎉

> ⚠️ ครั้งแรกอาจใช้เวลา 10–30 วินาที เพราะ Blender ต้องเปิดตัวก่อน
> และจะเห็นหน้าต่าง Blender แวบขึ้นมาแล้วปิดเอง — เป็นเรื่องปกติ

ถ้าไม่ผ่าน จะบอกสาเหตุเป็นภาษาไทย พร้อมบันทึกท้าย ๆ ของ Blender ให้ดู

---

## ขั้นที่ 4 — ต่อเข้ากับ Hermes

Hermes มีคำสั่งจัดการ MCP ในตัว ใช้คำสั่งเดียว (ใน PowerShell):

```powershell
hermes mcp add blender `
  --command "C:\Hermes-blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 120 `
  --args C:\Hermes-blender-mcp\blender_mcp_server.py
```

> ⚠️ **`--args` ต้องอยู่ท้ายสุดเสมอ** ถ้าเอา `--connect-timeout` ไปไว้ข้างหลัง
> มันจะถูกกลืนเป็นอาร์กิวเมนต์ของเซิร์ฟเวอร์ แล้ว Hermes จะขึ้นแค่
> `Failed to connect: Connection closed` ซึ่งหาสาเหตุยากมาก

> ⚠️ **ตรวจก่อนว่า Python ของ Hermes มีแพ็กเกจ `mcp`** ไม่งั้น Hermes จะปิด
> ความสามารถ MCP เงียบ ๆ (ไม่มีเครื่องมือขึ้นมาเลย) — ดูวิธีติดตั้งใน
> [`docs/02-Hermes-config.md`](02-Hermes-config.md) หัวข้อแรก

**เปิดไฟล์งานของคุณตั้งแต่ต้น** (ไม่ต้องเปิดเองทีหลัง):

```powershell
hermes mcp add blender `
  --command "C:\Hermes-blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 120 `
  --args C:\Hermes-blender-mcp\blender_mcp_server.py --blend-file "C:\งาน\บ้าน.blend"
```

---

## ขั้นที่ 5 — ลองใช้จริง

1. เริ่มเซสชันใหม่ใน Hermes (หรือสั่ง `/reload-mcp`)
2. ลองบอกว่า:

> "ดูว่าในฉาก Blender มีอะไรบ้าง แล้วสร้างทรงกลมที่ (2,0,1) ใส่สีฟ้า"

3. หรือเขียนคำสั่งที่ต้องใช้หลายเครื่องมือ:

> "สร้างลูกบาศก์ 3 อันเรียงกันตามแนวนอน ห่างกัน 3 หน่วย ใส่สีต่างกัน แล้วบันทึกเป็น C:\งาน\เรียง.blend"

---

## (ทางเลือก) โหมดมีหน้าต่าง — เห็นภาพขณะ AI ทำ

ถ้าอยากนั่งดู Blender เปลี่ยนไปมาให้ใช้ add-on:

1. คัดลอกโฟลเดอร์ `blender_addon` ไปเป็นชื่อ `blender_mcp_bridge` ที่:

```powershell
# เปิดโฟลเดอร์ addons ของ Blender 5.2
explorer "$env:APPDATA\Blender Foundation\Blender\5.2\scripts\addons"
```

2. สร้างโฟลเดอร์ `blender_mcp_bridge` แล้ววาง **สองไฟล์** นี้ข้างใน:
   - `blender_addon\__init__.py` → เปลี่ยนชื่อเป็น `__init__.py` ในโฟลเดอร์ใหม่
   - `blender_bridge.py` (จากโฟลเดอร์โปรเจกต์)

```
%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\blender_mcp_bridge\
├── __init__.py            ← จาก blender_addon/__init__.py
└── blender_bridge.py      ← จากโฟลเดอร์โปรเจกต์
```

3. เปิด Blender → `Edit > Preferences > Add-ons` → ค้นหา **"Hermes Blender MCP"** → ติ๊กเปิด
4. กด `N` ในมุมมอง 3D → แท็บ **"Blender MCP"** → กด **"เริ่มสะพาน (Start bridge)"**
5. จะเห็นพอร์ต (ค่าปริยาย 9876) และ token — กด **"คัดลอกคำสั่งเชื่อมต่อ"**
6. สั่ง Hermes ให้ใช้โหมด attach:

```powershell
hermes mcp add blender `
  --command "C:\Hermes-blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 60 `
  --args C:\Hermes-blender-mcp\blender_mcp_server.py --attach 127.0.0.1:9876 --token "วาง_TOKEN"
```

> 💡 ในโหมดนี้ Blender ต้องเปิดอยู่และกด "เริ่มสะพาน" ไว้ก่อนเสมอ
> และ **ควรบันทึกไฟล์ก่อน** ให้ AI ทำอะไร เพื่อกันมือลั่น

---

## แก้ปัญหาที่เจอบ่อยบน Windows

| อาการ | ทางแก้ |
|---|---|
| `python` ไม่รู้จัก | ติดตั้ง Python ใหม่แล้วติ๊ก "Add python.exe to PATH" |
| `install-windows.bat` ดับเบิลคลิกแล้วหน้าต่างปิดทันที | เปิด PowerShell ในโฟลเดอร์นั้นแล้วรัน `.\install-windows.bat` จะเห็นข้อความครบ |
| Blender เปิดช้ามากครั้งแรก | ปกติ (10–30 วินาที) — ครั้งต่อไปเร็วขึ้น |
| `Failed to connect: Connection closed` | ตรวจลำดับ `--args` (ต้องอยู่ท้ายสุด) |
| ไฟล์ .blend เปิดไม่ได้เพราะพาธมีช่องว่าง | ใส่เครื่องหมายคำพูดครอบพาธทั้งก้อน |
| Antivirus บล็อก | อนุญาต `blender_mcp_server.py` และ `blender.exe` (บางตัวกันโปรเซสที่เปิดโปรเซสอื่น) |
| อยากลบทั้งหมด | `hermes mcp remove blender` · ลบโฟลเดอร์โปรเจกต์ · ลบ add-on ใน Blender |
