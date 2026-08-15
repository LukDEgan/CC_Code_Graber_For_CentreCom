import os

BASE_URL = "https://www.centrecom.com.au"

OUTPUT_DIR = "output"
SALE_FILE = os.path.join(OUTPUT_DIR, "sale_cc_numbers.txt")
NOT_SALE_FILE = os.path.join(OUTPUT_DIR, "not_sale_cc_numbers.txt")
FAIL_FILE = os.path.join(OUTPUT_DIR, "failed_products.txt")

PROGRESS_FILE = "progress.json"

CONNECTION_POLL_INTERVAL_MS = 10_000
