@echo off
REM ============================================================================
REM  LPM Blender MCP — ติดตั้งสำหรับ Windows 11 (รันครั้งเดียว)
REM  ดับเบิลคลิกไฟล์นี้ หรือรันใน cmd/PowerShell:  install-windows.bat
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   ติดตั้ง LPM Blender MCP สําหรับ Windows 11
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
    echo [X] หา Python ไม่เจอ
    echo     ติดตั้งจาก https://www.python.org/downloads/ แล้วติ๊ก
    echo     "Add python.exe to PATH" ตอนติดตั้ง
    echo.
    pause
    exit /b 1
)
echo [1/4] ใช้ Python: %PY%
%PY% -c "import sys; print('      เวอร์ชัน', sys.version.split()[0])"

REM ---- 2) สร้าง venv (ถ้ามีอยู่แล้วก็ใช้ต่อ) ----
echo.
if exist ".venv\Scripts\python.exe" (
    echo [2/4] มี venv อยู่แล้ว: .venv
) else (
    echo [2/4] กําลังสร้าง venv ที่ .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [X] สร้าง venv ไม่สําเร็จ
        pause
        exit /b 1
    )
)

REM ---- 3) ติดตั้ง mcp SDK ----
echo.
echo [3/4] ติดตั้งแพ็กเกจที่ต้องใช้ ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] ติดตั้งแพ็กเกจไม่สําเร็จ
    pause
    exit /b 1
)

REM ---- 4) ตรวจว่าเจอ Blender และสคริปต์ครบ ----
echo.
echo [4/4] ตรวจการติดตั้ง ...
".venv\Scripts\python.exe" blender_mcp_server.py --check
set "CHECK=%ERRORLEVEL%"
echo.
echo ============================================================
if "%CHECK%"=="0" (
    echo   เสร็จแล้ว! เจอ Blender เรียบร้อย
) else (
    echo   ติดตั้งแพ็กเกจเสร็จ แต่ "หา Blender ไม่เจอ"
    echo   แก้ได้โดยตั้งค่าตัวแปร BLENDER_EXE หรือแก้ไฟล์ config ของ Hermes
    echo   ให้มีบรรทัด:  args: [..., "--blender", "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe"]
)
echo ============================================================
echo.
echo ขั้นต่อไป: ใส่ค่าต่อไปนี้ในไฟล์ %USERPROFILE%\.hermes\config.yaml
echo.
echo     mcp_servers:
echo       blender:
echo         command: "%CD%\.venv\Scripts\python.exe"
echo         args: ["%CD%\blender_mcp_server.py"]
echo         timeout: 300
echo         connect_timeout: 120
echo.
echo แล้วรีสตาร์ต Hermes Agent  (อ่านรายละเอียดใน README.md)
echo.
pause
