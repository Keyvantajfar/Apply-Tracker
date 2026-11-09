"""Command line:  gradapp  [gui | serve | list | add-user | set-password | check | repair | registration | import-legacy | version]"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from . import __version__


def _serve(a: argparse.Namespace) -> int:
    from .web.app import app
    from .core.storage import DATA_DIR, log
    host, port = a.host, a.port
    log.info("GradApp %s at http://%s:%s  (data in %s)", __version__, host, port, DATA_DIR)
    if a.dev:
        app.run(host=host, port=port, debug=True, threaded=True)
        return 0
    from waitress import serve
    # one process, several threads: the file storage uses an in-process lock
    serve(app, host=host, port=port, threads=8, ident="gradapp")
    return 0


def _gui(a: argparse.Namespace) -> int:
    from .desktop.launcher import run
    return run(port=a.port, mode=a.mode)


def _password(prompt: str = "Password: ") -> str:
    return os.environ.get("GRADAPP_PASSWORD") or getpass.getpass(prompt)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="gradapp", description="Multi-user tracker for graduate applications.")
    p.add_argument("--version", action="version", version=f"gradapp {__version__}")
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("gui", help="open GradApp in its own window (default for the downloaded binaries)")
    g.add_argument("--port", type=int, default=None)
    g.add_argument("--mode", choices=["auto", "webview", "app", "browser"], default="auto",
                   help="window type: native (pywebview), Chromium app window, or a plain browser tab")
    s = sub.add_parser("serve", help="start the web app (default)")
    s.add_argument("--host", default=os.environ.get("GRADAPP_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("GRADAPP_PORT", "5000")))
    s.add_argument("--dev", action="store_true", help="Flask debug server with reloader")
    sub.add_parser("list", help="show accounts")
    x = sub.add_parser("add-user", help="create an account"); x.add_argument("name")
    x = sub.add_parser("set-password", help="change a password"); x.add_argument("name")
    x = sub.add_parser("check", help="validate data files"); x.add_argument("name", nargs="?")
    x = sub.add_parser("repair", help="merge duplicates, estimate unscored programs"); x.add_argument("name")
    x = sub.add_parser("registration", help="allow or forbid self-registration"); x.add_argument("state", choices=["on", "off"])
    x = sub.add_parser("import-legacy", help="import an older single-user folder (universities.json, ...)")
    x.add_argument("folder"); x.add_argument("--user", required=True)
    sub.add_parser("version", help="print version")
    a = p.parse_args(argv)
    frozen = bool(getattr(sys, "frozen", False))
    if a.cmd is None:                    # double-clicked binary -> window; pip/Docker/terminal -> web server as before
        a = p.parse_args(["gui" if frozen else "serve"])
    if a.cmd == "gui" or frozen:
        from .core.paths import apply_default_data_dir
        apply_default_data_dir()         # before anything imports gradapp.core.storage
    if a.cmd == "gui":
        return _gui(a)
    if a.cmd == "serve":
        return _serve(a)
    if a.cmd == "version":
        print(__version__); return 0

    from werkzeug.security import generate_password_hash
    from .core import models, scoring
    from .core.migrate import import_legacy
    from .core.storage import DATA_DIR, read_json, setup_logging, write_json
    from .core.users import Workspace, create_user, list_users, user_exists
    setup_logging()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if a.cmd == "list":
        for u in list_users():
            d = Workspace(u).load_tracker()
            print(f"{u:20} {len(d['universities'])} universities, {sum(len(x['programs']) for x in d['universities'])} programs")
    elif a.cmd == "add-user":
        create_user(a.name, _password()); print("created", a.name)
    elif a.cmd == "set-password":
        if not user_exists(a.name):
            print("no such user"); return 1
        pw = _password("New password: ")
        if len(pw) < 6:
            print("too short (min 6)"); return 1
        ws = Workspace(a.name); acct = read_json(ws.account_path, {})
        acct["password_hash"] = generate_password_hash(pw); write_json(ws.account_path, acct); print("updated")
    elif a.cmd in ("check", "repair"):
        for n in ([a.name] if a.name else list_users()):
            ws = Workspace(n); data = ws.load_tracker()
            if a.cmd == "repair":
                rep = models.dedupe_tracker(data)
                est = sum(scoring.apply_rule_score(q) for u in data["universities"] for q in u["programs"])
                ws.save_tracker(data); print(f"{n}: {len(rep)} merges, {est} estimates")
            issues = models.health_check(data)
            print(f"{n}: {len(issues)} issues")
            for i in issues:
                if i["level"] != "info":
                    print(f"  [{i['level']}] {i['where']}: {i['msg']}")
    elif a.cmd == "registration":
        c = read_json(DATA_DIR / "config.json", {}); c["allow_registration"] = a.state == "on"
        write_json(DATA_DIR / "config.json", c); print("registration", a.state)
    elif a.cmd == "import-legacy":
        if not user_exists(a.user):
            create_user(a.user, _password("Password for the new account: "))
        for line in import_legacy(Workspace(a.user), a.folder):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
