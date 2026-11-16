#!/usr/bin/env python3
"""
ParaGravity - Universal Plug-and-Play Installer & Uninstaller
Works seamlessly across Windows, macOS, and Linux.

Usage:
    python install.py             # Install / update ParaGravity & in-DOM Account Switcher
    python install.py --uninstall # Completely restore factory Antigravity & remove CLI
    python install.py --status    # Check installation status & diagnostics
    python install.py --help      # Show help options
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import subprocess
import argparse
import tempfile
from pathlib import Path

VERSION = "Version 0.1.0"

# ANSI Colors for beautiful, friendly terminal output
if sys.platform == "win32":
    os.system("")  # Enable ANSI escape sequences on Windows 10+

C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"

SILENT = False

def print_banner():
    if not SILENT:
        print(f"""
{C_CYAN}{C_BOLD}  ╔═════════════════════════════════════════════════════════════════╗
  ║   Regravity {VERSION} • Native Multi-Account & Sandbox Manager    ║
  ║   Direct Google OAuth • 100% Zero-Proxy • Safe Local Storage    ║
  ╚═════════════════════════════════════════════════════════════════╝{C_RESET}
""")

def log_step(msg: str):
    if not SILENT:
        print(f"{C_CYAN}[i]{C_RESET} {msg}")

def log_success(msg: str):
    if not SILENT:
        print(f"{C_GREEN}[✓]{C_RESET} {C_BOLD}{msg}{C_RESET}")

def log_warn(msg: str):
    if not SILENT:
        print(f"{C_YELLOW}[!]{C_RESET} {msg}")

def log_error(msg: str):
    if not SILENT:
        print(f"{C_RED}[✗]{C_RESET} {C_BOLD}{msg}{C_RESET}")

def is_asar_patched(asar_file: Path | None) -> bool:
    """Fast check (<5ms) to determine if an app.asar file contains Regravity patches."""
    if not asar_file or not asar_file.is_file():
        return False
    try:
        with open(asar_file, "rb") as f:
            content = f.read()
            return b"paragravityNative" in content and b"paragravity:listAccounts" in content
    except Exception:
        return False

def get_home_dir() -> Path:
    return Path.home()

def get_gemini_dir() -> Path:
    return get_home_dir() / ".gemini"

def get_plugin_dir() -> Path:
    return get_gemini_dir() / "config" / "plugins" / "paragravity"

def get_local_bin_dir() -> Path:
    return get_home_dir() / ".local" / "bin"

def find_antigravity_asar(override_path: str | None = None) -> Path | None:
    """Finds the app.asar file across Windows, macOS, and Linux."""
    if override_path:
        p = Path(override_path).resolve()
        if p.is_file():
            return p
        if (p / "resources" / "app.asar").is_file():
            return p / "resources" / "app.asar"
        if (p / "Contents" / "Resources" / "app.asar").is_file():
            return p / "Contents" / "Resources" / "app.asar"

    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    prog_files = os.environ.get("PROGRAMFILES")
    prog_files_x86 = os.environ.get("PROGRAMFILES(X86)")

    if sys.platform == "win32":
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs" / "antigravity" / "resources" / "app.asar")
            candidates.append(Path(local_app_data) / "antigravity" / "resources" / "app.asar")
        if prog_files:
            candidates.append(Path(prog_files) / "Antigravity" / "resources" / "app.asar")
            candidates.append(Path(prog_files) / "antigravity" / "resources" / "app.asar")
        if prog_files_x86:
            candidates.append(Path(prog_files_x86) / "Antigravity" / "resources" / "app.asar")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Antigravity.app/Contents/Resources/app.asar"))
        candidates.append(get_home_dir() / "Applications" / "Antigravity.app" / "Contents" / "Resources" / "app.asar")
    else:  # Linux
        candidates.append(Path("/opt/antigravity/resources/app.asar"))
        candidates.append(Path("/usr/lib/antigravity/resources/app.asar"))
        candidates.append(get_home_dir() / ".local" / "share" / "antigravity" / "resources" / "app.asar")

    which_exe = shutil.which("Antigravity") or shutil.which("antigravity")
    if which_exe:
        exe_path = Path(which_exe).resolve()
        candidates.append(exe_path.parent / "resources" / "app.asar")
        candidates.append(exe_path.parent.parent / "Resources" / "app.asar")

    for c in candidates:
        if c.is_file():
            return c
    return None

def is_antigravity_running() -> bool:
    """Checks if any Antigravity IDE process is currently running."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq Antigravity.exe"], text=True, stderr=subprocess.DEVNULL)
            return "Antigravity.exe" in out
        else:
            out = subprocess.check_output(["pgrep", "-f", "Antigravity"], text=True, stderr=subprocess.DEVNULL)
            return bool(out.strip())
    except Exception:
        return False

def close_antigravity_processes() -> bool:
    """Safely closes running Antigravity processes."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "Antigravity.exe"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["pkill", "-f", "Antigravity"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

def ensure_npx_asar() -> bool:
    """Verifies that npx or asar is available."""
    return bool(shutil.which("npx") or shutil.which("asar"))

def extract_asar(asar_file: Path, target_dir: Path) -> bool:
    """Extracts app.asar using npx asar."""
    # Ensure expected unpacked directory exists if extracting from a backup (e.g. app.asar.bak)
    expected_unpacked = asar_file.parent / f"{asar_file.name}.unpacked"
    real_unpacked = asar_file.with_name("app.asar.unpacked")
    if not expected_unpacked.exists() and real_unpacked.is_dir():
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(expected_unpacked), str(real_unpacked)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                os.symlink(real_unpacked, expected_unpacked, target_is_directory=True)
        except Exception as e:
            log_warn(f"Could not link {expected_unpacked} to {real_unpacked}: {e}")

    cmd = ["npx", "asar", "extract", str(asar_file), str(target_dir)]
    if sys.platform == "win32":
        cmd[0] = "npx.cmd" if shutil.which("npx.cmd") else "npx"
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        log_error(f"Failed to extract asar via npx: {e}")
        return False

def pack_asar(source_dir: Path, target_file: Path) -> bool:
    """Packs target directory into app.asar using npx asar."""
    cmd = ["npx", "asar", "pack", str(source_dir), str(target_file)]
    if sys.platform == "win32":
        cmd[0] = "npx.cmd" if shutil.which("npx.cmd") else "npx"
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        log_error(f"Failed to pack asar via npx: {e}")
        return False

def patch_main_js(main_js_path: Path) -> bool:
    """Patches dist/main.js to support multi-window parallel launch with custom --user-data-dir."""
    if not main_js_path.is_file():
        log_error(f"dist/main.js not found at {main_js_path}")
        return False

    code = main_js_path.read_text(encoding="utf-8")
    if "hasCustomUserData" in code:
        log_step("dist/main.js is already patched for multi-window support.")
        return True

    target = "const gotTheLock = electron_1.app.requestSingleInstanceLock();"
    if target not in code:
        log_warn("Could not find exact singleInstanceLock target in main.js, scanning fallback...")
        target = "app.requestSingleInstanceLock();"
        if target not in code:
            log_error("Could not find requestSingleInstanceLock pattern in main.js")
            return False

    replacement = """let hasCustomUserData = false;
for (const arg of process.argv) {
    if (arg.startsWith('--user-data-dir=')) {
        const customUserData = arg.slice('--user-data-dir='.length).replace(/^"(.*)"$/, '$1');
        if (customUserData) {
            electron_1.app.setPath('userData', customUserData);
            hasCustomUserData = true;
        }
        break;
    }
}
const gotTheLock = hasCustomUserData || electron_1.app.requestSingleInstanceLock();"""

    # Check if the --user-data-dir loop was already there
    user_data_loop = "for (const arg of process.argv)"
    if user_data_loop in code and "electron_1.app.setPath('userData', customUserData)" in code:
        # Replace the combined loop and lock check
        prefix_start = code.find(user_data_loop)
        lock_end = code.find(target) + len(target)
        new_code = code[:prefix_start] + replacement + code[lock_end:]
    else:
        new_code = code.replace(target, replacement, 1)

    main_js_path.write_text(new_code, encoding="utf-8")
    return True

def strip_paragravity_ipc_handlers(code: str) -> str:
    """Remove every previously injected paragravity ipcMain.handle(...) block.

    Older releases injected the bridge without the "// --- ParaGravity Native
    IPC Bridge ---" marker and without cancelAddAccount. Matching on a marker
    leaves those handlers behind, and Electron throws
    "Attempted to register a second handler for 'paragravity:...'", which aborts
    startup and blanks the whole IDE. Strip every handler by brace matching
    instead so the bridge can always be re-injected cleanly.
    """
    needle = "ipcMain.handle('paragravity:"
    while needle in code:
        idx = code.find(needle)
        # Walk back to the start of the line (drops the leading indentation).
        line_start = code.rfind("\n", 0, idx) + 1
        brace = code.find("{", idx)
        if brace == -1:
            # Malformed injection: drop the whole line as a safety net.
            line_end = code.find("\n", idx)
            code = code[:line_start] + (code[line_end:] if line_end != -1 else "")
            continue
        depth = 0
        i = brace
        end = -1
        while i < len(code):
            ch = code[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    # Consume the trailing ")" and ";" of `.handle(...)`.
                    j = i + 1
                    while j < len(code) and code[j] in " \t\r\n":
                        j += 1
                    if j < len(code) and code[j] == ")":
                        j += 1
                        while j < len(code) and code[j] in " \t\r\n":
                            j += 1
                        if j < len(code) and code[j] == ";":
                            j += 1
                    end = j
                    break
            i += 1
        if end == -1:
            break
        code = code[:line_start] + code[end:]

    # Drop a leftover bridge marker comment from any older release.
    code = code.replace("    // --- ParaGravity Native IPC Bridge ---\n", "")
    timer_marker = "if (!global.__paragravitySyncTimer)"
    if timer_marker in code:
        t_idx = code.find(timer_marker)
        t_line_start = code.rfind("\n", 0, t_idx) + 1
        t_brace = code.find("{", t_idx)
        if t_brace != -1:
            t_depth = 0
            t_i = t_brace
            while t_i < len(code):
                if code[t_i] == "{":
                    t_depth += 1
                elif code[t_i] == "}":
                    t_depth -= 1
                    if t_depth == 0:
                        code = code[:t_line_start] + code[t_i + 1:]
                        break
                t_i += 1
    return code


def patch_ipc_handlers(ipc_path: Path) -> bool:
    """Patches dist/ipcHandlers.js to register paragravity native IPC handlers."""
    if not ipc_path.is_file():
        log_error(f"dist/ipcHandlers.js not found at {ipc_path}")
        return False

    code = ipc_path.read_text(encoding="utf-8")
    if "paragravity:syncConversations" in code and "executeJavaScript" in code and "paragravity:listAccounts" in code:
        log_step("dist/ipcHandlers.js is already patched with paragravity handlers.")
        return True

    # Strip any earlier injection regardless of whether it used the marker
    # comment or had cancelAddAccount, so we never register duplicate handlers.
    if "paragravity:" in code or "global.__paragravitySyncTimer" in code:
        before = code.count("ipcMain.handle('paragravity:")
        code = strip_paragravity_ipc_handlers(code)
        after = code.count("ipcMain.handle('paragravity:")
        log_step(f"Stripped {before - after} stale paragravity IPC handler(s).")

    ipc_block = """
    // --- ParaGravity Native IPC Bridge ---
    let activeAuthChild = null;
    electron_1.ipcMain.handle('paragravity:listAccounts', async (_event, force) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        const args = force ? [script, '--list', '--force'] : [script, '--list'];
        return new Promise((resolve) => {
            cp.execFile('python', args, { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ active: '', accounts: [], error: err.message });
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ active: '', accounts: [], error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:syncConversations', async () => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--sync-conversations'], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try {
                    const res = JSON.parse(stdout);
                    if (res && res.changes_detected > 0) {
                        electron_1.webContents.getAllWebContents().forEach(wc => {
                            if (!wc.isDestroyed()) wc.send('paragravity:conversationsUpdated');
                        });
                    }
                    resolve(res);
                } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    if (!global.__paragravitySyncTimer) {
        global.__paragravitySyncTimer = setInterval(() => {
            const cp = require('child_process');
            const path = require('path');
            const os = require('os');
            const fs = require('fs');

            // Signal handler for opening Regravity UI and Modals
            const sigFile = path.join(os.homedir(), '.gemini', '.open_regravity_ui');
            if (fs.existsSync(sigFile)) {
                try { fs.unlinkSync(sigFile); } catch (e) {}
                electron_1.webContents.getAllWebContents().forEach(wc => {
                    if (!wc.isDestroyed()) {
                        wc.send('paragravity:toggleUI');
                        wc.executeJavaScript(`
                            if (window.__pgOpen) {
                                window.__pgOpen();
                            } else {
                                const btn = document.querySelector('[data-testid="account-switcher-button"]');
                                if (btn) btn.click();
                            }
                        `).catch(() => {});
                    }
                });
            }
            const modalSig = path.join(os.homedir(), '.gemini', '.open_regravity_modal');
            if (fs.existsSync(modalSig)) {
                let mType = '';
                try {
                    mType = fs.readFileSync(modalSig, 'utf-8').trim();
                    fs.unlinkSync(modalSig);
                } catch (e) {}
                if (mType) {
                    electron_1.webContents.getAllWebContents().forEach(wc => {
                        if (!wc.isDestroyed()) {
                            wc.send('paragravity:openModal', mType);
                            wc.executeJavaScript(`
                                if (window.__pgOpen) window.__pgOpen();
                                setTimeout(() => {
                                    if ('${mType}' === 'detect' && window.__pgDetectAccounts) {
                                        window.__pgDetectAccounts();
                                    } else if ('${mType}'.startsWith('inspect:') && window.__pgInspect) {
                                        window.__pgInspect('${mType}'.split(':')[1]);
                                    }
                                }, 250);
                            `).catch(() => {});
                        }
                    });
                }
            }

            const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
            cp.execFile('python', [script, '--sync-conversations'], { windowsHide: true }, (err, stdout) => {
                if (!err && stdout) {
                    try {
                        const res = JSON.parse(stdout);
                        if (res && res.changes_detected > 0) {
                            electron_1.webContents.getAllWebContents().forEach(wc => {
                                if (!wc.isDestroyed()) wc.send('paragravity:conversationsUpdated');
                            });
                        }
                    } catch (e) {}
                }
            });
        }, 1500);
    }
    electron_1.ipcMain.handle('paragravity:switchAccount', async (_event, email) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--swap', email], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try {
                    const res = JSON.parse(stdout);
                    cp.execFile('python', [script, '--sync-conversations'], { windowsHide: true }, () => {});
                    resolve(res);
                } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:launchAccount', async (_event, email) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--launch', email], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try {
                    const res = JSON.parse(stdout);
                    setTimeout(() => {
                        cp.execFile('python', [script, '--sync-conversations'], { windowsHide: true }, () => {});
                    }, 1000);
                    resolve(res);
                } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:addAccount', async (_event, loginHint) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        const args = loginHint ? [script, '--auth', loginHint] : [script, '--auth'];
        return new Promise((resolve) => {
            if (activeAuthChild) {
                try { activeAuthChild.kill(); } catch (e) {}
                activeAuthChild = null;
            }
            const child = cp.execFile('python', args, { windowsHide: true }, (err, stdout) => {
                if (activeAuthChild === child) activeAuthChild = null;
                if (err) {
                    if (child.killed) return resolve({ success: false, cancelled: true, error: 'Authentication cancelled by user.' });
                    return resolve({ success: false, error: err.message });
                }
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ success: false, error: e.message }); }
            });
            activeAuthChild = child;
        });
    });
    electron_1.ipcMain.handle('paragravity:cancelAddAccount', async () => {
        const http = require('http');
        try {
            const req = http.get('http://127.0.0.1:50000/cancel', () => {});
            req.on('error', () => {});
            req.setTimeout(800, () => req.destroy());
        } catch (e) {}
        setTimeout(() => {
            if (activeAuthChild) {
                try { activeAuthChild.kill('SIGTERM'); } catch (e) {}
                activeAuthChild = null;
            }
        }, 200);
        return { success: true, message: 'Authentication cancelled.' };
    });
    electron_1.ipcMain.handle('paragravity:importActiveSession', async () => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--import-active'], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:removeAccount', async (_event, email) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--remove', email], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:resetProfile', async (_event, email) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--reset', email], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:inspectAccount', async (_event, email) => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--inspect', email], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ success: false, error: err.message });
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ success: false, error: e.message }); }
            });
        });
    });
    electron_1.ipcMain.handle('paragravity:detectAccounts', async () => {
        const cp = require('child_process');
        const path = require('path');
        const os = require('os');
        const script = path.join(os.homedir(), '.gemini', 'config', 'plugins', 'paragravity', 'session_swap.py');
        return new Promise((resolve) => {
            cp.execFile('python', [script, '--detect'], { windowsHide: true }, (err, stdout) => {
                if (err) return resolve({ detected: [], error: err.message });
                try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ detected: [], error: e.message }); }
            });
        });
    });
"""

    pos = code.find("function registerIpcHandlers(")
    if pos != -1:
        param_end = code.find(") {", pos)
        brace = code.find("{", param_end if param_end != -1 else pos)
        new_code = code[:brace + 1] + "\n" + ipc_block + "\n" + code[brace + 1:]
        ipc_path.write_text(new_code, encoding="utf-8")
        return True

    # Fallback to appending
    new_code = code + "\n" + ipc_block + "\n"
    ipc_path.write_text(new_code, encoding="utf-8")
    return True

def patch_preload_js(preload_path: Path, client_code: str) -> bool:
    """Patches dist/preload.js to expose window.paragravityNative and inject client.js into main world."""
    if not preload_path.is_file():
        log_error(f"dist/preload.js not found at {preload_path}")
        return False

    code = preload_path.read_text(encoding="utf-8")

    api_block = """
const paragravityNativeAPI = {
    listAccounts: (force) => electron_1.ipcRenderer.invoke('paragravity:listAccounts', Boolean(force)),
    switchAccount: (email) => electron_1.ipcRenderer.invoke('paragravity:switchAccount', email),
    launchAccount: (email) => electron_1.ipcRenderer.invoke('paragravity:launchAccount', email),
    addAccount: (loginHint) => electron_1.ipcRenderer.invoke('paragravity:addAccount', loginHint),
    cancelAddAccount: () => electron_1.ipcRenderer.invoke('paragravity:cancelAddAccount'),
    importActiveSession: () => electron_1.ipcRenderer.invoke('paragravity:importActiveSession'),
    removeAccount: (email) => electron_1.ipcRenderer.invoke('paragravity:removeAccount', email),
    resetProfile: (email) => electron_1.ipcRenderer.invoke('paragravity:resetProfile', email),
    inspectAccount: (email) => electron_1.ipcRenderer.invoke('paragravity:inspectAccount', email),
    detectAccounts: () => electron_1.ipcRenderer.invoke('paragravity:detectAccounts'),
    syncConversations: () => electron_1.ipcRenderer.invoke('paragravity:syncConversations'),
    onConversationsUpdated: (cb) => electron_1.ipcRenderer.on('paragravity:conversationsUpdated', cb),
    onToggleUI: (cb) => electron_1.ipcRenderer.on('paragravity:toggleUI', cb),
    onOpenModal: (cb) => electron_1.ipcRenderer.on('paragravity:openModal', (_e, type) => cb(type))
};
try {
    electron_1.contextBridge.exposeInMainWorld('paragravityNative', paragravityNativeAPI);
} catch (e) {
    window.paragravityNative = paragravityNativeAPI;
}
"""

    runner_block = f"""
function installAccountSwitcherNavButton() {{
    runMain({json.dumps(client_code)});
}}
installAccountSwitcherNavButton();
"""

    # 1. Ensure API bridge is present
    if "onToggleUI" not in code and "const paragravityNativeAPI =" in code:
        start_idx = code.find("const paragravityNativeAPI =")
        end_marker = "window.paragravityNative = paragravityNativeAPI;"
        end_idx = code.find(end_marker)
        if end_idx != -1:
            end_brace = code.find("}", end_idx)
            if end_brace != -1:
                code = code[:start_idx] + api_block.strip() + "\n" + code[end_brace + 1:]
    elif "paragravityNativeAPI" not in code:
        pos = code.find("electron_1.contextBridge.exposeInMainWorld(")
        if pos != -1:
            code = code[:pos] + api_block + "\n" + code[pos:]
        else:
            code = api_block + "\n" + code
    if "paragravityNativeAPI" not in code:
        pos = code.find("electron_1.contextBridge.exposeInMainWorld(")
        if pos != -1:
            code = code[:pos] + api_block + "\n" + code[pos:]
        else:
            code = api_block + "\n" + code

    # 2. Update or inject client runner block
    tag = "function installAccountSwitcherNavButton()"
    if tag in code:
        pos_start = code.find(tag)
        pos_call = code.find("installAccountSwitcherNavButton();", pos_start)
        if pos_call != -1:
            end_pos = pos_call + len("installAccountSwitcherNavButton();")
            code = code[:pos_start] + runner_block.strip() + code[end_pos:]
        else:
            code = code[:pos_start] + runner_block.strip()
    else:
        code = code.rstrip() + "\n" + runner_block.strip() + "\n"

    preload_path.write_text(code, encoding="utf-8")
    return True

def install_cli_launchers(repo_dir: Path) -> bool:
    """Installs global CLI launchers for regravity, rgrav, paragravity, and pgrav into ~/.local/bin."""
    local_bin = get_local_bin_dir()
    local_bin.mkdir(parents=True, exist_ok=True)

    session_swap_py = get_plugin_dir() / "session_swap.py"

    if sys.platform == "win32":
        cmd_content = f'@echo off\npython "{session_swap_py}" %*\n'
        for alias in ["regravity.cmd", "rgrav.cmd", "paragravity.cmd", "pgrav.cmd"]:
            target = local_bin / alias
            target.write_text(cmd_content, encoding="utf-8")
        log_success(f"Installed Windows CLI launchers (regravity, rgrav, paragravity, pgrav) in {local_bin}")
    else:
        sh_content = f'#!/usr/bin/env bash\nexec python3 "{session_swap_py}" "$@"\n'
        for alias in ["regravity", "rgrav", "paragravity", "pgrav"]:
            target = local_bin / alias
            target.write_text(sh_content, encoding="utf-8")
            target.chmod(0o755)
        log_success(f"Installed Unix CLI launchers in {local_bin}")

    # Ensure local_bin is on PATH
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                try:
                    curr_path, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    curr_path = ""
                local_bin_str = str(local_bin.resolve())
                if local_bin_str.lower() not in curr_path.lower():
                    new_path = f"{curr_path};{local_bin_str}" if curr_path else local_bin_str
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                    log_success(f"Added {local_bin} to User PATH automatically.")
                else:
                    log_step(f"{local_bin} is already in User PATH.")
        except Exception as e:
            log_warn(f"Could not automatically update User PATH: {e}")
    else:
        path_env = os.environ.get("PATH", "")
        if str(local_bin).lower() not in path_env.lower():
            log_warn(f"{local_bin} is not yet in your PATH. Add 'export PATH=\"$HOME/.local/bin:$PATH\"' to your shell profile.")
    return True

def deploy_plugin_files(source_dir: Path) -> bool:
    """Copies all plugin assets and configurations into ~/.gemini/config/plugins/paragravity."""
    target_dir = get_plugin_dir().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # If running directly from the target plugin directory, skip self-copying
    if source_dir.resolve() == target_dir:
        log_step("Already running from plugin directory ~/.gemini/config/plugins/paragravity.")
        accounts_dir = get_gemini_dir() / "accounts"
        accounts_dir.mkdir(parents=True, exist_ok=True)
        return True

    items_to_copy = [
        "session_swap.py",
        "client.js",
        "plugin.json",
        "README.md",
        "LICENSE",
        "rules",
        "skills",
        "assets"
    ]

    for item in items_to_copy:
        src = source_dir / item
        dst = target_dir / item
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, dst)

    # Ensure accounts directory exists
    accounts_dir = get_gemini_dir() / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)

    log_success(f"Deployed plugin bundle to {target_dir}")
    return True

def do_uninstall(asar_path: Path | None):
    """Restores factory Antigravity state and removes CLI launchers."""
    print(f"\n{C_BOLD}Starting ParaGravity Uninstallation...{C_RESET}\n")

    # 1. Restore ASAR
    if asar_path and asar_path.is_file():
        bak = asar_path.with_name("app.asar.bak")
        if bak.is_file():
            log_step(f"Restoring factory app.asar from {bak}...")
            if is_antigravity_running():
                log_warn("Antigravity is currently running. Closing it to restore original files...")
                close_antigravity_processes()
            shutil.copy2(bak, asar_path)
            log_success("Restored original factory app.asar.")
        else:
            log_warn("No app.asar.bak found. Existing app.asar was left untouched.")

    # 2. Stop and remove Guardian Watchdog service
    try:
        import guardian
        guardian.stop_guardian()
        guardian.uninstall_autostart()
        log_step("Stopped and unregistered Regravity Guardian watchdog.")
    except Exception:
        pass

    # 3. Remove CLI launchers
    local_bin = get_local_bin_dir()
    for name in ["regravity.cmd", "rgrav.cmd", "paragravity.cmd", "pgrav.cmd", "paragravity", "pgrav"]:
        p = local_bin / name
        if p.is_file():
            p.unlink()
            log_step(f"Removed CLI shortcut {name}")

    log_success("Regravity has been successfully uninstalled. Factory state restored.")
    print()

def do_status(asar_path: Path | None):
    """Prints current installation health and diagnostic overview."""
    print(f"\n{C_BOLD}Regravity Diagnostic & Status Overview:{C_RESET}\n")

    # Antigravity installation
    if asar_path and asar_path.is_file():
        log_success(f"Antigravity ASAR located: {asar_path} ({asar_path.stat().st_size:,} bytes)")
        bak = asar_path.with_name("app.asar.bak")
        if bak.is_file():
            log_success(f"Factory backup present: {bak} ({bak.stat().st_size:,} bytes)")
        else:
            log_warn("No backup (app.asar.bak) created yet.")
    else:
        log_error("Antigravity app.asar could not be located.")

    # Guardian Watchdog
    try:
        import guardian
        g_pid = guardian.is_guardian_running()
        if g_pid:
            log_success(f"Regravity Guardian: ACTIVE (PID {g_pid}) • Update resilience enabled")
        else:
            log_warn("Regravity Guardian: STOPPED (run 'python guardian.py --start' to enable update resilience)")
    except Exception:
        pass

    # Plugin directory
    plug_dir = get_plugin_dir()
    if (plug_dir / "plugin.json").is_file():
        log_success(f"Plugin installed at {plug_dir}")
    else:
        log_warn(f"Plugin not found in {plug_dir}")

    # Accounts
    accounts_dir = get_gemini_dir() / "accounts"
    if accounts_dir.is_dir():
        acc_count = len(list(accounts_dir.glob("*.json")))
        log_success(f"Managed Accounts: {acc_count} configured in {accounts_dir}")
    else:
        log_step(f"Accounts directory: {accounts_dir} (empty)")

    # CLI
    local_bin = get_local_bin_dir()
    cli_found = any((local_bin / x).is_file() for x in ["paragravity.cmd", "pgrav.cmd", "paragravity"])
    if cli_found:
        log_success(f"CLI launchers found in {local_bin}")
    else:
        log_warn(f"CLI launchers not found in {local_bin}")
    print()

def do_install(asar_path: Path | None, source_dir: Path, skip_asar: bool = False, force: bool = False):
    """Executes the full plug-and-play installation."""
    print(f"\n{C_BOLD}Installing Regravity {VERSION}...{C_RESET}\n")

    # 1. Deploy Plugin Bundle
    log_step("Deploying ParaGravity plugin bundle...")
    deploy_plugin_files(source_dir)

    # 2. Install CLI Launchers
    log_step("Configuring global CLI shortcuts (paragravity, pgrav)...")
    install_cli_launchers(source_dir)

    if skip_asar:
        log_warn("Skipping ASAR patching as requested (--skip-asar).")
        log_success("CLI and Plugin configuration completed successfully!")
        return

    # 3. Locate Antigravity ASAR
    if not asar_path or not asar_path.is_file():
        log_error("Could not automatically locate Antigravity app.asar.")
        log_step("Please provide the path using: python install.py --asar <path-to-app.asar>")
        sys.exit(1)

    log_success(f"Located Antigravity: {asar_path}")

    # 4. Handle Running Antigravity Process
    asar_in_place_writable = False
    try:
        with open(asar_path, "r+b"):
            asar_in_place_writable = True
    except Exception:
        asar_in_place_writable = False

    if is_antigravity_running() and not asar_in_place_writable:
        if force:
            log_warn("Closing running Antigravity IDE instances (--force)...")
            close_antigravity_processes()
        else:
            log_warn("Antigravity is currently running and locking app.asar.")
            ans = input(f"{C_YELLOW}Do you want the installer to close Antigravity now? [Y/n]: {C_RESET}").strip().lower()
            if ans in ("", "y", "yes"):
                close_antigravity_processes()
            else:
                log_error("Installation aborted. Please close Antigravity and rerun the installer.")
                sys.exit(1)
    elif is_antigravity_running() and asar_in_place_writable:
        log_step("Antigravity is running with live in-place stream write support. Proceeding without interruption...")

    # 5. Backup Factory ASAR & Google Update Detection
    bak_path = asar_path.with_name("app.asar.bak")
    current_is_patched = is_asar_patched(asar_path)

    if not current_is_patched:
        # A fresh unpatched official Google build was detected (initial install or Antigravity auto-update)
        log_step(f"Official Antigravity build detected. Synchronizing factory backup ({bak_path.name})...")
        try:
            shutil.copy2(asar_path, bak_path)
            log_success(f"Synchronized factory backup ({bak_path.name}).")
        except Exception as e:
            log_warn(f"Could not update factory backup: {e}")
        source_asar = asar_path
    else:
        if not bak_path.is_file():
            shutil.copy2(asar_path, bak_path)
            log_success("Created factory backup (app.asar.bak).")
        else:
            log_step("Factory backup already exists (app.asar.bak).")
        source_asar = bak_path if bak_path.is_file() else asar_path

    # Ensure factory backup unpacked directory is linked for asar CLI
    unpacked_path = asar_path.with_name("app.asar.unpacked")
    bak_unpacked_path = asar_path.with_name("app.asar.bak.unpacked")
    if unpacked_path.is_dir() and not bak_unpacked_path.exists():
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(bak_unpacked_path), str(unpacked_path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                os.symlink(unpacked_path, bak_unpacked_path, target_is_directory=True)
            log_success("Linked factory unpacked directory (app.asar.bak.unpacked).")
        except Exception as e:
            log_warn(f"Could not link {bak_unpacked_path} to {unpacked_path}: {e}")

    # 6. Verify Node / npx tools
    if not ensure_npx_asar():
        log_error("Node.js and npx are required to extract and pack app.asar.")
        log_step("Please install Node.js from https://nodejs.org or run with --skip-asar.")
        sys.exit(1)

    # 7. Unpack, Patch & Repack
    with tempfile.TemporaryDirectory(prefix="paragravity_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        extract_dir = tmp_dir / "asar_extracted"

        log_step(f"Unpacking {source_asar.name} archive...")
        if not extract_asar(source_asar, extract_dir):
            sys.exit(1)

        # Apply Patches
        log_step("Injecting multi-window parallel support into dist/main.js...")
        if not patch_main_js(extract_dir / "dist" / "main.js"):
            sys.exit(1)

        log_step("Registering native IPC bridge in dist/ipcHandlers.js...")
        if not patch_ipc_handlers(extract_dir / "dist" / "ipcHandlers.js"):
            sys.exit(1)

        log_step("Injecting in-DOM Account Switcher UI into dist/preload.js...")
        client_js_file = source_dir / "client.js"
        if not client_js_file.is_file():
            client_js_file = get_plugin_dir() / "client.js"

        if not client_js_file.is_file():
            log_error(f"client.js not found in {source_dir} or {get_plugin_dir()}")
            sys.exit(1)

        client_code = client_js_file.read_text(encoding="utf-8")
        if not patch_preload_js(extract_dir / "dist" / "preload.js", client_code):
            sys.exit(1)

        # Validate syntax
        node_bin = shutil.which("node")
        if node_bin:
            for chk in ["main.js", "ipcHandlers.js", "preload.js"]:
                f = extract_dir / "dist" / chk
                res = subprocess.run([node_bin, "-c", str(f)], capture_output=True)
                if res.returncode != 0:
                    log_error(f"Syntax validation failed on {chk}: {res.stderr.decode()}")
                    sys.exit(1)
            log_success("Syntax checks passed for all patched scripts.")

        # Repack
        log_step("Repacking app.asar archive...")
        new_asar = tmp_dir / "app_patched.asar"
        if not pack_asar(extract_dir, new_asar):
            sys.exit(1)

        # Deploy back to Antigravity
        log_step(f"Deploying patched app.asar to {asar_path.parent}...")
        try:
            shutil.copy2(new_asar, asar_path)
        except PermissionError:
            new_data = new_asar.read_bytes()
            with open(asar_path, "wb") as f:
                f.write(new_data)
        log_success("Deployed updated app.asar.")

    # 8. Post-Install Verification
    session_py = get_plugin_dir() / "session_swap.py"
    try:
        res = subprocess.check_output([sys.executable, str(session_py), "--list"], text=True)
        acc_info = json.loads(res)
        log_success(f"Plugin self-test passed: {len(acc_info.get('accounts', []))} accounts active.")
    except Exception as e:
        log_warn(f"Plugin self-test warning: {e}")

    # 9. Start Regravity Guardian Watchdog (Update Resilience Shield)
    try:
        import guardian
        guardian.install_autostart()
        guardian.start_guardian_background()
        log_success("Regravity Guardian active: automatic update survival enabled.")
    except Exception as e:
        log_warn(f"Could not initialize Guardian watchdog: {e}")

    print(f"\n{C_GREEN}{C_BOLD}═══════════════════════════════════════════════════════════════════{C_RESET}")
    print(f"{C_GREEN}{C_BOLD}  ✓ Regravity has been successfully installed and configured!      {C_RESET}")
    print(f"{C_GREEN}{C_BOLD}═══════════════════════════════════════════════════════════════════{C_RESET}\n")
    print(f"  • {C_BOLD}Launch Antigravity{C_RESET}: You will see the new {C_CYAN}Account Manager (Regravity){C_RESET} button on the sidebar.")
    print(f"  • {C_BOLD}Update Survival{C_RESET}: Guardian Watcher automatically re-patches Antigravity across Google updates.")
    print(f"  • {C_BOLD}CLI Access{C_RESET}: Run {C_CYAN}regravity --list{C_RESET}, {C_CYAN}rgrav --help{C_RESET}, or {C_CYAN}paragravity --list{C_RESET} from any terminal.")
    print(f"  • {C_BOLD}Uninstall anytime{C_RESET}: Run {C_CYAN}python install.py --uninstall{C_RESET} to restore original factory files.")
    print()

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Regravity Universal Plug-and-Play Installer")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall Regravity and restore factory app.asar")
    parser.add_argument("--status", action="store_true", help="Display installation diagnostics and status")
    parser.add_argument("--heal", action="store_true", help="Auto-heal Regravity if Antigravity was updated")
    parser.add_argument("--check", action="store_true", help="Check if app.asar is patched (exit code 0 if patched)")
    parser.add_argument("--silent", action="store_true", help="Run without printing progress messages")
    parser.add_argument("--asar", type=str, default=None, help="Custom path to Antigravity app.asar")
    parser.add_argument("--skip-asar", action="store_true", help="Skip modifying app.asar (CLI and plugin bundle only)")
    parser.add_argument("--force", "-f", action="store_true", help="Force action without interactive confirmation")
    args = parser.parse_args()

    global SILENT
    if args.silent:
        SILENT = True

    source_dir = Path(__file__).resolve().parent
    asar_path = find_antigravity_asar(args.asar)

    if args.check:
        sys.exit(0 if is_asar_patched(asar_path) else 1)

    if args.heal:
        if is_asar_patched(asar_path):
            log_success("Antigravity is already fully patched with Regravity.")
            sys.exit(0)
        log_step("Antigravity update detected! Auto-healing Regravity now...")
        do_install(asar_path, source_dir, skip_asar=args.skip_asar, force=True)
        sys.exit(0)

    print_banner()

    if args.status:
        do_status(asar_path)
    elif args.uninstall:
        do_uninstall(asar_path)
    else:
        do_install(asar_path, source_dir, skip_asar=args.skip_asar, force=args.force)

if __name__ == "__main__":
    main()
