import json
import tkinter as tk
from contextlib import contextmanager

import pytest
from conftest import requires_tk, run_in_mainloop

import gui as gui_module
import progress as progress_module
from scraper import BrowserClosedError, NetworkDisconnectedError

pytestmark = requires_tk


class SyncThread:
    """Stand-in for threading.Thread that runs its target synchronously.

    Real OS threads combined with rapid tk.Tk() creation/destruction across
    many tests in one process is a known source of a rare, timing-sensitive
    "Fatal Python error: Aborted" crash in Tcl/Tk -- unrelated to any
    application logic. These tests exercise what each worker function does,
    not real concurrency, so running synchronously sidesteps the race
    entirely while still exercising the same code paths.
    """

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)

    def is_alive(self):
        return False

    def join(self, timeout=None):
        pass


@pytest.fixture
def app_paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    sale_file = output_dir / "sale.txt"
    not_sale_file = output_dir / "not_sale.txt"
    fail_file = output_dir / "failed.txt"
    progress_file = tmp_path / "progress.json"

    for module in (gui_module, progress_module):
        monkeypatch.setattr(module, "OUTPUT_DIR", str(output_dir))
        monkeypatch.setattr(module, "SALE_FILE", str(sale_file))
        monkeypatch.setattr(module, "NOT_SALE_FILE", str(not_sale_file))
        if hasattr(module, "FAIL_FILE"):
            monkeypatch.setattr(module, "FAIL_FILE", str(fail_file))
        if hasattr(module, "PROGRESS_FILE"):
            monkeypatch.setattr(module, "PROGRESS_FILE", str(progress_file))

    monkeypatch.setattr(gui_module, "is_online", lambda: True)
    monkeypatch.setattr(gui_module.threading, "Thread", SyncThread)

    return {
        "output_dir": output_dir,
        "sale_file": sale_file,
        "not_sale_file": not_sale_file,
        "fail_file": fail_file,
        "progress_file": progress_file,
    }


def make_app():
    root = tk.Tk()
    app = gui_module.TicketApp(root)
    return root, app


# ---------------------------------------------------------------------------
# Output buttons + summary label
# ---------------------------------------------------------------------------


def test_output_buttons_start_disabled_and_enable_after_content(app_paths):
    root, app = make_app()
    results = {}

    def write_sale_file():
        app_paths["output_dir"].mkdir(exist_ok=True)
        app_paths["sale_file"].write_text("111111\n222222\n", encoding="utf-8")
        app._refresh_output_buttons()

    def capture():
        results["text"] = app.copy_sale_button.cget("text")
        results["state"] = str(app.copy_sale_button.cget("state"))

    run_in_mainloop(
        root,
        [
            (100, lambda: results.update(
                fresh_text=app.copy_sale_button.cget("text"),
                fresh_state=str(app.copy_sale_button.cget("state")),
            )),
            (100, write_sale_file),
            (100, capture),
        ],
    )

    assert results["fresh_text"] == "Copy Sale Codes (0)"
    assert results["fresh_state"] == "disabled"
    assert results["text"] == "Copy Sale Codes (2)"
    assert results["state"] == "normal"


def test_copy_sale_codes_puts_contents_on_clipboard(app_paths):
    app_paths["output_dir"].mkdir(exist_ok=True)
    app_paths["sale_file"].write_text("111111\n222222\n", encoding="utf-8")

    root, app = make_app()
    results = {}

    def do_copy():
        app._refresh_output_buttons()
        app.copy_sale_codes()

    def capture():
        results["clipboard"] = root.clipboard_get()
        results["status"] = app.status_label.cget("text")

    run_in_mainloop(root, [(100, do_copy), (100, capture)])

    assert results["clipboard"] == "111111\n222222"
    assert results["status"] == "Copied 2 sale codes to clipboard"


def test_output_summary_shows_no_scan_yet_on_fresh_launch(app_paths):
    root, app = make_app()
    results = {}

    def capture():
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")
        results["status"] = app.output_status_label.cget("text")

    run_in_mainloop(root, [(100, capture)])

    assert results["url"] == "No scan yet"
    assert results["filter"] == ""
    assert results["status"] == ""


def test_output_summary_shows_no_scan_yet_when_incomplete_run_has_no_output(app_paths):
    # An incomplete run that never got as far as saving anything has nothing
    # to open/copy -- must not be shown as if it were a real previous scan.
    progress_module.save_progress(
        "https://www.centrecom.com.au/prior-cat", "All items", 0, 0, 0, completed=False
    )

    root, app = make_app()
    results = {}

    def capture():
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")
        results["status"] = app.output_status_label.cget("text")

    run_in_mainloop(root, [(100, capture)])

    assert results["url"] == "No scan yet"
    assert results["filter"] == ""
    assert results["status"] == ""


def test_output_summary_reflects_reopened_completed_session(app_paths):
    app_paths["output_dir"].mkdir(exist_ok=True)
    app_paths["sale_file"].write_text("111111\n", encoding="utf-8")
    app_paths["progress_file"].write_text(
        json.dumps(
            {
                "category_url": "https://www.centrecom.com.au/prior-cat",
                "sale_filter": "All items",
                "next_index": 5,
                "cc_count": 1,
                "fail_count": 0,
                "completed": True,
            }
        ),
        encoding="utf-8",
    )

    root, app = make_app()
    results = {}

    def capture():
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")
        results["status"] = app.output_status_label.cget("text")
        results["color"] = str(app.output_status_label.cget("foreground"))

    run_in_mainloop(root, [(100, capture)])

    assert results["url"] == "https://www.centrecom.com.au/prior-cat"
    assert results["filter"] == "Filter: All items"
    assert results["status"] == "Scan complete — 1 sale, 0 not on sale"
    assert results["color"] == "green"


def test_output_summary_reflects_reopened_incomplete_session(app_paths):
    app_paths["output_dir"].mkdir(exist_ok=True)
    app_paths["sale_file"].write_text("111111\n", encoding="utf-8")
    progress_module.save_progress(
        "https://www.centrecom.com.au/prior-cat", "All items", 5, 1, 0, completed=False
    )

    root, app = make_app()
    results = {}

    def capture():
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")
        results["status"] = app.output_status_label.cget("text")
        results["color"] = str(app.output_status_label.cget("foreground"))

    run_in_mainloop(root, [(100, capture)])

    assert results["url"] == "https://www.centrecom.com.au/prior-cat"
    assert results["filter"] == "Filter: All items"
    assert results["status"] == "Scan incomplete — stopped partway (1 sale, 0 not on sale so far)"
    assert results["color"] == "orange"


def test_switching_filter_clears_opposite_file_and_updates_summary(app_paths, monkeypatch):
    # Simulate stale not-sale data from a previous "All items" run, then
    # switch to a new category with a single-status filter. clear_opposite_file
    # only runs once the new URL is confirmed valid (inside run_scraper), so
    # validation/scrape_category must be stubbed rather than run_scraper itself.
    app_paths["output_dir"].mkdir(exist_ok=True)
    app_paths["sale_file"].write_text("111111\n", encoding="utf-8")
    app_paths["not_sale_file"].write_text("222222\n", encoding="utf-8")
    progress_module.save_progress(
        "https://www.centrecom.com.au/old-cat", "All items", 1, 1, 0, completed=True
    )

    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)
    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))

    # A real scrape_category writes fresh progress for the new category/filter
    # as its first action on a mismatch (via start_new_run); stub just that
    # part so run_scraper's end-of-run summary refresh sees consistent state,
    # without the stub also wiping the sale file clear_opposite_file kept.
    def fake_scrape_category(page, category_url, sale_filter, **kw):
        progress_module.save_progress(category_url, sale_filter, 0, 0, 0, completed=False)

    monkeypatch.setattr(gui_module, "scrape_category", fake_scrape_category)

    root, app = make_app()
    results = {}

    def switch():
        app.url_entry.insert(0, "https://www.centrecom.com.au/new-cat")
        app.sale_filter.set("On sale")
        app._begin_scrape()

    def capture():
        results["not_sale_content"] = app_paths["not_sale_file"].read_text(encoding="utf-8")
        results["sale_content"] = app_paths["sale_file"].read_text(encoding="utf-8")
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")
        results["not_sale_button_state"] = str(app.copy_not_sale_button.cget("state"))

    run_in_mainloop(root, [(100, switch), (300, capture)])

    assert results["not_sale_content"] == ""
    assert results["sale_content"] == "111111\n"
    assert results["url"] == "https://www.centrecom.com.au/new-cat"
    assert results["filter"] == "Filter: On sale"
    assert results["not_sale_button_state"] == "disabled"


def test_invalid_url_does_not_change_output_summary(app_paths, monkeypatch):
    # Regression test: entering an invalid/rejected URL and clicking Start
    # must leave the output summary (and output buttons) exactly as they
    # were -- reflecting the last real, valid scan -- rather than jumping to
    # the not-yet-validated URL the user just typed.
    app_paths["output_dir"].mkdir(exist_ok=True)
    app_paths["sale_file"].write_text("111111\n", encoding="utf-8")
    progress_module.save_progress(
        "https://www.centrecom.com.au/old-cat", "All items", 1, 1, 0, completed=True
    )

    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)
    monkeypatch.setattr(
        gui_module,
        "validate_category_url",
        lambda page, url: (None, "URL must be from Centre Com"),
    )

    root, app = make_app()
    results = {}

    def attempt_invalid():
        app.url_entry.delete(0, "end")
        app.url_entry.insert(0, "https://example.com/not-centrecom")
        app.sale_filter.set("All items")
        app._begin_scrape()

    def capture():
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")
        results["sale_button_text"] = app.copy_sale_button.cget("text")
        results["status"] = app.status_label.cget("text")

    run_in_mainloop(root, [(100, attempt_invalid), (300, capture)])

    assert results["url"] == "https://www.centrecom.com.au/old-cat"
    assert results["filter"] == "Filter: All items"
    assert results["sale_button_text"] == "Copy Sale Codes (1)"
    assert results["status"] == "URL must be from Centre Com"


def test_valid_new_url_updates_summary_after_validation_succeeds(app_paths, monkeypatch):
    progress_module.save_progress(
        "https://www.centrecom.com.au/old-cat", "All items", 1, 1, 0, completed=True
    )

    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)
    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))

    # Simulate a real scrape_category completing the (empty) new category, so
    # the end-of-run summary refresh has something to reflect for it -- an
    # incomplete run with no output would correctly collapse to "No scan yet".
    def fake_scrape_category(page, category_url, sale_filter, **kw):
        progress_module.save_progress(category_url, sale_filter, 0, 0, 0, completed=True)

    monkeypatch.setattr(gui_module, "scrape_category", fake_scrape_category)

    root, app = make_app()
    results = {}

    def attempt_valid():
        app.url_entry.delete(0, "end")
        app.url_entry.insert(0, "https://www.centrecom.com.au/new-cat")
        app.sale_filter.set("All items")
        app._begin_scrape()

    def capture():
        results["url"] = app.output_url_label.cget("text")
        results["filter"] = app.output_filter_label.cget("text")

    run_in_mainloop(root, [(100, attempt_valid), (300, capture)])

    assert results["url"] == "https://www.centrecom.com.au/new-cat"
    assert results["filter"] == "Filter: All items"


# ---------------------------------------------------------------------------
# Stop -> "Stopped" status, Resume label, Restart button
# ---------------------------------------------------------------------------


def test_status_becomes_stopped_after_stop_resolves(app_paths, monkeypatch):
    progress_module.save_progress(
        "https://www.centrecom.com.au/cat", "All items", 2, 1, 0, completed=False
    )

    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))
    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)

    def fake_scrape_category(page, category_url, sale_filter, on_progress=None, stop_event=None):
        assert stop_event is not None and stop_event.is_set()
        return []

    monkeypatch.setattr(gui_module, "scrape_category", fake_scrape_category)

    root, app = make_app()
    results = {}

    def start_then_stop():
        app.stop_event.set()
        app.set_status("Stopping...")
        app.run_scraper("https://www.centrecom.com.au/cat", "All items")

    def capture():
        results["status"] = app.status_label.cget("text")

    run_in_mainloop(root, [(100, start_then_stop), (300, capture)])

    assert results["status"] == "Stopped"


def test_start_button_becomes_resume_and_restart_enabled_after_stop(app_paths, monkeypatch):
    progress_module.save_progress(
        "https://www.centrecom.com.au/cat", "All items", 2, 1, 0, completed=False
    )

    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))
    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)
    monkeypatch.setattr(
        gui_module,
        "scrape_category",
        lambda page, category_url, sale_filter, on_progress=None, stop_event=None: [],
    )

    root, app = make_app()
    results = {}

    def prime_and_stop():
        app.url_entry.insert(0, "https://www.centrecom.com.au/cat")
        app.stop_event.set()
        app.run_scraper("https://www.centrecom.com.au/cat", "All items")

    def capture():
        results["start_text"] = app.start_button.cget("text")
        results["restart_state"] = str(app.restart_button.cget("state"))

    run_in_mainloop(root, [(100, prime_and_stop), (300, capture)])

    assert results["start_text"] == "Resume"
    assert results["restart_state"] == "normal"


def test_refresh_start_controls_shows_start_when_no_matching_progress(app_paths):
    root, app = make_app()
    results = {}

    def check():
        results["start_text"] = app.start_button.cget("text")
        results["restart_state"] = str(app.restart_button.cget("state"))

    run_in_mainloop(root, [(100, check)])

    assert results["start_text"] == "Start"
    assert results["restart_state"] == "disabled"


def test_refresh_start_controls_keeps_restart_disabled_while_running(app_paths):
    # Simulate a scrape actively in progress (Stop enabled) with fields that
    # would otherwise look "resumable" -- Restart must stay disabled, since
    # clicking it would race with the background thread's file writes.
    root, app = make_app()
    results = {}

    def simulate_running():
        app.stop_button.config(state="normal")
        app.restart_button.config(state="normal")
        app._refresh_start_controls()

    def capture():
        results["restart_state"] = str(app.restart_button.cget("state"))

    run_in_mainloop(root, [(100, simulate_running), (100, capture)])

    assert results["restart_state"] == "disabled"


def test_restart_scrape_resets_progress_and_starts_fresh(app_paths, monkeypatch):
    app_paths["output_dir"].mkdir(exist_ok=True)
    app_paths["sale_file"].write_text("111111\n222222\n", encoding="utf-8")
    progress_module.save_progress(
        "https://www.centrecom.com.au/cat", "All items", 2, 2, 0, completed=False
    )

    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)
    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))

    scrape_calls = []

    def fake_scrape_category(page, category_url, sale_filter, on_progress=None, stop_event=None):
        scrape_calls.append((category_url, sale_filter))
        return []

    monkeypatch.setattr(gui_module, "scrape_category", fake_scrape_category)

    root, app = make_app()
    results = {}

    def click_restart():
        app.url_entry.insert(0, "https://www.centrecom.com.au/cat")
        app.sale_filter.set("All items")
        app.restart_scrape()

    def capture():
        results["sale_file_content"] = app_paths["sale_file"].read_text(encoding="utf-8")
        results["progress"] = progress_module.load_progress()
        results["scrape_calls"] = scrape_calls

    run_in_mainloop(root, [(100, click_restart), (300, capture)])

    assert results["sale_file_content"] == ""
    assert results["progress"]["next_index"] == 0
    assert results["progress"]["cc_count"] == 0
    assert results["scrape_calls"] == [("https://www.centrecom.com.au/cat", "All items")]


# ---------------------------------------------------------------------------
# Scan-scope label: explains the eligible/skipped product-count gap
# ---------------------------------------------------------------------------


def test_update_scan_scope_reports_skip_breakdown(app_paths):
    root, app = make_app()
    results = {}

    def apply():
        app.update_scan_scope(eligible=120, skipped=30, category_total=150)

    def capture():
        results["text"] = app.scan_scope_label.cget("text")

    run_in_mainloop(root, [(100, apply), (200, capture)])

    assert results["text"] == (
        "150 products found in this category — 120 are in stock at Adelaide "
        "retail (and match the filter) and will be checked; 30 skipped (not "
        "in stock at Adelaide retail, or excluded by the filter)."
    )


def test_update_scan_scope_no_skips_shows_simple_message(app_paths):
    root, app = make_app()
    results = {}

    def apply():
        app.update_scan_scope(eligible=50, skipped=0, category_total=50)

    def capture():
        results["text"] = app.scan_scope_label.cget("text")

    run_in_mainloop(root, [(100, apply), (200, capture)])

    assert results["text"] == "All 50 products in this category will be checked."


def test_handle_progress_listing_complete_updates_scan_scope_label(app_paths):
    root, app = make_app()
    results = {}

    def apply():
        app.handle_progress(
            "listing_complete", {"eligible": 5, "skipped": 2, "category_total": 7}
        )

    def capture():
        results["text"] = app.scan_scope_label.cget("text")

    run_in_mainloop(root, [(100, apply), (200, capture)])

    assert "7 products found in this category" in results["text"]
    assert "2 skipped" in results["text"]


def test_reset_display_clears_scan_scope_label(app_paths):
    root, app = make_app()
    results = {}

    def apply():
        app.update_scan_scope(eligible=5, skipped=2, category_total=7)
        app.reset_display()

    def capture():
        results["text"] = app.scan_scope_label.cget("text")

    run_in_mainloop(root, [(100, apply), (200, capture)])

    assert results["text"] == ""


# ---------------------------------------------------------------------------
# BrowserClosedError handling in run_scraper
# ---------------------------------------------------------------------------


@contextmanager
def fake_sync_playwright_context():
    class FakeBrowser:
        def new_page(self):
            return object()

        def close(self):
            pass

    class FakeChromium:
        def launch(self, headless=False):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    yield FakePlaywright()


def test_run_scraper_browser_closed_freezes_progress_instead_of_completing(
    app_paths, monkeypatch
):
    # Matching prior progress simulates "we were already resuming this exact
    # category/filter" -- so run_scraper's own mismatch check (which resets
    # the display for a genuinely new scan) doesn't fire and clobber the
    # in-flight progress this test primes below.
    progress_module.save_progress(
        "https://www.centrecom.com.au/cat", "All items", 5, 3, 0, completed=False
    )

    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))
    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)

    def fake_scrape_category(*a, **kw):
        raise BrowserClosedError("Browser window was closed")

    monkeypatch.setattr(gui_module, "scrape_category", fake_scrape_category)

    root, app = make_app()
    results = {}

    def start():
        app.update_product_progress(5, 20, 3)
        app.run_scraper("https://www.centrecom.com.au/cat", "All items")

    def capture():
        results["status"] = app.status_label.cget("text")
        results["progress_value"] = app.progress_bar["value"]
        results["progress_max"] = app.progress_bar["maximum"]
        results["start_state"] = str(app.start_button.cget("state"))
        results["stop_state"] = str(app.stop_button.cget("state"))

    run_in_mainloop(root, [(100, start), (300, capture)])

    assert results["status"] == "Stopped — the browser window was closed. Click Start to resume."
    assert results["progress_value"] == 5
    assert results["progress_max"] == 20
    assert results["start_state"] == "normal"
    assert results["stop_state"] == "disabled"


def test_run_scraper_network_disconnected_stops_and_updates_connection_indicator(
    app_paths, monkeypatch
):
    progress_module.save_progress(
        "https://www.centrecom.com.au/cat", "All items", 5, 3, 0, completed=False
    )

    monkeypatch.setattr(gui_module, "validate_category_url", lambda page, url: (url, None))
    monkeypatch.setattr(gui_module, "sync_playwright", fake_sync_playwright_context)

    def fake_scrape_category(*a, **kw):
        raise NetworkDisconnectedError("Network connection was lost")

    monkeypatch.setattr(gui_module, "scrape_category", fake_scrape_category)

    root, app = make_app()
    results = {}

    def start():
        app.update_product_progress(5, 20, 3)
        app.run_scraper("https://www.centrecom.com.au/cat", "All items")

    def capture():
        results["status"] = app.status_label.cget("text")
        results["start_state"] = str(app.start_button.cget("state"))
        results["stop_state"] = str(app.stop_button.cget("state"))
        results["connection_text"] = app.connection_label.cget("text")
        results["connection_color"] = str(app.connection_label.cget("foreground"))

    run_in_mainloop(root, [(100, start), (300, capture)])

    assert results["status"] == (
        "Stopped — network connection was lost. Reconnect and click Start to resume."
    )
    assert results["start_state"] == "normal"
    assert results["stop_state"] == "disabled"
    assert results["connection_text"] == "● Offline — no internet connection"
    assert results["connection_color"] == "red"


# ---------------------------------------------------------------------------
# Connectivity generation counter
# ---------------------------------------------------------------------------


def test_stale_connectivity_result_does_not_overwrite_newer_one(app_paths):
    root, app = make_app()
    results = {}

    def simulate_race():
        gen_old = app._begin_connection_check()
        gen_new = app._begin_connection_check()

        # Newer check's result arrives first...
        app._apply_connection_result(gen_new, True)
        # ...then a stale, older check's result arrives late.
        app._apply_connection_result(gen_old, False)

    def capture():
        results["text"] = app.connection_label.cget("text")

    run_in_mainloop(root, [(100, simulate_race), (100, capture)])

    assert results["text"] == "● Online"


def test_fresh_connectivity_result_is_applied(app_paths):
    root, app = make_app()
    results = {}

    def simulate():
        gen = app._begin_connection_check()
        app._apply_connection_result(gen, False)

    def capture():
        results["text"] = app.connection_label.cget("text")

    run_in_mainloop(root, [(100, simulate), (100, capture)])

    assert results["text"] == "● Offline — no internet connection"


# ---------------------------------------------------------------------------
# Window-close cleanup
# ---------------------------------------------------------------------------


class FakeThread:
    def __init__(self, alive=True):
        self.join_calls = []
        self._alive = alive

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self._alive = False


def test_on_close_sets_stop_event_and_joins_alive_scrape_thread(app_paths):
    root = tk.Tk()
    app = gui_module.TicketApp(root)

    fake_thread = FakeThread(alive=True)
    app.scrape_thread = fake_thread

    app.on_close()

    assert app.stop_event.is_set()
    assert fake_thread.join_calls == [5]


def test_on_close_with_no_scrape_thread_does_not_raise(app_paths):
    root = tk.Tk()
    app = gui_module.TicketApp(root)

    app.on_close()

    assert app.stop_event.is_set()


def test_on_close_does_not_join_already_dead_thread(app_paths):
    root = tk.Tk()
    app = gui_module.TicketApp(root)

    fake_thread = FakeThread(alive=False)
    app.scrape_thread = fake_thread

    app.on_close()

    assert fake_thread.join_calls == []
