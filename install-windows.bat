@echo off
REM ============================================================================
REM  Hermes Blender MCP — ติดตั้งสำหรับ Windows 11 (รันครั้งเดียว)
REM  ดับเบิลคลิกไฟล์นี้ หรือรันใน cmd/PowerShell:  install-windows.bat
REM
REM  ⚠️ เรื่อง encoding (สำคัญ) — ไฟล์นี้เป็น UTF-8 ไม่มี BOM
REM     cmd.exe เขียนข้อความ echo เป็น "ไบต์ดิบ" ตาม codepage ของหน้าต่าง
REM     ถ้า codepage ไม่ใช่ 65001 ภาษาไทยจะกลายเป็นตัวประหลาด
REM     จึงต้อง chcp 65001 ก่อนบรรทัดที่มีภาษาไทยทุกบรรทัด
REM     และข้อความขั้นตอน (echo) ใช้ภาษาอังกฤษล้วน เพื่อให้อ่านได้ทุกเครื่อง
REM ============================================================================
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   Hermes Blender MCP - Windows 11 installer
echo   ติดตั้ง Hermes Blender MCP สําหรับ Windows 11
echo ============================================================
echo.

REM ---- 1) หา Python ของเครื่อง (ไม่ใช่ของ Blender) ----
set "PY="
for %%P in (python.exe py.exe) do (
    if not defined PY (
        where %%P >nul 2>nul && set "PY=%%P"
    )
)
if not defined PY (
    echo [X] Python not found.
    echo     Install from https://www.python.org/downloads/ and tick
    echo     "Add python.exe to PATH" during setup.
    echo.
    echo [X] หา Python ไม่เจอ — ติดตั้งจาก python.org แล้วติ๊ก "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)
echo [1/4] Using Python: %PY%
%PY% -c "import sys; print('      version', sys.version.split()[0])"

REM ---- 2) สร้าง venv (ถ้ามีอยู่แล้วก็ใช้ต่อ) ----
echo.
if exist ".venv\Scripts\python.exe" (
    echo [2/4] venv already present: .venv
) else (
    echo [2/4] Creating venv in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [X] Could not create venv.
        echo [X] สร้าง venv ไม่สําเร็จ — ตรวจสิทธิ์เขียนโฟลเดอร์นี้
        pause
        exit /b 1
    )
)

REM ---- 3) ติดตั้ง mcp SDK ----
echo.
echo [3/4] Installing required packages ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Package install failed.
    echo [X] ติดตั้งแพ็กเกจไม่สําเร็จ — ตรวจอินเทอร์เน็ต/proxy แล้วรันใหม่
    pause
    exit /b 1
)

REM ---- 4) ตรวจว่าเจอ Blender และสคริปต์ครบ ----
echo.
echo [4/4] Checking the installation ...
".venv\Scripts\python.exe" blender_mcp_server.py --check
set "CHECK=%ERRORLEVEL%"
echo.
echo ============================================================
if "%CHECK%"=="0" (
    echo   Done - Blender found.
    echo   เสร็จแล้ว! เจอ Blender เรียบร้อย
) else (
    echo   Packages OK, but Blender was not found.
    echo   ติดตั้งแพ็กเกจเสร็จ แต่ "หา Blender ไม่เจอ"
    echo   Fix: set BLENDER_EXE, or add --blender to the Hermes config:
    echo   args: ["%CD%\blender_mcp_server.py", "--blender", "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"]
)
echo ============================================================
echo.
echo Next step - put this in %USERPROFILE%\.hermes\config.yaml
echo ขั้นต่อไป - ใส่ค่าต่อไปนี้ในไฟล์ %USERPROFILE%\.hermes\config.yaml
echo.
echo     mcp_servers:
echo       blender:
echo         command: "%CD%\.venv\Scripts\python.exe"
echo         args: ["%CD%\blender_mcp_server.py"]
echo         timeout: 300
echo         connect_timeout: 120
echo.
echo Then restart Hermes Agent.
echo แล้วรีสตาร์ต Hermes Agent
echo Thai manual: INSTALL.th.md   /   README.md
echo.
pause
