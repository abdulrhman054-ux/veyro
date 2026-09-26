"""Exit when the desktop app that started this backend is gone (crash, kill), so no hidden Python keeps running
paid morning reports or holding the port. Enabled only when VEYRO_PARENT_PID is set (the Electron shell sets it)."""
from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger("veyro.watchdog")


def alive(pid: int) -> bool:
    if os.name == "nt":
        # Never os.kill(pid, 0) on Windows: it terminates the process. Ask for its exit code instead.
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259   # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start(interval: float = 3.0) -> bool:
    pid = os.environ.get("VEYRO_PARENT_PID")
    if not pid or not pid.isdigit():
        return False

    def run():
        while True:
            time.sleep(interval)
            if not alive(int(pid)):
                log.warning("desktop app (pid %s) is gone: stopping the backend", pid)
                os._exit(0)
    threading.Thread(target=run, daemon=True, name="parent-watchdog").start()
    return True
