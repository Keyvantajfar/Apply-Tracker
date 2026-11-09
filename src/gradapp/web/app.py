"""Web layer: Flask routes + the browser UI (templates/, static/). All logic lives in gradapp.core."""
from __future__ import annotations

import io
import os
import time
import webbrowser
import zipfile
from collections import defaultdict, deque
from functools import wraps
from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for

from .. import __version__
from ..core import ai, importer, models, scoring
from ..core.resume import extract_text
from ..core.storage import DATA_DIR, log, now_iso, setup_logging, csv_text
from ..core.users import (Workspace, config, create_user, secret_key, user_exists, verify_login)

setup_logging()
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(SECRET_KEY=secret_key(), MAX_CONTENT_LENGTH=25 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
                  SESSION_COOKIE_SECURE=os.environ.get("GRADAPP_HTTPS") == "1",
                  JSON_AS_ASCII=False, TEMPLATES_AUTO_RELOAD=False)

_attempts: dict[str, deque] = defaultdict(deque)

# Set by gradapp.desktop when the UI runs inside an app window instead of a normal browser tab.
#   {"heartbeat": bool}  heartbeat=True means the server cannot see the window close, so the page pings us.
app.config["DESKTOP"] = None
app.config["LAST_SEEN"] = time.monotonic()


@app.context_processor
def _desktop_flag():
    return {"desktop": app.config["DESKTOP"]}


@app.before_request
def _seen():
    app.config["LAST_SEEN"] = time.monotonic()


# ---------- plumbing ----------

def err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code


def ws() -> Workspace:
    return Workspace(session["user"])


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("user") or not user_exists(session["user"]):
            session.clear()
            if request.path.startswith("/api/"):
                return err("Please sign in again.", 401)
            return redirect(url_for("login_page"))
        return fn(*a, **kw)
    return wrapper


@app.before_request
def csrf_guard():
    # Browsers can't add custom headers cross-site without a CORS preflight, so this blocks CSRF.
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and request.path.startswith("/api/"):
        if request.headers.get("X-GradApp") != "1":
            return err("Missing X-GradApp header.", 403)


@app.after_request
def no_cache(resp):
    if request.path.startswith("/api/") or request.path == "/":
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(413)
def too_big(_e):
    return err("That file is too large (limit 25 MB).", 413)


@app.errorhandler(Exception)
def crash(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            return err(e.description or e.name, e.code or 500)
        return e
    log.exception("UNHANDLED %s %s", request.method, request.path)
    return err(f"Server error: {e}", 500)


# ---------- pages & auth ----------

@app.get("/")
@login_required
def index():
    return render_template("index.html", user=ws().account())


@app.get("/login")
def login_page():
    if session.get("user") and user_exists(session["user"]):
        return redirect("/")
    return render_template("login.html", allow_registration=config()["allow_registration"])


@app.post("/api/login")
def api_login():
    ip = request.remote_addr or "?"
    q = _attempts[ip]
    now = time.time()
    while q and now - q[0] > 300:
        q.popleft()
    if len(q) >= 10:
        return err("Too many attempts. Wait a few minutes.", 429)
    body = request.get_json(silent=True) or {}
    w = verify_login(body.get("username", ""), body.get("password", ""))
    if not w:
        q.append(now)
        log.warning("LOGIN failed for %r from %s", body.get("username"), ip)
        return err("Wrong username or password.", 401)
    session.clear()
    session["user"] = w.username
    session.permanent = True
    log.info("LOGIN ok: %s", w.username)
    return jsonify({"ok": True})


@app.post("/api/register")
def api_register():
    if not config()["allow_registration"]:
        return err("Registration is turned off. Ask the person running this app to add you.", 403)
    body = request.get_json(silent=True) or {}
    try:
        w = create_user(body.get("username", ""), body.get("password", ""), body.get("display_name", ""))
    except ValueError as e:
        return err(str(e))
    session.clear()
    session["user"] = w.username
    session.permanent = True
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "version": __version__})


@app.post("/api/open-external")
@login_required
def open_external():
    """Desktop window only: open an http(s) link in the system browser (the window itself is not a browser)."""
    if not app.config["DESKTOP"]:
        return err("Not available.", 404)
    url = str((request.get_json(silent=True) or {}).get("url", ""))
    if not url.lower().startswith(("http://", "https://")):
        return err("Only http(s) links can be opened.")
    webbrowser.open(url)
    return jsonify({"ok": True})


# ---------- state ----------

def _state(w: Workspace) -> dict[str, Any]:
    data = w.load_tracker()
    return {
        "ok": True, "user": w.account(), "tracker": data, "profile": w.load_profile(),
        "settings": w.public_settings(), "stages": models.STAGES, "outreach": models.OUTREACH,
        "profile_labels": models.PROFILE_LABELS, "deadlines": models.next_deadlines(data),
        "docs": w.documents(), "server_time": now_iso(), "version": __version__,
    }


@app.get("/api/state")
@login_required
def api_state():
    st = _state(ws())
    n = sum(len(u["programs"]) for u in st["tracker"]["universities"])
    log.info("STATE %s: %d universities, %d programs", session["user"], len(st["tracker"]["universities"]), n)
    return jsonify(st)


def _deadlines(data):
    return models.next_deadlines(data)


# ---------- programs ----------

PROGRAM_EDITABLE = set(models.PROGRAM_TEXT) | {"tuition_eur_per_year", "deadlines", "sources", "stage", "apply", "tags"}


@app.post("/api/program/update")
@login_required
def program_update():
    body = request.get_json(silent=True) or {}
    patch = body.get("patch") or {}
    with ws().transaction() as data:
        u, p = models.find_program(data, body.get("id", ""))
        if not p:
            return err("Program not found.", 404)
        was_wishlist = p["stage"] == "Wishlist"
        for k, v in patch.items():
            if k in PROGRAM_EDITABLE:
                p[k] = v
        if "stage" in patch and was_wishlist and p["stage"] in ("Preparing", "Applied", "Interview", "Accepted") and "apply" not in patch:
            p["apply"] = True
        np_ = models.normalize_program(p, u["id"])
        np_["updated_at"] = now_iso()
        np_["id"] = p["id"]
        p.clear(); p.update(np_)
        if "score" in patch:
            try:
                scoring.set_manual_score(p, patch["score"], lock=True)
            except ValueError as e:
                return err(str(e))
        log.info("EDIT program %s fields=%s", p["id"], sorted(patch))
        out = dict(p)
    return jsonify({"ok": True, "program": out, "deadlines": _deadlines(ws().load_tracker())})


@app.post("/api/program/create")
@login_required
def program_create():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        uid = body.get("university_id")
        u = models.find_uni(data, uid) if uid else None
        if not u:
            nu = body.get("university") or {}
            name = models.s(nu.get("name"))
            if not name:
                return err("Choose a university or enter a new university name.")
            u = next((x for x in data["universities"] if models.uni_key(x["name"]) == models.uni_key(name)), None)
            if not u:
                base = models.slug(name); taken = {x["id"] for x in data["universities"]}; i, uid = 2, base
                while uid in taken:
                    uid = f"{base}-{i}"; i += 1
                u = {"id": uid, "name": name, "country": models.s(nu.get("country")), "city": models.s(nu.get("city")),
                     "batch": "", "website": "", "programs": [], "professors": []}
                data["universities"].append(u)
        raw = body.get("program") or {}
        taken_p = {p["id"] for x in data["universities"] for p in x["programs"]}
        if raw.get("id") and raw["id"] in taken_p:
            raw = {**raw, "id": ""}
        if not models.s(raw.get("name")):
            return err("The program needs a name.")
        p = models.normalize_program(raw, u["id"], taken_p)
        if p["fit_score"] is None:
            scoring.apply_rule_score(p)
        u["programs"].append(p)
        log.info("ADD program %s", p["id"])
        res = {"ok": True, "university": {k: v for k, v in u.items() if k not in ("programs", "professors")}, "program": p}
    res["deadlines"] = _deadlines(ws().load_tracker())
    return jsonify(res)


@app.post("/api/program/delete")
@login_required
def program_delete():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u, p = models.find_program(data, body.get("id", ""))
        if not p:
            return err("Program not found.", 404)
        u["programs"].remove(p)
        for q in u["professors"]:
            if q.get("program_id") == p["id"]:
                q["program_id"] = ""
        log.info("DELETE program %s", p["id"])
        res = {"ok": True, "removed": p, "university_id": u["id"]}
    res["deadlines"] = _deadlines(ws().load_tracker())
    return jsonify(res)


@app.post("/api/program/score")
@login_required
def program_score():
    """action: manual | clear | rule | ai. Only the score fields are touched."""
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    w = ws()
    data = w.load_tracker()
    u, p = models.find_program(data, body.get("id", ""))
    if not p:
        return err("Program not found.", 404)
    force = bool(body.get("force"))
    if action == "ai":
        settings = w.load_settings()
        profile = w.load_profile()
        if not any(profile.values()):
            return err("Your profile is empty. Fill it in (or upload a resume) so the AI has something to compare.")
        meta = p.get("score_meta") or {}
        if meta.get("locked") and not force:
            return jsonify({"ok": False, "locked": True, "error": "This score is locked because you set it by hand."}), 409
        try:
            res = ai.chat_json(settings, ai.score_messages(profile, w.all_documents_text(), u, p))
            if not isinstance(res, dict):
                raise ai.AIError("The AI did not return a JSON object.")
            scoring.set_ai_score(p, res, force=force)
        except (ai.AIError, ValueError) as e:
            log.error("AI score failed for %s: %s", p["id"], e)
            return err(str(e), 502)
    elif action == "manual":
        try:
            scoring.set_manual_score(p, body.get("value"), lock=body.get("lock", True), note=models.s(body.get("note")))
        except ValueError as e:
            return err(str(e))
    elif action == "clear":
        scoring.clear_score(p)
    elif action == "rule":
        meta = p.get("score_meta") or {}
        if meta.get("locked") and not force:
            return jsonify({"ok": False, "locked": True, "error": "This score is locked because you set it by hand."}), 409
        scoring.apply_rule_score(p, force=True)
    elif action == "unlock":
        p["score_meta"]["locked"] = False
    else:
        return err("Unknown score action.")
    p["updated_at"] = now_iso()
    w.save_tracker(data)
    return jsonify({"ok": True, "program": p})


# ---------- universities ----------

@app.post("/api/uni/update")
@login_required
def uni_update():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u = models.find_uni(data, body.get("id", ""))
        if not u:
            return err("University not found.", 404)
        for k in ("name", "country", "city", "batch", "website"):
            if k in (body.get("patch") or {}):
                u[k] = models.s(body["patch"][k]) if k != "website" else models.to_link(body["patch"][k])
        if not u["name"]:
            return err("A university needs a name.")
        res = {k: v for k, v in u.items() if k not in ("programs", "professors")}
    return jsonify({"ok": True, "university": res})


@app.post("/api/uni/delete")
@login_required
def uni_delete():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u = models.find_uni(data, body.get("id", ""))
        if not u:
            return err("University not found.", 404)
        data["universities"].remove(u)
        log.info("DELETE university %s (%d programs)", u["id"], len(u["programs"]))
    return jsonify({"ok": True, "removed": u, "deadlines": _deadlines(ws().load_tracker())})


@app.post("/api/uni/restore")
@login_required
def uni_restore():
    body = request.get_json(silent=True) or {}
    u = body.get("university")
    if not isinstance(u, dict):
        return err("Nothing to restore.")
    with ws().transaction() as data:
        if models.find_uni(data, u.get("id", "")):
            return err("That university is already back.")
        data["universities"].append(u)
    return jsonify({"ok": True, **_state(ws())})


# ---------- professors ----------

PROF_EDITABLE = set(models.PROF_TEXT) | {"sources", "outreach_status", "program_id"}


@app.post("/api/prof/update")
@login_required
def prof_update():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u, q = models.find_prof(data, body.get("id", ""))
        if not q:
            return err("Professor not found.", 404)
        for k, v in (body.get("patch") or {}).items():
            if k in PROF_EDITABLE:
                q[k] = v
        nq = models.normalize_prof(q, u["id"])
        nq["id"] = q["id"]
        q.clear(); q.update(nq)
        out = dict(q)
    return jsonify({"ok": True, "professor": out})


@app.post("/api/prof/create")
@login_required
def prof_create():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u = models.find_uni(data, body.get("university_id", ""))
        if not u:
            return err("Choose a university first.")
        raw = body.get("professor") or {}
        if not models.s(raw.get("name")):
            return err("The professor needs a name.")
        taken = {q["id"] for x in data["universities"] for q in x["professors"]}
        q = models.normalize_prof({**raw, "id": ""}, u["id"], None, taken)
        u["professors"].append(q)
        out = dict(q)
    return jsonify({"ok": True, "professor": out, "university_id": u["id"]})


@app.post("/api/prof/delete")
@login_required
def prof_delete():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u, q = models.find_prof(data, body.get("id", ""))
        if not q:
            return err("Professor not found.", 404)
        u["professors"].remove(q)
    return jsonify({"ok": True, "removed": q, "university_id": u["id"]})


@app.post("/api/prof/restore")
@login_required
def prof_restore():
    body = request.get_json(silent=True) or {}
    with ws().transaction() as data:
        u = models.find_uni(data, body.get("university_id", ""))
        q = body.get("professor")
        if not u or not isinstance(q, dict):
            return err("Nothing to restore.")
        if not any(x["id"] == q.get("id") for x in u["professors"]):
            u["professors"].append(q)
    return jsonify({"ok": True})


# ---------- profile, documents ----------

@app.get("/api/profile")
@login_required
def profile_get():
    return jsonify({"ok": True, "profile": ws().load_profile()})


@app.put("/api/profile")
@login_required
def profile_put():
    body = request.get_json(silent=True) or {}
    prof = ws().save_profile(body.get("profile") or {})
    return jsonify({"ok": True, "profile": prof})


@app.post("/api/docs")
@login_required
def docs_add():
    w = ws()
    added, errors = [], []
    for f in request.files.getlist("files"):
        if not f or not f.filename:
            continue
        try:
            text = extract_text(f.filename, f.read())
            added.append({"name": w.add_document(f.filename, text), "chars": len(text)})
        except ValueError as e:
            errors.append(f"{f.filename}: {e}")
    pasted = (request.form.get("text") or "").strip()
    if pasted:
        added.append({"name": w.add_document(request.form.get("title") or "pasted-notes", pasted), "chars": len(pasted)})
    log.info("DOCS %s added=%s errors=%s", w.username, [a["name"] for a in added], errors)
    if not added and errors:
        return err(" ".join(errors))
    return jsonify({"ok": True, "added": added, "errors": errors, "docs": w.documents()})


@app.get("/api/docs/<name>")
@login_required
def docs_get(name):
    p = ws().docs_dir / os.path.basename(name)
    if not p.exists():
        return err("Document not found.", 404)
    return jsonify({"ok": True, "name": p.name, "text": p.read_text(encoding="utf-8", errors="replace")})


@app.post("/api/docs/delete")
@login_required
def docs_delete():
    w = ws()
    w.delete_document((request.get_json(silent=True) or {}).get("name", ""))
    return jsonify({"ok": True, "docs": w.documents()})


@app.post("/api/profile/ai-extract")
@login_required
def profile_ai_extract():
    """Returns PROPOSED fields. Nothing is saved until the user accepts them in the UI."""
    w = ws()
    body = request.get_json(silent=True) or {}
    docs = w.all_documents_text()
    extra = models.s(body.get("extra"))
    if not docs and not extra:
        return err("Upload a resume or write something about yourself first.")
    try:
        res = ai.chat_json(w.load_settings(), ai.profile_messages(w.load_profile(), docs, extra))
    except ai.AIError as e:
        return err(str(e), 502)
    fields = res.get("fields") if isinstance(res, dict) else None
    if not isinstance(fields, dict):
        return err("The AI answer had no 'fields'. Try again.", 502)
    cur = w.load_profile()
    proposals = []
    for k, v in fields.items():
        key = "".join(ch if ch.isalnum() else "_" for ch in str(k).lower()).strip("_")
        val = models.s(v)
        if key and val and cur.get(key) != val:
            proposals.append({"key": key, "label": models.PROFILE_LABELS.get(key, key.replace("_", " ").capitalize()),
                              "old": cur.get(key, ""), "new": val})
    return jsonify({"ok": True, "proposals": proposals, "summary": models.s(res.get("summary"))})


# ---------- settings ----------

@app.get("/api/settings")
@login_required
def settings_get():
    return jsonify({"ok": True, "settings": ws().public_settings()})


@app.put("/api/settings")
@login_required
def settings_put():
    body = request.get_json(silent=True) or {}
    patch = {k: body[k] for k in ("ai_base_url", "ai_model", "ai_timeout", "theme") if k in body}
    if "ai_api_key" in body:
        patch["ai_api_key"] = body["ai_api_key"]          # "" clears; omit to keep
    w = ws()
    w.save_settings(patch)
    return jsonify({"ok": True, "settings": w.public_settings()})


@app.post("/api/settings/test")
@login_required
def settings_test():
    try:
        t0 = time.time()
        out = ai.chat(ws().load_settings(), [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=200)
        return jsonify({"ok": True, "reply": out[:80], "seconds": round(time.time() - t0, 1)})
    except ai.AIError as e:
        return err(str(e), 502)


@app.post("/api/account/password")
@login_required
def account_password():
    body = request.get_json(silent=True) or {}
    try:
        ws().set_password(body.get("old", ""), body.get("new", ""))
    except ValueError as e:
        return err(str(e))
    return jsonify({"ok": True})


@app.post("/api/account/name")
@login_required
def account_name():
    w = ws()
    w.set_display_name((request.get_json(silent=True) or {}).get("name", ""))
    return jsonify({"ok": True, "user": w.account()})


# ---------- assistant chat ----------

@app.get("/api/chat")
@login_required
def chat_get():
    return jsonify({"ok": True, "messages": ws().load_chat()})


@app.post("/api/chat")
@login_required
def chat_post():
    w = ws()
    msg = models.s((request.get_json(silent=True) or {}).get("message"))
    if not msg:
        return err("Type a message first.")
    history = w.load_chat()
    history.append({"role": "user", "content": msg, "at": now_iso()})
    data = w.load_tracker()
    try:
        raw = ai.chat(w.load_settings(), ai.chat_messages(
            w.load_profile(), w.all_documents_text(), data,
            [{"role": m["role"], "content": m["content"]} for m in history]), temperature=0.3)
    except ai.AIError as e:
        w.save_chat(history[:-1])
        return err(str(e), 502)
    text, raw_actions = ai.split_actions(raw)
    actions = ai.validate_actions(data, raw_actions)
    history.append({"role": "assistant", "content": text, "at": now_iso(), "actions": actions})
    w.save_chat(history)
    return jsonify({"ok": True, "reply": text, "actions": actions})


@app.post("/api/chat/clear")
@login_required
def chat_clear():
    ws().save_chat([])
    return jsonify({"ok": True})


@app.post("/api/actions/apply")
@login_required
def actions_apply():
    w = ws()
    raw = (request.get_json(silent=True) or {}).get("actions") or []
    applied = []
    with w.transaction() as data:
        actions = ai.validate_actions(data, raw)
        profile = None
        for a in actions:
            if a["type"] == "update_profile":
                profile = profile if profile is not None else w.load_profile()
                profile[a["key"]] = a["value"]
                applied.append(a["label"])
                continue
            u, p = models.find_program(data, a["program_id"])
            if a["type"] == "set_stage":
                p["stage"] = a["value"]
                if a["value"] in ("Preparing", "Applied", "Interview", "Accepted"):
                    p["apply"] = True
            elif a["type"] == "set_apply":
                p["apply"] = a["value"]
            elif a["type"] == "add_note":
                p["notes"] = (p["notes"] + "\n" if p["notes"] else "") + a["value"]
            elif a["type"] == "set_score":
                scoring.set_manual_score(p, a["value"], lock=True, note="Set from the assistant chat.")
            p["updated_at"] = now_iso()
            applied.append(a["label"])
        if profile is not None:
            w.save_profile(profile)
    log.info("ACTIONS applied: %s", applied)
    return jsonify({"ok": True, "applied": applied, **_state(w)})


# ---------- research prompt + import ----------

@app.post("/api/import/prompt")
@login_required
def import_prompt():
    w = ws()
    opts = request.get_json(silent=True) or {}
    existing = []
    if opts.get("skip_existing", True):
        existing = [f"{u['name']} - {p['name']}" for u in w.load_tracker()["universities"] for p in u["programs"]]
    try:
        if opts.get("convert"):
            text = importer.build_convert_prompt(models.s(opts.get("focus")) or "general")
        else:
            text = importer.build_research_prompt(opts, w.load_profile(), existing)
    except ValueError as e:
        return err(str(e))
    return jsonify({"ok": True, "prompt": text, "chars": len(text), "tag": importer.FOCUS_TAG.get(models.s(opts.get("focus")) or "general", "")})


def _import_run(commit: bool):
    w = ws()
    body = request.get_json(silent=True) or {}
    try:
        incoming, warnings = importer.parse_import(body.get("text") or body.get("json") or "", models.s(body.get("tag"))[:40])
        new_data, summary = importer.plan_import(w.load_tracker(), incoming, body.get("mode", "fill"),
                                                 estimate_scores=body.get("estimate_scores", True))
    except ValueError as e:
        return err(str(e))
    summary["warnings"] = warnings
    if not commit:
        return jsonify({"ok": True, "preview": True, **summary})
    c = summary["counts"]
    if not any(c[k] for k in ("new_universities", "new_programs", "updated_programs", "new_professors", "updated_professors")):
        return jsonify({"ok": True, "preview": False, "nothing": True, **summary})
    with w.transaction() as data:       # backup is made by save_tracker
        data.clear(); data.update(new_data)
    log.info("IMPORT committed for %s: %s", w.username, c)
    return jsonify({"ok": True, "preview": False, **summary, **_state(w)})


@app.post("/api/import/preview")
@login_required
def import_preview():
    return _import_run(False)


@app.post("/api/import/commit")
@login_required
def import_commit():
    return _import_run(True)


# ---------- health, export ----------

@app.get("/api/health")
@login_required
def health():
    return jsonify({"ok": True, "issues": models.health_check(ws().load_tracker())})


@app.post("/api/health/fix")
@login_required
def health_fix():
    report = []
    with ws().transaction() as data:
        report += models.dedupe_tracker(data)
        n = 0
        for u in data["universities"]:
            for p in u["programs"]:
                n += scoring.apply_rule_score(p)
        if n:
            report.append(f"estimated {n} unscored programs")
    return jsonify({"ok": True, "report": report, **_state(ws())})


@app.get("/api/export/<kind>")
@login_required
def export(kind: str):
    w = ws()
    data = w.load_tracker()
    if kind == "programs":
        return Response(csv_text(models.flatten_programs(data), models.PROGRAM_CSV_HEADERS), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=programs.csv"})
    if kind == "professors":
        return Response(csv_text(models.flatten_profs(data), models.PROF_CSV_HEADERS), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=professors.csv"})
    if kind == "tracker":
        return send_file(w.tracker_path, as_attachment=True, download_name="universities.json")
    if kind == "all":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in w.dir.rglob("*"):
                rel = p.relative_to(w.dir)
                if p.is_file() and rel.parts[0] != "backups" and p.name not in ("account.json", "settings.json"):
                    z.write(p, str(rel))
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"{w.username}-gradapp-export.zip", mimetype="application/zip")
    return err("Unknown export.", 404)
