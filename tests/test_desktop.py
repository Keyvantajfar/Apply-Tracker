"""Desktop launcher: window lifecycle with a fake browser, data folder rules, external-link endpoint."""
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
_TMP = tempfile.mkdtemp(prefix="gradapp-test-desktop-")
os.environ["GRADAPP_DATA"] = _TMP

from gradapp.core import paths  # noqa: E402
from gradapp.desktop import launcher  # noqa: E402

H = {"X-GradApp": "1"}


class DataDir(unittest.TestCase):
    def test_env_wins_and_nothing_changes(self):
        with mock.patch.dict(os.environ, {"GRADAPP_DATA": "/somewhere"}):
            self.assertIsNone(paths.apply_default_data_dir())
            self.assertEqual(os.environ["GRADAPP_DATA"], "/somewhere")

    def test_old_data_folder_keeps_being_used(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ):
            os.environ.pop("GRADAPP_DATA")
            (Path(d) / "data" / "users").mkdir(parents=True)
            old = os.getcwd(); os.chdir(d)
            try:
                self.assertIsNone(paths.apply_default_data_dir())
                self.assertNotIn("GRADAPP_DATA", os.environ)
            finally:
                os.chdir(old)

    def test_fresh_start_uses_the_user_app_folder(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ):
            os.environ.pop("GRADAPP_DATA")
            old = os.getcwd(); os.chdir(d)
            try:
                got = paths.apply_default_data_dir()
                self.assertEqual(got, paths.platform_data_dir())
                self.assertEqual(os.environ["GRADAPP_DATA"], str(got))
            finally:
                os.chdir(old)


class Browser(unittest.TestCase):
    def test_override_and_command(self):
        with mock.patch.dict(os.environ, {"GRADAPP_BROWSER": sys.executable}):
            self.assertEqual(launcher.find_chromium(), sys.executable)
        cmd = launcher._chromium_cmd("/x/chrome", "http://127.0.0.1:5000/", Path("/p"))
        self.assertIn("--app=http://127.0.0.1:5000/", cmd)
        self.assertIn("--user-data-dir=/p", cmd)


@unittest.skipIf(sys.platform == "win32", "uses a shell script as the fake browser")
class Lifecycle(unittest.TestCase):
    def _fake_browser(self, body: str) -> str:
        p = Path(tempfile.mkdtemp()) / "fakebrowser"
        p.write_text("#!/bin/sh\n" + textwrap.dedent(body))
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        return str(p)

    def test_window_closing_stops_the_server_and_page_has_desktop_flag(self):
        out = Path(tempfile.mkdtemp()) / "page.html"
        # a "browser" that fetches the login page, stays open 5 s (so it counts as a window), then closes
        fake = self._fake_browser(f'''
            url="${{1#--app=}}"
            {sys.executable} -c "import sys,urllib.request;open(sys.argv[1],'w').write(urllib.request.urlopen(sys.argv[2]+'login').read().decode())" "{out}" "$url"
            sleep 5
        ''')
        with mock.patch.dict(os.environ, {"GRADAPP_BROWSER": fake}):
            port = launcher._free_port("127.0.0.1")
            self.assertEqual(launcher.run(port=port, mode="app"), 0)
        html = out.read_text()
        self.assertIn("window.__DESKTOP__", html)
        self.assertIn("desktop.js", html)
        self.assertFalse(launcher.is_gradapp("127.0.0.1", port))      # server was stopped with the window

    def test_unusable_browser_falls_back_to_a_tab_that_quits_when_idle(self):
        fake = self._fake_browser("exit 1\n")
        with mock.patch.dict(os.environ, {"GRADAPP_BROWSER": fake}), \
                mock.patch.object(launcher, "IDLE_LIMIT", 1.0), mock.patch.object(launcher.webbrowser, "open") as op:
            port = launcher._free_port("127.0.0.1")
            self.assertEqual(launcher.run(port=port, mode="auto"), 0)
        op.assert_called_once()

    def test_existing_server_is_reused_and_left_running(self):
        from waitress import create_server
        from gradapp.web.app import app
        port = launcher._free_port("127.0.0.1")
        srv = create_server(app, host="127.0.0.1", port=port)
        import threading
        threading.Thread(target=srv.run, daemon=True).start()
        try:
            fake = self._fake_browser("sleep 5\n")
            with mock.patch.dict(os.environ, {"GRADAPP_BROWSER": fake}):
                self.assertEqual(launcher.run(port=port, mode="app"), 0)
            self.assertTrue(launcher.is_gradapp("127.0.0.1", port))
        finally:
            srv.close()


class ExternalLinks(unittest.TestCase):
    def setUp(self):
        from gradapp.web.app import app
        from gradapp.core.users import create_user
        self.app = app
        try:
            create_user("desk", "secret1")
        except Exception:
            pass
        self.c = app.test_client()
        self.c.post("/api/login", json={"username": "desk", "password": "secret1"}, headers=H)

    def tearDown(self):
        self.app.config["DESKTOP"] = None

    def test_disabled_outside_the_desktop_window(self):
        self.assertEqual(self.c.post("/api/open-external", json={"url": "https://example.org"}, headers=H).status_code, 404)

    def test_only_http_links_open(self):
        self.app.config["DESKTOP"] = {"heartbeat": False}
        with mock.patch("gradapp.web.app.webbrowser.open") as op:
            self.assertEqual(self.c.post("/api/open-external", json={"url": "file:///etc/passwd"}, headers=H).status_code, 400)
            op.assert_not_called()
            self.assertEqual(self.c.post("/api/open-external", json={"url": "https://example.org/x"}, headers=H).status_code, 200)
            op.assert_called_once_with("https://example.org/x")
            self.assertEqual(self.c.post("/api/open-external", json={"url": "https://example.org"}).status_code, 403)  # no CSRF header


if __name__ == "__main__":
    unittest.main()
