import json
import os

from config import CC_FILE, FAIL_FILE, PROGRESS_FILE


def save_cc_number(cc_number, filename=CC_FILE):
    with open(filename, "a", encoding="utf-8") as file:
        file.write(cc_number + "\n")


def start_new_run(category_url):
    open(CC_FILE, "w", encoding="utf-8").close()
    open(FAIL_FILE, "w", encoding="utf-8").close()

    save_progress(category_url, 0, 0)


def save_progress(category_url, next_index, cc_count, completed=False):
    data = {
        "category_url": category_url,
        "next_index": next_index,
        "cc_count": cc_count,
        "completed": completed,
    }

    with open(PROGRESS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return None

    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return None


def get_cc_file_count():
    if not os.path.exists(CC_FILE):
        return 0

    with open(CC_FILE, "r", encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def load_cc_numbers():
    if not os.path.exists(CC_FILE):
        return []

    with open(CC_FILE, "r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]
