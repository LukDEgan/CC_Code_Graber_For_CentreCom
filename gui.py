import os
import subprocess
import threading
from tkinter import messagebox, ttk

import sv_ttk
from playwright.sync_api import sync_playwright

from config import CONNECTION_POLL_INTERVAL_MS, NOT_SALE_FILE, OUTPUT_DIR, SALE_FILE
from connectivity import is_online
from file_actions import open_path
from progress import clear_opposite_file, count_lines, load_progress, start_new_run
from scraper import BrowserClosedError, NetworkDisconnectedError, scrape_category
from validation import normalise_url, validate_category_url


class TicketApp:
    def __init__(self, root):
        self.root = root
        self.stop_event = threading.Event()
        self.scrape_thread = None
        self._closed = False

        root.title("Centre Com Ticket Generator")
        root.geometry("640x560")
        root.minsize(800, 700)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        sv_ttk.set_theme("dark")

        container = ttk.Frame(root, padding=24)
        container.pack(fill="both", expand=True)

        self._build_header(container)
        self._build_connection_row(container)
        ttk.Separator(container).pack(fill="x", pady=(16, 20))
        self._build_form(container)
        self._build_actions(container)
        self._build_status(container)
        self._build_stats(container)
        self._build_output_actions(container)
        self._refresh_output_buttons()
        self._refresh_output_summary()
        self._refresh_start_controls()

        self._poll_in_progress = False
        self._connection_check_generation = 0
        self.check_connection()
        self._safe_after(CONNECTION_POLL_INTERVAL_MS, self._poll_connection)

    def on_close(self):
        self._closed = True
        self.stop_event.set()

        if self.scrape_thread and self.scrape_thread.is_alive():
            self.scrape_thread.join(timeout=5)

        self.root.destroy()

    def _safe_after(self, delay, func, *args):
        # Background threads (scrape, connectivity checks) call this to
        # schedule UI updates. Once the window is closing/closed, root.after
        # from another thread can hard-crash Tcl instead of raising a normal
        # Python exception, so skip scheduling entirely.
        if self._closed:
            return

        self.root.after(delay, func, *args)

    def _build_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x")

        ttk.Label(
            header,
            text="Centre Com Ticket Generator",
            font="SunValleySubtitleFont"
        ).pack(side="left")

        self.theme_button = ttk.Button(
            header,
            text="Light mode",
            command=self.toggle_theme
        )
        self.theme_button.pack(side="right")

    def toggle_theme(self):
        sv_ttk.toggle_theme()
        self.theme_button.config(
            text="Light mode" if sv_ttk.get_theme() == "dark" else "Dark mode"
        )

    def _build_connection_row(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(14, 0))

        self.connection_label = ttk.Label(
            row,
            text="● Checking connection...",
            foreground="grey"
        )
        self.connection_label.pack(side="left")

        self.retry_button = ttk.Button(
            row,
            text="Retry connection",
            command=self.check_connection
        )
        self.retry_button.pack(side="right")

    def _build_form(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill="x", pady=(0, 20))
        form.columnconfigure(0, weight=1)

        ttk.Label(
            form, text="Centre Com Category URL", font="SunValleyBodyStrongFont"
        ).grid(row=0, column=0, sticky="w")

        self.url_entry = ttk.Entry(form)
        self.url_entry.grid(row=1, column=0, sticky="ew", pady=(6, 16))
        self.url_entry.bind("<KeyRelease>", lambda event: self._refresh_start_controls())

        ttk.Label(
            form, text="Ticket Type", font="SunValleyBodyStrongFont"
        ).grid(row=2, column=0, sticky="w")

        self.sale_filter = ttk.Combobox(
            form,
            values=["All items", "On sale", "Not on sale"],
            state="readonly",
        )
        self.sale_filter.set("All items")
        self.sale_filter.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.sale_filter.bind("<<ComboboxSelected>>", lambda event: self._refresh_start_controls())

    def _build_actions(self, parent):
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, 20))
        actions.columnconfigure((0, 1, 2), weight=1)

        self.start_button = ttk.Button(
            actions,
            text="Start",
            style="Accent.TButton",
            command=self.start_scrape
        )
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.restart_button = ttk.Button(
            actions,
            text="Restart",
            command=self.restart_scrape,
            state="disabled"
        )
        self.restart_button.grid(row=0, column=1, sticky="ew", padx=8)

        self.stop_button = ttk.Button(
            actions,
            text="Stop",
            command=self.stop_scrape,
            state="disabled"
        )
        self.stop_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    def _build_status(self, parent):
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill="x", pady=(0, 24))

        self.status_label = ttk.Label(
            status_frame, text="Ready", font="SunValleyBodyStrongFont"
        )
        self.status_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(status_frame, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(8, 0))

        self.scan_scope_label = ttk.Label(
            status_frame,
            text="",
            font="SunValleyCaptionFont",
            wraplength=540
        )
        self.scan_scope_label.pack(anchor="w", pady=(6, 0))

    def _build_stats(self, parent):
        stats = ttk.Frame(parent)
        stats.pack(fill="x")
        stats.columnconfigure((0, 1, 2), weight=1)

        self.product_value = self._make_stat_tile(
            stats, "Products checked", column=0
        )
        self.cc_value = self._make_stat_tile(
            stats, "CC numbers found", column=1
        )
        self.failed_value = self._make_stat_tile(
            stats, "Failed", column=2
        )

    def _make_stat_tile(self, parent, caption, column):
        tile = ttk.Frame(parent, padding=12, relief="solid", borderwidth=1)
        tile.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))

        value_label = ttk.Label(tile, text="0", font="SunValleyTitleFont")
        value_label.pack(anchor="w")

        ttk.Label(tile, text=caption, font="SunValleyCaptionFont").pack(anchor="w")

        return value_label

    def _build_output_actions(self, parent):
        section = ttk.Frame(parent)
        section.pack(fill="x", pady=(24, 0))

        ttk.Label(section, text="Output", font="SunValleyBodyStrongFont").pack(anchor="w")

        self.output_url_label = ttk.Label(
            section,
            text="No scan yet",
            font="SunValleyCaptionFont",
            wraplength=540
        )
        self.output_url_label.pack(anchor="w", pady=(4, 0))

        self.output_filter_label = ttk.Label(
            section,
            text="",
            font="SunValleyCaptionFont"
        )
        self.output_filter_label.pack(anchor="w")

        self.output_status_label = ttk.Label(
            section,
            text="",
            font="SunValleyCaptionFont"
        )
        self.output_status_label.pack(anchor="w")

        buttons = ttk.Frame(section)
        buttons.pack(fill="x", pady=(8, 0))
        buttons.columnconfigure((0, 1, 2), weight=1)

        self.copy_sale_button = ttk.Button(
            buttons,
            text="Copy Sale Codes (0)",
            command=self.copy_sale_codes
        )
        self.copy_sale_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.copy_not_sale_button = ttk.Button(
            buttons,
            text="Copy Not On Sale Codes (0)",
            command=self.copy_not_sale_codes
        )
        self.copy_not_sale_button.grid(row=0, column=1, sticky="ew", padx=8)

        self.open_folder_button = ttk.Button(
            buttons,
            text="Open Output Folder",
            command=self.open_output_folder
        )
        self.open_folder_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

    def _refresh_output_buttons(self):
        sale_count = count_lines(SALE_FILE)
        not_sale_count = count_lines(NOT_SALE_FILE)

        self.copy_sale_button.config(
            text=f"Copy Sale Codes ({sale_count})",
            state="normal" if sale_count else "disabled"
        )
        self.copy_not_sale_button.config(
            text=f"Copy Not On Sale Codes ({not_sale_count})",
            state="normal" if not_sale_count else "disabled"
        )

    def _set_output_summary(self, category_url, sale_filter):
        # Sets just the identity of the scan (URL + filter) and clears the
        # completion line -- used when a scan is about to start/resume, before
        # its outcome is known. _refresh_output_summary fills the completion
        # line back in once the run stops, from the state actually on disk.
        if not category_url:
            self.output_url_label.config(text="No scan yet")
            self.output_filter_label.config(text="")
        else:
            self.output_url_label.config(text=category_url)
            self.output_filter_label.config(text=f"Filter: {sale_filter}")

        self.output_status_label.config(text="")

    def _refresh_output_summary(self):
        progress = load_progress()

        sale_count = count_lines(SALE_FILE)
        not_sale_count = count_lines(NOT_SALE_FILE)
        completed = bool(progress and progress.get("completed", False))

        # An incomplete run with no output yet (e.g. a freshly truncated
        # progress.json) has nothing to show or copy -- treat it the same as
        # no prior run at all rather than implying there's something to open.
        if not progress or not (completed or sale_count or not_sale_count):
            self._set_output_summary("", "")
            return

        self._set_output_summary(
            progress.get("category_url", ""), progress.get("sale_filter", "")
        )

        if completed:
            self.output_status_label.config(
                text=f"Scan complete — {sale_count} sale, {not_sale_count} not on sale",
                foreground="green"
            )
        else:
            self.output_status_label.config(
                text=(
                    f"Scan incomplete — stopped partway "
                    f"({sale_count} sale, {not_sale_count} not on sale so far)"
                ),
                foreground="orange"
            )

    def _copy_codes(self, filename, label):
        with open(filename, encoding="utf-8") as file:
            codes = [line.strip() for line in file if line.strip()]

        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(codes))
        self.root.update()

        self.set_status(f"Copied {len(codes)} {label} codes to clipboard")

    def copy_sale_codes(self):
        self._copy_codes(SALE_FILE, "sale")

    def copy_not_sale_codes(self):
        self._copy_codes(NOT_SALE_FILE, "not on sale")

    def open_output_folder(self):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        threading.Thread(
            target=self._open_output_folder_worker,
            daemon=True
        ).start()

    def _open_output_folder_worker(self):
        try:
            open_path(os.path.abspath(OUTPUT_DIR))
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            self._safe_after(0, messagebox.showerror, "Couldn't open folder", str(error))

    def _begin_connection_check(self):
        self._connection_check_generation += 1
        return self._connection_check_generation

    def _apply_connection_result(self, generation, online):
        if generation != self._connection_check_generation:
            return

        self.update_connection_status(online)

    def check_connection(self):
        self.retry_button.config(state="disabled")
        self.connection_label.config(text="● Checking connection...", foreground="grey")
        generation = self._begin_connection_check()

        threading.Thread(
            target=self._check_connection_worker,
            args=(generation,),
            daemon=True
        ).start()

    def _check_connection_worker(self, generation):
        online = is_online()
        self._safe_after(0, self._apply_connection_result, generation, online)

    def update_connection_status(self, online):
        if online:
            self.connection_label.config(text="● Online", foreground="green")
        else:
            self.connection_label.config(
                text="● Offline — no internet connection",
                foreground="red"
            )

        self.retry_button.config(state="normal")

    def _poll_connection(self):
        if not self._poll_in_progress:
            self._poll_in_progress = True
            generation = self._begin_connection_check()
            threading.Thread(
                target=self._poll_connection_worker,
                args=(generation,),
                daemon=True
            ).start()

        self._safe_after(CONNECTION_POLL_INTERVAL_MS, self._poll_connection)

    def _poll_connection_worker(self, generation):
        online = is_online()
        self._safe_after(0, self._on_poll_result, generation, online)

    def _on_poll_result(self, generation, online):
        self._apply_connection_result(generation, online)
        self._poll_in_progress = False

    def stop_scrape(self):
        self.stop_event.set()
        self.set_status("Stopping...")

    def reset_display(self):
        self.progress_bar["value"] = 0
        self.product_value.config(text="0 / 0")
        self.cc_value.config(text="0")
        self.failed_value.config(text="0")
        self.scan_scope_label.config(text="")
        self._refresh_output_buttons()

    def _refresh_start_controls(self):
        if str(self.stop_button.cget("state")) == "normal":
            # A scrape is actively running -- don't let editing the URL/filter
            # fields enable Restart mid-run, which would race with the
            # background thread's own writes to the same output files.
            self.restart_button.config(state="disabled")
            return

        category_url = normalise_url(self.url_entry.get().strip())
        sale_filter = self.sale_filter.get()

        progress = load_progress()
        is_resumable = bool(
            progress
            and progress.get("category_url") == category_url
            and progress.get("sale_filter") == sale_filter
            and not progress.get("completed", False)
        )

        self.start_button.config(text="Resume" if is_resumable else "Start")
        self.restart_button.config(state="normal" if is_resumable else "disabled")

    def restart_scrape(self):
        category_url = normalise_url(self.url_entry.get().strip())
        sale_filter = self.sale_filter.get()

        start_new_run(category_url, sale_filter)
        self.reset_display()
        self._set_output_summary(category_url, sale_filter)

        self.start_scrape()

    def start_scrape(self):
        self.stop_event.clear()

        self.start_button.config(state="disabled")
        self.set_status("Checking connection...")
        generation = self._begin_connection_check()

        threading.Thread(
            target=self._start_scrape_worker,
            args=(generation,),
            daemon=True
        ).start()

    def _start_scrape_worker(self, generation):
        online = is_online()
        self._safe_after(0, self._on_start_connectivity_checked, generation, online)

    def _on_start_connectivity_checked(self, generation, online):
        self._apply_connection_result(generation, online)

        if not online:
            self.set_status(
                "Start failed — no internet connection. Reconnect and click Start again."
            )
            self.start_button.config(state="normal")
            return

        self._begin_scrape()

    def _begin_scrape(self):
        sale_filter = self.sale_filter.get()

        category_url = self.url_entry.get().strip()
        category_url = normalise_url(category_url)

        progress = load_progress()

        if (
            progress
            and progress.get("category_url") == category_url
            and progress.get("sale_filter") == sale_filter
            and not progress.get("completed", False)
        ):
            self.set_status("Resuming previous run...")

            self.product_value.config(
                text=f"{progress.get('next_index', 0)} / ?"
            )

            self.cc_value.config(
                text=str(progress.get('cc_count', 0))
            )

            self.failed_value.config(
                text=str(progress.get('fail_count', 0))
            )

            self._refresh_output_buttons()
            self._set_output_summary(category_url, sale_filter)

        if (
            progress
            and progress.get("category_url") == category_url
            and progress.get("sale_filter") == sale_filter
            and progress.get("completed", False)
        ):
            run_again = messagebox.askyesno(
                "Category already completed",
                "This category has already been completed.\n\n"
                "Would you like to run it again?"
            )

            if not run_again:
                self.set_status("Cancelled")
                self.start_button.config(state="normal")
                return

            start_new_run(category_url, sale_filter)
            self._refresh_output_buttons()
            self._set_output_summary(category_url, sale_filter)
        self._safe_after(
            0,
            self.start_button.config,
            {"state": "disabled"}
        )
        self._safe_after(
            0,
            self.restart_button.config,
            {"state": "disabled"}
        )
        self._safe_after(
            0,
            self.stop_button.config,
            {"state": "normal"}
        )
        self.scrape_thread = threading.Thread(
            target=self.run_scraper,
            args=(category_url, sale_filter),
            daemon=True
        )

        self.scrape_thread.start()

    def run_scraper(self, category_url, sale_filter):
        self._safe_after(
        0,
        self.start_button.config,
        {"state": "disabled"}
    )

        self._safe_after(
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
                    self._safe_after(
                        0,
                        self.set_status,
                        error
                    )
                    browser.close()
                    return

                progress = load_progress()
                if (
                    progress is None
                    or progress.get("category_url") != category_url
                    or progress.get("sale_filter") != sale_filter
                ):
                    clear_opposite_file(sale_filter)
                    self._safe_after(0, self.reset_display)
                    self._safe_after(0, self._set_output_summary, category_url, sale_filter)

                scrape_category(
                    page,
                    category_url,
                    sale_filter,
                    on_progress=self.handle_progress,
                    stop_event=self.stop_event
                )

                if self.stop_event.is_set():
                    finished_progress = load_progress()
                    if not (finished_progress and finished_progress.get("completed", False)):
                        self._safe_after(0, self.set_status, "Stopped")

                browser.close()

        except BrowserClosedError:
            self._safe_after(
                0,
                self.set_status,
                "Stopped — the browser window was closed. Click Start to resume."
            )

        except NetworkDisconnectedError:
            self._safe_after(0, self.update_connection_status, False)
            self._safe_after(
                0,
                self.set_status,
                "Stopped — network connection was lost. Reconnect and click Start to resume."
            )

        except Exception as e:
            self._safe_after(
                0,
                self.set_status,
                f"Error: {e}"
            )

        finally:
            self._safe_after(
                0,
                self.start_button.config,
                {"state": "normal"}
            )

            self._safe_after(
                0,
                self.stop_button.config,
                {"state": "disabled"}
            )

            self._safe_after(0, self._refresh_start_controls)
            self._safe_after(0, self._refresh_output_summary)

    def handle_progress(self, event, data):
        if event == "page":
            self._safe_after(
                0,
                self.set_status,
                f"Reading page {data['current']} of {data['total']}"
            )

        elif event == "listing_complete":
            self._safe_after(
                0,
                self.update_scan_scope,
                data["eligible"],
                data["skipped"],
                data["category_total"]
            )

        elif event == "product":
            self._safe_after(
                0,
                self.update_product_progress,
                data["current"],
                data["total"],
                data["cc_count"]
            )

            self._safe_after(
                0,
                self.set_status,
                f"Checking product {data['current']} of {data['total']}"
            )

        elif event == "cc_found":
            self._safe_after(
                0,
                self.update_cc_count,
                data["cc_count"]
            )

        elif event == "failed":
            self._safe_after(
                0,
                self.update_failed_count,
                data["fail_count"]
            )

        elif event == "complete":
            self._safe_after(
                0,
                self.finish_scrape,
                data["cc_count"]
            )


    def update_scan_scope(self, eligible, skipped, category_total):
        if skipped:
            self.scan_scope_label.config(
                text=(
                    f"{category_total} products found in this category — {eligible} are in "
                    f"stock at Adelaide retail (and match the filter) and will be checked; "
                    f"{skipped} skipped (not in stock at Adelaide retail, or excluded by the "
                    f"filter)."
                )
            )
        else:
            self.scan_scope_label.config(
                text=f"All {category_total} products in this category will be checked."
            )

    def update_product_progress(self, current, total, cc_count):
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = current

        self.product_value.config(text=f"{current} / {total}")
        self.cc_value.config(text=str(cc_count))
        self._refresh_output_buttons()


    def update_cc_count(self, count):
        self.cc_value.config(text=str(count))
        self._refresh_output_buttons()

    def update_failed_count(self, count):
        self.failed_value.config(text=str(count))

    def finish_scrape(self, cc_count):
        self.progress_bar["value"] = self.progress_bar["maximum"]
        self._refresh_output_buttons()

        self.status_label.config(
            text=f"Complete — {cc_count} CC numbers found"
        )


    def set_status(self, text):
        self.status_label.config(text=text)
