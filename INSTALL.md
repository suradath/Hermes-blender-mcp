# Installation Guide

This guide installs **LPM Blender MCP** — an MCP server that lets an AI agent
(Hermes Agent, Claude Desktop, or any MCP client) read and drive **Blender 5.2**
through `bpy`.

> 🇹🇭 คู่มือภาษาไทย: **[INSTALL.th.md](INSTALL.th.md)**

There are **two installable pieces**. You only need the first one:

| # | Component | Needed? | What it is |
|---|---|---|---|
| 1 | **MCP server** (`blender_mcp_server.py` + `blender_bridge.py`) | ✅ Yes | Runs on your normal Python and launches Blender itself |
| 2 | **Blender add-on** (`blender_mcp_bridge`) | Optional | Only if you want to drive a Blender window that is already open |

**Contents**

- [1. Requirements](#1-requirements)
- [2. Get the code](#2-get-the-code)
- [3. Install the MCP server](#3-install-the-mcp-server)
- [4. Verify the installation](#4-verify-the-installation)
- [5. Connect your agent](#5-connect-your-agent)
- [6. Optional: install the Blender add-on](#6-optional-install-the-blender-add-on)
- [7. Using it](#7-using-it)
- [8. Uninstall](#8-uninstall)
- [9. Troubleshooting](#9-troubleshooting)

---

## 1. Requirements

| | Requirement | Notes |
|---|---|---|
| Blender | **5.2 LTS** (works from 4.0+) | 5.2 LTS was released 2026-07-14 |
| Python | **3.10+** | Your system Python — **not** Blender's bundled Python |
| Package | `mcp>=2.0,<3` | Installed automatically in step 3 |
| MCP client | Hermes Agent, Claude Desktop, … | Needs the `mcp` package on the client side too (see [5](#5-connect-your-agent)) |

> ⚠️ **Do not try to install the `mcp` package into Blender's own Python.**
> The bridge runs inside Blender and uses **only the standard library** — that is
> deliberate, so nothing has to be installed there.

---

## 2. Get the code

```bash
git clone https://github.com/<you>/blender-mcp.git
cd blender-mcp
```

No git? Download the ZIP from the repository page and extract it.

---

## 3. Install the MCP server

### 🪟 Windows 11 (PowerShell)

The easy way — the installer does everything and reports whether Blender was found:

```powershell
cd C:\path\to\blender-mcp
.\install-windows.bat
```

Or manually:

```powershell
cd C:\path\to\blender-mcp
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe blender_mcp_server.py --check
```

### 🐧 Linux / 🍎 macOS

```bash
cd /path/to/blender-mcp
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python blender_mcp_server.py --check
```

Expected output of `--check`:

```
Blender: /usr/bin/blender (เจอใน PATH)
สคริปต์สะพาน: /path/to/blender-mcp/blender_bridge.py ✅
```

If it says **"หา Blender ไม่เจอ"** (Blender not found), point at it explicitly:

```bash
# Windows
.\.venv\Scripts\python.exe blender_mcp_server.py --check `
  --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"

# Linux / macOS
./.venv/bin/python blender_mcp_server.py --check --blender /usr/bin/blender
```

You can also set the environment variable `BLENDER_EXE` instead of passing
`--blender` every time.

---

## 4. Verify the installation

This is the step that actually proves it works — it starts Blender for real and
calls **every tool once** (in a throwaway default scene, it does not touch your
`.blend` files):

```bash
# Windows
run-blender-mcp.bat --selftest

# Linux / macOS
./run-blender-mcp.sh --selftest
```

Expected:

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

> First run takes 10–30 s (Blender's start-up). A Blender window may flash —
> that is expected with `--gui` off.

**Run the test suite** (no Blender required, 200+ checks):

```bash
bash tests/run_all.sh
```

---

## 5. Connect your agent

### Hermes Agent (recommended path)

Hermes ships an MCP manager that connects, discovers the tools and writes the
config for you:

```bash
hermes mcp add blender \
  --command "/path/to/blender-mcp/.venv/bin/python" \
  --connect-timeout 120 \
  --args /path/to/blender-mcp/blender_mcp_server.py
```

Windows PowerShell:

```powershell
hermes mcp add blender `
  --command "C:\path\to\blender-mcp\.venv\Scripts\python.exe" `
  --connect-timeout 120 `
  --args C:\path\to\blender-mcp\blender_mcp_server.py
```

> ⚠️ **`--args` must be the LAST option.** Anything after it is passed to the
> server process, so `--connect-timeout` placed after `--args` makes the server
> exit and Hermes only reports `Failed to connect: Connection closed`.
> Put all Hermes options *before* `--args`.

> ⚠️ **Hermes needs the `mcp` package in its own Python**, otherwise MCP support
> is disabled *silently* (no tools appear, no error):
>
> ```bash
> ~/.hermes/bin/uv pip install --python "$(which python3)" mcp
> ```

Successful output:

```
  Connecting to 'blender'...
  ✓ Connected! Found 8 tool(s) from 'blender':
    get_scene_hierarchy · add_primitive_mesh · modify_object_transform · …
  Enable all 8 tools? [Y/n/select]: Y
  ✓ Saved 'blender' to ~/.hermes/config.yaml (8/8 tools enabled)
```

Confirm later with:

```bash
hermes mcp list          # status
hermes mcp test blender  # → ✓ Connected · ✓ Tools discovered: 8
```

Then start a new session (or run `/reload-mcp`) to load the tools.

### Manual configuration (Hermes)

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  blender:
    command: /path/to/blender-mcp/.venv/bin/python
    args:
      - /path/to/blender-mcp/blender_mcp_server.py
    connect_timeout: 120.0
    enabled: true
    timeout: 300            # 3D work can be slow; the default is 120
```

### Other MCP clients (Claude Desktop, etc.)

```json
{
  "mcpServers": {
    "blender": {
      "command": "/path/to/blender-mcp/.venv/bin/python",
      "args": ["/path/to/blender-mcp/blender_mcp_server.py"]
    }
  }
}
```

Windows — use double backslashes in JSON:

```json
"command": "C:\\path\\to\\blender-mcp\\.venv\\Scripts\\python.exe"
```

### Useful server options

| Option | Why you would use it |
|---|---|
| `--blend-file "C:\work\house.blend"` | Open that file at start-up instead of the default scene |
| `--blender /path/to/blender.exe` | Blender is not in `PATH` / is not in a standard location |
| `--timeout 300` | Long scripts or renders |
| `--gui` | Launch Blender **with** a window (uses the timer mode) |
| `--attach 127.0.0.1:9876 --token …` | Attach to a Blender that is already running (see step 6) |
| `--check` / `--list-tools` / `--selftest` | Diagnostics |

---

## 6. Optional: install the Blender add-on

**You do not need this** unless you want the AI to work on a Blender window that
is already open (so you can watch it happen).

### 6a. Build the installable ZIP

```bash
python tools/build_addon_zip.py          # or: .venv/bin/python tools/…
```

Output: `dist/blender_mcp_bridge-<version>.zip`

### 6b. Install it in Blender

1. Open Blender → `Edit > Preferences > Add-ons`
2. Click the **▼** arrow (top-right) → **Install from Disk…**
3. Choose `dist/blender_mcp_bridge-1.0.0.zip`
4. Tick the checkbox next to **"LPM Blender MCP Bridge"**

### 6c. Start the bridge

1. In the 3D viewport press **`N`** → open the **"Blender MCP"** tab
2. Press **"Start bridge"** — the panel shows `host:port` (default `127.0.0.1:9876`)
   and a token
3. Press **"Copy connection command"**

### 6d. Point your agent at it

```bash
hermes mcp add blender --command "/path/to/.venv/bin/python" --connect-timeout 60 \
  --args /path/to/blender_mcp_server.py --attach 127.0.0.1:9876 --token "<token from the panel>"
```

> The port must match the panel **and** the token must match. Both are just
> defaults/configurable — the port only ever listens on `127.0.0.1`.
> Never expose this port to a network: the protocol is unencrypted.

<details>
<summary>Manual install (without the ZIP builder) — advanced</summary>

Create a folder named `blender_mcp_bridge` inside Blender's add-ons directory and
put **both** files inside it:

```
<addons>/blender_mcp_bridge/
├── __init__.py            ← from blender_addon/__init__.py
└── blender_bridge.py      ← from the repo root
```

| OS | Add-ons directory (Blender 5.2) |
|---|---|
| Windows | `%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\` |
| Linux | `~/.config/blender/5.2/scripts/addons/` |
| macOS | `~/Library/Application Support/Blender/5.2/scripts/addons/` |

Both files must sit together — the add-on loads the bridge from its own folder.
</details>

---

## 7. Using it

Tools are exposed with your client's prefix, e.g. in Hermes:

```
mcp_blender_get_scene_hierarchy     mcp_blender_get_object_details
mcp_blender_add_primitive_mesh      mcp_blender_delete_object
mcp_blender_modify_object_transform mcp_blender_set_object_material
mcp_blender_execute_blender_script  mcp_blender_save_blend_file
```

Plus two resources: `blender://file/metadata`, `blender://scene/hierarchy`.

Try prompts like:

> "Look at what's in the Blender scene, then add a red cube at (0, 0, 3) scaled to half size."

> "Create three spheres in a row, 2 units apart, each with a different colour."

> "Save the current file as `C:\work\layout.blend`."

**Two things worth knowing**

- **Rotation is in degrees** in every tool (`bpy` uses radians internally — the
  conversion is done for you).
- `execute_blender_script` runs raw `bpy` code with a guard that refuses
  `import os`/`subprocess`, `open()`, `eval()`, dunder access and
  session-destroying operators such as `bpy.ops.wm.quit_blender`. Optional
  `allow_unsafe=true` skips the check. It is a **guardrail, not a sandbox** — see
  the [README](README.md) (ข้อ 6).

---

## 8. Uninstall

```bash
hermes mcp remove blender        # or remove the entry from config.yaml
```

Then delete the project folder (the `.venv` is inside it). If you installed the
add-on: Blender → `Edit > Preferences > Add-ons` → untick → **Remove**, and delete
the `blender_mcp_bridge` folder from the add-ons directory.

Nothing is written outside the project folder, except the add-on folder itself
and a log file under your temp directory (`%TEMP%\blender-mcp\` /
`/tmp/blender-mcp/`).

---

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `หา Blender ไม่เจอ` / Blender not found | Pass `--blender "<full path>"`, or set `BLENDER_EXE`. Note that agent runtimes pass a **filtered environment** to subprocesses (`PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`, `XDG_*` only) — `PROGRAMFILES`/`LOCALAPPDATA` are usually missing, so an explicit path is the reliable fix |
| `Blender ไม่พร้อมภายใน 90 วินาที` | A Blender message box is blocking start-up, or it is genuinely slow. The error message includes the tail of Blender's own output; you can also run `blender -b --python blender_bridge.py -- --port 0 --selftest` by hand |
| `Failed to connect: Connection closed` | Almost always `--args` not being last (see step 5), or the server crashing at start-up. Test by hand: `echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \| .venv/bin/python blender_mcp_server.py` |
| Tools never appear in Hermes | The `mcp` package is missing from Hermes's Python (silent disable), or the server was added after the session started → new session or `/reload-mcp` |
| A tool call times out | Increase `timeout` in the config / `--timeout`. **Blender cannot be interrupted mid-call** — a long loop or render keeps running until it finishes |
| Add-on appears but says it cannot find `blender_bridge.py` | The two files are not in the same folder — re-read [6b](#6b-install-it-in-blender) or set `BLENDER_MCP_DIR` |
| "refused because it breaks the safety guard" | Intended behaviour; pass `allow_unsafe=true` if you really mean it |
| Logs | `%TEMP%\blender-mcp\server-*.log` (Windows) or `/tmp/blender-mcp/server-*.log` |

Still stuck? Open an issue with the log tail and the output of
`python blender_mcp_server.py --check`.

---

## For maintainers — publishing a release

So users do not need Python just to install the add-on:

```bash
python tools/build_addon_zip.py
# attach dist/blender_mcp_bridge-<version>.zip to a GitHub Release
```

Then the add-on section can say "download the `.zip` from Releases → Install from
Disk". Bump `bl_info["version"]` in `blender_addon/__init__.py` before building —
the ZIP is named after it automatically.
