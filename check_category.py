from playwright.sync_api import sync_playwright
import json
import os
CATEGORY_URL = "https://www.centrecom.com.au/audio-speakers"
BASE_URL = "https://www.centrecom.com.au"
CC_FILE = "cc_numbers.txt"
PROGRESS_FILE = "progress.json"

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


def get_retail_product_urls(page, category_url):
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

def save_cc_number(cc_number, filename="cc_numbers.txt"):
    with open(filename, "a") as file:
        file.write(cc_number + "\n")

def start_new_run():
    open(CC_FILE, "w").close()

    with open(PROGRESS_FILE, "w") as file:
        json.dump({"next_index": 0}, file)

def save_progress(next_index):
    with open(PROGRESS_FILE, "w") as file:
        json.dump({"next_index": next_index}, file)

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return 0

    with open(PROGRESS_FILE, "r") as file:
        data = json.load(file)

    return data["next_index"]

def main():

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        product_urls = get_retail_product_urls(page, CATEGORY_URL)

        print(f"\nProducts found: {len(product_urls)}")

        cc_numbers = []

        start_index = load_progress()

        if start_index == 0:
            start_new_run()
            start_index = 0

        for i, product_url in enumerate(product_urls[start_index:], start=start_index):
            full_url = BASE_URL + product_url

            print(f"Checking {i + 1}/{len(product_urls)}")

            try:
                page.goto(full_url)

                if is_in_stock_adelaide(page):
                    cc_number = get_cc_number(page)
                    
                    cc_numbers.append(cc_number)
                    save_cc_number(cc_number)
                    save_progress(i + 1)

                    print(f"  In Stock -> CC#: {cc_number}")
                else:
                    print("  Not in stock -> skipping")

            except Exception as e:
                print(f"  ERROR -> {full_url}")
                print(f"  {e}")

        print("\nFinal CC list:")

        for cc_number in cc_numbers:
            print(cc_number)
        
        input("\nPress Enter to close...")
        browser.close()


if __name__ == "__main__":
    main()
