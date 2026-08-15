import json
import os

from config import FAIL_FILE, NOT_SALE_FILE, OUTPUT_DIR, PROGRESS_FILE, SALE_FILE


def _file_for_status(sale_status):
    return SALE_FILE if sale_status == "sale" else NOT_SALE_FILE


def save_cc_number(cc_number, sale_status):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(_file_for_status(sale_status), "a", encoding="utf-8") as file:
        file.write(cc_number + "\n")


def start_new_run(category_url, sale_filter):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    open(SALE_FILE, "w", encoding="utf-8").close()
    open(NOT_SALE_FILE, "w", encoding="utf-8").close()
    open(FAIL_FILE, "w", encoding="utf-8").close()

    save_progress(category_url, sale_filter, 0, 0, 0)


def clear_opposite_file(sale_filter):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if sale_filter == "On sale":
        open(NOT_SALE_FILE, "w", encoding="utf-8").close()
    elif sale_filter == "Not on sale":
        open(SALE_FILE, "w", encoding="utf-8").close()


PROGRESS_KEYS = {
    "category_url",
    "sale_filter",
    "next_index",
    "cc_count",
    "fail_count",
    "completed",
}


def save_progress(category_url, sale_filter, next_index, cc_count, fail_count, completed=False):
    data = {
        "category_url": category_url,
        "sale_filter": sale_filter,
        "next_index": next_index,
        "cc_count": cc_count,
        "fail_count": fail_count,
        "completed": completed,
    }

    tmp_file = PROGRESS_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    os.replace(tmp_file, PROGRESS_FILE)


def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return None

    try:
        with open(PROGRESS_FILE, encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict) or not PROGRESS_KEYS.issubset(data):
        return None

    return data


def count_lines(filename):
    if not os.path.exists(filename):
        return 0

    with open(filename, encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def get_cc_file_count():
    return count_lines(SALE_FILE) + count_lines(NOT_SALE_FILE)


def load_cc_numbers():
    numbers = []

    for filename in (SALE_FILE, NOT_SALE_FILE):
        if not os.path.exists(filename):
            continue

        with open(filename, encoding="utf-8") as file:
            numbers.extend(line.strip() for line in file if line.strip())

    return numbers
