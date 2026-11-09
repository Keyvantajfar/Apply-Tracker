"""PyInstaller entry point (the package uses relative imports, so it cannot be the entry itself)."""
import os
import sys


def _prepare_windowed_process():
    """A windowed build (no console) has no stdout/stderr; code that prints or logs would crash on None."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    if sys.platform == "win32" and len(sys.argv) > 1 and sys.argv[1] != "gui":
        # run from a terminal with a command (add-user, check ...): print into that terminal
        try:
            import ctypes
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8")
                sys.stdin = open("CONIN$", "r", encoding="utf-8")
        except Exception:
            pass


_prepare_windowed_process()

from gradapp.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
