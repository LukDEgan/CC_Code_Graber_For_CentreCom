from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalise_url(url):
    parsed_url = urlparse(url)

    params = parse_qs(parsed_url.query)
    params.pop("pagenumber", None)

    new_query = urlencode(params, doseq=True)

    return urlunparse(
        parsed_url._replace(
            query=new_query,
            fragment="",
        )
    )


def handle_input(page):
    while True:
        category_url = input("Enter Centre Com category URL: ").strip()

        parsed_url = urlparse(category_url)

        if parsed_url.scheme not in ("http", "https"):
            print("Invalid URL")
            continue

        if parsed_url.hostname not in ("centrecom.com.au", "www.centrecom.com.au"):
            print("URL must be from Centre Com")
            continue

        category_url = normalise_url(category_url)

        try:
            page.goto(category_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            print("Could not load page")
            continue

        if page.locator(".product-grid").count() == 0:
            print("URL is not a category page")
            continue

        return category_url
