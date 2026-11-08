"""Data model: normalisation, validation, merging and deadline parsing.

Tracker layout (data/users/<name>/tracker.json):

    {"meta": {...}, "universities": [
        {"id","name","country","city","batch","website",
         "programs":   [ {program}, ... ],
         "professors": [ {professor}, ... ]}
    ]}

IDs are globally unique ("<university-slug>--<program-slug>"), which fixes the
old bug where "p_m-sc-data-science" existed at 15 universities.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from .storage import log, now_iso

STAGES = ["Wishlist", "Preparing", "Applied", "Interview", "Accepted", "Rejected", "Declined"]
OUTREACH = ["Not Contacted", "Drafted", "Active Contact", "Active Advisor", "No Reply", "Declined"]

# Fields the *user* owns. Import/merge never overwrites these on existing records.
USER_PROGRAM_FIELDS = {"stage", "apply", "notes", "fit_score", "score_meta", "created_at"}
USER_PROF_FIELDS = {"outreach_status", "last_contacted", "notes", "created_at"}

PROGRAM_TEXT = [
    "name", "degree", "language", "duration", "official_link", "admission_mode", "gpa_rule",
    "auto_gpa_filter_risk", "last_two_years_gpa_usable", "direct_phd_possible", "funding",
    "funding_note", "tuition_note", "notes", "risk_alert", "fit_note", "verification", "partners",
]
PROF_TEXT = [
    "name", "title", "affiliation", "research_interests", "relevance", "email", "email_source",
    "page", "open_phd_calls", "direct_phd_possible", "verification", "notes", "last_contacted",
]

PROGRAM_CSV_HEADERS = [
    "id", "university_id", "country", "city", "university", "batch", "program", "degree", "language", "duration",
    "tuition_eur_per_year", "tuition_note", "official_link", "deadlines", "admission_mode", "gpa_rule",
    "auto_gpa_filter_risk", "last_two_years_gpa_usable", "direct_phd_possible", "funding", "funding_note",
    "stage", "apply", "fit_score", "score_source", "notes", "risk_alert", "fit_note", "verification", "partners", "tags", "sources",
]
PROF_CSV_HEADERS = [
    "id", "country", "university", "program", "program_id", "name", "title", "affiliation",
    "research_interests", "relevance", "email", "email_source", "page", "open_phd_calls",
    "direct_phd_possible", "verification", "outreach_status", "last_contacted", "notes", "sources",
]

PROFILE_LABELS = {
    "applicant": "Name", "degree": "Degree", "university": "University", "gpa_overall": "GPA (overall)",
    "gpa_last_two_years": "GPA (last two years)", "gpa_german_bavarian": "GPA on the German scale",
    "gpa_german_scale": "GPA on the German scale", "credits_passed": "Credits passed",
    "credits_total": "Credits total", "current_semester": "Current semester",
    "current_semester_credits": "Credits this semester", "final_semester_credits": "Credits final semester",
    "approx_ects_cs": "ECTS in computer science", "math_stats_ects": "ECTS in maths and statistics",
    "english": "English", "research": "Research", "skills": "Skills", "goals": "Goals",
}
NEW_PROFILE_KEYS = ["applicant", "degree", "university", "gpa_overall", "gpa_german_scale",
                    "approx_ects_cs", "math_stats_ects", "english", "research", "skills", "goals"]


# ---------- small helpers ----------

def slug(text: Any, maxlen: int = 48) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return (s[:maxlen].strip("-")) or "item"


def boolish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def s(v: Any) -> str:
    """Coerce to a trimmed string; None -> ''."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple)):
        return "; ".join(s(x) for x in v if s(x))
    if isinstance(v, dict):
        return "; ".join(f"{k}: {s(x)}" for k, x in v.items() if s(x))
    return str(v).strip()


def to_score(v: Any) -> float | None:
    """0-100 number, or None when the value is blank / text. Text is *never* turned into 0."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(max(0.0, min(100.0, float(v))), 1)
    t = str(v).strip().rstrip("%")
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return round(max(0.0, min(100.0, float(t))), 1)
    return None


def parse_tuition(v: Any) -> tuple[float | None, str]:
    """Return (numeric EUR/year or None, leftover text to keep as a note)."""
    if v is None or v == "":
        return None, ""
    if isinstance(v, bool):
        return None, ""
    if isinstance(v, (int, float)):
        return float(v), ""
    t = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return float(t), ""
    return None, t


def norm_key(text: Any) -> str:
    t = str(text or "").lower()
    t = re.sub(r"\b(m\.?\s?sc\.?|msc|master of science|master of arts|m\.?a\.?|master)\b( in| of)?", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def uni_key(name: Any, city: Any = "") -> str:
    return norm_key(name)


def to_sources(v: Any) -> list[str]:
    if isinstance(v, list):
        out = [s(x) for x in v if s(x)]
    else:
        out = re.findall(r"https?://[^\s,;\"'<>\]\)]+", s(v))
    seen, res = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


def to_deadlines(v: Any) -> dict[str, str]:
    if isinstance(v, dict):
        return {str(k): s(x) for k, x in v.items() if s(x)}
    t = s(v)
    if not t:
        return {}
    if t.startswith("{"):
        try:
            import json
            d = json.loads(t)
            if isinstance(d, dict):
                return {str(k): s(x) for k, x in d.items() if s(x)}
        except Exception:  # noqa: BLE001
            pass
    return {"note": t}


def to_tags(v: Any) -> list[str]:
    """Labels such as 'Erasmus Mundus' or 'DAAD'. Accepts a list or a comma/semicolon separated string."""
    items = v if isinstance(v, (list, tuple)) else re.split(r"[;,]", s(v))
    out: list[str] = []
    for x in items:
        x = s(x)[:40].strip()
        if x and x.lower() not in {y.lower() for y in out}:
            out.append(x)
    return out[:8]


def to_link(v: Any) -> str:
    t = s(v)
    if t and not re.match(r"https?://", t, re.I):
        m = re.search(r"https?://\S+", t)
        if m:
            return m.group(0)
        if re.fullmatch(r"[\w.-]+\.[a-z]{2,}(/\S*)?", t, re.I):
            return "https://" + t
    return t


# ---------- deadline parsing (best effort, used for the "next deadlines" strip) ----------

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_deadline_dates(text: str, today: date | None = None) -> list[date]:
    """Find dates in free text like '15 Jun (non-EU)', 'Jan 15', '2027-01-15'. Yearless dates roll to the next occurrence."""
    today = today or date.today()
    found: list[date] = []
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        try:
            found.append(date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{4}))?", text, re.I):
        found += _mk(int(m[1]), m[2], m[3], today)
    for m in re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?", text, re.I):
        found += _mk(int(m[2]), m[1], m[3], today)
    return sorted(set(found))


def _mk(day: int, mon: str, year: str | None, today: date) -> list[date]:
    mo = _MONTHS[mon[:3].lower()]
    try:
        if year:
            return [date(int(year), mo, day)]
        d = date(today.year, mo, day)
        if d < today:
            d = date(today.year + 1, mo, day)
        return [d]
    except ValueError:
        return []


def next_deadlines(data: dict[str, Any], today: date | None = None, days: int = 400) -> list[dict[str, Any]]:
    today = today or date.today()
    out = []
    for u in data.get("universities", []):
        for p in u.get("programs", []):
            if p.get("stage") in ("Rejected", "Declined", "Accepted"):
                continue
            best = None
            for label, raw in (p.get("deadlines") or {}).items():
                for d in parse_deadline_dates(s(raw), today):
                    if d >= today and (best is None or d < best[0]):
                        best = (d, label, s(raw))
            if best and (best[0] - today).days <= days:
                out.append({"program_key": p["id"], "university": u["name"], "program": p["name"],
                            "date": best[0].isoformat(), "days_left": (best[0] - today).days,
                            "label": best[1], "raw": best[2], "apply": bool(p.get("apply")), "stage": p.get("stage")})
    out.sort(key=lambda x: (not x["apply"], x["days_left"]))
    return out


# ---------- normalisation ----------

def new_score_meta() -> dict[str, Any]:
    return {"source": "", "locked": False, "updated_at": "", "rationale": "", "blockers": [],
            "strengths": [], "risks": [], "next_step": ""}


def normalize_score_meta(m: Any, has_score: bool) -> dict[str, Any]:
    base = new_score_meta()
    if isinstance(m, dict):
        for k in base:
            if k in m:
                base[k] = m[k]
    base["locked"] = boolish(base["locked"])
    for k in ("blockers", "strengths", "risks"):
        v = base[k]
        base[k] = [s(x) for x in v if s(x)] if isinstance(v, list) else ([s(v)] if s(v) else [])
    for k in ("source", "updated_at", "rationale", "next_step"):
        base[k] = s(base[k])
    if base["source"] not in ("manual", "ai", "rule", ""):
        base["source"] = "manual"
    if not has_score:
        base = new_score_meta()
    return base


def normalize_program(p: dict[str, Any], uni_id: str, taken: set[str] | None = None) -> dict[str, Any]:
    p = deepcopy(p) if isinstance(p, dict) else {}
    out: dict[str, Any] = {}
    # renames from the old app / from AI imports
    # older versions stored these under applicant-specific names such as "fit_with_<name>"
    for legacy_key in [k for k in p if str(k).startswith("fit_with_")]:
        if "fit_note" not in p:
            p["fit_note"] = p[legacy_key]
        p.pop(legacy_key)
    if "program" in p and "name" not in p:
        p["name"] = p["program"]
    old_status = s(p.get("status"))
    if "verification" not in p and old_status and old_status not in STAGES:
        p["verification"] = old_status
    stage = s(p.get("stage")) or (old_status if old_status in STAGES else "")
    stage = next((x for x in STAGES if x.lower() == stage.lower()), "Wishlist")

    for k in PROGRAM_TEXT:
        out[k] = s(p.get(k))
    out["name"] = out["name"] or "Untitled program"
    out["degree"] = out["degree"] or "Master"
    out["official_link"] = to_link(p.get("official_link"))
    tuition, tnote = parse_tuition(p.get("tuition_eur_per_year", p.get("tuition")))
    out["tuition_eur_per_year"] = tuition
    out["tuition_note"] = out["tuition_note"] or tnote
    out["deadlines"] = to_deadlines(p.get("deadlines"))
    out["sources"] = to_sources(p.get("sources"))
    out["tags"] = to_tags(p.get("tags"))
    out["stage"] = stage
    out["apply"] = boolish(p.get("apply"))
    score = to_score(p.get("fit_score"))
    if p.get("fit_score") not in (None, "") and score is None:
        log.warning("fit_score %r on '%s' is not a number; ignored", p.get("fit_score"), out["name"])
    out["fit_score"] = score
    out["score_meta"] = normalize_score_meta(p.get("score_meta"), score is not None)
    out["created_at"] = s(p.get("created_at")) or now_iso()
    out["updated_at"] = s(p.get("updated_at")) or out["created_at"]

    pid = s(p.get("id"))
    base = slug(out["name"])
    if not pid or not pid.startswith(uni_id + "--"):
        pid = f"{uni_id}--{base}"
    if taken is not None:
        orig, n = pid, 2
        while pid in taken:
            pid = f"{orig}-{n}"
            n += 1
        taken.add(pid)
    out["id"] = pid
    return {"id": out.pop("id"), **out}


def normalize_prof(q: dict[str, Any], uni_id: str, prog_map: dict[str, str] | None = None,
                   taken: set[str] | None = None) -> dict[str, Any]:
    q = deepcopy(q) if isinstance(q, dict) else {}
    for legacy_key in [k for k in q if str(k).startswith("relevance_to_")]:
        if "relevance" not in q:
            q["relevance"] = q[legacy_key]
        q.pop(legacy_key)
    if "status" in q and "verification" not in q:
        q["verification"] = q.pop("status")
    out: dict[str, Any] = {k: s(q.get(k)) for k in PROF_TEXT}
    out["name"] = out["name"] or "Unnamed professor"
    out["page"] = to_link(q.get("page")) if re.search(r"https?://|\.\w{2,}", s(q.get("page"))) else out["page"]
    out["sources"] = to_sources(q.get("sources"))
    oc = s(q.get("outreach_status"))
    out["outreach_status"] = next((x for x in OUTREACH if x.lower() == oc.lower()), oc or "Not Contacted")
    pid = s(q.get("program_id"))
    if pid and prog_map:
        pid = prog_map.get(pid, pid)
    out["program_id"] = pid
    out["created_at"] = s(q.get("created_at")) or now_iso()
    qid = s(q.get("id"))
    if not qid or not qid.startswith(uni_id + "--"):
        qid = f"{uni_id}--{slug(out['name'])}"
    if taken is not None:
        orig, n = qid, 2
        while qid in taken:
            qid = f"{orig}-{n}"
            n += 1
        taken.add(qid)
    return {"id": qid, **out}


def normalize_university(u: dict[str, Any], taken_unis: set[str] | None = None,
                         taken_progs: set[str] | None = None, taken_profs: set[str] | None = None) -> dict[str, Any]:
    u = deepcopy(u) if isinstance(u, dict) else {}
    name = s(u.get("name")) or "Unnamed university"
    uid = s(u.get("id"))
    if not uid or "_" in uid or uid != slug(uid, 60):
        uid = slug(name)
    if taken_unis is not None:
        orig, n = uid, 2
        while uid in taken_unis:
            uid = f"{orig}-{n}"
            n += 1
        taken_unis.add(uid)
    taken_progs = taken_progs if taken_progs is not None else set()
    taken_profs = taken_profs if taken_profs is not None else set()
    prog_map: dict[str, str] = {}
    progs = []
    for p in u.get("programs") or []:
        np_ = normalize_program(p, uid, taken_progs)
        if isinstance(p, dict) and p.get("id"):
            prog_map[s(p["id"])] = np_["id"]
        prog_map.setdefault(np_["name"], np_["id"])
        progs.append(np_)
    profs = [normalize_prof(q, uid, prog_map, taken_profs) for q in (u.get("professors") or [])]
    return {"id": uid, "name": name, "country": s(u.get("country")), "city": s(u.get("city")),
            "batch": s(u.get("batch")), "website": to_link(u.get("website")),
            "programs": progs, "professors": profs}


def normalize_tracker(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        raw = {"universities": raw}
    if not isinstance(raw, dict):
        raw = {}
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    tu, tp, tq = set(), set(), set()
    unis = [normalize_university(u, tu, tp, tq) for u in raw.get("universities", []) if isinstance(u, dict)]
    return {"meta": meta, "universities": unis}


# ---------- merging ----------

def _empty(v: Any) -> bool:
    return v in (None, "", [], {})


def merge_record(dst: dict[str, Any], src: dict[str, Any], mode: str, user_fields: set[str]) -> list[str]:
    """Merge src into dst in place. mode: 'fill' (only blanks) or 'overwrite' (everything except user fields).
    Returns the list of changed keys."""
    changed = []
    for k, v in src.items():
        if k in ("id", "created_at", "updated_at", "program_id") or k in ("programs", "professors"):
            continue
        if k in user_fields and not _empty(dst.get(k)):
            continue
        if isinstance(v, list) and isinstance(dst.get(k), list):
            merged = list(dst[k]) + [x for x in v if x not in dst[k]]
            if merged != dst[k]:
                dst[k] = merged
                changed.append(k)
            continue
        if isinstance(v, dict) and isinstance(dst.get(k), dict) and k != "score_meta":
            merged = {**v, **dst[k]} if mode == "fill" else {**dst[k], **v}
            if merged != dst[k]:
                dst[k] = merged
                changed.append(k)
            continue
        if _empty(v):
            continue
        if _empty(dst.get(k)) or (mode == "overwrite" and dst.get(k) != v):
            dst[k] = v
            changed.append(k)
    return changed


def dedupe_tracker(data: dict[str, Any]) -> list[str]:
    """Merge universities with the same name and programs/professors with the same name. Returns a human-readable report."""
    report: list[str] = []
    by_uni: dict[str, dict[str, Any]] = {}
    merged_unis: list[dict[str, Any]] = []
    alias: dict[str, str] = {}  # dropped duplicate program id -> kept id
    for u in data["universities"]:
        k = uni_key(u["name"])
        if k in by_uni:
            keep = by_uni[k]
            report.append(f"merged duplicate university '{u['name']}' ({u['id']} into {keep['id']})")
            merge_record(keep, u, "fill", set())
            keep["programs"] += u["programs"]
            keep["professors"] += u["professors"]
        else:
            by_uni[k] = u
            merged_unis.append(u)
    for u in merged_unis:
        progs: dict[str, dict[str, Any]] = {}
        for p in u["programs"]:
            k = norm_key(p["name"])
            if k in progs:
                keep = progs[k]
                merge_record(keep, p, "fill", USER_PROGRAM_FIELDS)
                if keep.get("fit_score") is None and p.get("fit_score") is not None:
                    keep["fit_score"], keep["score_meta"] = p["fit_score"], p["score_meta"]
                alias[p["id"]] = keep["id"]
                report.append(f"merged duplicate program '{p['name']}' at {u['name']}")
            else:
                progs[k] = p
        u["programs"] = list(progs.values())
        profs: dict[str, dict[str, Any]] = {}
        for q in u["professors"]:
            k = norm_key(q["name"])
            if k in profs:
                merge_record(profs[k], q, "fill", USER_PROF_FIELDS)
                report.append(f"merged duplicate professor '{q['name']}' at {u['name']}")
            else:
                profs[k] = q
        u["professors"] = list(profs.values())
    data["universities"] = merged_unis
    # re-normalise ids after merges so they stay unique and consistent
    pid_remap: dict[str, str] = {}
    tp, tq = set(), set()
    for u in data["universities"]:
        for p in u["programs"]:
            new = f"{u['id']}--{slug(p['name'])}"
            n, orig = 2, new
            while new in tp:
                new = f"{orig}-{n}"
                n += 1
            tp.add(new)
            pid_remap[p["id"]] = new
            p["id"] = new
        for q in u["professors"]:
            new = f"{u['id']}--{slug(q['name'])}"
            n, orig = 2, new
            while new in tq:
                new = f"{orig}-{n}"
                n += 1
            tq.add(new)
            q["id"] = new
            pid = alias.get(q.get("program_id", ""), q.get("program_id", ""))
            q["program_id"] = pid_remap.get(pid, pid)
    return report


def health_check(data: dict[str, Any]) -> list[dict[str, str]]:
    """Problems the user can fix: missing links, no score, duplicate ids, etc."""
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for u in data["universities"]:
        for p in u["programs"]:
            where = f"{u['name']} / {p['name']}"
            if p["id"] in seen:
                issues.append({"level": "error", "where": where, "msg": "duplicate program id", "id": p["id"]})
            seen.add(p["id"])
            if not p.get("official_link", "").startswith("http"):
                issues.append({"level": "warn", "where": where, "msg": "no official link", "id": p["id"]})
            if p.get("fit_score") is None:
                issues.append({"level": "info", "where": where, "msg": "no score yet", "id": p["id"]})
            if not p.get("deadlines"):
                issues.append({"level": "info", "where": where, "msg": "no deadline captured", "id": p["id"]})
        ids = {p["id"] for p in u["programs"]}
        for q in u["professors"]:
            if q.get("program_id") and q["program_id"] not in ids:
                issues.append({"level": "warn", "where": f"{u['name']} / {q['name']}",
                               "msg": "professor linked to a program that no longer exists", "id": q["id"]})
    return issues


# ---------- flattening for CSV export ----------

def flatten_programs(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for u in data["universities"]:
        for p in u["programs"]:
            rows.append({**p, "university_id": u["id"], "country": u["country"], "city": u["city"],
                         "university": u["name"], "batch": u["batch"], "program": p["name"],
                         "score_source": (p.get("score_meta") or {}).get("source", "")})
    return rows


def flatten_profs(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for u in data["universities"]:
        pm = {p["id"]: p["name"] for p in u["programs"]}
        for q in u["professors"]:
            rows.append({**q, "country": u["country"], "university": u["name"],
                         "program": pm.get(q.get("program_id", ""), "")})
    return rows


def find_program(data: dict[str, Any], pid: str):
    for u in data["universities"]:
        for p in u["programs"]:
            if p["id"] == pid:
                return u, p
    return None, None


def find_prof(data: dict[str, Any], qid: str):
    for u in data["universities"]:
        for q in u["professors"]:
            if q["id"] == qid:
                return u, q
    return None, None


def find_uni(data: dict[str, Any], uid: str):
    return next((u for u in data["universities"] if u["id"] == uid), None)


def today_str() -> str:
    return datetime.now().date().isoformat()
