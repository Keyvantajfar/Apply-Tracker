"""Accounts and per-user workspaces (plain files under data/users/<name>/)."""
from __future__ import annotations

import os
import re
import secrets
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from werkzeug.security import check_password_hash, generate_password_hash

from . import models
from .storage import (DATA_DIR, _lock, atomic_write, log, make_backup, now_iso, read_json, write_csv,
                      write_json)

USERS_DIR = DATA_DIR / "users"
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")

DEFAULT_SETTINGS = {
    "ai_base_url": "https://api.openai.com/v1",
    "ai_model": "gpt-4o-mini",
    "ai_api_key": "",
    "ai_timeout": 300,
    "theme": "auto",
}


def secret_key() -> str:
    """Session signing key: GRADAPP_SECRET_KEY if set, otherwise generated once and kept in data/secret.key."""
    if os.environ.get("GRADAPP_SECRET_KEY"):
        return os.environ["GRADAPP_SECRET_KEY"]
    p = DATA_DIR / "secret.key"
    if not p.exists():
        atomic_write(p, secrets.token_hex(32))
        try:
            p.chmod(0o600)
        except OSError:
            pass
    return p.read_text(encoding="utf-8").strip()


def config() -> dict[str, Any]:
    return {"allow_registration": True, **read_json(DATA_DIR / "config.json", {})}


def valid_username(name: str) -> bool:
    return bool(USERNAME_RE.match(name or ""))


def list_users() -> list[str]:
    if not USERS_DIR.exists():
        return []
    return sorted(p.name for p in USERS_DIR.iterdir() if (p / "account.json").exists())


def user_exists(name: str) -> bool:
    return valid_username(name) and (USERS_DIR / name / "account.json").exists()


def create_user(name: str, password: str, display_name: str = "", min_len: int = 6) -> "Workspace":
    name = (name or "").strip().lower()
    if not valid_username(name):
        raise ValueError("Username must be 3-32 characters: letters, digits, '-' or '_'.")
    if len(password or "") < min_len:
        raise ValueError(f"Password must be at least {min_len} characters.")
    if user_exists(name):
        raise ValueError("That username is taken.")
    ws = Workspace(name)
    ws.dir.mkdir(parents=True, exist_ok=True)
    write_json(ws.account_path, {"username": name, "display_name": display_name or name,
                                 "password_hash": generate_password_hash(password), "created_at": now_iso()})
    write_json(ws.tracker_path, {"meta": {"created": now_iso()}, "universities": []})
    write_json(ws.profile_path, {k: "" for k in models.NEW_PROFILE_KEYS})
    log.info("USER created: %s", name)
    return ws


def verify_login(name: str, password: str) -> "Workspace | None":
    name = (name or "").strip().lower()
    if not user_exists(name):
        # burn comparable time so usernames can't be probed by timing
        check_password_hash(generate_password_hash("x"), password or "")
        return None
    ws = Workspace(name)
    acct = read_json(ws.account_path, {})
    if check_password_hash(acct.get("password_hash", ""), password or ""):
        return ws
    return None


class Workspace:
    def __init__(self, username: str):
        if not valid_username(username):
            raise ValueError("bad username")
        self.username = username
        self.dir = USERS_DIR / username
        self.account_path = self.dir / "account.json"
        self.tracker_path = self.dir / "tracker.json"
        self.profile_path = self.dir / "profile.json"
        self.settings_path = self.dir / "settings.json"
        self.chat_path = self.dir / "chat.json"
        self.resume_path = self.dir / "resume.txt"
        self.docs_dir = self.dir / "docs"
        self.programs_csv = self.dir / "programs.csv"
        self.professors_csv = self.dir / "professors.csv"

    # ----- account -----
    def account(self) -> dict[str, Any]:
        a = read_json(self.account_path, {})
        a.pop("password_hash", None)
        return a

    def set_password(self, old: str, new: str) -> None:
        acct = read_json(self.account_path, {})
        if not check_password_hash(acct.get("password_hash", ""), old or ""):
            raise ValueError("Current password is wrong.")
        if len(new or "") < 6:
            raise ValueError("New password must be at least 6 characters.")
        acct["password_hash"] = generate_password_hash(new)
        write_json(self.account_path, acct)

    def set_display_name(self, name: str) -> None:
        acct = read_json(self.account_path, {})
        acct["display_name"] = (name or self.username).strip()[:60]
        write_json(self.account_path, acct)

    # ----- tracker -----
    def load_tracker(self) -> dict[str, Any]:
        raw = read_json(self.tracker_path, {"meta": {}, "universities": []})
        return models.normalize_tracker(raw)

    def save_tracker(self, data: dict[str, Any], backup: bool = True) -> dict[str, Any]:
        data = models.normalize_tracker(data)
        data["meta"]["saved_at"] = now_iso()
        write_json(self.tracker_path, data, backup=backup)
        # Clean, fully-quoted CSV exports for people who like spreadsheets. JSON is the source of truth.
        write_csv(self.programs_csv, models.flatten_programs(data), models.PROGRAM_CSV_HEADERS)
        write_csv(self.professors_csv, models.flatten_profs(data), models.PROF_CSV_HEADERS)
        n_p = sum(len(u["programs"]) for u in data["universities"])
        n_q = sum(len(u["professors"]) for u in data["universities"])
        log.info("SAVE %s: %d universities, %d programs, %d professors", self.username,
                 len(data["universities"]), n_p, n_q)
        return data

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        """Read-modify-write under a lock; saves only if the block finishes without an exception."""
        with _lock:
            data = self.load_tracker()
            yield data
            self.save_tracker(data)

    # ----- profile -----
    def load_profile(self) -> dict[str, str]:
        p = read_json(self.profile_path, {})
        return {str(k): models.s(v) for k, v in p.items()} if isinstance(p, dict) else {}

    def save_profile(self, profile: dict[str, Any]) -> dict[str, str]:
        clean = {}
        for k, v in (profile or {}).items():
            key = re.sub(r"[^a-z0-9_]+", "_", str(k).strip().lower()).strip("_")[:40]
            if key:
                clean[key] = models.s(v)
        write_json(self.profile_path, clean, backup=True)
        log.info("PROFILE saved for %s (%d fields)", self.username, len(clean))
        return clean

    # ----- settings -----
    def load_settings(self) -> dict[str, Any]:
        return {**DEFAULT_SETTINGS, **read_json(self.settings_path, {})}

    def save_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        cur = self.load_settings()
        for k in DEFAULT_SETTINGS:
            if k in patch:
                if k == "ai_api_key" and patch[k] in (None, "__keep__"):
                    continue
                cur[k] = patch[k]
        cur["ai_base_url"] = str(cur["ai_base_url"]).strip().rstrip("/")
        write_json(self.settings_path, cur)
        return cur

    def public_settings(self) -> dict[str, Any]:
        st = self.load_settings()
        key = st.pop("ai_api_key", "")
        st["has_api_key"] = bool(key)
        return st

    # ----- resume / documents -----
    def documents(self) -> list[dict[str, Any]]:
        if not self.docs_dir.exists():
            return []
        return [{"name": p.name, "chars": len(p.read_text(encoding="utf-8", errors="replace"))}
                for p in sorted(self.docs_dir.glob("*.txt"))]

    def add_document(self, name: str, text: str) -> str:
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:60] or "document"
        fn = f"{safe}.txt"
        atomic_write(self.docs_dir / fn, text)
        return fn

    def delete_document(self, name: str) -> bool:
        p = self.docs_dir / Path(name).name
        if p.exists() and p.parent == self.docs_dir:
            p.unlink()
            return True
        return False

    def all_documents_text(self, limit: int = 24000) -> str:
        parts = []
        if self.resume_path.exists():
            parts.append(self.resume_path.read_text(encoding="utf-8", errors="replace"))
        if self.docs_dir.exists():
            for p in sorted(self.docs_dir.glob("*.txt")):
                parts.append(f"--- {p.stem} ---\n" + p.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(x for x in parts if x.strip())[:limit]

    # ----- chat -----
    def load_chat(self) -> list[dict[str, Any]]:
        c = read_json(self.chat_path, [])
        return c if isinstance(c, list) else []

    def save_chat(self, messages: list[dict[str, Any]]) -> None:
        write_json(self.chat_path, messages[-200:])
