@echo off
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
        echo [!] ยังไม่มี venv — กําลังใช้ python ของเครื่อง
        echo     แนะนําให้รัน install-windows.bat ก่อน
        set "PY=python"
    )
)

"%PY%" "%CD%\blender_mcp_server.py" %*
