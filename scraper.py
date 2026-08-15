import os
from urllib.parse import urljoin

import playwright.sync_api

from config import BASE_URL, FAIL_FILE, OUTPUT_DIR
from connectivity import is_online
from progress import (
    get_cc_file_count,
    is_completed,
    load_cc_numbers,
    load_progress,
    progress_matches,
    save_cc_number,
    save_progress,
    start_new_run,
)


class BrowserClosedError(Exception):
    pass


class NetworkDisconnectedError(Exception):
    pass


def report_progress(callback, event, **data):
    if callback:
        callback(event, data)


def is_browser_closed_error(page, error):
    if page.is_closed():
        return True

    return isinstance(error, playwright.sync_api.Error) and "closed" in str(error).lower()


def goto(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as error:
        if is_browser_closed_error(page, error):
            raise BrowserClosedError("Browser window was closed") from error
        if not is_online():
            raise NetworkDisconnectedError("Network connection was lost") from error
        raise

def is_in_stock_adelaide(page):
    adelaide = page.locator(
        "span.prod_store_stock",
        has_text="Adelaide",
    )

    if adelaide.count() == 0:
        return False

    adelaide_row = adelaide.first.locator("..")
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

def build_page_url(category_url, page_number):
    separator = "&" if "?" in category_url else "?"
    return f"{category_url}{separator}pagenumber={page_number}"

def get_retail_product_urls(
    page,
    category_url,
    sale_filter="All items",
    on_progress=None,
    stop_event=None,
):
    product_urls = []

    goto(page, category_url)

    is_deal_page = page.locator("#deal-products-wrap").count()>0
    if is_deal_page:
        total_pages = 1
    else:
        total_pages = get_total_pages(page)

    print(f"Category has {total_pages} pages")
    skipped_products = 0   
    for page_number in range(1, total_pages + 1):
        if stop_event and stop_event.is_set():
            print("Scrape stopped by user.")
            return product_urls, skipped_products

        url = build_page_url(category_url, page_number)

        print(url)
        #print(f"Reading page {page_number}/{total_pages}")
        report_progress(
            on_progress,
            "page",
            current=page_number,
            total=total_pages
        )

        goto(page, url)
        if is_deal_page:
            products = page.locator("div.deal-grid-box")
        else:
            products = page.locator("div.prbox_box")
         
        for i in range(products.count()):
            product = products.nth(i)
            if is_deal_page:
                sale_status = "sale"
            else:
                sale_status = get_sale_status(product)

            print(f"filter: {sale_filter}, Status: {sale_status}")
            if sale_filter == "On sale" and sale_status == "not_sale":
                skipped_products += 1
                continue

            if sale_filter == "Not on sale" and sale_status == "sale":
                skipped_products += 1
                continue

            if is_deal_page:
                href = product.locator("a").first.get_attribute("href")

                if href:
                    product_urls.append({
                        "url": urljoin(BASE_URL, href),
                        "sale_status": "sale"
                    })
            else:
                store_icons = product.locator(".prbox_stockicons .prbox_icon")

                # Your original logic uses the second stock icon as the retail-store icon.
                if store_icons.count() < 2:
                    skipped_products+=1
                    continue

                store_icon = store_icons.nth(1)
                classes = store_icon.get_attribute("class") or ""

                tooltip_locator = store_icon.locator(".tooltip")
                tooltip = tooltip_locator.inner_text() if tooltip_locator.count() else ""

                if (
                    "prbox_green" in classes
                    and "Available at one or more retail stores." in tooltip
                ):
                    href = product.locator("a.prbox_link").get_attribute("href")

                    if href:
                        product_urls.append({"url":urljoin(BASE_URL, href),
                                            "sale_status": sale_status})
                else:
                    skipped_products+=1

    unique_products = []

    seen_urls = set()

    for product in product_urls:
        if product["url"] not in seen_urls:
            seen_urls.add(product["url"])
            unique_products.append(product)

    return unique_products, skipped_products

def get_product_page_sale_status(page):
    if page.locator(".deallabel").count() > 0:
        return "sale"

    return "not_sale"

def check_product(
    page,
    product_url,
    sale_status,
    sale_filter,
    retries=2
):
    for attempt in range(retries + 1):
        try:
            page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=20000
            )

            if sale_status == "unknown":
                sale_status = get_product_page_sale_status(page)

            if sale_filter == "On sale" and sale_status != "sale":
                return None, False, sale_status

            if sale_filter == "Not on sale" and sale_status != "not_sale":
                return None, False, sale_status

            if is_in_stock_adelaide(page):
                return get_cc_number(page), False, sale_status

            return None, False, sale_status

        except Exception as error:
            if is_browser_closed_error(page, error):
                raise BrowserClosedError("Browser window was closed") from error

            if not is_online():
                raise NetworkDisconnectedError("Network connection was lost") from error

            if attempt == retries:
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                with open(FAIL_FILE, "a", encoding="utf-8") as file:
                    file.write(product_url + "\n")

                print(f"Failed permanently: {product_url}")
                print(f"Reason: {error}")

                return None, True, sale_status

            print(f"Retrying {product_url}...")

def get_sale_status(product):
    has_was_price = product.locator(".wasprice").count() > 0
    has_reg_price = product.locator(".regprice").count() > 0
    has_on_sale = product.locator(".onsale").count() > 0
    has_sale_price = product.locator(".saleprice").count() > 0

    if has_on_sale:
        return "sale"

    if has_was_price or has_reg_price:
        print("has a was sale")
        return "sale"

    if has_sale_price:
        return "unknown"

    return "not_sale"

def scrape_category(
    page,
    category_url,
    sale_filter="All items",
    on_progress=None,
    stop_event=None,
):
    # Reset for a genuinely new category/filter (or bail out on an
    # already-completed one) before pagination runs, not after -- otherwise
    # the old run's output file sits there stale, looking live, for the
    # entire time it takes to page through the new category.
    progress = load_progress()

    if not progress_matches(progress, category_url, sale_filter):
        start_new_run(category_url, sale_filter)
        progress = load_progress()

    elif is_completed(progress):
        return

    product_urls, skipped_products = get_retail_product_urls(
        page, category_url, sale_filter, on_progress, stop_event
    )

    if stop_event and stop_event.is_set():
        print("Scrape stopped by user while listing products.")
        return load_cc_numbers()

    print(f"TOTAL PRODUCTS SCANNED: {skipped_products+len(product_urls)}")
    print(f"Found {len(product_urls)} retail-available products")
    print(f"Skipped {skipped_products} products due to grey icon or sale filter")

    report_progress(
        on_progress,
        "listing_complete",
        eligible=len(product_urls),
        skipped=skipped_products,
        category_total=len(product_urls) + skipped_products,
    )

    next_index = progress.get("next_index", 0)
    cc_count = progress.get("cc_count", 0)
    fail_count = progress.get("fail_count", 0)

    # The CC file should contain exactly as many numbers as progress.json says
    # have been successfully saved. If not, the run is no longer trustworthy.
    if get_cc_file_count() != cc_count:
        print("Progress mismatch detected. Restarting category from the beginning.")
        start_new_run(category_url, sale_filter)
        next_index = 0
        cc_count = 0
        fail_count = 0

    # If the category changed enough that the saved index is impossible,
    # restart rather than silently skipping work.
    if next_index < 0 or next_index > len(product_urls):
        print("Saved product index is invalid. Restarting category from the beginning.")
        start_new_run(category_url, sale_filter)
        next_index = 0
        cc_count = 0
        fail_count = 0

    if next_index:
        print(f"Resuming at product {next_index + 1}/{len(product_urls)}")

    for index in range(next_index, len(product_urls)):
        if stop_event and stop_event.is_set():
            print("Scrape stopped by user.")
            return load_cc_numbers()
        # Catch external edits or a previous partial write before continuing.
        if get_cc_file_count() != cc_count:
            print("Progress mismatch detected during run. Restarting category.")
            start_new_run(category_url, sale_filter)
            return scrape_category(
                page,
                category_url,
                sale_filter=sale_filter,
                on_progress=on_progress,
                stop_event=stop_event
            )

        product_data = product_urls[index]
        product_url = product_data["url"]
        product_sale_status = product_data["sale_status"]
        #print(f"Checking product {index + 1}/{len(product_urls)}")
        report_progress(
            on_progress,
            "product",
            current=index + 1,
            total=len(product_urls),
            cc_count=cc_count
        )
        cc_number, failed, resolved_status = check_product(
            page, product_url, product_sale_status, sale_filter
        )
        if failed:
            fail_count += 1

            report_progress(
                on_progress,
                "failed",
                fail_count=fail_count
            )
        if cc_number is not None:
            save_cc_number(cc_number, resolved_status)
            cc_count += 1
            report_progress(
                on_progress,
                "cc_found",
                cc_number=cc_number,
                cc_count=cc_count
            )


        # next_index always points at the NEXT product to process.
        save_progress(
            category_url,
            sale_filter=sale_filter,
            next_index=index + 1,
            cc_count=cc_count,
            fail_count=fail_count,
            completed=False,
        )

    save_progress(
        category_url,
        sale_filter=sale_filter,
        next_index=len(product_urls),
        cc_count=cc_count,
        fail_count=fail_count,
        completed=True,
    )
    report_progress(
        on_progress,
        "complete",
        total=len(product_urls),
        cc_count=cc_count
    )

    #print(f"Finished. Saved {cc_count} Adelaide CC numbers.")
    return load_cc_numbers()
