# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project purpose

A desktop tool that scrapes Centre Com (centrecom.com.au, an Australian computer hardware
retailer) for a given category URL and sale-status filter (all / on sale / not on sale). It
finds products in stock at the **Adelaide retail store** and writes their CC product codes to
`output/sale_cc_numbers.txt` / `output/not_sale_cc_numbers.txt`, for price-ticketing purposes.
When the filter is "All items" it still scans everything but splits results into the sale vs.
not-sale files. The actual end-to-end workflow: run a scrape, then copy the codes (via the GUI's
Copy buttons) into a separate internal ticket-generation website — the GUI is not the last step.

## Tech stack

- Python 3.12, no packaging for the app itself (flat scripts, no pyproject.toml/setup.py) — the
  `packaging/` folder holds build-only tooling for the Windows installer, see "Packaging /
  distribution" below; it doesn't change how the app runs from source.
- GUI: `tkinter`/`ttk`, themed with **sv-ttk** (Sun Valley — native-looking Windows 11 Fluent
  style, light/dark). `sv_ttk.set_theme(...)` must be called before building widgets; named fonts
  like `"SunValleyBodyStrongFont"`/`"SunValleyTitleFont"`/`"SunValleyCaptionFont"` come from the
  theme, not tkinter itself.
- Scraping: **Playwright** sync API driving a real, non-headless browser window (`headless=False`)
  — requires a display, won't run headless/CI as-is. `gui.py`'s `run_scraper` launches it with
  `channel="msedge"` (Microsoft Edge, Chromium-based) rather than Playwright's own downloaded
  Chromium — Edge ships on every Windows 11 machine already, so the packaged .exe doesn't need to
  bundle or download a separate browser binary; see "Packaging / distribution" below. This means a
  dev machine needs Edge installed too (not just `playwright install chromium`), including on
  Linux/WSL — install it from Microsoft's own apt repo (`packages.microsoft.com/repos/edge`,
  package `microsoft-edge-stable`), not via `playwright install`, since `msedge` isn't one of
  Playwright's downloadable/managed browsers (see "Packaging / distribution" below); confirmed
  working under WSL2 with WSLg for the visible window. No requests/BeautifulSoup/selenium.
- No external services, API keys, or `.env` — it's an unauthenticated public-site scraper.
- Connectivity: `connectivity.py`'s `is_online()` does a raw TCP check (stdlib `socket`) against
  Centre Com, not a real HTTP request — cheap, no Playwright/browser needed. The GUI polls it
  every `config.CONNECTION_POLL_INTERVAL_MS` (10s) in a background thread for the always-visible
  status indicator, in addition to checking fresh on every Start press.

## Running it

```
python main.py
```

`requirements.txt` only pins Playwright's own transitive deps (from a `pip freeze`). No
`playwright install ...` step is needed: the app launches via `channel="msedge"` (see "Tech
stack" above), which uses whatever Edge install is already on the machine rather than a
Playwright-managed browser — nothing to download.

## Key files

- `main.py` — GUI entry point (`TicketApp` from `gui.py`).
- `gui.py` — tkinter GUI. Validates the category URL, runs the scrape in a background thread
  (`self.scrape_thread`) with a `threading.Event` for cooperative stop/cancel, and prompts to
  resume or restart an incomplete run. `root.protocol("WM_DELETE_WINDOW", self.on_close)` sets
  `stop_event` and joins the scrape thread with a bounded timeout on window close, so Playwright's
  browser/driver get a chance to clean up on the thread that actually owns them (Playwright's sync
  API is thread-affine) before the window is destroyed. Three independent connectivity-check paths
  (manual retry, Start-press check, background poll) share a monotonic
  `self._connection_check_generation` counter — each check's completion callback only updates the
  indicator if it's still the most recent check, so a slow/stale check can't overwrite a fresher
  result. All background-thread-originated widget updates go through `self._safe_after(...)`
  (not `root.after` directly) — it's a no-op once `self._closed` is set by `on_close`, since
  calling `root.after` from another thread on an already-destroyed root can hard-crash Tcl rather
  than raise a catchable Python exception.
- **Start/Resume/Restart/Stop button state.** There are three action buttons: `start_button`
  (label toggles "Start"/"Resume"), `restart_button` (only enabled when the current URL/filter
  exactly match a saved, *incomplete* run — clicking it calls `start_new_run` then `start_scrape`),
  and `stop_button`. `_refresh_start_controls()` is the single source of truth for this state —
  it re-derives "Start" vs "Resume" and Restart's enabled state from `load_progress()` against the
  live `url_entry`/`sale_filter` values, bound to `<KeyRelease>`/`<<ComboboxSelected>>` so it stays
  live as the user types, and also called from `run_scraper`'s `finally` block (covers normal
  completion, Stop, `BrowserClosedError`, and any other exception uniformly) and once at startup.
  It early-returns (forcing Restart disabled) whenever `stop_button` is currently `"normal"` —
  i.e. a scrape is actively running — specifically so editing the fields mid-scrape can't enable
  Restart and race `start_new_run`'s file truncation against the background thread's own writes.
  `run_scraper` also distinguishes a genuinely stopped run from a completed one before setting the
  status text: after `scrape_category` returns, if `stop_event` is set *and* `progress.json` isn't
  `completed`, status becomes `"Stopped"` (not left on `"Stopping..."`); if it did complete in that
  same window, the `"complete"`-event status is left alone.
- **The "Output" section (summary label + Copy buttons) only reflects confirmed, validated scans.**
  `_begin_scrape` no longer touches it eagerly on a category/filter mismatch — `start_new_run`,
  `reset_display`, and `_set_output_summary` all moved into `run_scraper`, right after
  `validate_category_url` succeeds. Typing an invalid/rejected URL and clicking Start now leaves
  the summary and Copy buttons showing the last real, valid scan untouched instead of jumping to
  the not-yet-validated input. Keep this ordering if you touch `_begin_scrape`/`run_scraper` again —
  it's easy to reintroduce eager updates that leak an unvalidated URL into the UI.
  On a mismatch, `run_scraper` calls `start_new_run(category_url, sale_filter)` itself,
  synchronously, *before* scheduling `reset_display`/`_set_output_summary` via `_safe_after` —
  not just clearing the excluded status's file and leaving the rest for `scrape_category` to
  reset later. `_safe_after` only *schedules* a callback on the Tk mainloop; it doesn't run
  synchronously with the background scrape thread, so if the reset itself were left for later
  (or for a separate call), there'd be a window where a UI refresh could read old output files
  before they were actually truncated — which is exactly what let a stopped-mid-pagination run
  keep showing stale codes from the previous category. Doing the full reset first, before
  anything is scheduled, closes that window by construction. `scrape_category` still carries
  its own independent mismatch-and-reset check (see the `scraper.py` entry below) as a safety
  net for callers that don't go through `run_scraper`; by the time the GUI's own reset has
  already run, that check simply finds nothing to do.
- `scraper.py` — core scraping logic: paginate the category, filter by sale status, check
  Adelaide retail stock, extract CC codes. `check_product` resolves and returns each product's
  final sale status ("sale"/"not_sale") so the caller knows which output file to write to. Has
  crash-resume logic that cross-checks `progress.json` against the combined line count of both
  CC output files and restarts the category if they disagree (implemented as a recursive call to
  `scrape_category`, not a loop).
- `progress.py` — persistence helpers. `save_cc_number(cc_number, sale_status)` writes to
  `output/sale_cc_numbers.txt` or `output/not_sale_cc_numbers.txt` depending on status;
  `get_cc_file_count`/`load_cc_numbers` read from both combined; `count_lines(filename)` is the
  public per-file line counter the GUI uses for the sale/not-sale split. `start_new_run`
  truncates all three output files (sale, not-sale, failed) plus `progress.json` — `gui.py`'s
  `run_scraper` calls this right after the new category/filter combo's URL is successfully
  validated (not before — see the `gui.py` entry above), so a stale file from an unrelated
  previous run never sits there with a live Copy button, but an invalid URL attempt also never
  touches it. `save_progress` writes atomically (temp
  file + `os.replace`) and `load_progress` validates the parsed JSON is a dict with all expected
  keys — both guard against a crash mid-write or a hand-edited file silently corrupting state.
- `scraper.py`'s `BrowserClosedError` — raised (via the shared `goto` helper, used by both
  `scraper.py` and `validation.py`, and directly in `check_product`) whenever a Playwright call
  fails in a way that indicates the browser is gone: `page.is_closed()` is true (clean window
  close), OR the error is a `playwright.sync_api.Error` whose message mentions "closed" (an
  unclean crash/kill, where `is_closed()` never gets set — see `is_browser_closed_error`). This is
  deliberately NOT treated like a normal per-product failure (which retries and logs to
  `failed_products.txt`) — it propagates all the way up through `scrape_category` uncaught, so the
  loop stops immediately at the real point of interruption instead of blazing through every
  remaining product as an instant "failure" and reporting a false `"complete"`. `gui.py`'s
  `run_scraper` catches it specifically (before the generic `except Exception`) to show a clear
  "browser was closed" status instead of either a false-complete progress bar or a raw error
  string. `scrape_category` also checks `stop_event` immediately after `get_retail_product_urls`
  returns (which itself only checks `stop_event` between pages) — clicking Stop while it's still
  paging returns a truncated list, and without this check the very next validity test would treat
  that as "the category shrank" and wipe all existing output/progress via `start_new_run`.
- `validation.py` — URL normalization and category-page validation (Centre Com domains only).
  Shares `scraper.goto`/`is_browser_closed_error` so a browser closed during validation produces
  the same `BrowserClosedError` as everywhere else, not a generic error.
- `config.py` — constants (`BASE_URL`, `OUTPUT_DIR`, output file paths).
- `file_actions.py` — the only OS-specific code in the repo. `open_path(path)` opens a file/folder
  in the OS's default handler: `os.startfile` on Windows, `open` on macOS, `xdg-open` on plain
  Linux, and — since `sys.platform` reports `"linux"` under WSL too — a dedicated WSL branch
  (`_is_wsl()` checks `/proc/version` for "microsoft") that converts the path with `wslpath -w`
  and opens it via `explorer.exe`. `explorer.exe` is called with `check=False` deliberately: it's
  a known Windows quirk that it often exits non-zero even after successfully opening the folder.
  Every subprocess call has `timeout=OPEN_TIMEOUT` (10s) so a stalled file-manager process can't
  hang the caller forever. Used only by the GUI's "Open Output Folder" button (run in a background
  thread — this is the one blocking OS call in the app that isn't Playwright) — the Copy-to-clipboard
  buttons use tkinter's built-in clipboard (`root.clipboard_clear`/`clipboard_append`), no OS
  branching needed.

## Tests

`tests/` — pytest suite covering `progress.py`, `scraper.py`, `validation.py`, `connectivity.py`,
`file_actions.py`, and `gui.py`. Run with `pytest` (or `.venv/bin/python -m pytest`) from the repo
root. GUI tests need a real display; `tests/conftest.py`'s `requires_tk` skip-guard makes them
skip cleanly (not fail) when none is available, so plain `pytest` always works — use
`xvfb-run -a pytest` to actually exercise them without a real display.

Two things to know before writing more tests here:
- **`from config import X` bindings are independent per module.** `progress.py`, `scraper.py`,
  and `gui.py` each do their own `from config import SALE_FILE, ...` — patching `config.SALE_FILE`
  in a test does **not** affect `progress.SALE_FILE`/`gui.SALE_FILE`, since each import created its
  own binding. Monkeypatch the constant on every *consuming* module that's actually exercised by
  the test (see the `paths`/`app_paths` fixtures in `tests/test_progress.py`/`tests/test_gui.py`
  for the pattern), not on `config` itself.
- **`tests/conftest.py`'s `run_in_mainloop(root, steps)`** formalizes the pattern used throughout
  this project's development for verifying tkinter behavior: a list of `(delay_ms, fn)` steps
  chained via `root.after`, run against a real `mainloop()`, with the window destroyed
  automatically after the last step. Prefer it over inventing a new driving mechanism per test.
- **`tests/test_gui.py`'s `app_paths` fixture patches `threading.Thread` to `SyncThread`**, which
  runs its target synchronously instead of on a real OS thread. This isn't just a speed
  optimization: real threads combined with rapid `tk.Tk()` creation/destruction across many tests
  in one process reproducibly triggers a `Fatal Python error: Aborted` crash in Tcl/Tk — confirmed
  unrelated to this app's own code (it reproduced with `test_progress.py`, which never touches
  `gui`/`scraper`/Playwright, running before `test_gui.py`). GUI tests exercise what each worker
  function *does*, not real concurrency, so synchronous execution is safe and sidesteps the crash
  entirely. Any new GUI test that spawns a `threading.Thread` (directly or via an app method) gets
  this automatically through `app_paths` — don't remove it without re-verifying the crash is gone
  (`for i in {1..10}; do pytest -q; done` should stay green every time).

## Gotchas

- Product/stock detection relies on **positional DOM selectors** reverse-engineered from the
  live site (e.g. the 2nd `.product-code .value` element, the 2nd stock-availability icon).
  These will silently break if Centre Com changes their page markup — verify against the real
  site, not just code review, when touching `scraper.py`.
- Two category layouts are handled differently: normal category pages (`div.prbox_box`,
  `.product-grid`) vs "deal" pages (`div.deal-grid-box`, `#deal-products-wrap`), the latter
  always treated as single-page and always on-sale.
- `output/` (sale/not-sale/failed files) and `progress.json` are run-time output/state, gitignored
  and untracked — don't commit fresh scrape output as if it were source changes.
- Commits go directly to `main` (solo project, no branches/PRs).

## Packaging / distribution

Coworkers run a packaged Windows installer, not `python main.py` from source. Built entirely by
CI — there is no local Windows machine in this project's dev loop, and PyInstaller can't
cross-compile a Windows `.exe` from Linux/WSL.

- `config.py` branches on `sys.frozen`: a PyInstaller build points `OUTPUT_DIR`/`PROGRESS_FILE` at
  `%LOCALAPPDATA%\CentreComTicketGenerator\` instead of CWD-relative paths, since the installed app
  lives in Program Files where a normal user can't write. Dev/test behavior (relative `output`/
  `progress.json`) is untouched — `sys.frozen` is never set when running from source.
- `packaging/CentreComTicketGenerator.spec` — PyInstaller spec, `--onedir` (not onefile: onefile
  would re-extract Playwright's ~150MB+ driver payload to a temp dir on every launch, which is both
  slow and a known source of driver-path bugs once frozen). Explicitly collects `sv_ttk`'s package
  data (`.tcl` theme files + sprite PNGs — confirmed both `pyinstaller-hooks-contrib`'s own
  `hook-sv_ttk.py` and the explicit `collect_data_files("sv_ttk")` fire; the explicit call is
  redundant-but-harmless belt-and-suspenders). Playwright's own driver folder (the embedded Node.js
  runtime + JS driver scripts the Python `sync_api` shells out to via subprocess — separate from
  the browser itself) needs no manual entry: Playwright registers its own PyInstaller hook via a
  `pyinstaller40` entry point, auto-discovered at build time. Spec files are `exec()`'d by
  PyInstaller rather than imported, so `__file__` isn't defined inside one — use the `SPECPATH`
  PyInstaller injects into the exec namespace instead (this repo's spec does).
- `packaging/requirements-build.txt` — build-only deps (`pyinstaller`), kept separate from the
  app's own `requirements.txt` since it's a build tool, not a runtime dependency.
- `packaging/installer.iss` — Inno Setup script wrapping the PyInstaller `dist/` output into
  `CentreComTicketGeneratorSetup.exe`: installs to Program Files (`PrivilegesRequired=admin`),
  Start Menu shortcut, optional desktop shortcut, auto-generated uninstaller.
- `.github/workflows/build-windows.yml` — two jobs. `test` runs the existing suite on
  `ubuntu-latest` via `xvfb-run -a pytest -q` and gates the build. `build-windows` (depends on
  `test`) runs on `windows-latest`: installs deps, runs PyInstaller against the spec, installs Inno
  Setup via Chocolatey (confirmed **not** preinstalled on current `windows-latest` images — an
  open `actions/runner-images` request, not a given), builds the installer, uploads it as a
  workflow artifact, and — only when triggered by a `v*` tag push — attaches it to a GitHub
  Release. Deliberately no `playwright install ...` step: `msedge` isn't one of Playwright's
  managed/downloadable browsers (confirmed in the installed driver's `browsers.json` —
  `installByDefault` only lists `chromium`/`chromium-headless-shell`/`firefox`/`webkit`/`ffmpeg`),
  it's located purely by scanning known OS install paths, and `windows-latest` always ships Edge.
- **To cut a release**: push a `v*` tag (e.g. `v1.0.1`). Coworkers download
  `CentreComTicketGeneratorSetup.exe` from the repo's GitHub Releases page. `workflow_dispatch` is
  also enabled for on-demand test builds (uploaded as a workflow artifact, not attached to a
  release, since the release-attach step is gated on the tag-push trigger).
- No code-signing certificate, so Windows SmartScreen will likely warn "Unknown publisher" on
  first run of the installer (and possibly the app) — expected, not a bug; coworkers click "More
  info → Run anyway."
