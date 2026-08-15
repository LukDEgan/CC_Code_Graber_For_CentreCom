from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from scraper import (
    BrowserClosedError,
    NetworkDisconnectedError,
    goto,
    is_browser_closed_error,
)


def normalise_url(url):
    parsed_url = urlparse(url)

    params = parse_qs(parsed_url.query)
    params.pop("pagenumber", None)

    new_query = urlencode(params, doseq=True)

    return urlunparse(
        parsed_url._replace(
            query=new_query,
            fragment=""
        )
    )


def validate_category_url(page, category_url):
    category_url = category_url.strip()

    try:
        parsed_url = urlparse(category_url)
    except ValueError:
        return None, "Invalid URL"

    if parsed_url.scheme not in ("http", "https"):
        return None, "Invalid URL"

    if parsed_url.hostname not in (
        "centrecom.com.au",
        "www.centrecom.com.au"
    ):
        return None, "URL must be from Centre Com"

    category_url = normalise_url(category_url)

    try:
        goto(page, category_url)
    except (BrowserClosedError, NetworkDisconnectedError):
        raise
    except Exception:
        return None, "Could not load page"

    try:
        has_product_grid = page.locator(".product-grid").count() > 0
        has_deal_wrap = page.locator("#deal-products-wrap").count() > 0
    except Exception as error:
        if is_browser_closed_error(page, error):
            raise BrowserClosedError("Browser window was closed") from error
        return None, "Could not load page"

    if not has_product_grid and not has_deal_wrap:
        return None, "URL is not a category page"

    return category_url, None
