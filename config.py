import os
import sys

BASE_URL = "https://www.centrecom.com.au"

if getattr(sys, "frozen", False):
    # Packaged (PyInstaller) build: CWD-relative paths would resolve inside
    # Program Files, which a normal user can't write to. Use a per-user
    # writable location instead.
    _APP_DATA_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "CentreComTicketGenerator",
    )
    OUTPUT_DIR = os.path.join(_APP_DATA_DIR, "output")
    PROGRESS_FILE = os.path.join(_APP_DATA_DIR, "progress.json")
else:
    OUTPUT_DIR = "output"
    PROGRESS_FILE = "progress.json"

SALE_FILE = os.path.join(OUTPUT_DIR, "sale_cc_numbers.txt")
NOT_SALE_FILE = os.path.join(OUTPUT_DIR, "not_sale_cc_numbers.txt")
FAIL_FILE = os.path.join(OUTPUT_DIR, "failed_products.txt")

CONNECTION_POLL_INTERVAL_MS = 10_000
