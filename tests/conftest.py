import sys
import tkinter as tk
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _tk_root_available():
    try:
        root = tk.Tk()
    except tk.TclError:
        return False

    root.destroy()
    return True


TK_AVAILABLE = _tk_root_available()

requires_tk = pytest.mark.skipif(not TK_AVAILABLE, reason="no display available for tkinter")


def run_in_mainloop(root, steps):
    """Run (delay_ms, fn) steps in sequence via root.after, then destroy the window.

    Each fn takes no arguments. Mirrors the ad-hoc verification pattern used
    throughout development: schedule a step, let it run on the real mainloop,
    schedule the next one from inside it.
    """

    def schedule(index):
        if index >= len(steps):
            root.after(50, root.destroy)
            return

        delay, fn = steps[index]

        def run_step():
            fn()
            schedule(index + 1)

        root.after(delay, run_step)

    schedule(0)
    root.mainloop()
