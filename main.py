from playwright.sync_api import sync_playwright

from scraper import scrape_category
from validation import handle_input

def progress_update(event, data):
    print("EVENT:", event, data)
    
def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            category_url = handle_input(page)
            products = scrape_category(page, category_url, progress_update)

            #print(f"Run complete: {len(products)} CC numbers saved.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
