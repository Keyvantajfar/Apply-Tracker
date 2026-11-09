"""Run the web app on a free local port and show it in a window that looks like an application.

Window, in order of preference:
  1. pywebview  (native window; only if installed:  pip install "gradapp[native]")
  2. an installed Chromium-based browser in --app mode: Edge, Chrome, Chromium, Brave ... (no tabs, no address bar)
  3. the default browser (a normal tab). The server then quits by itself once the tab has been closed.
The app exits when the window closes: the page reports it, and the process is also ended explicitly (see cli._gui).
The server stops when the window closes. If a GradApp server already answers on the port, it is reused and left running.
"""
from __future__ import annotations

import json
import os
import shutil
import secrets
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
IDLE_LIMIT = 120.0          # seconds without any request before we assume the window is gone (page pings every 20 s)
BYE_GRACE = 3.0             # after the page says goodbye, wait this long for a follow-up request (reload / page change)

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


def _show_chromium(url: str, profile: Path, app, signals: bool = True) -> bool:
    exe = find_chromium()
    if not exe:
        return False
    profile.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(_chromium_cmd(exe, url, profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    app.config["DESKTOP"] = {**app.config["DESKTOP"], "heartbeat": True}
    try:
        return _watch(app, proc, signals)
    finally:
        if proc.poll() is None:                      # the browser may linger in the background (Edge does); it is ours, end it
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def _show_browser_tab(url: str, app, signals: bool = True) -> None:
    app.config["DESKTOP"] = {**app.config["DESKTOP"], "heartbeat": True}
    webbrowser.open(url)
    print(f"GradApp is open in your browser at {url}. It quits by itself after you close the tab.", flush=True)
    _watch(app, None, signals)


def _watch(app, proc, signals: bool = True) -> bool:
    """Block until the window is gone. Three signals, because no single one is reliable on every OS:
    the page says goodbye (pagehide), the window process exits, or nothing has been heard for IDLE_LIMIT.
    signals=False when the server belongs to another process (we cannot hear the page): only the window process counts.
    Returns False only if the browser failed to start at all (exit code != 0 within a few seconds)."""
    started = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            if proc is not None and proc.poll() is not None:
                if now - started < 4 and proc.returncode != 0:
                    return False                     # e.g. a sandboxed snap that may not use our profile folder
                if now - started >= 4:
                    return True                      # window process ended = window closed
                proc = None                          # exited at once with success: handed to a running browser; rely on the page
            if not signals:
                if proc is None:
                    return True                      # nothing left that we can watch
                time.sleep(0.4)
                continue
            bye, seen = app.config["BYE"], app.config["LAST_SEEN"]
            if bye > started and now - bye > BYE_GRACE and seen <= bye:
                return True                          # window said goodbye and nothing followed (a reload would have)
            if now - max(seen, started) > IDLE_LIMIT:
                return True
            time.sleep(0.4)
    except KeyboardInterrupt:
        return True


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
    app.config["DESKTOP"] = {"heartbeat": False, "token": secrets.token_urlsafe(16)}
    try:
        shown = (mode in ("auto", "webview") and _show_webview(url, profile)) \
            or (mode in ("auto", "app") and _show_chromium(url, profile, app, server is not None))
        if not shown:
            _show_browser_tab(url, app, server is not None)
    finally:
        if server is not None:
            server.close()
    return 0
