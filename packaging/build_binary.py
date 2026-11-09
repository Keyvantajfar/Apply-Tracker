"""Build a single-file executable for the current OS:  python packaging/build_binary.py
Output: dist/gradapp-<os>-<arch>[.exe]   (pip install -e ".[dev]" first)"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "src" / "gradapp" / "web"
sep = ";" if sys.platform == "win32" else ":"
subprocess.check_call([
    sys.executable, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm", "--name", "gradapp",
    "--add-data", f"{src / 'templates'}{sep}gradapp/web/templates",
    "--add-data", f"{src / 'static'}{sep}gradapp/web/static",
    "--collect-submodules", "gradapp", "--collect-submodules", "waitress",
    "--distpath", str(root / "dist" / "pyi"), "--workpath", str(root / "build"), "--specpath", str(root / "build"),
    str(root / "packaging" / "gradapp_entry.py"),
], cwd=root)
os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
exe = "gradapp.exe" if sys.platform == "win32" else "gradapp"
out = root / "dist" / f"gradapp-{os_name}-{arch}{'.exe' if sys.platform == 'win32' else ''}"
shutil.move(str(root / "dist" / "pyi" / exe), out)
shutil.rmtree(root / "dist" / "pyi", ignore_errors=True)
print("built", out)
