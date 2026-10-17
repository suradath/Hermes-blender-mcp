# 04 — ตั้งค่า repo บน GitHub (Description · Topics · Social preview)

เอกสารนี้รวมข้อความพร้อมคัดลอกสำหรับช่อง **Description** ของ repo บน GitHub
รวมถึง topics และภาพตัวอย่าง — เขียนจากข้อเท็จจริงของโปรเจกต์ (ไม่มีการอวดเกินจริง)

---

## 1. Description (ช่อง "About" ของ repo) — แนะนำ

> 🎯 ใช้ข้อความนี้ (ความยาว ~140 ตัวอักษร — แสดงเต็มในหน้า repo)

**ภาษาไทย (แนะนำถ้าเน้นคนไทย):**

```
MCP Server ให้ Hermes Agent สั่งงาน Blender 5.2 ผ่าน bpy — 12 เครื่องมือ · คลังของฟรี CC0 · ตัวสร้างโมเดลโพลิกอน · ทดสอบ 791 ข้อ
```

**English (แนะนำถ้าอยากให้คนนอกเข้าถึง):**

```
MCP server letting Hermes Agent drive Blender 5.2 via bpy — 12 tools, keyless CC0 assets, procedural low-poly generators, 791 tests.
```

---

## 2. Description ทางเลือก

### สั้นมาก (เหมาะวางคู่กับชื่อ repo)

| ภาษา | ข้อความ |
|---|---|
| ไทย | `ให้ AI สั่งงาน Blender ได้จากแชท — MCP server 12 เครื่องมือ · โมเดลโพลิกอนจากโค้ด · เทสต์ครบ` |
| อังกฤษ | `Drive Blender from your AI agent — MCP server, 12 tools, keyless assets, procedural low-poly models.` |

### ยาว (ใช้ในหน้า About แบบละเอียด / social preview)

**ไทย:**
```
MCP Server (stdio) สำหรับ Hermes Agent ขับ Blender 5.2 ผ่าน bpy: อ่านฉาก สร้าง/ขยับวัตถุ ใส่สี
รันสคริปต์ ถ่ายภาพหน้าจอ คลัง HDRI/โมเดล CC0 ที่ไม่ต้องใช้คีย์ และตัวสร้างโมเดลโพลิกอน
(ตัวละคร บ้านทรงไทย ต้นไม้ สุนัข ฉากหมู่) — ทุกชั้นทดสอบอัตโนมัติ 791 ข้อ
```

**อังกฤษ:**
```
Stdio MCP server that lets Hermes Agent (or any MCP client) read and drive Blender 5.2 through bpy:
scene inspection, object creation/transform, materials, script execution, viewport screenshots,
a keyless CC0 asset library (HDRIs/textures/models) and procedural low-poly generators —
verified by 791 automated checks.
```

---

## 3. Topics (แท็กของ repo — ใส่ได้สูงสุด 20)

```
mcp
model-context-protocol
blender
blender-3d
bpy
blender-addon
hermes-agent
ai-agent
llm-tools
python
procedural-generation
low-poly
polyhaven
3d-modeling
asset-generation
automation
windows
thai
mit-license
```

> 💡 เลือก 15–20 ตัวที่ตรงที่สุด · ไม่ต้องใส่ให้ครบ (แท็กที่ไม่ตรงทำให้ค้นหาแล้วผิดหวัง)

---

## 4. Social preview (ภาพที่ขึ้นตอนแชร์ลิงก์)

GitHub แนะนำขนาด **1280×640 px** · ใช้ภาพจากโปรเจกต์ได้เลย:

| ภาพ | ขนาดจริง | หมายเหตุ |
|---|---|---|
| `docs/images/09-scene.png` | 1240×820 | ภาพหมู่ครบทุกแบบ — **แนะนำ** (อาจต้องครอปสูงให้เป็น 2:1) |
| `docs/images/05-thai-house-3q.png` | 980×700 | บ้านทรงไทยเดี่ยว ชัดและอ่านง่าย |
| `docs/images/04-compare.png` | 2069×908 | เทียบต้นแบบกับโมเดล (กว้างเกิน 2:1 เล็กน้อย) |

---

## 5. สร้าง repo ด้วย `gh` (คำสั่งเดียวจบ)

```bash
# สร้าง repo ใหม่ + ผูก remote + push + ใส่ description และ topics
cd /data/coding/Hermes-blender-mcp
gh repo create Hermes-blender-mcp --public --source . --remote origin --push \
  --description "MCP Server ให้ Hermes Agent สั่งงาน Blender 5.2 ผ่าน bpy — 12 เครื่องมือ · คลังของฟรี CC0 · ตัวสร้างโมเดลโพลิกอน · ทดสอบ 791 ข้อ"

# ถ้ามี repo อยู่แล้ว ใส่ description/topics ทีหลัง
gh repo edit --description "MCP server letting Hermes Agent drive Blender 5.2 via bpy — 12 tools, keyless CC0 assets, procedural low-poly generators, 791 tests."
for t in mcp model-context-protocol blender bpy hermes-agent ai-agent python \
         procedural-generation low-poly polyhaven 3d-modeling automation windows thai mit-license; do
  gh repo edit --add-topic "$t"
done
```

> ⚠️ ก่อน publish: ตรวจว่า `LICENSE` เป็น MIT แล้ว (มีอยู่) และภาพต้นแบบใน `docs/images/01-*`, `04-*`
> มาจากตัวอย่างที่ผู้ใช้แนบมา — เอกสาร §8 ระบุไว้แล้วว่าลบได้ถ้าเจ้าของไม่ประสงค์ให้เผยแพร่

---

## 6. สิ่งที่ Description **ไม่ควร** พูด (กันอวดเกินจริง)

- ❌ "ปั้นโมเดลละเอียดจากรูปอัตโนมัติ" — โปรเจกต์ทำ blockout/เรขาคณิตจากสเปก ไม่ใช่ image-to-3D
- ⚠️ "ทดสอบกับ Blender จริงครบทุกฟีเจอร์" — ทดสอบบน **Windows 11 + Blender 5.2.2** แล้วด้วย `--selftest`
  (9 ขั้น: ฉาก/สร้าง/ย้าย/วัสดุ/รายละเอียด/สคริปต์/ลบ/เส้นทางคอลเลกชัน/screenshot) แต่ยังไม่ได้
  ไล่ทดสอบทุกเครื่องมือ (เช่น Poly Haven ดาวน์โหลดของจริง · โหมด viewport แบบมีหน้าต่าง)
- ❌ "ใช้ได้ทุกเวอร์ชันของ Blender" — กำหนดเป้าไว้ที่ **5.2 LTS** (โค้ด `bpy` ส่วนใหญ่ใช้ได้กับ 4.x แต่ยังไม่ได้ทดสอบ)
