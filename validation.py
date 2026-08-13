from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


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

    parsed_url = urlparse(category_url)

    if parsed_url.scheme not in ("http", "https"):
        return None, "Invalid URL"

    if parsed_url.hostname not in (
        "centrecom.com.au",
        "www.centrecom.com.au"
    ):
        return None, "URL must be from Centre Com"

    category_url = normalise_url(category_url)

    try:
        page.goto(
            category_url,
            wait_until="domcontentloaded"
        )
    except Exception:
        return None, "Could not load page"

    if page.locator(".product-grid").count() == 0:
        return None, "URL is not a category page"

    return category_url, None
