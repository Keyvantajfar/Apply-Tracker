"""Research-prompt generator and JSON importer.

Flow: user builds a prompt here -> pastes it into ANY AI with web access (ChatGPT, Gemini, Claude, Perplexity...)
-> pastes the JSON answer back -> preview (nothing saved) -> import (backup is made first).
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from . import models, scoring
from .ai import AIError, extract_json
from .storage import log

SCHEMA_EXAMPLE = {
    "universities": [
        {
            "name": "Technical University of Example",
            "country": "Germany",
            "city": "Example City",
            "website": "https://www.example.edu/",
            "programs": [
                {
                    "name": "M.Sc. Data Science",
                    "degree": "Master",
                    "language": "English",
                    "duration": "4 semesters",
                    "tuition_eur_per_year": 0,
                    "tuition_note": "No tuition; semester fee about 350 EUR",
                    "official_link": "https://www.example.edu/data-science-msc",
                    "deadlines": {"winter": "2027-05-31", "summer": "2027-01-15"},
                    "admission_mode": "open admission | local admission restriction | aptitude test | ...",
                    "gpa_rule": "Minimum requirements in plain words (ECTS per subject, minimum grade, tests)",
                    "language_requirement": "IELTS 6.5 or TOEFL 88",
                    "funding": "Scholarships, assistantships, tuition waivers that apply to international students",
                    "risk_alert": "Anything that could disqualify or surprise an applicant, or empty",
                    "verification": "verified on official page | partly verified | listing only",
                    "sources": ["https://www.example.edu/data-science-msc/admission"],
                }
            ],
            "professors": [
                {
                    "name": "Prof. Jane Doe",
                    "title": "Professor",
                    "affiliation": "Chair of Machine Learning",
                    "research_interests": "graph neural networks, recommender systems",
                    "email": "jane.doe@example.edu",
                    "email_source": "https://www.example.edu/people/jane-doe",
                    "page": "https://www.example.edu/people/jane-doe",
                    "open_phd_calls": "yes - link or reference, or 'none seen'",
                    "program": "M.Sc. Data Science",
                    "verification": "email verified on official page",
                    "sources": ["https://www.example.edu/people/jane-doe"],
                }
            ],
        }
    ]
}


FOCUS_TAG = {"general": "", "erasmus": "Erasmus Mundus", "daad": "DAAD"}

# What each focus adds to the schema example (the AI sees these extra fields filled in).
_ERASMUS_EXTRA = {
    "partners": "Coordinator and partner universities with countries, e.g. 'Univ A (Spain, coordinator); Univ B (Germany); Univ C (Italy)'",
    "tags": ["Erasmus Mundus"],
    "funding": "EMJM scholarship: exact monthly amount, duration, what it covers, and which applicant categories "
               "(programme-country / partner-country) are eligible, as stated on the programme page; plus any "
               "programme-specific or consortium scholarships",
    "deadlines": {"scholarship": "2027-01-15", "self_funded": "2027-03-31"},
    "risk_alert": "Anything that could disqualify or surprise an applicant (nationality or residence rules, "
                  "scholarship quotas, limits on how many applications are allowed, mandatory tests)",
}
_DAAD_EXTRA = {
    "tags": ["DAAD"],
    "funding": "The DAAD scholarship that can fund this programme: name, monthly amount, duration, eligibility "
               "(nationality, years since bachelor, work experience), how to apply (to DAAD directly or via the university) "
               "and its deadline. Say 'no DAAD scholarship found' if none applies",
    "deadlines": {"daad_scholarship": "2026-11-15", "university": "2027-05-31"},
}


def _schema_for(focus: str) -> dict[str, Any]:
    schema = json.loads(json.dumps(SCHEMA_EXAMPLE))
    prog = schema["universities"][0]["programs"][0]
    if focus == "erasmus":
        prog.update(_ERASMUS_EXTRA)
        prog["name"] = "Official programme name (ACRONYM)"
        schema["universities"][0]["name"] = "Coordinating university"
        schema["universities"][0].pop("professors", None)
    elif focus == "daad":
        prog.update(_DAAD_EXTRA)
    return schema


def _focus_rules(focus: str) -> list[str]:
    if focus == "erasmus":
        return [
            "", "## Erasmus Mundus rules",
            "- Only programmes that are officially Erasmus Mundus Joint Masters (EMJM). Check the official Erasmus Mundus "
            "catalogue on the Erasmus+ website (erasmus-plus.ec.europa.eu) and the programme's own site. Labels that only "
            "look similar (for example quality labels such as EMOS, or EIT Digital Master School) are NOT Erasmus Mundus: leave them out.",
            "- One entry per programme, not per partner. Put the coordinating university in the university \"name\", and "
            "list every consortium university with its country in \"partners\".",
            "- \"funding\": copy the scholarship terms exactly from the programme page or the official EMJM page, and say "
            "which applicant categories get which amount. If the programme says nationality or residence changes eligibility, put it in \"risk_alert\".",
            "- \"deadlines\": give the scholarship round and the self-funded round separately (keys \"scholarship\" and "
            "\"self_funded\") for the NEXT intake, with the exact date.",
            "- Put \"Erasmus Mundus\" in \"tags\". Skip the \"professors\" list for this search.",
            "- Prefer programmes whose admission requirements fit the applicant profile below; list at least the number of "
            "programmes asked for, but do not pad the list with programmes that clearly do not fit the field.",
        ]
    if focus == "daad":
        return [
            "", "## DAAD rules",
            "- Use DAAD's own databases: the International Programmes database (programmes) and the scholarship database "
            "(daad.de) to find programmes in Germany and the scholarships that can fund them. Then confirm requirements on the "
            "university's official page.",
            "- One entry per programme. Put the DAAD scholarship that can fund it in \"funding\": scholarship name, "
            "monthly amount, duration, eligibility (nationality, years since bachelor's degree, work experience) and whether "
            "the application goes to DAAD or to the university.",
            "- \"deadlines\": give the DAAD scholarship deadline (key \"daad_scholarship\") and the university deadline "
            "(key \"university\") separately, with exact dates for the NEXT intake.",
            "- Put anything about eligibility that could rule the applicant out (nationality, graduation date, minimum work "
            "experience, required language certificate) in \"risk_alert\".",
            "- Put \"DAAD\" in \"tags\". Include professors only if asked above.",
        ]
    return []


def build_research_prompt(opts: dict[str, Any], profile: dict[str, str], existing: list[str]) -> str:
    focus = models.s(opts.get("focus")) or "general"
    if focus not in FOCUS_TAG:
        raise ValueError("Unknown focus.")
    countries = [c.strip() for c in models.s(opts.get("countries")).replace("\n", ",").split(",") if c.strip()]
    if not countries:
        if focus == "daad":
            countries = ["Germany"]
        elif focus == "erasmus":
            countries = ["any European country"]
        else:
            raise ValueError("Enter at least one country.")
    level = models.s(opts.get("level")) or "Master"
    fields = models.s(opts.get("fields")) or "any field relevant to the applicant profile"
    intake = models.s(opts.get("intake"))
    language = models.s(opts.get("language"))
    budget = models.s(opts.get("max_tuition"))
    count = int(opts.get("count") or 10)
    with_profs = bool(opts.get("professors", True)) and focus != "erasmus"
    extra = models.s(opts.get("extra"))

    kind = {"general": f"{level} programs", "erasmus": f"Erasmus Mundus Joint {level} programmes",
            "daad": f"{level} programmes funded or fundable by DAAD"}[focus]
    per = "programmes" if focus == "erasmus" else "universities per country"
    lines = [
        f"You are a careful research assistant for a graduate-school applicant. Use web search / browsing. "
        f"Find real {kind} in: {', '.join(countries)}.",
        "",
        "## What to find",
        f"- Field of study: {fields}",
        (f"- About {count} {per} (fewer is fine if fewer truly fit), best matches first."
         if focus == "erasmus" else
         f"- About {count} {per} (fewer is fine if fewer truly fit), 1-3 programs each, best matches first."),
    ]
    if intake:
        lines.append(f"- Intake: {intake}")
    if language:
        lines.append(f"- Language of instruction: {language}")
    if budget:
        lines.append(f"- Maximum tuition: {budget} (EUR per year; skip programs above it, mention funding that offsets it)")
    if with_profs:
        lines.append("- For each university, 1-3 professors whose research matches the field and who supervise students "
                     "(PhD/MSc). Only include professors you found on an official university page.")
    if extra:
        lines.append(f"- Also: {extra}")
    lines += _focus_rules(focus)
    if opts.get("include_profile") and any(profile.values()):
        lines += ["", "## Applicant (judge admission requirements against this; do not copy it into the output)",
                  "\n".join(f"- {models.PROFILE_LABELS.get(k, k)}: {v}" for k, v in profile.items() if v)]
    if existing:
        lines += ["", "## Already tracked - do NOT include these again", "\n".join(f"- {x}" for x in existing[:120])]

    lines += [
        "", "## Rules for accuracy (important)",
        "1. Open the OFFICIAL university or department page for every program and read the admission requirements. "
        "Third-party listings (Mastersportal, DAAD, etc.) are only acceptable for discovery; mark such entries "
        "\"verification\": \"listing only\".",
        "2. NEVER guess. If you cannot find a value on an official page, use \"\" (or null for tuition) and say so in "
        "\"verification\". Do not write \"not captured\" or \"N/A\" inside value fields.",
        "3. Emails: copy only addresses published on an official page. Never construct an email from a name pattern.",
        "4. Deadlines: copy the exact dates for NON-EU / international applicants when they differ, ISO format "
        "YYYY-MM-DD where possible, otherwise the exact wording. Use keys like \"winter\", \"summer\", \"non_eu\".",
        "5. tuition_eur_per_year must be a NUMBER in EUR per year (0 if no tuition). Convert other currencies and say "
        "how in \"tuition_note\". Include semester fees in the note, not in the number.",
        "6. gpa_rule: state the real hard requirements in plain words (minimum grade and how it is computed, required "
        "ECTS per subject area, entrance tests, language certificates). Put anything that could reject an applicant "
        "in \"risk_alert\".",
        "7. Every program needs \"official_link\" (the program page, https) and at least one URL in \"sources\".",
        ("8. Do not include scores, ratings or stages - the tracker computes those itself." if focus == "general" else
         "8. Do not include scores, chances, ratings or ranks (guessed percentages are useless to me) - the tracker computes those itself."),
        "9. No duplicates: one entry per program, one entry per university.",
        "", "## Output format",
        "Reply with ONE JSON code block and nothing else (no introduction, no summary). Use exactly this structure "
        "(field names must match; extra fields are ignored):",
        "```json", json.dumps(_schema_for(focus), ensure_ascii=False, indent=2), "```",
        "",
        "If the answer is too long for one reply, finish the JSON of the " + ("universities" if focus == "general" else "entries") +
        " you have completed (valid, closed JSON) and tell me to say \"continue\"; then send the next " +
        ("universities" if focus == "general" else "entries") + " in the same format.",
    ]
    return "\n".join(lines)


def build_convert_prompt(focus: str = "general") -> str:
    """Prompt for turning a list an AI already produced (in the same chat) into the import format."""
    if focus not in FOCUS_TAG:
        raise ValueError("Unknown focus.")
    extra = {"erasmus": 'Put the coordinating university in the university "name" and the other consortium universities (with countries) in "partners". Put "Erasmus Mundus" in "tags". Put scholarship terms in "funding" and the scholarship / self-funded deadlines in "deadlines".',
             "daad": 'Put the DAAD scholarship details (name, amount, duration, eligibility, deadline) in "funding" and put "DAAD" in "tags".',
             "general": ""}[focus]
    return "\n".join([
        "Convert the list of programmes you gave me above into the JSON format below. Convert only; do NOT add anything you "
        "did not already state or cannot support with a source.",
        "",
        "Rules:",
        "- Group programmes under their university: {\"universities\": [{\"name\", \"country\", \"city\", \"programs\": [...]}]}.",
        "- Map each of your fields to the closest field below: link -> official_link, requirements -> gpa_rule, "
        "fund/funding -> funding, application window -> deadlines (an object, ISO dates where known), "
        "program_name -> name, risks -> risk_alert.",
        "- DROP rankings, suitability scores and chance percentages. Do not convert them.",
        "- If a value is not in your list, use \"\" (or null for tuition). Never fill gaps with guesses; instead set "
        "\"verification\": \"converted from an unverified list\".",
        "- tuition_eur_per_year must be a number (0 if no tuition) or null.",
        "- Every programme must keep its link; put it in \"official_link\" and also in \"sources\".",
        extra,
        "",
        "Reply with ONE JSON code block and nothing else. Structure:",
        "```json", json.dumps(_schema_for(focus), ensure_ascii=False, indent=2), "```",
        "",
        "If it is too long for one reply, close the JSON validly and I will say \"continue\".",
    ])


# ---------- parsing ----------

def _flat_rows_to_unis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unis: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = models.s(r.get("university") or r.get("university_name"))
        if not name:
            continue
        u = unis.setdefault(models.uni_key(name), {"name": name, "country": r.get("country", ""), "city": r.get("city", ""),
                                                  "programs": [], "professors": []})
        u["programs"].append({k: v for k, v in r.items() if k not in ("university", "country", "city")})
    return list(unis.values())


def parse_import(payload: Any, tag: str = "") -> tuple[list[dict[str, Any]], list[str]]:
    """Accept text or already-parsed JSON. Returns (universities, warnings). Raises ValueError with a clear message."""
    warnings: list[str] = []
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8-sig", "replace")
    if isinstance(payload, str):
        if not payload.strip():
            raise ValueError("Paste the AI's JSON answer first.")
        try:
            payload = extract_json(payload)
        except AIError as e:
            raise ValueError("Could not find valid JSON in that text. If the AI's answer was cut off, ask it to "
                             "continue and paste only complete JSON. Make sure code fences and quotes were not altered.") from e
    unis = None
    if isinstance(payload, dict):
        if isinstance(payload.get("universities"), list):
            unis = payload["universities"]
        elif isinstance(payload.get("programs"), list):
            unis = _flat_rows_to_unis(payload["programs"])
        elif payload.get("name") and isinstance(payload.get("programs", []), list):
            unis = [payload]
    elif isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "programs" in payload[0]:
            unis = payload
        elif payload and isinstance(payload[0], dict) and ("university" in payload[0] or "program" in payload[0]):
            unis = _flat_rows_to_unis(payload)
    if unis is None:
        raise ValueError('Expected {"universities": [ ... ]}. That JSON has a different shape.')
    clean = []
    for i, u in enumerate(unis, start=1):
        if not isinstance(u, dict) or not models.s(u.get("name")):
            warnings.append(f"Entry {i}: no university name, skipped.")
            continue
        u = deepcopy(u)
        u.pop("id", None)
        for p in u.get("programs") or []:
            if isinstance(p, dict):
                p.pop("id", None)
                p.pop("fit_score", None)       # the tracker owns scores
                p.pop("score_meta", None)
                p.pop("stage", None)
                p.pop("apply", None)
                for k in ("rank", "suitability_score", "full_scholarship_chance_pct", "admission_or_waiver_chance_pct"):
                    p.pop(k, None)
                if tag:
                    p["tags"] = models.to_tags(list(models.to_tags(p.get("tags"))) + [tag])
                if p.get("language_requirement") and not p.get("gpa_rule"):
                    pass
                if p.get("language_requirement"):
                    lr = models.s(p["language_requirement"])
                    p["gpa_rule"] = (models.s(p.get("gpa_rule")) + f" Language requirement: {lr}").strip()
        progs = {models.norm_key(p.get("name") or p.get("program")): models.s(p.get("name") or p.get("program"))
                 for p in (u.get("programs") or []) if isinstance(p, dict)}
        for q in u.get("professors") or []:
            if isinstance(q, dict):
                q.pop("id", None)
                q.pop("outreach_status", None)
                ref = models.s(q.get("program") or q.get("program_id"))
                q["program_id"] = progs.get(models.norm_key(ref), "") if ref else ""
        clean.append(u)
    if not clean:
        raise ValueError("The JSON contained no universities.")
    return clean, warnings


# ---------- merging into a tracker ----------

def _unique(base: str, taken: set[str]) -> str:
    out, n = base, 2
    while out in taken:
        out = f"{base}-{n}"
        n += 1
    taken.add(out)
    return out


def plan_import(data: dict[str, Any], incoming: list[dict[str, Any]], mode: str = "fill",
                estimate_scores: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (new_data, summary). Never mutates `data`. mode: add | fill | overwrite."""
    if mode not in ("add", "fill", "overwrite"):
        raise ValueError("Unknown import mode.")
    data = deepcopy(data)
    norm = models.normalize_tracker({"universities": incoming})
    taken_u = {u["id"] for u in data["universities"]}
    taken_p = {p["id"] for u in data["universities"] for p in u["programs"]}
    taken_q = {q["id"] for u in data["universities"] for q in u["professors"]}
    by_key = {models.uni_key(u["name"]): u for u in data["universities"]}
    items: list[dict[str, Any]] = []
    c = {"new_universities": 0, "new_programs": 0, "updated_programs": 0, "skipped_programs": 0,
         "new_professors": 0, "updated_professors": 0, "skipped_professors": 0}
    for nu in norm["universities"]:
        key = models.uni_key(nu["name"])
        target = by_key.get(key)
        if not target:
            target = {"id": _unique(models.slug(nu["name"]), taken_u), "name": nu["name"], "country": nu["country"],
                      "city": nu["city"], "batch": nu["batch"], "website": nu["website"], "programs": [], "professors": []}
            data["universities"].append(target)
            by_key[key] = target
            c["new_universities"] += 1
            items.append({"kind": "university", "action": "new", "name": nu["name"], "detail": nu["country"]})
        elif mode != "add":
            models.merge_record(target, {k: nu[k] for k in ("country", "city", "website", "batch")}, "fill", set())
        pmap = {models.norm_key(p["name"]): p for p in target["programs"]}
        idmap: dict[str, str] = {}
        for np_ in nu["programs"]:
            ex = pmap.get(models.norm_key(np_["name"]))
            if ex is None:
                new = dict(np_)
                new["id"] = _unique(f"{target['id']}--{models.slug(np_['name'])}", taken_p)
                if estimate_scores:
                    scoring.apply_rule_score(new)
                target["programs"].append(new)
                pmap[models.norm_key(new["name"])] = new
                idmap[np_["id"]] = new["id"]
                c["new_programs"] += 1
                items.append({"kind": "program", "action": "new", "name": f"{nu['name']} / {np_['name']}",
                              "detail": "" if str(new["official_link"]).startswith("http") else "no official link"})
            else:
                idmap[np_["id"]] = ex["id"]
                if mode == "add":
                    c["skipped_programs"] += 1
                    items.append({"kind": "program", "action": "skip", "name": f"{nu['name']} / {np_['name']}", "detail": "already tracked"})
                else:
                    ch = models.merge_record(ex, np_, mode, models.USER_PROGRAM_FIELDS)
                    if ch:
                        c["updated_programs"] += 1
                        items.append({"kind": "program", "action": "update", "name": f"{nu['name']} / {np_['name']}",
                                      "detail": "changed: " + ", ".join(ch[:6])})
                    else:
                        c["skipped_programs"] += 1
                        items.append({"kind": "program", "action": "skip", "name": f"{nu['name']} / {np_['name']}", "detail": "nothing new"})
        qmap = {models.norm_key(q["name"]): q for q in target["professors"]}
        for nq in nu["professors"]:
            ex = qmap.get(models.norm_key(nq["name"]))
            nq = dict(nq)
            nq["program_id"] = idmap.get(nq.get("program_id", ""), "")
            if ex is None:
                nq["id"] = _unique(f"{target['id']}--{models.slug(nq['name'])}", taken_q)
                target["professors"].append(nq)
                qmap[models.norm_key(nq["name"])] = nq
                c["new_professors"] += 1
                items.append({"kind": "professor", "action": "new", "name": f"{nu['name']} / {nq['name']}", "detail": ""})
            elif mode == "add":
                c["skipped_professors"] += 1
            else:
                ch = models.merge_record(ex, nq, mode, models.USER_PROF_FIELDS)
                if nq.get("program_id") and not ex.get("program_id"):
                    ex["program_id"] = nq["program_id"]
                c["updated_professors" if ch else "skipped_professors"] += 1
    log.info("IMPORT plan (%s): %s", mode, c)
    return data, {"counts": c, "items": items[:400]}
