"""OpenAI-compatible AI client plus the prompts the app uses (score, profile, chat).

Works with OpenAI, OpenRouter, and local servers (Ollama, LM Studio, vLLM). The API key is optional so
local models need none. Reasoning models that emit <think>...</think> are handled.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import models
from .storage import log


class AIError(Exception):
    pass


def chat(settings: dict[str, Any], messages: list[dict[str, str]], temperature: float = 0.2,
         max_tokens: int | None = None) -> str:
    base = str(settings.get("ai_base_url") or "").rstrip("/")
    model = settings.get("ai_model") or ""
    if not base or not model:
        raise AIError("Set the AI server URL and model in Settings first.")
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    if max_tokens:
        body["max_tokens"] = max_tokens
    headers = {"Content-Type": "application/json"}
    if settings.get("ai_api_key"):
        headers["Authorization"] = f"Bearer {settings['ai_api_key']}"
    req = Request(f"{base}/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    timeout = float(settings.get("ai_timeout") or 300)
    n_chars = sum(len(m["content"]) for m in messages)
    log.info("AI  -> %s model=%s prompt=%d chars", base, model, n_chars)
    try:
        with urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        log.error("AI  <- HTTP %s %s", e.code, detail)
        if e.code in (401, 403):
            raise AIError("The AI server rejected the API key (HTTP %s). Check it in Settings." % e.code) from e
        raise AIError(f"The AI server returned HTTP {e.code}. {detail}") from e
    except (URLError, TimeoutError, OSError) as e:
        log.error("AI  <- connection failed: %s", e)
        raise AIError(f"Could not reach the AI server at {base}. Is it running, and is the URL right? ({e})") from e
    except json.JSONDecodeError as e:
        raise AIError("The AI server sent a reply that is not JSON.") from e
    try:
        content = result["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise AIError("The AI server's reply had no message content.") from e
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    log.info("AI  <- %d chars", len(content))
    return content


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model reply (handles ``` fences and chatter)."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S | re.I)
    if m and m.group(1).strip()[:1] in "{[":
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = t.find(open_c)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(t)):
                c = t[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == open_c:
                    depth += 1
                elif c == close_c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start:i + 1])
                        except Exception:  # noqa: BLE001
                            break
            start = t.find(open_c, start + 1)
    raise AIError("The AI did not return valid JSON.")


def chat_json(settings: dict[str, Any], messages: list[dict[str, str]], retries: int = 1) -> Any:
    reply = chat(settings, messages, temperature=0.1)
    try:
        return extract_json(reply)
    except AIError:
        if not retries:
            raise
        log.warning("AI reply was not JSON; retrying once. Reply started: %r", reply[:160])
        messages = messages + [{"role": "assistant", "content": reply[:2000]},
                               {"role": "user", "content": "That was not valid JSON. Reply again with ONLY the JSON object, no commentary, no code fences."}]
        return extract_json(chat(settings, messages, temperature=0))


# ---------- prompts ----------

def profile_text(profile: dict[str, str]) -> str:
    lines = [f"- {models.PROFILE_LABELS.get(k, k.replace('_', ' ').title())}: {v}" for k, v in profile.items() if v]
    return "\n".join(lines) or "(profile is empty)"


def program_brief(uni: dict[str, Any], p: dict[str, Any]) -> str:
    keep = ["name", "degree", "language", "duration", "tuition_eur_per_year", "tuition_note", "deadlines", "admission_mode",
            "gpa_rule", "auto_gpa_filter_risk", "last_two_years_gpa_usable", "funding", "funding_note",
            "risk_alert", "fit_note", "verification", "notes"]
    d = {"university": uni["name"], "country": uni["country"], "city": uni["city"]}
    d.update({k: p.get(k) for k in keep if p.get(k) not in (None, "", {}, [])})
    return json.dumps(d, ensure_ascii=False, indent=1)


def score_messages(profile: dict[str, str], docs: str, uni: dict[str, Any], p: dict[str, Any]) -> list[dict[str, str]]:
    system = ("You are an experienced graduate-admissions advisor. You judge how well ONE applicant fits ONE program "
              "using only the facts supplied. If a fact is missing, say it is unknown instead of guessing. "
              "Reply with ONLY a JSON object, no commentary.")
    user = f"""APPLICANT PROFILE
{profile_text(profile)}

APPLICANT DOCUMENTS (excerpt)
{docs[:6000] or '(none uploaded)'}

PROGRAM
{program_brief(uni, p)}

Score the chance that this applicant is ADMITTED and that the program is a GOOD FIT for their goals (funding, location, topic).
Scale: 85-100 strong match, 65-84 good, 45-64 possible but uncertain, 20-44 unlikely, 0-19 blocked by a hard rule.
Hard blockers (missing required ECTS, GPA below a fixed cutoff, wrong degree) must keep the score below 25.

Return exactly:
{{"score": <number 0-100>,
  "rationale": "<2-3 sentences>",
  "blockers": ["<hard blockers, or empty>"],
  "strengths": ["<short bullets>"],
  "risks": ["<short bullets>"],
  "next_step": "<one concrete action>"}}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def profile_messages(profile: dict[str, str], docs: str, extra: str) -> list[dict[str, str]]:
    keys = ", ".join(models.NEW_PROFILE_KEYS)
    system = ("You build an applicant profile for graduate-school applications from the applicant's own documents. "
              "Use only what the documents say. Never invent numbers. Reply with ONLY a JSON object.")
    user = f"""CURRENT PROFILE (may be empty)
{profile_text(profile)}

DOCUMENTS (resume, transcripts, notes)
{docs[:14000] or '(none)'}

EXTRA INFORMATION FROM THE APPLICANT
{extra[:4000] or '(none)'}

Return exactly:
{{"fields": {{"<snake_case_key>": "<value>", ...}},
  "summary": "<2 sentences describing this applicant>"}}

Prefer these keys when relevant: {keys}. You may add other short snake_case keys (for example publications, certificates,
work_experience, languages, target_countries). Keep each value under 400 characters. Skip keys you have no evidence for.
Always give grades together with their scale (for example "14.28/20"), and credits with their system (ECTS or local)."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


ACTION_HELP = """If (and only if) the applicant asks you to change something, or a change clearly follows, end your reply with ONE block:
```actions
[{"type":"set_stage","program_id":"<id>","value":"Applied"},
 {"type":"set_apply","program_id":"<id>","value":true},
 {"type":"add_note","program_id":"<id>","value":"<text>"},
 {"type":"set_score","program_id":"<id>","value":72},
 {"type":"update_profile","key":"<snake_case>","value":"<text>"}]
```
Stages: Wishlist, Preparing, Applied, Interview, Accepted, Rejected, Declined. Use ids exactly as listed. The applicant must approve each action; never claim it is done."""


def tracker_summary(data: dict[str, Any], limit: int = 14000) -> str:
    lines = []
    for u in data["universities"]:
        for p in u["programs"]:
            dl = "; ".join(f"{k}: {v}" for k, v in (p.get("deadlines") or {}).items())[:80]
            risk = (p.get("auto_gpa_filter_risk") or "")[:90]
            tu = p.get("tuition_eur_per_year")
            lines.append(f"[{p['id']}] {u['name']} ({u['country']}) - {p['name']} | stage={p['stage']} apply={p['apply']} "
                         f"score={p.get('fit_score')} tuition={tu if tu is not None else '?'} | deadline: {dl or '?'} | risk: {risk or '?'}")
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit] + "\n...(truncated)"


def chat_messages(profile: dict[str, str], docs: str, data: dict[str, Any], history: list[dict[str, str]]) -> list[dict[str, str]]:
    system = f"""You are the assistant inside a graduate-application tracker. Be concise, practical and honest about risks.
Answer from the applicant's data below; when something is not in the data, say so rather than guessing.

APPLICANT PROFILE
{profile_text(profile)}

DOCUMENTS (excerpt)
{docs[:3000] or '(none)'}

TRACKED PROGRAMS
{tracker_summary(data)}

{ACTION_HELP}"""
    return [{"role": "system", "content": system}] + history[-16:]


def split_actions(reply: str) -> tuple[str, list[dict[str, Any]]]:
    m = re.search(r"```actions\s*(.*?)```", reply, re.S | re.I)
    if not m:
        return reply.strip(), []
    text = (reply[:m.start()] + reply[m.end():]).strip()
    try:
        raw = json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return text, []
    return text, raw if isinstance(raw, list) else []


def validate_actions(data: dict[str, Any], raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Whitelist + resolve to human-readable labels. Anything unknown is dropped."""
    out = []
    for a in raw[:12]:
        if not isinstance(a, dict):
            continue
        t = a.get("type")
        if t == "update_profile":
            key = re.sub(r"[^a-z0-9_]+", "_", str(a.get("key", "")).lower()).strip("_")
            if key and models.s(a.get("value")):
                out.append({"type": t, "key": key, "value": models.s(a["value"]),
                            "label": f"Set profile field '{key}' to: {models.s(a['value'])[:80]}"})
            continue
        uni, p = models.find_program(data, str(a.get("program_id", "")))
        if not p:
            continue
        who = f"{uni['name']} / {p['name']}"
        if t == "set_stage" and a.get("value") in models.STAGES:
            out.append({"type": t, "program_id": p["id"], "value": a["value"], "label": f"{who}: move to {a['value']}"})
        elif t == "set_apply":
            v = models.boolish(a.get("value"))
            out.append({"type": t, "program_id": p["id"], "value": v, "label": f"{who}: {'mark' if v else 'unmark'} as applying"})
        elif t == "add_note" and models.s(a.get("value")):
            out.append({"type": t, "program_id": p["id"], "value": models.s(a["value"]), "label": f"{who}: add note '{models.s(a['value'])[:80]}'"})
        elif t == "set_score" and models.to_score(a.get("value")) is not None:
            out.append({"type": t, "program_id": p["id"], "value": models.to_score(a["value"]), "label": f"{who}: set score to {models.to_score(a['value'])}"})
    return out
