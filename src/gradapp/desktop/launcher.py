"""Run the web app on a free local port and show it in a window that looks like an application.

Window, in order of preference:
  1. pywebview  (native window; only if installed:  pip install "gradapp[native]")
  2. an installed Chromium-based browser in --app mode: Edge, Chrome, Chromium, Brave ... (no tabs, no address bar)
  3. the default browser (a normal tab). The server then quits by itself once the tab has been closed.
The server stops when the window closes. If a GradApp server already answers on the port, it is reused and left running.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from .. import __version__

TITLE = "GradApp"
PREFERRED_PORT = 5000
IDLE_LIMIT = 120.0          # seconds without any request before the browser-tab mode quits (page pings every 20 s)

_LINUX_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
                   "microsoft-edge-stable", "brave-browser", "brave", "vivaldi")


# ---------- helpers ----------

def _port_free(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0 if sys.platform == "win32" else 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def _free_port(host: str) -> int:
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def is_gradapp(host: str, port: int) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/healthz", timeout=1.5) as r:
            d = json.load(r)
        return bool(d.get("ok")) and "version" in d
    except Exception:
        return False


def find_chromium() -> str | None:
    """Path of an installed Chromium-based browser, or None. GRADAPP_BROWSER overrides the search."""
    forced = os.environ.get("GRADAPP_BROWSER")
    if forced:
        return shutil.which(forced) or (forced if Path(forced).exists() else None)
    c: list[str] = []
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        for r in filter(None, roots):
            c += [rf"{r}\Microsoft\Edge\Application\msedge.exe", rf"{r}\Google\Chrome\Application\chrome.exe",
                  rf"{r}\BraveSoftware\Brave-Browser\Application\brave.exe", rf"{r}\Chromium\Application\chrome.exe"]
    elif sys.platform == "darwin":
        for base in ("/Applications", str(Path.home() / "Applications")):
            for app, exe in (("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"),
                             ("Brave Browser", "Brave Browser"), ("Chromium", "Chromium")):
                c.append(f"{base}/{app}.app/Contents/MacOS/{exe}")
    else:
        c += [p for p in (shutil.which(n) for n in _LINUX_BROWSERS) if p]
    return next((p for p in c if Path(p).exists()), None)


def _chromium_cmd(exe: str, url: str, profile: Path) -> list[str]:
    cmd = [exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1360,900",
           "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"]
    if sys.platform.startswith("linux"):
        cmd.append("--class=GradApp")
    return cmd


# ---------- window strategies; each returns True if it showed the app and the window has now been closed ----------

def _show_webview(url: str, profile: Path) -> bool:
    try:
        import webview  # type: ignore
    except ImportError:
        return False
    try:
        webview.create_window(TITLE, url, width=1360, height=900, min_size=(900, 600))
        webview.start(private_mode=False, storage_path=str(profile / "webview"))
        return True
    except Exception as e:  # missing GTK/Qt/WebView2 runtime: try the next strategy
        print(f"native window unavailable ({e}); trying a browser window", file=sys.stderr)
        return False


def _show_chromium(url: str, profile: Path, app) -> bool:
    exe = find_chromium()
    if not exe:
        return False
    profile.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        proc = subprocess.Popen(_chromium_cmd(exe, url, profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.wait()                                  # the usual case: lives until the window is closed
        return True
    if proc.returncode != 0:
        return False                                 # e.g. a sandboxed snap that may not use our profile folder
    # exited at once with success: the browser handed the window to a running instance, so we cannot watch it
    app.config["DESKTOP"] = {"heartbeat": True}
    _wait_until_idle(app, started)
    return True


def _show_browser_tab(url: str, app) -> None:
    app.config["DESKTOP"] = {"heartbeat": True}
    webbrowser.open(url)
    print(f"GradApp is open in your browser at {url}. It quits by itself after you close the tab.", flush=True)
    _wait_until_idle(app, time.monotonic())


def _wait_until_idle(app, since: float) -> None:
    app.config["LAST_SEEN"] = max(app.config["LAST_SEEN"], since)
    try:
        while time.monotonic() - app.config["LAST_SEEN"] < IDLE_LIMIT:
            time.sleep(2)
    except KeyboardInterrupt:
        pass


# ---------- entry point ----------

def run(host: str = "127.0.0.1", port: int | None = None, mode: str = "auto") -> int:
    """mode: auto | webview | app | browser"""
    from ..core.storage import DATA_DIR, log
    from ..web.app import app
    from waitress import create_server

    port = port or int(os.environ.get("GRADAPP_PORT", PREFERRED_PORT))
    profile = DATA_DIR / ".window-profile"
    if is_gradapp(host, port):                       # already running: just open a window on it
        url, server = f"http://{host}:{port}/", None
    else:
        if not _port_free(host, port):
            port = _free_port(host)
        url = f"http://{host}:{port}/"
        server = create_server(app, host=host, port=port, threads=8, ident="gradapp")
        threading.Thread(target=server.run, name="gradapp-server", daemon=True).start()
        log.info("GradApp %s window mode at %s (data in %s)", __version__, url, DATA_DIR)
        for _ in range(100):
            if is_gradapp(host, port):
                break
            time.sleep(0.1)
    app.config["DESKTOP"] = {"heartbeat": False}
    try:
        shown = (mode in ("auto", "webview") and _show_webview(url, profile)) \
            or (mode in ("auto", "app") and _show_chromium(url, profile, app))
        if not shown:
            _show_browser_tab(url, app)
    finally:
        if server is not None:
            server.close()
    return 0
