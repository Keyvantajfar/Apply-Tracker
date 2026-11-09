# Changelog

Format: [Keep a Changelog](https://keepachangelog.com), versions follow [SemVer](https://semver.org).

## [1.1.1] - 2026-11-09
### Fixed
- Windows: the app stayed in Task Manager after its window was closed (Edge can keep its own process alive, so waiting for it never ended). The window now tells the app when it closes, the app ends the browser process it started, and always exits the process itself.

## [1.1.0] - 2026-11-09
### Added
- App-style window: the downloaded app (and `gradapp gui`) opens in its own window with no tabs or address bar, instead of a console plus a browser tab. Uses pywebview if installed (`pip install "gradapp[native]"`), otherwise a Chromium-based browser (Edge, Chrome, Chromium, Brave) in app mode, otherwise your default browser. Closing the window stops the server.
- Official/professor links opened from the app window go to your normal browser.
- Windows: no console window. macOS: `GradApp.app` bundle (zipped). Linux: single file.
- App icon.
### Changed
- Source split into `gradapp.core` (backend library, no Flask), `gradapp.web` (Flask routes, templates, static files) and `gradapp.desktop` (window launcher).
- Downloaded binaries keep data in the per-user app folder (`%APPDATA%\GradApp`, `~/Library/Application Support/GradApp`, `~/.local/share/gradapp`). A `./data` folder from an earlier version is still used if present; `GRADAPP_DATA` overrides both.
- Linux binary is about 35% smaller (symbols stripped, unused modules left out).
- Release workflow smoke-tests every built app by starting its server.
### Fixed
- Error messages no longer mention `app.py`.

## [1.0.1] - 2026-11-08
First public release.
### Added
- Multi-user accounts with per-user tracker, profile, documents and chat history (plain JSON/CSV files).
- AI profile builder from uploaded resumes (PDF, DOCX, TXT, MD), assistant chat with approve-to-apply actions.
- Scores with a source (you / AI / estimate), lock, and rationale; AI re-scoring touches only score fields.
- "Find programs": research prompts for any external AI (Any, Erasmus Mundus, DAAD), convert-a-list prompt, previewed JSON import.
- Labels and partner universities on programs.
- `gradapp` command: `serve`, `add-user`, `set-password`, `check`, `repair`, `registration`, `import-legacy`.
- Docker image, single-file binaries, Python wheel.
### Fixed
- Scores showing 0% when a CSV row was malformed: JSON is the source of truth, text is never turned into a score.
