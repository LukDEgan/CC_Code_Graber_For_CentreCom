import pytest

import validation
from scraper import BrowserClosedError


class FakeLocator:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(
        self,
        product_grid_count=0,
        deal_wrap_count=0,
        goto_error=None,
        locator_error=None,
        closed=False,
    ):
        self.product_grid_count = product_grid_count
        self.deal_wrap_count = deal_wrap_count
        self.goto_error = goto_error
        self.locator_error = locator_error
        self._closed = closed
        self.goto_calls = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        if self.goto_error:
            raise self.goto_error

    def is_closed(self):
        return self._closed

    def locator(self, selector):
        if self.locator_error:
            raise self.locator_error

        if selector == ".product-grid":
            return FakeLocator(self.product_grid_count)
        if selector == "#deal-products-wrap":
            return FakeLocator(self.deal_wrap_count)

        raise AssertionError(f"unexpected selector: {selector}")


def test_normalise_url_strips_pagenumber():
    result = validation.normalise_url(
        "https://www.centrecom.com.au/cat?pagenumber=3&other=1"
    )
    assert "pagenumber" not in result
    assert "other=1" in result


def test_normalise_url_strips_fragment():
    result = validation.normalise_url("https://www.centrecom.com.au/cat#section")
    assert "#" not in result


def test_normalise_url_preserves_other_query_params():
    result = validation.normalise_url("https://www.centrecom.com.au/cat?sort=price")
    assert "sort=price" in result


def test_validate_rejects_invalid_scheme():
    page = FakePage()
    result, error = validation.validate_category_url(page, "ftp://www.centrecom.com.au/cat")
    assert result is None
    assert error == "Invalid URL"
    assert page.goto_calls == []


def test_validate_rejects_wrong_host():
    page = FakePage()
    result, error = validation.validate_category_url(page, "https://example.com/cat")
    assert result is None
    assert error == "URL must be from Centre Com"
    assert page.goto_calls == []


def test_validate_rejects_malformed_url_without_crashing():
    page = FakePage()
    result, error = validation.validate_category_url(page, "http://[::1/x")
    assert result is None
    assert error == "Invalid URL"


def test_validate_goto_generic_failure_returns_friendly_error():
    page = FakePage(goto_error=Exception("net::ERR_TIMED_OUT"))
    result, error = validation.validate_category_url(
        page, "https://www.centrecom.com.au/cat"
    )
    assert result is None
    assert error == "Could not load page"


def test_validate_goto_failure_with_closed_page_raises_browser_closed():
    page = FakePage(goto_error=Exception("boom"), closed=True)
    with pytest.raises(BrowserClosedError):
        validation.validate_category_url(page, "https://www.centrecom.com.au/cat")


def test_validate_no_matching_locators_returns_not_a_category_page():
    page = FakePage(product_grid_count=0, deal_wrap_count=0)
    result, error = validation.validate_category_url(
        page, "https://www.centrecom.com.au/cat"
    )
    assert result is None
    assert error == "URL is not a category page"


def test_validate_product_grid_present_succeeds():
    page = FakePage(product_grid_count=5)
    result, error = validation.validate_category_url(
        page, "https://www.centrecom.com.au/cat"
    )
    assert error is None
    assert result is not None


def test_validate_deal_wrap_present_succeeds():
    page = FakePage(deal_wrap_count=2)
    result, error = validation.validate_category_url(
        page, "https://www.centrecom.com.au/cat"
    )
    assert error is None
    assert result is not None


def test_validate_locator_failure_after_goto_returns_friendly_error():
    page = FakePage(locator_error=Exception("net::ERR_ABORTED"))
    result, error = validation.validate_category_url(
        page, "https://www.centrecom.com.au/cat"
    )
    assert result is None
    assert error == "Could not load page"


def test_validate_locator_failure_with_closed_page_raises_browser_closed():
    page = FakePage(locator_error=Exception("boom"), closed=True)
    with pytest.raises(BrowserClosedError):
        validation.validate_category_url(page, "https://www.centrecom.com.au/cat")
