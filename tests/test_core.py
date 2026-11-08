"""Run:  python -m unittest discover -s tests -v     (from the repo root, after pip install -e .)"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "fixtures" / "legacy_sample"
_TMP = tempfile.mkdtemp(prefix="gradapp-test-")
os.environ["GRADAPP_DATA"] = _TMP          # must be set before importing the app

from gradapp.core import ai, importer, models, scoring  # noqa: E402
from gradapp.core.migrate import build_tracker_from_legacy  # noqa: E402
from gradapp.core.storage import csv_text, read_csv_strict, write_csv  # noqa: E402

H = {"X-GradApp": "1"}


class Scores(unittest.TestCase):
    def test_text_is_never_zero(self):
        # the original bug: CSV "unknown" / "n/a" became 0
        for bad in ("unknown", "n/a - eligibility issue first", "", None, " software engineering; letters"):
            self.assertIsNone(models.to_score(bad), bad)
        self.assertEqual(models.to_score("85"), 85.0)
        self.assertEqual(models.to_score("85%"), 85.0)
        self.assertEqual(models.to_score(150), 100.0)
        self.assertEqual(models.to_score(0), 0.0)     # a real zero is allowed

    def test_locked_score_is_not_overwritten(self):
        p = models.normalize_program({"name": "X"}, "u")
        scoring.set_manual_score(p, 90)
        self.assertFalse(scoring.set_ai_score(p, {"score": 10}))
        self.assertEqual(p["fit_score"], 90)
        self.assertTrue(scoring.set_ai_score(p, {"score": 10}, force=True))
        self.assertEqual(p["score_meta"]["source"], "ai")

    def test_ai_score_touches_only_score_fields(self):
        p = models.normalize_program({"name": "X", "notes": "mine", "stage": "Applied"}, "u")
        before = {k: v for k, v in p.items() if k not in ("fit_score", "score_meta")}
        scoring.set_ai_score(p, {"score": 70, "rationale": "ok"})
        after = {k: v for k, v in p.items() if k not in ("fit_score", "score_meta")}
        self.assertEqual(before, after)

    def test_rule_score_fills_only_unscored(self):
        p = models.normalize_program({"name": "X", "fit_score": 40}, "u")
        self.assertFalse(scoring.apply_rule_score(p))
        q = models.normalize_program({"name": "Y", "tuition_eur_per_year": 0}, "u")
        self.assertTrue(scoring.apply_rule_score(q))
        self.assertEqual(q["score_meta"]["source"], "rule")


class Migration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.profile, cls.extra, cls.report = build_tracker_from_legacy(SAMPLE)

    def prog(self, uni_part, name_part):
        for u in self.data["universities"]:
            for p in u["programs"]:
                if uni_part in u["name"] and name_part in p["name"]:
                    return p
        self.fail(f"{uni_part}/{name_part} missing")

    def test_flagged_programs_keep_their_scores(self):
        self.assertEqual(self.prog("Example University", "Data Science")["fit_score"], 92)
        self.assertEqual(self.prog("Example University", "Industrial")["fit_score"], 85)
        self.assertIsNotNone(self.prog("Sample Institute", "Postgraduate")["fit_score"])

    def test_nothing_is_lost(self):
        names = {models.norm_key(p["name"]) for u in self.data["universities"] for p in u["programs"]}
        raw = json.loads((SAMPLE / "universities.json").read_text(encoding="utf-8"))
        for u in raw["universities"]:
            for p in u["programs"]:
                self.assertIn(models.norm_key(p["name"]), names)
        self.assertEqual(len(self.data["universities"]), 3)
        self.assertEqual(sum(len(u["programs"]) for u in self.data["universities"]), 4)
        self.assertEqual(sum(len(u["professors"]) for u in self.data["universities"]), 2)

    def test_ids_are_unique_and_links_valid(self):
        ids = [p["id"] for u in self.data["universities"] for p in u["programs"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(models.health_check(self.data) and [i for i in models.health_check(self.data) if i["level"] == "error"], [])
        d = next(u for u in self.data["universities"] if "Example University" in u["name"])
        linked = [q for q in d["professors"] if q["program_id"]]
        self.assertTrue(linked)
        self.assertTrue(all(q["program_id"] in {p["id"] for p in d["programs"]} for q in linked))

    def test_profile_and_settings_kept(self):
        self.assertEqual(self.profile["applicant"], "Alex Example")
        self.assertEqual(self.profile["gpa_overall"], "3.4")
        self.assertEqual(self.extra["settings"]["ai_model"], "sample-model")

    def test_status_text_became_verification_not_stage(self):
        p = self.prog("Example University", "Data Science")
        self.assertEqual(p["stage"], "Wishlist")
        self.assertIn("verified", p["verification"])


class CsvSafety(unittest.TestCase):
    def test_roundtrip_with_commas_quotes_newlines(self):
        rows = [{"id": "a", "notes": 'He said "hi", then left,\nnew line', "sources": ["http://a,b", "http://c"]}]
        p = Path(_TMP) / "t.csv"
        write_csv(p, rows, ["id", "notes", "sources"])
        back, problems = read_csv_strict(p)
        self.assertEqual(problems, [])
        self.assertEqual(back[0]["notes"], rows[0]["notes"])
        self.assertEqual(json.loads(back[0]["sources"]), rows[0]["sources"])

    def test_malformed_rows_are_reported_not_misread(self):
        p = Path(_TMP) / "bad.csv"
        p.write_text("a,b,c\n1,2,3\n1,2,3,4\n", encoding="utf-8")
        rows, problems = read_csv_strict(p)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(problems), 1)

    def test_legacy_csv_is_detected_as_broken(self):
        _rows, problems = read_csv_strict(SAMPLE / "programs.csv")
        self.assertEqual(len(problems), 3)


class Importer(unittest.TestCase):
    base = staticmethod(lambda: models.normalize_tracker({"universities": [{"name": "TU Example", "country": "Germany", "programs": [
        {"name": "M.Sc. Data Science", "stage": "Applied", "apply": True, "notes": "mine", "fit_score": 70, "language": ""}]}]}))
    answer = {"universities": [{"name": "TU Example", "country": "Germany", "programs": [
        {"name": "MSc Data Science", "language": "English", "notes": "AI says hi", "stage": "Wishlist", "fit_score": 5, "tuition_eur_per_year": "0"},
        {"name": "M.Sc. Statistics", "tuition_eur_per_year": 0, "official_link": "example.org/stat"}],
        "professors": [{"name": "Prof. A", "program": "m.sc. statistics", "email": "a@x.org"}]}]}

    def test_parse_variants(self):
        txt = "Sure! Here you go:\n```json\n" + json.dumps(self.answer) + "\n```\nLet me know."
        for payload in (txt, self.answer, self.answer["universities"], json.dumps(self.answer)):
            unis, _w = importer.parse_import(payload)
            self.assertEqual(unis[0]["name"], "TU Example")
        flat = {"programs": [{"university": "A Uni", "country": "Spain", "name": "MSc X"}, {"university": "A Uni", "name": "MSc Y"}]}
        unis, _ = importer.parse_import(flat)
        self.assertEqual(len(unis), 1)
        self.assertEqual(len(unis[0]["programs"]), 2)
        for bad in ("", "not json at all", '{"foo": 1}', '{"universities": []}'):
            with self.assertRaises(ValueError):
                importer.parse_import(bad)

    def test_fill_keeps_user_fields_and_matches_fuzzy_names(self):
        data = self.base()
        incoming, _ = importer.parse_import(self.answer)
        new, summary = importer.plan_import(data, incoming, "fill")
        progs = {p["name"]: p for p in new["universities"][0]["programs"]}
        self.assertEqual(len(progs), 2)                       # "MSc Data Science" matched the existing one
        ds = progs["M.Sc. Data Science"]
        self.assertEqual((ds["stage"], ds["apply"], ds["notes"], ds["fit_score"]), ("Applied", True, "mine", 70))
        self.assertEqual(ds["language"], "English")           # blank filled
        self.assertEqual(progs["M.Sc. Statistics"]["official_link"], "https://example.org/stat")
        self.assertIsNotNone(progs["M.Sc. Statistics"]["fit_score"])   # estimate added
        self.assertEqual(summary["counts"]["new_professors"], 1)
        prof = new["universities"][0]["professors"][0]
        self.assertEqual(prof["program_id"], progs["M.Sc. Statistics"]["id"])
        self.assertEqual(len(data["universities"][0]["programs"]), 1)  # input not mutated

    def test_add_mode_never_changes_existing(self):
        data = self.base()
        incoming, _ = importer.parse_import(self.answer)
        new, summary = importer.plan_import(data, incoming, "add")
        self.assertEqual(new["universities"][0]["programs"][0]["language"], "")
        self.assertEqual(summary["counts"]["new_programs"], 1)

    def test_overwrite_changes_facts_but_not_user_fields(self):
        data = self.base()
        incoming, _ = importer.parse_import(self.answer)
        new, _ = importer.plan_import(data, incoming, "overwrite")
        ds = new["universities"][0]["programs"][0]
        self.assertEqual(ds["language"], "English")
        self.assertEqual((ds["stage"], ds["notes"], ds["fit_score"]), ("Applied", "mine", 70))

    def test_prompt(self):
        txt = importer.build_research_prompt({"countries": "Germany, Spain", "fields": "statistics", "include_profile": True},
                                              {"degree": "B.Sc. Statistics"}, ["TU Example - M.Sc. Data Science"])
        for needle in ("Germany, Spain", '"universities"', "official_link", "NEVER guess", "TU Example - M.Sc. Data Science", "B.Sc. Statistics"):
            self.assertIn(needle, txt)
        with self.assertRaises(ValueError):
            importer.build_research_prompt({"countries": ""}, {}, [])


class AIHelpers(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(ai.extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(ai.extract_json('Result: {"a": {"b": "}"}} thanks'), {"a": {"b": "}"}})
        with self.assertRaises(ai.AIError):
            ai.extract_json("no json here")

    def test_actions_are_whitelisted(self):
        data = models.normalize_tracker({"universities": [{"name": "U", "programs": [{"name": "P"}]}]})
        pid = data["universities"][0]["programs"][0]["id"]
        raw = [{"type": "set_stage", "program_id": pid, "value": "Applied"}, {"type": "set_stage", "program_id": pid, "value": "Hacked"},
               {"type": "delete_everything", "program_id": pid}, {"type": "set_score", "program_id": "nope", "value": 5},
               {"type": "update_profile", "key": "Goals!", "value": "x"}]
        ok = ai.validate_actions(data, raw)
        self.assertEqual([a["type"] for a in ok], ["set_stage", "update_profile"])
        self.assertEqual(ok[1]["key"], "goals")

    def test_split_actions(self):
        text, acts = ai.split_actions('Do this.\n```actions\n[{"type":"set_apply"}]\n```')
        self.assertEqual(text, "Do this.")
        self.assertEqual(len(acts), 1)


class Deadlines(unittest.TestCase):
    def test_parse(self):
        from datetime import date
        t = date(2026, 10, 13)
        self.assertEqual(models.parse_deadline_dates("15 Jun (non-EU)", t), [date(2027, 6, 15)])
        self.assertEqual(models.parse_deadline_dates("2027-01-15", t), [date(2027, 1, 15)])
        self.assertEqual(models.parse_deadline_dates("window 16 Oct - 15 Jan (2025/26: 16 Oct 2025)", t),
                         [date(2025, 10, 16), date(2026, 10, 16), date(2027, 1, 15)])


class V2Labels(unittest.TestCase):
    def test_tags_normalise(self):
        self.assertEqual(models.to_tags("Erasmus Mundus, DAAD; erasmus mundus"), ["Erasmus Mundus", "DAAD"])
        self.assertEqual(models.to_tags(None), [])
        self.assertEqual(len(models.to_tags([str(i) for i in range(20)])), 8)

    def test_old_data_without_tags_loads(self):
        old = {"universities": [{"id": "x", "name": "U", "programs": [{"id": "p_a", "name": "A", "status": "verified", "fit_score": 50}]}]}
        n = models.normalize_tracker(old)
        p = n["universities"][0]["programs"][0]
        self.assertEqual((p["tags"], p["partners"], p["fit_score"]), ([], "", 50))

    def test_general_prompt_unchanged_and_focus_prompts(self):
        opts = {"countries": "Germany", "fields": "statistics"}
        g = importer.build_research_prompt(opts, {}, [])
        self.assertEqual(g, importer.build_research_prompt({**opts, "focus": "general"}, {}, []))
        self.assertNotIn("Erasmus Mundus rules", g)
        e = importer.build_research_prompt({"focus": "erasmus", "fields": "statistics"}, {}, [])
        for needle in ("Erasmus Mundus rules", '"partners"', "EMOS", '"tags"', "self_funded", "any European country"):
            self.assertIn(needle, e)
        d = importer.build_research_prompt({"focus": "daad"}, {}, [])
        for needle in ("DAAD rules", "daad_scholarship", "in: Germany"):
            self.assertIn(needle, d)
        with self.assertRaises(ValueError):
            importer.build_research_prompt({"focus": "nope", "countries": "X"}, {}, [])
        c = importer.build_convert_prompt("erasmus")
        self.assertIn("DROP rankings", c)
        self.assertIn("Erasmus Mundus", c)

    def test_user_style_list_is_converted_and_guesses_dropped(self):
        listing = [{"rank": 1, "acronym": "X", "name": "EM Joint Master X", "suitability_score": 97, "full_scholarship_chance_pct": "30%",
                    "tuition_eur_per_year": 0, "partners": "A (ES); B (DE)", "official_link": "https://x.eu"}]
        unis, _ = importer.parse_import({"universities": [{"name": "Coordinator U", "country": "Spain", "programs": listing}]}, "Erasmus Mundus")
        data, summary = importer.plan_import(models.normalize_tracker({"universities": []}), unis, "fill")
        p = data["universities"][0]["programs"][0]
        self.assertEqual(p["tags"], ["Erasmus Mundus"])
        self.assertEqual(p["partners"], "A (ES); B (DE)")
        self.assertEqual(p["score_meta"]["source"], "rule")        # estimate, never the AI's guess of 97

    def test_import_adds_tag_to_existing_without_touching_user_fields(self):
        base = models.normalize_tracker({"universities": [{"name": "U", "programs": [{"name": "P", "stage": "Applied", "notes": "mine", "fit_score": 70}]}]})
        unis, _ = importer.parse_import({"universities": [{"name": "U", "programs": [{"name": "P"}]}]}, "DAAD")
        new, _ = importer.plan_import(base, unis, "fill")
        p = new["universities"][0]["programs"][0]
        self.assertEqual((p["tags"], p["stage"], p["notes"], p["fit_score"]), (["DAAD"], "Applied", "mine", 70))
        again, _ = importer.plan_import(new, importer.parse_import({"universities": [{"name": "U", "programs": [{"name": "P"}]}]}, "DAAD")[0], "fill")
        self.assertEqual(again["universities"][0]["programs"][0]["tags"], ["DAAD"])   # no duplicate label

    def test_csv_has_tags_and_partners(self):
        self.assertIn("tags", models.PROGRAM_CSV_HEADERS)
        self.assertIn("partners", models.PROGRAM_CSV_HEADERS)


class WebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from gradapp import app as A
        from gradapp.core.migrate import import_legacy
        from gradapp.core.users import Workspace, create_user
        create_user("tester", "pass1234")
        import_legacy(Workspace("tester"), SAMPLE)
        cls.A = A
        cls.c = A.app.test_client()

    def login(self, c=None, u="tester", p="pass1234"):
        c = c or self.c
        return c.post("/api/login", json={"username": u, "password": p}, headers=H)

    def test_01_auth(self):
        self.assertEqual(self.c.get("/").status_code, 302)
        self.assertEqual(self.c.get("/api/state").status_code, 401)
        self.assertEqual(self.login(p="wrong").status_code, 401)
        self.assertEqual(self.c.post("/api/login", json={"username": "tester", "password": "pass1234"}).status_code, 403)  # CSRF header
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_02_state_has_migrated_data(self):
        self.login()
        st = self.c.get("/api/state").json
        progs = [p for u in st["tracker"]["universities"] for p in u["programs"]]
        self.assertEqual(len(progs), 4)
        scores = {p["id"]: p["fit_score"] for p in progs}
        self.assertEqual(scores["example-tu--m-sc-data-science"], 92)
        self.assertTrue(all(s is not None for s in scores.values()))
        self.assertEqual(st["profile"]["applicant"], "Alex Example")

    def test_03_edit_persist_and_csv_export_stay_valid(self):
        self.login()
        pid = "example-tu--m-sc-data-science"
        r = self.c.post("/api/program/update", json={"id": pid, "patch": {"notes": 'a, "quoted"\nline', "stage": "Preparing"}}, headers=H).json
        self.assertTrue(r["program"]["apply"])                # moving past Wishlist marks it as applying
        ws = self.A.Workspace("tester")
        again = ws.load_tracker()
        p = models.find_program(again, pid)[1]
        self.assertEqual(p["notes"], 'a, "quoted"\nline')
        rows, problems = read_csv_strict(ws.programs_csv)
        self.assertEqual(problems, [])
        self.assertEqual(len(rows), 4)
        row = next(r for r in rows if r["id"] == pid)
        self.assertEqual(row["fit_score"], "92.0")
        self.assertEqual(row["notes"], 'a, "quoted"\nline')

    def test_04_score_actions(self):
        self.login()
        pid = "example-tu--m-sc-industrial-mathematics"
        r = self.c.post("/api/program/score", json={"id": pid, "action": "manual", "value": 61}, headers=H).json
        self.assertEqual((r["program"]["fit_score"], r["program"]["score_meta"]["locked"]), (61, True))
        r = self.c.post("/api/program/score", json={"id": pid, "action": "rule"}, headers=H)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.c.post("/api/program/score", json={"id": pid, "action": "manual", "value": "abc"}, headers=H).status_code, 400)
        r = self.c.post("/api/program/score", json={"id": pid, "action": "clear"}, headers=H).json
        self.assertIsNone(r["program"]["fit_score"])

    def test_05_ai_failure_is_reported_cleanly(self):
        self.login()
        self.c.put("/api/settings", json={"ai_base_url": "http://127.0.0.1:9/v1", "ai_model": "x", "ai_timeout": 3}, headers=H)
        r = self.c.post("/api/program/score", json={"id": "example-tu--m-sc-data-science", "action": "ai", "force": True}, headers=H)
        self.assertEqual(r.status_code, 502)
        self.assertIn("Could not reach the AI server", r.json["error"])
        self.assertNotIn("ai_api_key", self.c.get("/api/settings").json["settings"])

    def test_06_create_delete_restore(self):
        self.login()
        r = self.c.post("/api/program/create", json={"university": {"name": "New Uni", "country": "Spain"}, "program": {"name": "MSc Test", "tuition_eur_per_year": "1200"}}, headers=H).json
        pid = r["program"]["id"]
        self.assertEqual(r["program"]["tuition_eur_per_year"], 1200)
        rem = self.c.post("/api/program/delete", json={"id": pid}, headers=H).json
        back = self.c.post("/api/program/create", json={"university_id": rem["university_id"], "program": rem["removed"]}, headers=H).json
        self.assertEqual(back["program"]["id"], pid)

    def test_07_import_roundtrip_and_backup(self):
        self.login()
        payload = {"universities": [{"name": "Imported Uni", "country": "Italy", "programs": [{"name": "MSc Imp", "official_link": "https://x.org"}]}]}
        pre = self.c.post("/api/import/preview", json={"text": json.dumps(payload)}, headers=H).json
        self.assertEqual(pre["counts"]["new_programs"], 1)
        self.assertEqual(self.c.post("/api/import/preview", json={"text": "garbage"}, headers=H).status_code, 400)
        done = self.c.post("/api/import/commit", json={"text": json.dumps(payload)}, headers=H).json
        self.assertTrue(done["ok"])
        self.assertTrue(any(p["name"] == "MSc Imp" for u in done["tracker"]["universities"] for p in u["programs"]))
        self.assertTrue(list((self.A.Workspace("tester").dir / "backups").glob("tracker.*.json")))

    def test_08_registration_isolation(self):
        c2 = self.A.app.test_client()
        r = c2.post("/api/register", json={"username": "ada", "password": "secret1", "display_name": "Ada"}, headers=H)
        self.assertEqual(r.status_code, 200)
        st = c2.get("/api/state").json
        self.assertEqual(st["tracker"]["universities"], [])
        self.assertEqual(c2.post("/api/register", json={"username": "ada", "password": "secret1"}, headers=H).status_code, 400)
        self.assertEqual(c2.post("/api/register", json={"username": "x", "password": "secret1"}, headers=H).status_code, 400)
        # ada cannot touch tester's program ids
        r = c2.post("/api/program/update", json={"id": "example-tu--m-sc-data-science", "patch": {"notes": "hack"}}, headers=H)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.c.get("/api/state").json["user"]["username"], "tester")

    def test_09_corrupt_json_does_not_crash(self):
        self.login()
        ws = self.A.Workspace("tester")
        good = ws.tracker_path.read_text(encoding="utf-8")
        ws.tracker_path.write_text("{ broken", encoding="utf-8")
        try:
            r = self.c.get("/api/state")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(list(ws.dir.glob("tracker.json.corrupt-*")))
        finally:
            ws.tracker_path.write_text(good, encoding="utf-8")

    def test_11_labels_api(self):
        self.login()
        pid = "example-tu--m-sc-data-science"
        r = self.c.post("/api/program/update", json={"id": pid, "patch": {"tags": ["DAAD", "Erasmus Mundus"], "partners": "A; B"}}, headers=H).json
        self.assertEqual(r["program"]["tags"], ["DAAD", "Erasmus Mundus"])
        self.assertEqual(r["program"]["partners"], "A; B")
        p = self.c.post("/api/import/prompt", json={"focus": "erasmus", "fields": "statistics"}, headers=H).json
        self.assertEqual(p["tag"], "Erasmus Mundus")
        cv = self.c.post("/api/import/prompt", json={"focus": "daad", "convert": True}, headers=H).json
        self.assertEqual(cv["tag"], "DAAD")
        pay = {"universities": [{"name": "Coord U", "country": "Spain", "programs": [{"name": "EM X", "official_link": "https://x.eu"}]}]}
        done = self.c.post("/api/import/commit", json={"text": json.dumps(pay), "tag": "Erasmus Mundus"}, headers=H).json
        prog = [p for u in done["tracker"]["universities"] for p in u["programs"] if p["name"] == "EM X"][0]
        self.assertEqual(prog["tags"], ["Erasmus Mundus"])

    def test_10_documents_and_profile(self):
        self.login()
        import io
        r = self.c.post("/api/docs", data={"files": (io.BytesIO(b"Python, statistics, GNNs"), "resume.txt")}, headers=H, content_type="multipart/form-data").json
        self.assertEqual(r["docs"][0]["name"], "resume.txt")
        bad = self.c.post("/api/docs", data={"files": (io.BytesIO(b"x"), "evil.exe")}, headers=H, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.c.get("/api/docs/..%2f..%2faccount.json").status_code, 404)
        self.c.put("/api/profile", json={"profile": {"Goals!": "x", "applicant": "K"}}, headers=H)
        self.assertEqual(self.c.get("/api/profile").json["profile"], {"goals": "x", "applicant": "K"})


if __name__ == "__main__":
    unittest.main()
