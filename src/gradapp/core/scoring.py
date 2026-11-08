"""Scores.

A program's score always has a *source*:
  manual - typed by the user (locked by default so nothing overwrites it)
  ai     - written by the AI re-score (only the score + short rationale)
  rule   - a transparent estimate from the program's own fields (Estimate)

Scores are never fabricated from text: blank means "not scored yet".
"""
from __future__ import annotations

from typing import Any

from .models import to_score
from .storage import log, now_iso


def rule_score(p: dict[str, Any]) -> tuple[float, str]:
    """Generic, explainable estimate. Returns (score, rationale)."""
    score = 55.0
    why: list[str] = []
    risk = (p.get("auto_gpa_filter_risk") or "").lower()
    admission = (p.get("admission_mode") or "").lower()
    verification = (p.get("verification") or "").lower()

    head = risk.split(":")[0].strip()
    if head.startswith(("low", "none", "minimal")):
        score += 15; why.append("low GPA-filter risk +15")
    elif head.startswith(("medium", "moderate")):
        score -= 5; why.append("medium GPA-filter risk -5")
    elif head.startswith("high"):
        score -= 18; why.append("high GPA-filter risk -18")
    elif head.startswith(("disqualif", "severe", "unlikely", "blocked")):
        score -= 40; why.append("blocked by an eligibility rule -40")

    if "open admission" in admission or "nc-frei" in admission or "zulassungsfrei" in admission:
        score += 6; why.append("open admission +6")
    elif "restrict" in admission or "numerus" in admission or "selective" in admission:
        score -= 4; why.append("restricted admission -4")

    tuition = p.get("tuition_eur_per_year")
    if tuition == 0:
        score += 6; why.append("no tuition +6")
    elif isinstance(tuition, (int, float)) and tuition >= 10000:
        score -= 10; why.append("tuition over 10k/year -10")
    elif isinstance(tuition, (int, float)) and tuition >= 3000:
        score -= 4; why.append("tuition over 3k/year -4")

    if "english" in (p.get("language") or "").lower():
        score += 4; why.append("taught in English +4")
    if "scholarship" in (p.get("funding") or "").lower():
        score += 3; why.append("scholarship mentioned +3")
    if p.get("risk_alert"):
        score -= 5; why.append("risk alert -5")

    if "not yet researched" in verification or "listing only" in verification or "not verified" in verification:
        score = min(score, 55.0); why.append("unverified details cap at 55")

    score = round(max(0.0, min(100.0, score)), 1)
    return score, "; ".join(why) or "no signals; neutral baseline"


def apply_rule_score(p: dict[str, Any], force: bool = False) -> bool:
    """Set an estimate unless the user (or AI) already scored it. Returns True when changed."""
    meta = p.get("score_meta") or {}
    if p.get("fit_score") is not None and not force:
        return False
    if meta.get("locked") and not force:
        return False
    val, why = rule_score(p)
    p["fit_score"] = val
    p["score_meta"] = {**meta, "source": "rule", "locked": False, "updated_at": now_iso(),
                       "rationale": why, "blockers": [], "strengths": [], "risks": [], "next_step": ""}
    log.info("SCORE rule  %-6s %s  (%s)", val, p.get("name"), why)
    return True


def set_manual_score(p: dict[str, Any], value: Any, lock: bool = True, note: str = "") -> None:
    v = to_score(value)
    if v is None:
        raise ValueError("score must be a number between 0 and 100")
    meta = p.get("score_meta") or {}
    p["fit_score"] = v
    p["score_meta"] = {**meta, "source": "manual", "locked": bool(lock), "updated_at": now_iso(),
                       "rationale": note or (meta.get("rationale", "") if meta.get("source") == "manual" else ""),
                       "blockers": [], "strengths": [], "risks": [], "next_step": ""}
    log.info("SCORE manual %-6s %s locked=%s", v, p.get("name"), lock)


def clear_score(p: dict[str, Any]) -> None:
    p["fit_score"] = None
    p["score_meta"] = {"source": "", "locked": False, "updated_at": "", "rationale": "", "blockers": [],
                       "strengths": [], "risks": [], "next_step": ""}


def set_ai_score(p: dict[str, Any], result: dict[str, Any], force: bool = False) -> bool:
    """Write ONLY the score fields. Refuses when the user locked a manual score unless force=True."""
    meta = p.get("score_meta") or {}
    if meta.get("locked") and not force:
        log.info("SCORE ai skipped (locked) %s", p.get("name"))
        return False
    v = to_score(result.get("score"))
    if v is None:
        raise ValueError("AI result had no numeric score")
    p["fit_score"] = v
    p["score_meta"] = {
        "source": "ai", "locked": False, "updated_at": now_iso(),
        "rationale": str(result.get("rationale") or "")[:1200],
        "blockers": [str(x) for x in (result.get("blockers") or [])][:8],
        "strengths": [str(x) for x in (result.get("strengths") or [])][:8],
        "risks": [str(x) for x in (result.get("risks") or [])][:8],
        "next_step": str(result.get("next_step") or "")[:600],
    }
    log.info("SCORE ai    %-6s %s", v, p.get("name"))
    return True


def tier(score: float | None) -> str:
    if score is None:
        return "unscored"
    if score >= 75:
        return "strong"
    if score >= 45:
        return "possible"
    return "unlikely"
