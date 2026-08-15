import os
import subprocess
import sys

OPEN_TIMEOUT = 10


def _is_wsl():
    if not sys.platform.startswith("linux"):
        return False

    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except (OSError, ValueError):
        return False


def open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=True, timeout=OPEN_TIMEOUT)
    elif _is_wsl():
        windows_path = subprocess.run(
            ["wslpath", "-w", path],
            check=True,
            capture_output=True,
            text=True,
            timeout=OPEN_TIMEOUT,
        ).stdout.strip()
        subprocess.run(["explorer.exe", windows_path], check=False, timeout=OPEN_TIMEOUT)
    else:
        subprocess.run(["xdg-open", path], check=True, timeout=OPEN_TIMEOUT)
