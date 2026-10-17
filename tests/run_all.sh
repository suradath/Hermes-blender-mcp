#!/usr/bin/env bash
# ============================================================================
#  รันชุดทดสอบทั้งหมดของ LPM Blender MCP
#    bash tests/run_all.sh
#  ใช้ venv ของโปรเจกต์ถ้ามี (ต้องมี mcp ติดตั้งแล้ว)
# ============================================================================
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [[ -x ".venv/bin/python" ]]; then
    PY=".venv/bin/python"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
    PY=".venv/Scripts/python.exe"
else
    PY="python3"
fi

echo "======================================================================"
echo "  ทดสอบ LPM Blender MCP  (Hermes ⇄ Blender 5.2)"
echo "  โปรเจกต์: $ROOT"
echo "  Python  : $($PY -V 2>&1)"
echo "======================================================================"

declare -a NAMES=(
    "test_addon_structure.py"
    "test_docs_links.py"
    "test_example_character.py"
    "test_server_utils.py"
    "test_bridge_logic.py"
    "test_mcp_e2e.py"
)
declare -a LOGS=()
OVERALL=0

for name in "${NAMES[@]}"; do
    printf '  %-28s ' "$name"
    log="/tmp/blender_mcp_${name%.py}.log"
    if "$PY" -u "tests/$name" > "$log" 2>&1; then
        printf '✅ %s\n' "$(grep -E 'ผ่านทั้งหมด' "$log" | tail -1 | sed 's/^[[:space:]]*//')"
        LOGS+=("$name|ok|$log")
    else
        printf '❌ ล้มเหลว — ดู %s\n' "$log"
        LOGS+=("$name|fail|$log")
        OVERALL=1
    fi
done

echo "----------------------------------------------------------------------"
if [[ "$OVERALL" == "0" ]]; then
    echo "  🎉 ผ่านทั้งหมด ${#NAMES[@]} ชุด"
else
    echo "  ❌ มีชุดที่ไม่ผ่าน — รายละเอียดด้านล่าง"
    for entry in "${LOGS[@]}"; do
        IFS='|' read -r n s l <<< "$entry"
        [[ "$s" == "fail" ]] && { echo; echo "── $n ──"; tail -25 "$l"; }
    done
fi
echo "======================================================================"
exit "$OVERALL"
