from playwright.sync_api import sync_playwright

CATEGORY_URL = "https://www.centrecom.com.au/keyboards"


def get_total_pages(page):
    summary = page.locator("li.total-summary").inner_text()

    # "Page 1 of 30 (884 total)"
    parts = summary.split()

    total_pages = int(parts[3])

    return total_pages


def get_product_urls(page, category_url):
    product_urls = []

    page.goto(category_url)

    total_pages = get_total_pages(page)

    print(f"Category has {total_pages} pages")

    for page_number in range(1, total_pages + 1):
        url = f"{category_url}?pagenumber={page_number}"

        print(f"Reading page {page_number}/{total_pages}")

        page.goto(url)

        product_links = page.locator("a.prbox_link")

        for i in range(product_links.count()):
            href = product_links.nth(i).get_attribute("href")

            if href:
                product_urls.append(href)

    return product_urls


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        product_urls = get_product_urls(page, CATEGORY_URL)

        print(f"\nProducts found: {len(product_urls)}")

        for i, url in enumerate(product_urls):
            print(f"Product {i} -> {url}")

        input("\nPress Enter to close...")

        browser.close()


if __name__ == "__main__":
    main()
