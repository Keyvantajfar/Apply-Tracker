"""Import an older single-user GradApp folder (universities.json, optional programs.csv / professors.csv /
app_memory.json) into an account.   Command line:  gradapp import-legacy FOLDER --user NAME

Rules:
  * universities.json is the source of truth. The old programs.csv could be malformed (unquoted commas shifted
    its columns, which produced 0% scores), so it is only checked and reported, never trusted.
  * Nothing is lost: every field is carried over (a few were renamed, see models.py).
  * Well-formed professor CSV rows can fill blanks; malformed rows are skipped and listed in the report.
  * Scores are kept as they were; unscored programs get a rule-based estimate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import models, scoring
from .storage import log, now_iso, read_csv_strict, read_json
from .users import Workspace


def build_tracker_from_legacy(legacy: Path) -> tuple[dict[str, Any], dict[str, str], dict[str, Any], list[str]]:
    legacy = Path(legacy)
    if not (legacy / "universities.json").exists():
        raise FileNotFoundError(f"No universities.json in {legacy}")
    report: list[str] = []
    raw = read_json(legacy / "universities.json", {"universities": []})
    n_raw_unis = len(raw.get("universities", []))
    n_raw_progs = sum(len(u.get("programs", [])) for u in raw.get("universities", []))
    data = models.normalize_tracker(raw)
    report.append(f"Read universities.json: {n_raw_unis} university entries, {n_raw_progs} programs.")
    report += ["  - " + r for r in models.dedupe_tracker(data)]

    # professors: fill blanks from well-formed CSV rows
    pcsv = legacy / "professors.csv"
    if pcsv.exists():
        rows, problems = read_csv_strict(pcsv)
        report += [f"professors.csv: {x}" for x in problems]
        filled = 0
        by_name = {(models.uni_key(u["name"]), models.norm_key(q["name"])): q for u in data["universities"] for q in u["professors"]}
        for r in rows:
            q = by_name.get((models.uni_key(r.get("university")), models.norm_key(r.get("name"))))
            if q:
                src = models.normalize_prof(r, "x")
                filled += len(models.merge_record(q, src, "fill", models.USER_PROF_FIELDS))
        report.append(f"professors.csv: {len(rows)} well-formed rows, {filled} blank fields filled.")
    # programs csv: only report health, the JSON already holds everything
    gcsv = legacy / "programs.csv"
    if gcsv.exists():
        rows, problems = read_csv_strict(gcsv)
        report.append(f"programs.csv: {len(rows)} well-formed rows; {len(problems)} malformed rows ignored "
                      f"(universities.json used instead):")
        report += ["    " + p for p in problems]

    # scores: carry over, then fill unscored with a transparent rule-based estimate
    carried = estimated = 0
    for u in data["universities"]:
        for p in u["programs"]:
            if p["fit_score"] is not None:
                p["score_meta"] = {**p["score_meta"], "source": "manual", "locked": False, "updated_at": now_iso(),
                                   "rationale": "Carried over from your previous tracker."}
                carried += 1
            elif scoring.apply_rule_score(p):
                estimated += 1
    report.append(f"Scores: {carried} carried over unchanged, {estimated} unscored programs got a rule-based estimate.")

    mem = read_json(legacy / "app_memory.json", {})
    profile = {**(raw.get("applicant_profile") or {}), **(mem.get("applicant_profile") or {})}
    profile = {k: models.s(v) for k, v in profile.items()}
    settings = {}
    st = mem.get("settings") or {}
    if st.get("ai_base_url"):
        settings["ai_base_url"] = st["ai_base_url"]
    if st.get("ai_model"):
        settings["ai_model"] = st["ai_model"]
    data["meta"]["migrated_from"] = "legacy folder"
    n_unis = len(data["universities"])
    n_progs = sum(len(u["programs"]) for u in data["universities"])
    n_profs = sum(len(u["professors"]) for u in data["universities"])
    report.append(f"Result: {n_unis} universities, {n_progs} programs, {n_profs} professors.")
    return data, profile, {"settings": settings, "resume_text": mem.get("resume_text", "")}, report


def import_legacy(ws: Workspace, legacy: Path) -> list[str]:
    """Replace the account's tracker and profile with the migrated legacy data (a backup of the old tracker is kept)."""
    data, profile, extra, report = build_tracker_from_legacy(legacy)
    ws.save_tracker(data, backup=True)
    ws.save_profile(profile)
    if extra["settings"]:
        ws.save_settings(extra["settings"])
    if extra["resume_text"]:
        ws.resume_path.write_text(extra["resume_text"], encoding="utf-8")
    (ws.dir / "migration_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    for line in report:
        log.info("MIGRATE %s", line)
    return report
