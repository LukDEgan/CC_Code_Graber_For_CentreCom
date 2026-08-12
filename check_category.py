from playwright.sync_api import sync_playwright
import json
import os
BASE_URL = "https://www.centrecom.com.au"
CC_FILE = "cc_numbers.txt"
PROGRESS_FILE = "progress.json"
FAIL_FILE = "failed_products.txt"

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
        separator = "&" if "?" in category_url else "?"
        url = f"{category_url}{separator}pagenumber={page_number}"
        print(url)

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

def start_new_run(category_url):
    open(CC_FILE, "w").close()
    open(FAIL_FILE, "w").close()

    save_progress(category_url, 0, 0)

def save_progress(category_url, next_index, cc_count, completed=False):
    data = {
        "category_url": category_url,
        "next_index": next_index,
        "cc_count": cc_count,
        "completed": completed
    }

    with open(PROGRESS_FILE, "w") as file:
        json.dump(data, file)

def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return None

    with open(PROGRESS_FILE, "r") as file:
        data = json.load(file)

    return data

def get_cc_file_count():
    if not os.path.exists(CC_FILE):
        return 0

    with open(CC_FILE, "r") as file:
        return sum(1 for line in file if line.strip())
    
def check_product(page, product_url, retries=2):
    for attempt in range(retries + 1):
        try:
            page.goto(product_url, timeout=30000)

            if is_in_stock_adelaide(page):
                return get_cc_number(page)

            return None

        except Exception as e:
            if attempt == retries:
                with open(FAIL_FILE, "a") as file:
                    file.write(get_cc_number(page) + "\n")

                print(f"Failed permanently: {product_url}")
                return None

            print(f"Retrying {product_url}...")
def main():
    category_url = input("Enter Centre Com category URL: ").strip()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        product_urls = get_retail_product_urls(page, category_url)

        print(f"\nProducts found: {len(product_urls)}")

        cc_numbers = []

        progress = load_progress()

        if progress is None:
            start_new_run(category_url)
            start_index = 0
            cc_count = 0

        elif progress["category_url"] != category_url:
            print("Different category detected. Starting new run.")
            start_new_run(category_url)
            start_index = 0
            cc_count = 0

        elif get_cc_file_count() != progress["cc_count"]:
            print("CC file does not match saved progress. Starting new run.")
            start_new_run(category_url)
            start_index = 0
            cc_count = 0

        elif progress["completed"]:
            print("Previous run completed. Starting a fresh scan.")
            start_new_run(category_url)
            start_index = 0
            cc_count = 0

        else:
            start_index = progress["next_index"]
            cc_count = progress["cc_count"]

            print(f"Resuming from product {start_index}")

        for i, product_url in enumerate(product_urls[start_index:], start=start_index):
            full_url = BASE_URL + product_url

            print(f"Checking {i + 1}/{len(product_urls)}")

            cc_number = check_product(page, full_url)

            if cc_number:
                print(f"    In Stock -> CC:{cc_number}")
                save_cc_number(cc_number)
                cc_count+=1
            else:
                print("Not In Stock -> Skipping")
            save_progress(category_url, i+1, cc_count)

        save_progress(category_url, len(product_urls), cc_count, completed=True)
        print("\nFinal CC list:")

        for cc_number in cc_numbers:
            print(cc_number)
        
        input("\nPress Enter to close...")
        browser.close()


if __name__ == "__main__":
    main()
