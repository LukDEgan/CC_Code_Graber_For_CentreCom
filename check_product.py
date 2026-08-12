from playwright.sync_api import sync_playwright

PRODUCT_URL = "https://www.centrecom.com.au/fantech-aera-arch-wireless-ergonomic-silent-keyboard-and-mouse-combo-with-wrist-rest"
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
        page.goto(PRODUCT_URL)

        stock_status = get_adelaide_stock(page)

        if stock_status.strip() == "In Stock":
            cc_number = get_cc_number(page)
            print(f"In stock - CC#: {cc_number}")
        else:
            print("Not in stock - skipping")

        browser.close()

if __name__ == "__main__":
    main()

