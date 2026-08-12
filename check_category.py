from playwright.sync_api import sync_playwright

CATEGORY_URL = "https://www.centrecom.com.au/audio-speakers"
BASE_URL = "https://www.centrecom.com.au"

def is_in_stock_adelaide(page):
    adelaide = page.locator(
        "span.prod_store_stock",
        has_text="Adelaide"
    )

    adelaide_row = adelaide.locator("..")

    row_text = adelaide_row.inner_text()

    return "In Stock" in row_text


def get_cc_number(page):
    product_codes = page.locator(".product-code .value")

    cc_number = product_codes.nth(1).inner_text()

    return cc_number.strip()

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

        products = page.locator("div.prbox_box")

        for i in range(products.count()):
            product = products.nth(i)

            store_icon = product.locator(
                ".prbox_stockicons .prbox_icon"
            ).nth(1)

            classes = store_icon.get_attribute("class")
            tooltip = store_icon.locator(".tooltip").inner_text()

            if (
                classes
                and "prbox_green" in classes
                and "Available at one or more retail stores." in tooltip
            ):
                href = product.locator("a.prbox_link").get_attribute("href")

                if href:
                    product_urls.append(href)

    return product_urls




def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        product_urls = get_product_urls(page, CATEGORY_URL)

        print(f"\nProducts found: {len(product_urls)}")

        cc_numbers = []

        for i, product_url in enumerate(product_urls):
            full_url = BASE_URL + product_url

            print(f"Checking {i + 1}/{len(product_urls)}")

            try:
                page.goto(full_url)

                if is_in_stock_adelaide(page):
                    cc_number = get_cc_number(page)
                    cc_numbers.append(cc_number)

                    print(f"  In Stock -> CC#: {cc_number}")
                else:
                    print("  Not in stock -> skipping")

            except Exception as e:
                print(f"  ERROR -> {full_url}")
                print(f"  {e}")

        print("\nFinal CC list:")

        for cc_number in cc_numbers:
            print(cc_number)

        with open("cc_numbers.txt", "w") as file:
            for cc_number in cc_numbers:
                file.write(cc_number + "\n")
        input("\nPress Enter to close...")
        browser.close()


if __name__ == "__main__":
    main()
