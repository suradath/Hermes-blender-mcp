@echo off
REM ไฟล์นี้เป็น UTF-8 ไม่มี BOM + CRLF — cmd.exe ต้องได้ทั้งสองอย่าง
REM ขึ้นบรรทัดใหม่ด้วย LF อย่างเดียว หรือมี BOM จะทำให้บล็อก if พัง
REM และห้ามมีวงเล็บ ( ) ในข้อความ echo ที่อยู่ข้างในบล็อก if — cmd จะปิดบล็อกผิดที่
REM อาการที่เจอจริง: ". was unexpected at this time."
chcp 65001 >nul 2>&1
REM ============================================================================
REM  Hermes Blender MCP — ตัวเปิด MCP server (Windows 11)
REM  ปกติ Hermes จะเรียกไฟล์นี้ให้เองตาม config.yaml — ไม่ต้องดับเบิลคลิก
REM  แต่ถ้าอยากลองเอง:  run-hermes-blender-mcp.bat --check
REM                      run-hermes-blender-mcp.bat --selftest
REM  ⚠️  ห้ามรันตรง ๆ ในหน้าต่าง cmd เฉย ๆ — มันจะรอคำสั่ง JSON-RPC ทาง stdin
REM ============================================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    if exist ".venv\bin\python.exe" (
        set "PY=.venv\bin\python.exe"
    ) else (
        echo [!] No venv found - using the system Python.
        echo     Run install-windows.bat first - it is recommended.
        echo [!] ยังไม่มี venv — กําลังใช้ python ของเครื่อง แนะนําให้รัน install-windows.bat ก่อน
        set "PY=python"
    )
)

"%PY%" "%CD%\blender_mcp_server.py" %*
