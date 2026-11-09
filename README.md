# GradApp

<img width="1354" height="896" alt="image" src="https://github.com/user-attachments/assets/5626b64b-8ced-49c5-9cae-48f389ec7a86" />


A multi-user tracker for graduate applications. Plain files only (JSON and CSV), no database, works offline.
Track programs, professors and deadlines, build a profile from your resume with AI, score fit, and import
research done by any AI through a ready-made prompt.

## Install and run

Pick one:

```bash
# 1. App: download from the Releases page and open it. It shows GradApp in its own window.
#    Windows: gradapp-windows-<arch>.exe     macOS: unzip gradapp-macos-<arch>.app.zip, open GradApp.app
#    Linux:   chmod +x gradapp-linux-<arch> && ./gradapp-linux-<arch>

# 2. Python 3.10+
pip install gradapp-1.1.0-py3-none-any.whl     # from the Releases page, or: pip install .
gradapp

# 3. Docker
docker run -p 127.0.0.1:5000:5000 -v gradapp-data:/data ghcr.io/OWNER/gradapp:latest
```

Click **Create account** (first account, nothing is pre-created). With pip or Docker, open http://127.0.0.1:5000 yourself,
or run `gradapp gui` to get the app window.

Data location: the downloaded app uses your user folder (`%APPDATA%\GradApp`, `~/Library/Application Support/GradApp`,
`~/.local/share/gradapp`); pip uses `./data` in the folder you start it from; Docker uses `/data`. An existing `./data`
folder is still picked up by the app. Override everything with `GRADAPP_DATA`.

**About the window.** It is your Chromium-based browser (Edge on Windows, otherwise Chrome, Chromium or Brave) opened in
app mode with its own profile, so there are no tabs or address bar. If none is installed, GradApp falls back to a normal
browser tab and quits by itself after you close it. For a true native window: `pip install "gradapp[native]"`
(WebView2 on Windows, WebKit on macOS, GTK/Qt WebKit on Linux). `gradapp gui --mode app|webview|browser` forces one.

**macOS:** the app is not signed, so Gatekeeper may refuse the first launch. Right-click, Open, or run
`xattr -dr com.apple.quarantine GradApp.app`.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `GRADAPP_HOST` / `GRADAPP_PORT` | `127.0.0.1` / `5000` | Bind address. Use `0.0.0.0` only on a network you trust. |
| `GRADAPP_DATA` | `./data` | Data folder. |
| `GRADAPP_SECRET_KEY` | generated in `data/secret.key` | Session signing key. |
| `GRADAPP_HTTPS` | off | Set `1` behind HTTPS so cookies are marked Secure. |

**Single process only.** Storage uses an in-process lock, so run one instance (it serves several threads).
It is built for personal or small-group use, not for a public multi-tenant site.

## Commands

```
gradapp gui [--port P] [--mode auto|webview|app|browser]   # app window (default for the binaries)
gradapp serve [--host H] [--port P] [--dev]
gradapp add-user NAME            # password from prompt or GRADAPP_PASSWORD
gradapp set-password NAME
gradapp check [NAME]             # validate data files
gradapp repair NAME              # merge duplicates, estimate unscored programs (backup made)
gradapp registration on|off      # allow self-registration on the login page
gradapp import-legacy FOLDER --user NAME
gradapp version
```

`import-legacy` imports an older single-user folder (`universities.json`, optional `programs.csv`,
`professors.csv`, `app_memory.json`) and writes a `migration_report.txt` in the account folder.

## What you get

| Page | What it does |
|---|---|
| Programs | One clean list grouped by fit. Click a row to open the official page. Press `/` to search, `n` to add. |
| Pipeline | Drag cards between Wishlist, Preparing, Applied, Interview, Accepted, Rejected, Declined. |
| Professors | Outreach status, copy email, open page, edit everything. |
| My profile | Editable fields plus resume/transcript upload. "Build profile with AI" proposes fields you accept or reject. |
| Assistant | Chat that knows your profile and programs; proposed changes need your approval. |
| Find programs | Builds a research prompt for **any** AI with web access (Any, Erasmus Mundus, DAAD), then imports its JSON answer with a preview. A second prompt converts a list an AI already gave you. |

**Scores** have a source and are never invented from text: *You* (locked), *AI* (writes only the score and its
explanation), *Estimate* (transparent rule-based guess, dashed ring).

**AI server:** Settings takes a URL, model and optional key for any OpenAI-compatible server (OpenAI,
OpenRouter, Ollama, LM Studio, vLLM). The key stays on the server and is never sent back to the browser.

## Your data

```
data/users/<name>/
  tracker.json      source of truth
  programs.csv, professors.csv   exports, rewritten on every save
  profile.json, settings.json, resume.txt, docs/, chat.json
  backups/          last 15 versions of tracker.json
data/logs/app.log
```

Corrupt files are quarantined as `*.corrupt-<time>` and the app keeps running. Settings has an
"Everything (zip)" export.

## Code layout

```
src/gradapp/
  core/      backend library: storage, accounts, models, scoring, AI client, importer (no Flask; reusable)
  web/       Flask routes + browser UI (templates/, static/)
  desktop/   app-window launcher (gradapp gui)
  cli.py     the gradapp command
```

## Development

```bash
pip install -e ".[dev]"
python -m unittest discover -s tests -v
python packaging/build_binary.py     # app for this OS -> dist/ (.exe, .app.zip or Linux binary)
python -m build                      # wheel + sdist -> dist/
```

### Releasing

1. Update `src/gradapp/__init__.py` (`__version__`) and `CHANGELOG.md`.
2. `git tag v<version> && git push --tags`.
3. The `Release` workflow tests, builds the wheel, binaries (Linux, Windows, macOS) and the Docker image
   (`ghcr.io/<owner>/gradapp`), and attaches everything plus `SHA256SUMS.txt` to a GitHub Release.

Replace `OWNER` in this README, `Dockerfile` and `docker-compose.yml` with your GitHub user or organisation.

## License

No license has been chosen yet. Until you add a `LICENSE` file, all rights are reserved. See `THIRD_PARTY_NOTICES.md`.
