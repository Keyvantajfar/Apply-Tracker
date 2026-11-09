"""Build the desktop app for the current OS:  python packaging/build_binary.py
  Windows  dist/gradapp-windows-<arch>.exe          single file, no console window
  macOS    dist/gradapp-macos-<arch>.app.zip        GradApp.app bundle (zipped)
  Linux    dist/gradapp-linux-<arch>                single file
(pip install -e ".[dev]" first.)  Command-line use of the binary still works: gradapp-... add-user NAME, check, ..."""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
web = root / "src" / "gradapp" / "web"
dist = root / "dist"
sep = ";" if sys.platform == "win32" else ":"
os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")

# nothing in GradApp uses these; leaving them out only shrinks the binary
EXCLUDES = ["tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3", "distutils", "setuptools", "pkg_resources",
            "pip", "wheel", "numpy", "PIL", "yaml", "IPython", "matplotlib", "scipy", "pandas", "cryptography"]

cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--name", "GradApp" if os_name == "macos" else "gradapp",
       "--add-data", f"{web / 'templates'}{sep}gradapp/web/templates",
       "--add-data", f"{web / 'static'}{sep}gradapp/web/static",
       "--collect-submodules", "gradapp", "--collect-submodules", "waitress",
       "--distpath", str(dist / "pyi"), "--workpath", str(root / "build"), "--specpath", str(root / "build")]
for m in EXCLUDES:
    cmd += ["--exclude-module", m]
if os_name == "windows":
    cmd += ["--onefile", "--noconsole", "--icon", str(root / "packaging" / "icon.png")]
elif os_name == "macos":
    cmd += ["--onedir", "--windowed", "--icon", str(root / "packaging" / "icon.png"),
            "--osx-bundle-identifier", "app.gradapp.GradApp"]
else:
    cmd += ["--onefile", "--strip"]
cmd.append(str(root / "packaging" / "gradapp_entry.py"))
subprocess.check_call(cmd, cwd=root)

dist.mkdir(exist_ok=True)
if os_name == "macos":
    app = dist / "pyi" / "GradApp.app"
    out = dist / f"gradapp-macos-{arch}.app.zip"
    subprocess.check_call(["ditto", "-c", "-k", "--keepParent", str(app), str(out)])   # keeps symlinks and permissions
else:
    exe = dist / "pyi" / ("gradapp.exe" if os_name == "windows" else "gradapp")
    out = dist / f"gradapp-{os_name}-{arch}{'.exe' if os_name == 'windows' else ''}"
    shutil.move(str(exe), out)
shutil.rmtree(dist / "pyi", ignore_errors=True)
print("built", out, f"{out.stat().st_size / 1e6:.1f} MB")
