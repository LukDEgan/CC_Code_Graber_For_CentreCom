import threading

import pytest

import progress as progress_module
import scraper
from scraper import BrowserClosedError, NetworkDisconnectedError

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_build_page_url_appends_query_param_when_none_present():
    assert scraper.build_page_url("https://x.com/cat", 3) == "https://x.com/cat?pagenumber=3"


def test_build_page_url_appends_extra_param_when_query_present():
    assert (
        scraper.build_page_url("https://x.com/cat?sort=price", 3)
        == "https://x.com/cat?sort=price&pagenumber=3"
    )


class FakeCountLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakeProductListing:
    def __init__(
        self, has_on_sale=False, has_was_price=False, has_reg_price=False, has_sale_price=False
    ):
        self._flags = {
            ".onsale": has_on_sale,
            ".wasprice": has_was_price,
            ".regprice": has_reg_price,
            ".saleprice": has_sale_price,
        }

    def locator(self, selector):
        return FakeCountLocator(1 if self._flags.get(selector) else 0)


def test_get_sale_status_on_sale():
    assert scraper.get_sale_status(FakeProductListing(has_on_sale=True)) == "sale"


def test_get_sale_status_was_price_counts_as_sale():
    assert scraper.get_sale_status(FakeProductListing(has_was_price=True)) == "sale"


def test_get_sale_status_sale_price_only_is_unknown():
    assert scraper.get_sale_status(FakeProductListing(has_sale_price=True)) == "unknown"


def test_get_sale_status_no_flags_is_not_sale():
    assert scraper.get_sale_status(FakeProductListing()) == "not_sale"


class FakeDealLabelPage:
    def __init__(self, has_deal_label):
        self._has_deal_label = has_deal_label

    def locator(self, selector):
        assert selector == ".deallabel"
        return FakeCountLocator(1 if self._has_deal_label else 0)


def test_get_product_page_sale_status_with_deal_label():
    assert scraper.get_product_page_sale_status(FakeDealLabelPage(True)) == "sale"


def test_get_product_page_sale_status_without_deal_label():
    assert scraper.get_product_page_sale_status(FakeDealLabelPage(False)) == "not_sale"


def test_report_progress_calls_callback_with_event_and_data():
    calls = []
    scraper.report_progress(lambda event, data: calls.append((event, data)), "page", current=1)
    assert calls == [("page", {"current": 1})]


def test_report_progress_noop_when_no_callback():
    scraper.report_progress(None, "page", current=1)  # should not raise


# ---------------------------------------------------------------------------
# check_product: BrowserClosedError vs. normal-failure branching
# ---------------------------------------------------------------------------


class FakeLocator:
    def __init__(self, count=0, text=""):
        self._count = count
        self._text = text

    def count(self):
        return self._count

    def inner_text(self):
        return self._text

    def nth(self, index):
        return self

    @property
    def first(self):
        return self

    def locator(self, selector):
        return self


class FakePage:
    def __init__(
        self,
        in_stock=False,
        cc_code="123456",
        deal_label=False,
        goto_error=None,
        goto_errors=None,
        closed=False,
    ):
        self.in_stock = in_stock
        self.cc_code = cc_code
        self.deal_label = deal_label
        self.goto_error = goto_error
        self.goto_errors = list(goto_errors) if goto_errors is not None else None
        self._closed = closed
        self.goto_calls = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)

        if self.goto_errors is not None:
            error = self.goto_errors.pop(0) if self.goto_errors else None
            if error:
                raise error
            return

        if self.goto_error:
            raise self.goto_error

    def is_closed(self):
        return self._closed

    def locator(self, selector, has_text=None):
        if selector == "span.prod_store_stock":
            count = 1 if self.in_stock is not None else 0
            text = "In Stock" if self.in_stock else "Out of Stock"
            return FakeLocator(count=count, text=text)
        if selector == ".product-code .value":
            return FakeLocator(text=self.cc_code)
        if selector == ".deallabel":
            return FakeLocator(count=1 if self.deal_label else 0)
        raise AssertionError(f"unexpected selector: {selector}")


@pytest.fixture
def fail_paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    fail_file = output_dir / "failed.txt"
    monkeypatch.setattr(scraper, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(scraper, "FAIL_FILE", str(fail_file))
    # Default to "online" so existing per-product-failure tests exercise the
    # normal retry path rather than a real network call to check_product's
    # is_online() fallback. Tests for the offline path override this.
    monkeypatch.setattr(scraper, "is_online", lambda: True)
    return fail_file


def test_check_product_in_stock_returns_cc_number(fail_paths):
    page = FakePage(in_stock=True, cc_code="654321")
    result = scraper.check_product(page, "http://x.com/p", "sale", "All items")
    assert result == ("654321", False, "sale")


def test_check_product_not_in_adelaide_returns_none(fail_paths):
    page = FakePage(in_stock=None)
    result = scraper.check_product(page, "http://x.com/p", "sale", "All items")
    assert result == (None, False, "sale")


def test_check_product_filters_out_wrong_sale_status(fail_paths):
    page = FakePage(in_stock=True)
    result = scraper.check_product(page, "http://x.com/p", "not_sale", "On sale")
    assert result == (None, False, "not_sale")
    assert page.goto_calls == ["http://x.com/p"]


def test_check_product_resolves_unknown_status_via_deal_label(fail_paths):
    page = FakePage(in_stock=True, deal_label=True)
    result = scraper.check_product(page, "http://x.com/p", "unknown", "All items")
    assert result == ("123456", False, "sale")


def test_check_product_retries_then_succeeds(fail_paths):
    page = FakePage(in_stock=True, goto_errors=[Exception("net::ERR_TIMED_OUT"), None])
    result = scraper.check_product(page, "http://x.com/p", "sale", "All items", retries=2)
    assert result == ("123456", False, "sale")
    assert len(page.goto_calls) == 2


def test_check_product_exhausts_retries_and_logs_failure(fail_paths):
    page = FakePage(goto_error=Exception("net::ERR_TIMED_OUT"))
    result = scraper.check_product(page, "http://x.com/p", "sale", "All items", retries=2)
    assert result == (None, True, "sale")
    assert fail_paths.read_text(encoding="utf-8") == "http://x.com/p\n"


def test_check_product_clean_close_raises_browser_closed(fail_paths):
    page = FakePage(goto_error=Exception("boom"), closed=True)
    with pytest.raises(BrowserClosedError):
        scraper.check_product(page, "http://x.com/p", "sale", "All items")
    assert not fail_paths.exists()


def test_check_product_unclean_crash_raises_browser_closed(fail_paths, monkeypatch):
    # page.is_closed() stays False (unclean disconnect), but Playwright raises
    # its own Error subclass with a "closed" message -- this is the gap fix #6
    # closes. playwright.sync_api.Error is public; TargetClosedError isn't
    # exported in this version, so construct the public base class directly.
    error = scraper.playwright.sync_api.Error("Target page, context or browser has been closed")
    page = FakePage(goto_error=error, closed=False)

    with pytest.raises(BrowserClosedError):
        scraper.check_product(page, "http://x.com/p", "sale", "All items")

    assert not fail_paths.exists()


def test_check_product_generic_playwright_error_without_closed_message_is_normal_failure(
    fail_paths,
):
    error = scraper.playwright.sync_api.Error("net::ERR_NAME_NOT_RESOLVED")
    page = FakePage(goto_error=error, closed=False)

    result = scraper.check_product(page, "http://x.com/p", "sale", "All items", retries=0)

    assert result == (None, True, "sale")


def test_check_product_raises_network_disconnected_when_offline(fail_paths, monkeypatch):
    # A dropped wifi/ethernet connection must stop the run immediately rather
    # than retrying and racing through every remaining product as an instant
    # "failure" (which previously looked like the scrape "continuing as if
    # nothing had happened").
    monkeypatch.setattr(scraper, "is_online", lambda: False)
    page = FakePage(goto_error=Exception("net::ERR_INTERNET_DISCONNECTED"))

    with pytest.raises(NetworkDisconnectedError):
        scraper.check_product(page, "http://x.com/p", "sale", "All items")

    assert not fail_paths.exists()
    assert len(page.goto_calls) == 1


# ---------------------------------------------------------------------------
# scrape_category state machine
# ---------------------------------------------------------------------------


@pytest.fixture
def progress_paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    sale_file = output_dir / "sale.txt"
    not_sale_file = output_dir / "not_sale.txt"
    fail_file = output_dir / "failed.txt"
    progress_file = tmp_path / "progress.json"

    monkeypatch.setattr(progress_module, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(progress_module, "SALE_FILE", str(sale_file))
    monkeypatch.setattr(progress_module, "NOT_SALE_FILE", str(not_sale_file))
    monkeypatch.setattr(progress_module, "FAIL_FILE", str(fail_file))
    monkeypatch.setattr(progress_module, "PROGRESS_FILE", str(progress_file))

    return {
        "output_dir": output_dir,
        "sale_file": sale_file,
        "not_sale_file": not_sale_file,
        "fail_file": fail_file,
        "progress_file": progress_file,
    }


def fake_products(n):
    return [
        {"url": f"http://x.com/p{i}", "sale_status": "sale"} for i in range(n)
    ]


def test_scrape_category_normal_completion(progress_paths, monkeypatch):
    monkeypatch.setattr(
        scraper,
        "get_retail_product_urls",
        lambda *a, **kw: (fake_products(2), 0),
    )
    monkeypatch.setattr(
        scraper,
        "check_product",
        lambda page, url, status, sale_filter: (url[-1], False, "sale"),
    )

    events = []
    scraper.scrape_category(
        page=None,
        category_url="http://x.com/cat",
        sale_filter="All items",
        on_progress=lambda event, data: events.append(event),
    )

    assert "complete" in events
    data = progress_module.load_progress()
    assert data["completed"] is True
    assert data["cc_count"] == 2
    assert progress_paths["sale_file"].read_text(encoding="utf-8") == "0\n1\n"


def test_scrape_category_already_completed_returns_without_paginating(
    progress_paths, monkeypatch
):
    # Matching category/filter that's already completed should bail out
    # before even listing the category -- there's nothing to do, so paging
    # through every page just to hit the no-op completed check is wasted work.
    progress_module.save_progress("http://x.com/cat", "All items", 2, 2, 0, completed=True)

    def fail_if_called(*a, **kw):
        raise AssertionError("get_retail_product_urls should not be called")

    monkeypatch.setattr(scraper, "get_retail_product_urls", fail_if_called)

    result = scraper.scrape_category(
        page=None, category_url="http://x.com/cat", sale_filter="All items"
    )

    assert result is None
    data = progress_module.load_progress()
    assert data == {
        "category_url": "http://x.com/cat",
        "sale_filter": "All items",
        "next_index": 2,
        "cc_count": 2,
        "fail_count": 0,
        "completed": True,
    }


def test_scrape_category_resets_output_before_pagination_on_mismatch(
    progress_paths, monkeypatch
):
    # The whole point of moving the reset earlier: a stale file from an old
    # category must be gone *before* pagination starts, not after -- so it's
    # never visible/copyable mid-listing as if it belonged to the new scan.
    progress_module.save_progress("http://x.com/old-cat", "All items", 1, 1, 0, completed=True)
    progress_paths["output_dir"].mkdir()
    progress_paths["sale_file"].write_text("999999\n", encoding="utf-8")

    seen_sale_file_content_during_listing = {}

    def fake_get_retail_product_urls(page, category_url, sale_filter, on_progress, stop_event):
        seen_sale_file_content_during_listing["content"] = progress_paths[
            "sale_file"
        ].read_text(encoding="utf-8")
        return fake_products(1), 0

    monkeypatch.setattr(scraper, "get_retail_product_urls", fake_get_retail_product_urls)
    monkeypatch.setattr(
        scraper,
        "check_product",
        lambda page, url, status, sale_filter: (url[-1], False, "sale"),
    )

    scraper.scrape_category(
        page=None, category_url="http://x.com/new-cat", sale_filter="All items"
    )

    assert seen_sale_file_content_during_listing["content"] == ""


def test_scrape_category_reports_listing_complete_with_skip_breakdown(
    progress_paths, monkeypatch
):
    # Products skipped due to a greyed-out in-store icon (or a sale-filter
    # mismatch) mean the "total" the UI checks against is smaller than the
    # category's real product count -- the caller needs the skip breakdown
    # to explain that gap rather than let it look like a scanning bug.
    monkeypatch.setattr(
        scraper,
        "get_retail_product_urls",
        lambda *a, **kw: (fake_products(2), 30),
    )
    monkeypatch.setattr(
        scraper,
        "check_product",
        lambda page, url, status, sale_filter: (url[-1], False, "sale"),
    )

    events = []
    scraper.scrape_category(
        page=None,
        category_url="http://x.com/cat",
        sale_filter="All items",
        on_progress=lambda event, data: events.append((event, data)),
    )

    listing_events = [data for event, data in events if event == "listing_complete"]
    assert listing_events == [{"eligible": 2, "skipped": 30, "category_total": 32}]


def test_scrape_category_resumes_from_saved_index(progress_paths, monkeypatch):
    progress_module.save_progress("http://x.com/cat", "All items", 1, 1, 0, completed=False)
    progress_paths["output_dir"].mkdir()
    progress_paths["sale_file"].write_text("0\n", encoding="utf-8")

    checked = []
    monkeypatch.setattr(
        scraper,
        "get_retail_product_urls",
        lambda *a, **kw: (fake_products(2), 0),
    )

    def fake_check_product(page, url, status, sale_filter):
        checked.append(url)
        return (url[-1], False, "sale")

    monkeypatch.setattr(scraper, "check_product", fake_check_product)

    scraper.scrape_category(
        page=None, category_url="http://x.com/cat", sale_filter="All items"
    )

    assert checked == ["http://x.com/p1"]


def test_scrape_category_self_heals_on_cc_count_mismatch(progress_paths, monkeypatch):
    # progress.json claims 5 codes were saved, but the file is actually empty --
    # this must be treated as untrustworthy and restarted from scratch.
    progress_module.save_progress("http://x.com/cat", "All items", 3, 5, 0, completed=False)

    monkeypatch.setattr(
        scraper,
        "get_retail_product_urls",
        lambda *a, **kw: (fake_products(1), 0),
    )
    monkeypatch.setattr(
        scraper,
        "check_product",
        lambda page, url, status, sale_filter: (url[-1], False, "sale"),
    )

    scraper.scrape_category(
        page=None, category_url="http://x.com/cat", sale_filter="All items"
    )

    data = progress_module.load_progress()
    assert data["cc_count"] == 1
    assert data["completed"] is True


def test_scrape_category_stop_during_relist_does_not_wipe_existing_progress(
    progress_paths, monkeypatch
):
    # Regression test for the CRITICAL fix: pre-existing, self-consistent
    # progress (3 codes saved, matching the file), then the user clicks Stop
    # while get_retail_product_urls is still paging -- it returns a truncated
    # list. Previously this fell through into the validity check
    # (next_index > len(product_urls)) and wiped everything via start_new_run.
    progress_module.save_progress("http://x.com/cat", "All items", 3, 3, 0, completed=False)
    progress_paths["output_dir"].mkdir()
    progress_paths["sale_file"].write_text("a\nb\nc\n", encoding="utf-8")

    stop_event = threading.Event()
    stop_event.set()

    def fake_get_retail_product_urls(page, category_url, sale_filter, on_progress, stop_event):
        # Simulates returning early, mid-pagination, with a short list.
        return fake_products(1), 0

    monkeypatch.setattr(scraper, "get_retail_product_urls", fake_get_retail_product_urls)

    check_product_calls = []
    monkeypatch.setattr(
        scraper,
        "check_product",
        lambda *a, **kw: check_product_calls.append(a),
    )

    result = scraper.scrape_category(
        page=None,
        category_url="http://x.com/cat",
        sale_filter="All items",
        stop_event=stop_event,
    )

    assert check_product_calls == []
    assert result == ["a", "b", "c"]
    assert progress_paths["sale_file"].read_text(encoding="utf-8") == "a\nb\nc\n"
    data = progress_module.load_progress()
    assert data["next_index"] == 3
    assert data["cc_count"] == 3
    assert data["completed"] is False


def test_scrape_category_propagates_browser_closed_mid_loop(progress_paths, monkeypatch):
    monkeypatch.setattr(
        scraper,
        "get_retail_product_urls",
        lambda *a, **kw: (fake_products(3), 0),
    )

    call_count = {"n": 0}

    def fake_check_product(page, url, status, sale_filter):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (url[-1], False, "sale")
        raise BrowserClosedError("Browser window was closed")

    monkeypatch.setattr(scraper, "check_product", fake_check_product)

    events = []
    with pytest.raises(BrowserClosedError):
        scraper.scrape_category(
            page=None,
            category_url="http://x.com/cat",
            sale_filter="All items",
            on_progress=lambda event, data: events.append(event),
        )

    assert "complete" not in events
    data = progress_module.load_progress()
    assert data["next_index"] == 1
    assert data["completed"] is False


def test_scrape_category_propagates_network_disconnected_mid_loop(progress_paths, monkeypatch):
    monkeypatch.setattr(
        scraper,
        "get_retail_product_urls",
        lambda *a, **kw: (fake_products(3), 0),
    )

    call_count = {"n": 0}

    def fake_check_product(page, url, status, sale_filter):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (url[-1], False, "sale")
        raise NetworkDisconnectedError("Network connection was lost")

    monkeypatch.setattr(scraper, "check_product", fake_check_product)

    events = []
    with pytest.raises(NetworkDisconnectedError):
        scraper.scrape_category(
            page=None,
            category_url="http://x.com/cat",
            sale_filter="All items",
            on_progress=lambda event, data: events.append(event),
        )

    assert "complete" not in events
    data = progress_module.load_progress()
    assert data["next_index"] == 1
    assert data["completed"] is False
