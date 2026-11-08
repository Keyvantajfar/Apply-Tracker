# Changelog

Format: [Keep a Changelog](https://keepachangelog.com), versions follow [SemVer](https://semver.org).

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
