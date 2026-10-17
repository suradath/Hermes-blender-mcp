#!/usr/bin/env bash
# ============================================================================
#  Hermes Blender MCP — ตัวเปิด MCP server (Linux / macOS)
#  ปกติ Hermes จะเรียกให้เองตาม config.yaml
#  ลองเองได้:  ./run-hermes-blender-mcp.sh --check      (ตรวจว่าเจอ Blender ไหม)
#              ./run-hermes-blender-mcp.sh --selftest   (เปิด Blender แล้วลองทุกเครื่องมือ)
#  ⚠️  ห้ามรันเฉย ๆ — มันจะรอคำสั่ง JSON-RPC ทาง stdin
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
  PY=".venv/Scripts/python.exe"
else
  echo "[!] ยังไม่มี venv — กําลังใช้ python ของเครื่อง (แนะนําให้รัน tests/run_all.sh ก่อน)"
  PY="python3"
fi

exec "$PY" "$(pwd)/blender_mcp_server.py" "$@"
