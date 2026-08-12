from playwright.sync_api import sync_playwright

CATEGORY_URL = "https://www.centrecom.com.au/keyboards"
BASE_URL = "https://www.centrecom.com.au"
def get_adelaide_stock(page):
    adelaide = page.locator(
        "span.prod_store_stock",
        has_text="Adelaide"
    )

    adelaide_row = adelaide.locator("..")

    stock_status = adelaide_row.locator(
        "span.stock-result3"
    ).inner_text()

    return stock_status

def get_cc_number(page):
    product_codes = page.locator(".product-code .value")
    cc_number = product_codes.nth(1).inner_text()

    return cc_number.strip()

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()
        page.goto(CATEGORY_URL)

        product_links = page.locator("a.prbox_link")

        print(f"Products found: {product_links.count()}")

        for i in range(product_links.count()):
            link = product_links.nth(i)

            href = link.get_attribute("href")

            print(f"Product {i} -> {href}")

        input("Press Enter to close...")

        browser.close()

if __name__ == "__main__":
    main()


