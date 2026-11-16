#!/usr/bin/env python3
"""
Regravity Guardian: Automatic Update Resilience Watchdog for Google Antigravity.

Monitors Antigravity's installation directory for background updates.
When Google Antigravity auto-updates and overwrites app.asar, Guardian
automatically re-applies Regravity's native patches in-place within seconds,
ensuring the Account Manager sidebar button and parallel window support
never disappear.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Windows process creation flags
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

def get_gemini_dir() -> Path:
    return Path.home() / ".gemini"

def get_plugin_dir() -> Path:
    return get_gemini_dir() / "config" / "plugins" / "paragravity"

def get_log_file() -> Path:
    log_dir = get_gemini_dir() / "antigravity"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "guardian.log"

def get_lock_file() -> Path:
    log_dir = get_gemini_dir() / "antigravity"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "guardian.lock"

def log_msg(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [GUARDIAN] {msg}"
    try:
        with open(get_log_file(), "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass
    if sys.stdout and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        print(formatted)

def find_antigravity_asar() -> Path | None:
    candidates = [
        Path.home() / "AppData" / "Local" / "Programs" / "antigravity" / "resources" / "app.asar",
        Path("C:/Program Files/Antigravity/resources/app.asar"),
        Path("C:/Program Files (x86)/Antigravity/resources/app.asar"),
        Path.home() / "AppData" / "Local" / "antigravity" / "resources" / "app.asar",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None

def is_asar_patched(asar_path: Path) -> bool:
    """Fast check (<5ms) to determine if app.asar has Regravity patches."""
    if not asar_path.is_file():
        return False
    try:
        with open(asar_path, "rb") as f:
            content = f.read()
            return b"paragravityNative" in content and b"paragravity:listAccounts" in content
    except Exception:
        return False

def trigger_heal(asar_path: Path, silent: bool = True) -> bool:
    """Invokes install.py to re-apply patches to app.asar."""
    plugin_dir = get_plugin_dir()
    install_py = plugin_dir / "install.py"
    if not install_py.is_file():
        log_msg(f"ERROR: Cannot find installer at {install_py}")
        return False

    py_exe = sys.executable or shutil.which("python") or "python"
    cmd = [py_exe, str(install_py), "--force"]
    if silent:
        cmd.append("--silent")

    log_msg(f"Initiating auto-healing on {asar_path}...")
    try:
        res = subprocess.run(
            cmd,
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if res.returncode == 0:
            log_msg("SUCCESS: Antigravity re-patched successfully! Account Manager restored.")
            return True
        else:
            log_msg(f"FAILURE: Auto-healing exited with code {res.returncode}. Error: {res.stderr[:200]}")
            return False
    except Exception as e:
        log_msg(f"EXCEPTION during auto-heal: {e}")
        return False

# ---------------------------------------------------------------------------
# Autostart Registration (Windows HKCU Run & Startup Folder)
# ---------------------------------------------------------------------------

def install_autostart():
    """Configures automatic launch on Windows login via HKCU Run and Startup folder."""
    if sys.platform != "win32":
        return

    plugin_dir = get_plugin_dir()
    guardian_script = plugin_dir / "guardian.py"
    pythonw = shutil.which("pythonw") or shutil.which("python") or sys.executable

    # 1. Windows CurrentUser Registry Run Key
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        run_cmd = f'"{pythonw}" "{guardian_script}" --run'
        winreg.SetValueEx(key, "RegravityGuardian", 0, winreg.REG_SZ, run_cmd)
        winreg.CloseKey(key)
        log_msg("Registered Windows Autostart in HKCU Run.")
    except Exception as e:
        log_msg(f"Could not register in HKCU Run: {e}")

    # 2. Windows Startup Folder VBS Shortcut (Fail-safe, 0 console window)
    try:
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup_dir.is_dir():
            vbs_file = startup_dir / "RegravityGuardian.vbs"
            vbs_content = (
                'Set WshShell = CreateObject("WScript.Shell")\n'
                f'WshShell.Run """{pythonw}""" & " """{guardian_script}""" --run", 0, False\n'
            )
            vbs_file.write_text(vbs_content, encoding="utf-8")
            log_msg(f"Created startup shortcut at {vbs_file}")
    except Exception as e:
        log_msg(f"Could not create Startup VBS shortcut: {e}")

def uninstall_autostart():
    """Removes automatic launch entries."""
    if sys.platform != "win32":
        return

    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "RegravityGuardian")
            log_msg("Removed HKCU Run key.")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception as e:
        log_msg(f"Could not remove HKCU Run key: {e}")

    try:
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        vbs_file = startup_dir / "RegravityGuardian.vbs"
        if vbs_file.is_file():
            vbs_file.unlink()
            log_msg("Removed Startup VBS shortcut.")
    except Exception as e:
        log_msg(f"Could not remove Startup VBS shortcut: {e}")

# ---------------------------------------------------------------------------
# Guardian Process Lifecycle
# ---------------------------------------------------------------------------

def is_guardian_running() -> int | None:
    """Returns PID if guardian is running and responsive, else None."""
    lock_file = get_lock_file()
    if not lock_file.is_file():
        return None
    try:
        content = lock_file.read_text(encoding="utf-8").strip()
        pid = int(content)
        # Check if process is still running
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return pid
        else:
            os.kill(pid, 0)
            return pid
    except Exception:
        pass
    # Stale lock
    try:
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass
    return None

def start_guardian_background():
    """Spawns guardian as a detached headless background process."""
    running_pid = is_guardian_running()
    if running_pid:
        log_msg(f"Guardian is already running (PID {running_pid}).")
        return

    pythonw = shutil.which("pythonw") or shutil.which("python") or sys.executable
    script = get_plugin_dir() / "guardian.py"

    log_msg(f"Starting Guardian background daemon with {pythonw}...")
    try:
        if sys.platform == "win32":
            # Use WMI Win32_Process to break away from parent job objects
            target_cmd = f'"{pythonw}" "{script}" --run'
            ps_script = f"([wmiclass]'win32_process').Create('{target_cmd}')"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            if "ReturnValue      : 0" in res.stdout or "ReturnValue: 0" in res.stdout:
                time.sleep(1.0)
                new_pid = is_guardian_running()
                if new_pid:
                    log_msg(f"Guardian successfully started in background via WMI (PID {new_pid}).")
                    return
        # Fallback to standard Popen
        flags = CREATE_NO_WINDOW | DETACHED_PROCESS if sys.platform == "win32" else 0
        subprocess.Popen(
            [pythonw, str(script), "--run"],
            cwd=str(get_plugin_dir()),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags
        )
        time.sleep(0.5)
        new_pid = is_guardian_running()
        if new_pid:
            log_msg(f"Guardian successfully started in background (PID {new_pid}).")
        else:
            log_msg("Guardian spawned.")
    except Exception as e:
        log_msg(f"Failed to spawn background guardian: {e}")

def stop_guardian():
    """Stops any running guardian process."""
    pid = is_guardian_running()
    if not pid:
        log_msg("Guardian is not currently running.")
        return

    log_msg(f"Stopping Guardian process (PID {pid})...")
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, 15)
    except Exception as e:
        log_msg(f"Error terminating PID {pid}: {e}")

    try:
        get_lock_file().unlink(missing_ok=True)
    except Exception:
        pass
    log_msg("Guardian stopped.")

# ---------------------------------------------------------------------------
# Main Watcher Loop
# ---------------------------------------------------------------------------

def run_watch_loop():
    """Continuous low-footprint monitoring loop."""
    import traceback
    try:
        _run_watch_loop_inner()
    except Exception as e:
        log_msg(f"FATAL GUARDIAN ERROR: {e}\n{traceback.format_exc()}")
        raise

def _run_watch_loop_inner():
    # Ensure single instance
    lock_file = get_lock_file()
    existing_pid = is_guardian_running()
    if existing_pid and existing_pid != os.getpid():
        log_msg(f"Guardian already running under PID {existing_pid}. Exiting redundant instance.")
        sys.exit(0)

    try:
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as e:
        log_msg(f"Could not write lockfile: {e}")

    log_msg(f"Regravity Guardian Watcher started (PID {os.getpid()}).")

    asar_path = find_antigravity_asar()
    log_msg(f"asar_path resolved: {asar_path}")
    if not asar_path:
        log_msg("Antigravity app.asar not found yet. Sleeping until installed...")

    last_stat: tuple[float, int] | None = None
    if asar_path and asar_path.is_file():
        log_msg("Checking if asar is patched on startup...")
        if not is_asar_patched(asar_path):
            log_msg("Startup check: app.asar is UNPATCHED. Auto-healing now...")
            trigger_heal(asar_path, silent=True)
        else:
            log_msg("Startup check: app.asar is already patched.")

        try:
            st = asar_path.stat()
            last_stat = (st.st_mtime, st.st_size)
        except Exception:
            pass

    log_msg("Loop starting now...")
    cooldown_until = 0.0

    while True:
        try:
            time.sleep(3)

            now = time.time()
            if now < cooldown_until:
                continue

            if not asar_path or not asar_path.is_file():
                asar_path = find_antigravity_asar()
                if not asar_path or not asar_path.is_file():
                    continue

            try:
                st = asar_path.stat()
                current_stat = (st.st_mtime, st.st_size)
            except Exception:
                continue

            if last_stat is None or current_stat != last_stat:
                log_msg(f"Detected modification in {asar_path.name} (size: {current_stat[1]} bytes). Checking patch status...")
                # Give file stream 1.5s to finish writing if updater is actively flushing
                time.sleep(1.5)

                try:
                    st = asar_path.stat()
                    current_stat = (st.st_mtime, st.st_size)
                except Exception:
                    pass

                last_stat = current_stat

                if not is_asar_patched(asar_path):
                    log_msg("CRITICAL: app.asar is UNPATCHED! Antigravity was updated by Google.")
                    success = trigger_heal(asar_path, silent=True)
                    if success:
                        try:
                            st = asar_path.stat()
                            last_stat = (st.st_mtime, st.st_size)
                        except Exception:
                            pass
                        cooldown_until = time.time() + 5.0
                else:
                    log_msg("app.asar modification checked: Regravity patch signature is active.")

        except KeyboardInterrupt:
            log_msg("Guardian shutting down on user interrupt.")
            break
        except Exception as e:
            log_msg(f"Watch loop error: {e}")
            time.sleep(5)

    log_msg("Loop has terminated!")
    try:
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Regravity Guardian - Update Resilience Watchdog")
    parser.add_argument("--run", action="store_true", help="Run the continuous monitoring loop in foreground")
    parser.add_argument("--start", action="store_true", help="Start Guardian background daemon (pythonw)")
    parser.add_argument("--stop", action="store_true", help="Stop running Guardian daemon")
    parser.add_argument("--status", action="store_true", help="Check Guardian and patch status")
    parser.add_argument("--heal", action="store_true", help="Check patch and auto-heal immediately if needed")
    parser.add_argument("--install-autostart", action="store_true", help="Register Windows startup and HKCU Run keys")
    parser.add_argument("--uninstall-autostart", action="store_true", help="Unregister Windows startup keys")
    args = parser.parse_args()

    if args.install_autostart:
        install_autostart()
        return

    if args.uninstall_autostart:
        uninstall_autostart()
        return

    if args.start:
        install_autostart()
        start_guardian_background()
        return

    if args.stop:
        stop_guardian()
        return

    if args.status:
        pid = is_guardian_running()
        asar = find_antigravity_asar()
        patched = is_asar_patched(asar) if asar else False
        print("\nRegravity Guardian Status:")
        print(f"  • Daemon Running : {'YES (PID ' + str(pid) + ')' if pid else 'NO'}")
        print(f"  • Antigravity ASAR: {asar or 'Not Found'}")
        print(f"  • Patch Signature: {'ACTIVE (Account Manager Ready)' if patched else 'UNPATCHED (Update pending)'}")
        log_f = get_log_file()
        if log_f.is_file():
            print(f"  • Log File       : {log_f}")
        print("")
        return

    if args.heal:
        asar = find_antigravity_asar()
        if not asar:
            print("[!] Antigravity app.asar not located.")
            sys.exit(1)
        if is_asar_patched(asar):
            print("[✓] Antigravity is already fully patched with Regravity.")
            sys.exit(0)
        else:
            print("[i] Antigravity update detected. Auto-healing Regravity now...")
            ok = trigger_heal(asar, silent=False)
            sys.exit(0 if ok else 1)

    if args.run:
        run_watch_loop()
        return

    # Default action if no args: show status
    parser.print_help()

if __name__ == "__main__":
    main()
