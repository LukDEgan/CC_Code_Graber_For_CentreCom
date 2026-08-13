import tkinter as tk
import threading

from playwright.sync_api import sync_playwright

from scraper import scrape_category
from validation import validate_category_url
from progress import load_progress, start_new_run
from tkinter import ttk, messagebox
from validation import validate_category_url, normalise_url


class TicketApp:
    def __init__(self, root):
        self.root = root
        self.stop_event = threading.Event()
        root.title("Centre Com Ticket Generator")
        root.geometry("600x350")

        # URL input
        ttk.Label(root, text="Centre Com Category URL").pack(pady=(20, 5))

        self.url_entry = ttk.Entry(root, width=70)
        self.url_entry.pack(padx=20)
        
        # Start button
        self.start_button = ttk.Button(
            root,
            text="Start",
            command=self.start_scrape
        )
        self.start_button.pack(pady=15)

        # Status
        self.status_label = ttk.Label(
            root,
            text="Ready"
        )
        self.status_label.pack(pady=5)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            root,
            length=450,
            mode="determinate"
        )
        self.progress_bar.pack(pady=10)

        # Product counter
        self.product_label = ttk.Label(
            root,
            text="Products checked: 0 / 0"
        )
        self.product_label.pack()

        # CC counter
        self.cc_label = ttk.Label(
            root,
            text="CC numbers found: 0"
        )
        self.cc_label.pack()

        # Failed Counter
        self.failed_count = 0
        self.failed_label = ttk.Label(
            root,
            text="Failed: 0"
        )
        self.failed_label.pack()

        
        self.stop_button = ttk.Button(
            root,
            text="Stop",
            command=self.stop_scrape,
            state="disabled"
        )
        self.stop_button.pack(pady=5)

    def stop_scrape(self):
        self.stop_event.set()
        self.set_status("Stopping...")

    def reset_display(self):
        self.progress_bar["value"] = 0

        self.product_label.config(
            text="Products checked: 0 / 0"
        )

        self.cc_label.config(
            text="CC numbers found: 0"
        )

        self.failed_label.config(
            text="Failed: 0"
        )

    def start_scrape(self):
        self.stop_event.clear()
        self.root.after(
            0,
            self.start_button.config,
            {"state": "disabled"}
        )
        self.root.after(
            0,
            self.stop_button.config,
            {"state": "normal"}
        )

        category_url = self.url_entry.get().strip()
        category_url = normalise_url(category_url)

        progress = load_progress()
        if progress is None or progress.get("category_url") != category_url:
            self.reset_display()

        if (
            progress
            and progress.get("category_url") == category_url
            and not progress.get("completed", False)
        ):
            self.set_status("Resuming previous run...")

            self.product_label.config(
                text=f"Products checked: {progress.get('next_index', 0)} / ?"
            )

            self.cc_label.config(
                text=f"CC numbers found: {progress.get('cc_count', 0)}"
            )

            self.failed_label.config(
                text=f"Failed: {progress.get('fail_count', 0)}"
            )

        if (
            progress
            and progress.get("category_url") == category_url
            and progress.get("completed", False)
        ):
            run_again = messagebox.askyesno(
                "Category already completed",
                "This category has already been completed.\n\n"
                "Would you like to run it again?"
            )

            if not run_again:
                self.set_status("Cancelled")
                return

            start_new_run(category_url)

        thread = threading.Thread(
            target=self.run_scraper,
            args=(category_url,),
            daemon=True
        )

        thread.start()

    def run_scraper(self, category_url):
        self.root.after(
        0,
        self.start_button.config,
        {"state": "disabled"}
    )

        self.root.after(
            0,
            self.set_status,
            "Starting..."
        )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()

                category_url, error = validate_category_url(
                    page,
                    category_url
                )

                if error:
                    self.root.after(
                        0,
                        self.set_status,
                        error
                    )
                    browser.close()
                    return
                
                scrape_category(
                    page,
                    category_url,
                    on_progress=self.handle_progress,
                    stop_event=self.stop_event
                )

                browser.close()

        except Exception as e:
            self.root.after(
                0,
                self.set_status,
                f"Error: {e}"
            )

        finally:
            self.root.after(
                0,
                self.start_button.config,
                {"state": "normal"}
            )
            
            self.root.after(
                0,
                self.stop_button.config,
                {"state": "disabled"}
            )

    def handle_progress(self, event, data):
        if event == "page":
            self.root.after(
                0,
                self.set_status,
                f"Reading page {data['current']} of {data['total']}"
            )

        elif event == "product":
            self.root.after(
                0,
                self.update_product_progress,
                data["current"],
                data["total"],
                data["cc_count"]
            )

            self.root.after(
                0,
                self.set_status,
                f"Checking product {data['current']} of {data['total']}"
            )

        elif event == "cc_found":
            self.root.after(
                0,
                self.update_cc_count,
                data["cc_count"]
            )

        elif event == "failed":
            self.root.after(
                0,
                self.update_failed_count,
                data["fail_count"]
            )

        elif event == "complete":
            self.root.after(
                0,
                self.finish_scrape,
                data["cc_count"]
            )


    def update_product_progress(self, current, total, cc_count):
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = current

        self.product_label.config(
            text=f"Products checked: {current} / {total}"
        )

        self.cc_label.config(
            text=f"CC numbers found: {cc_count}"
        )


    def update_cc_count(self, count):
        self.cc_label.config(
            text=f"CC numbers found: {count}"
        )

    def update_failed_count(self, count):
        self.failed_label.config(
            text=f"Failed: {count}"
        )

    def finish_scrape(self, cc_count):
        self.progress_bar["value"] = self.progress_bar["maximum"]

        self.status_label.config(
            text=f"Complete — {cc_count} CC numbers found"
        )


    def set_status(self, text):
        self.status_label.config(text=text)

