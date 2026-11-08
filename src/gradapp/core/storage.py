"""File storage: atomic JSON/CSV writes, rolling backups, logging setup.

Everything the app persists is a plain text file under DATA_DIR, so you can
open, edit and diff it by hand.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import shutil
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("GRADAPP_DATA") or Path.cwd() / "data").resolve()
LOG_DIR = DATA_DIR / "logs"
MAX_BACKUPS = 15

log = logging.getLogger("gradapp")
_lock = threading.RLock()


def setup_logging(level: int = logging.INFO) -> None:
    """Console + rotating file log (data/logs/app.log). Safe to call twice."""
    if log.handlers:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logfile = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    logfile.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    log.setLevel(level)
    log.addHandler(console)
    log.addHandler(logfile)
    log.propagate = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, fallback: Any) -> Any:
    """Read JSON. A corrupt file is quarantined (renamed *.corrupt-<ts>) and the fallback returned."""
    path = Path(path)
    if not path.exists():
        return deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bad = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            shutil.copy2(path, bad)
        except OSError:
            pass
        log.error("JSON READ FAILED %s: %s (copy kept as %s)", path.name, e, bad.name)
        return deepcopy(fallback)


def atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a crash can never leave a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def write_json(path: Path, payload: Any, backup: bool = False) -> None:
    path = Path(path)
    if backup and path.exists():
        make_backup(path)
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def make_backup(path: Path) -> None:
    """Keep the last MAX_BACKUPS copies in <dir>/backups/."""
    path = Path(path)
    bdir = path.parent / "backups"
    try:
        bdir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, bdir / f"{path.stem}.{stamp}{path.suffix}")
        olds = sorted(bdir.glob(f"{path.stem}.*{path.suffix}"))
        for old in olds[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)
    except OSError as e:
        log.warning("backup of %s failed: %s", path.name, e)


def csv_cell(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def csv_text(rows: list[dict[str, Any]], headers: list[str]) -> str:
    buf = io.StringIO()
    # QUOTE_ALL: this is what the old app got wrong; fields with commas were left unquoted.
    w = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n", quoting=csv.QUOTE_ALL)
    w.writeheader()
    for r in rows:
        w.writerow({h: csv_cell(r.get(h, "")) for h in headers})
    return buf.getvalue()


def write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    atomic_write(path, csv_text(rows, headers))


def read_csv_strict(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Read a CSV and report rows whose column count doesn't match the header."""
    problems: list[str] = []
    rows: list[dict[str, str]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        for i, raw in enumerate(reader, start=2):
            if len(raw) != len(header):
                problems.append(f"line {i}: {len(raw)} columns, expected {len(header)} (skipped)")
                continue
            rows.append(dict(zip(header, raw)))
    return rows, problems


def deep_copy(x: Any) -> Any:
    return deepcopy(x)
