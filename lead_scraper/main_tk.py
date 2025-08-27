import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict
import os
import logging

from .sources.yellowpages import YellowPagesScraper
from .sources.yelp import YelpScraper
from .sources.yelp_selenium import YelpSeleniumScraper
from .sources.google_maps import GoogleMapsScraper
from .sources.generic_html import GenericHTMLScraper
from .sources.generic_selenium import GenericSeleniumScraper
from .exporter import export_to_csv, export_to_excel, export_selected
from .utils import deduplicate_records, score_lead, logger, is_business_email


class TkTextLogHandler:
    def __init__(self, text_widget: tk.Text) -> None:
        self.text_widget = text_widget

    def emit(self, record) -> None:  # type: ignore[override]
        msg = logger.handlers[0].format(record) if logger.handlers else f"{record.levelname}: {record.getMessage()}\n"
        self.text_widget.after(0, lambda: (self.text_widget.insert(tk.END, msg + "\n"), self.text_widget.see(tk.END)))


class ScraperApp:
    """Simple Tkinter application to run directory scrapers and export results."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Lead Generation Scraper")
        self.root.geometry("1080x860")

        self.keyword_var = tk.StringVar()
        self.location_var = tk.StringVar()
        self.target_url_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.IntVar(value=0)
        self.headless_var = tk.BooleanVar(value=True)
        self.max_pages_var = tk.IntVar(value=5)
        self.concurrency_var = tk.IntVar(value=10)
        self.delay_var = tk.DoubleVar(value=0.5)
        self.filter_var = tk.StringVar()
        self.domain_filter_var = tk.StringVar()
        self.require_business_email_var = tk.BooleanVar(value=False)

        self.source_vars = {
            "Google Maps": tk.BooleanVar(value=True),
            "Yelp (Selenium)": tk.BooleanVar(value=True),
            "Yelp (Requests)": tk.BooleanVar(value=False),
            "Yellow Pages": tk.BooleanVar(value=False),
            "Generic (Selenium)": tk.BooleanVar(value=False),
            "Generic (HTML)": tk.BooleanVar(value=False),
        }

        self._results: List[Dict[str, str]] = []
        self._scrape_thread: threading.Thread | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 8}

        frm = ttk.Frame(self.root)
        frm.pack(fill=tk.BOTH, expand=True)

        row_url = ttk.Frame(frm)
        row_url.pack(fill=tk.X, **pad)
        ttk.Label(row_url, text="Target URL (optional):").pack(side=tk.LEFT)
        ttk.Entry(row_url, textvariable=self.target_url_var, width=70).pack(side=tk.LEFT, padx=8)

        row = ttk.Frame(frm)
        row.pack(fill=tk.X, **pad)
        ttk.Label(row, text="Business keyword:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.keyword_var, width=30).pack(side=tk.LEFT, padx=8)

        row2 = ttk.Frame(frm)
        row2.pack(fill=tk.X, **pad)
        ttk.Label(row2, text="Location:").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.location_var, width=30).pack(side=tk.LEFT, padx=39)

        # Settings
        row_settings = ttk.LabelFrame(frm, text="Settings")
        row_settings.pack(fill=tk.X, **pad)
        ttk.Label(row_settings, text="Max pages").pack(side=tk.LEFT)
        ttk.Spinbox(row_settings, from_=1, to=50, textvariable=self.max_pages_var, width=5).pack(side=tk.LEFT, padx=6)
        ttk.Label(row_settings, text="Concurrency").pack(side=tk.LEFT)
        ttk.Spinbox(row_settings, from_=1, to=50, textvariable=self.concurrency_var, width=5).pack(side=tk.LEFT, padx=6)
        ttk.Label(row_settings, text="Delay (s)").pack(side=tk.LEFT)
        ttk.Spinbox(row_settings, from_=0, to=5, increment=0.1, textvariable=self.delay_var, width=6).pack(side=tk.LEFT, padx=6)

        # Filters
        row_filters = ttk.LabelFrame(frm, text="Filters")
        row_filters.pack(fill=tk.X, **pad)
        ttk.Label(row_filters, text="Domain filter (contains)").pack(side=tk.LEFT)
        ttk.Entry(row_filters, textvariable=self.domain_filter_var, width=30).pack(side=tk.LEFT, padx=6)
        ttk.Checkbutton(row_filters, text="Require business email (exclude free email domains)", variable=self.require_business_email_var).pack(side=tk.LEFT, padx=10)

        # Source selection
        row_sources = ttk.LabelFrame(frm, text="Sources")
        row_sources.pack(fill=tk.X, **pad)
        for name, var in self.source_vars.items():
            ttk.Checkbutton(row_sources, text=name, variable=var).pack(side=tk.LEFT, padx=8)

        # Headless toggle
        row_headless = ttk.Frame(frm)
        row_headless.pack(fill=tk.X, **pad)
        ttk.Checkbutton(row_headless, text="Run headless", variable=self.headless_var).pack(side=tk.LEFT)

        row3 = ttk.Frame(frm)
        row3.pack(fill=tk.X, **pad)
        self.start_btn = ttk.Button(row3, text="Start Scraping", command=self.start_scraping)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(row3, text="Stop", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        row4 = ttk.Frame(frm)
        row4.pack(fill=tk.X, **pad)
        ttk.Label(row4, textvariable=self.status_var).pack(side=tk.LEFT)

        row5 = ttk.Frame(frm)
        row5.pack(fill=tk.X, **pad)
        self.progress = ttk.Progressbar(row5, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X)

        # Progress log
        log_frame = ttk.LabelFrame(frm, text="Progress Log")
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=8)
        self.log_text = tk.Text(log_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        # attach handler
        self.log_handler = TkTextLogHandler(self.log_text)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
        import logging as _logging
        _logging.getLogger("lead_scraper").addHandler(handler)
        _logging.getLogger("lead_scraper").addHandler(self.log_handler)  # type: ignore[arg-type]

        # Filter bar
        row_filter = ttk.Frame(frm)
        row_filter.pack(fill=tk.X, **pad)
        self.filter_var.set("")
        ttk.Label(row_filter, text="Filter (name/website/email/phone/address):").pack(side=tk.LEFT)
        ttk.Entry(row_filter, textvariable=self.filter_var, width=40).pack(side=tk.LEFT, padx=8)
        ttk.Button(row_filter, text="Apply", command=self.apply_filter).pack(side=tk.LEFT)
        ttk.Button(row_filter, text="Clear", command=self.clear_filter).pack(side=tk.LEFT, padx=6)

        # Results table with extra columns
        columns = ("name", "website", "email", "phone", "address", "socials", "source", "score", "status", "notes")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings", height=18, selectmode="extended")
        for col, text, width in [
            ("name", "Business Name", 200),
            ("website", "Website", 200),
            ("email", "Email", 180),
            ("phone", "Phone", 120),
            ("address", "Address", 240),
            ("socials", "Socials", 200),
            ("source", "Source", 120),
            ("score", "Score", 60),
            ("status", "Status", 100),
            ("notes", "Notes", 200),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Inline edit controls for status and notes
        row_edit = ttk.Frame(frm)
        row_edit.pack(fill=tk.X, **pad)
        ttk.Button(row_edit, text="Set Status: New", command=lambda: self.bulk_set_status("New")).pack(side=tk.LEFT)
        ttk.Button(row_edit, text="Set Status: Contacted", command=lambda: self.bulk_set_status("Contacted")).pack(side=tk.LEFT, padx=6)
        ttk.Button(row_edit, text="Set Status: Qualified", command=lambda: self.bulk_set_status("Qualified")).pack(side=tk.LEFT, padx=6)
        ttk.Button(row_edit, text="Set Status: Not Interested", command=lambda: self.bulk_set_status("Not Interested")).pack(side=tk.LEFT, padx=6)
        ttk.Button(row_edit, text="Add Note", command=self.add_note_dialog).pack(side=tk.LEFT, padx=12)

        # Export buttons
        row6 = ttk.Frame(frm)
        row6.pack(fill=tk.X, **pad)
        ttk.Button(row6, text="Export CSV (All)", command=self.export_csv).pack(side=tk.LEFT)
        ttk.Button(row6, text="Export Excel (All)", command=self.export_excel).pack(side=tk.LEFT, padx=8)
        ttk.Button(row6, text="Export CSV (Selected)", command=self.export_csv_selected).pack(side=tk.LEFT, padx=16)
        ttk.Button(row6, text="Export Excel (Selected)", command=self.export_excel_selected).pack(side=tk.LEFT)

    def start_scraping(self) -> None:
        keyword = self.keyword_var.get().strip()
        location = self.location_var.get().strip()
        target_url = self.target_url_var.get().strip()
        if not (keyword or target_url):
            messagebox.showerror("Input Error", "Provide either a target URL or a keyword+location.")
            return

        if not any(v.get() for v in self.source_vars.values()):
            messagebox.showerror("Select Sources", "Please select at least one source.")
            return

        self._results = []
        self.tree.delete(*self.tree.get_children())
        self.status_var.set("Starting...")
        self.progress_var.set(0)
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        self._scrape_thread = threading.Thread(
            target=self._run_scrape,
            args=(
                keyword,
                location,
                target_url,
                self.headless_var.get(),
                int(self.max_pages_var.get()),
                int(self.concurrency_var.get()),
                float(self.delay_var.get()),
            ),
            daemon=True,
        )
        self._scrape_thread.start()

    def stop_scraping(self) -> None:
        messagebox.showinfo("Stop", "Stopping after current requests finish.")
        self._stop_flag = True

    def _update_progress(self, percent: int, status: str) -> None:
        self.progress_var.set(percent)
        self.status_var.set(status)

    def _append_results(self, rows: List[Dict[str, str]]) -> None:
        # apply domain filter and business email filter on insert
        domain_filter = (self.domain_filter_var.get() or "").lower().strip()
        require_business_email = self.require_business_email_var.get()
        for r in rows:
            if domain_filter and domain_filter not in (r.get("website") or "").lower():
                continue
            if require_business_email:
                emails = [e.strip() for e in (r.get("email") or "").split(",") if e.strip()]
                if emails and not any(is_business_email(e) for e in emails):
                    continue
            self.tree.insert("", tk.END, values=(
                r.get("name", ""),
                r.get("website", ""),
                r.get("email", ""),
                r.get("phone", ""),
                r.get("address", ""),
                r.get("socials", ""),
                r.get("source", ""),
                r.get("score", ""),
                r.get("status", ""),
                r.get("notes", ""),
            ))
        self._results.extend(rows)

    def _autosave(self, rows: List[Dict[str, str]]) -> None:
        if not rows:
            return
        os.makedirs(".autosave", exist_ok=True)
        path = os.path.join(".autosave", "leads_autosave.csv")
        try:
            export_to_csv(rows, path)
            logger.info(f"Autosaved {len(rows)} rows to {path}")
        except Exception as e:
            logger.warning(f"Autosave failed: {e}")

    def _run_scrape(self, keyword: str, location: str, target_url: str, headless: bool, max_pages: int, concurrency: int, delay: float) -> None:
        self._stop_flag = False
        try:
            selected = []
            if self.source_vars["Google Maps"].get():
                selected.append(GoogleMapsScraper(headless=headless))
            if self.source_vars["Yelp (Selenium)"].get():
                selected.append(YelpSeleniumScraper(headless=headless))
            if self.source_vars["Yelp (Requests)"].get():
                selected.append(YelpScraper())
            if self.source_vars["Yellow Pages"].get():
                selected.append(YellowPagesScraper())
            if self.source_vars["Generic (Selenium)"].get() and target_url:
                selected.append(GenericSeleniumScraper(headless=headless))
            if self.source_vars["Generic (HTML)"].get() and target_url:
                selected.append(GenericHTMLScraper())

            all_rows: List[Dict[str, str]] = []
            for idx, scraper in enumerate(selected, start=1):
                if self._stop_flag:
                    break
                self._update_progress(int((idx - 1) / max(1, len(selected)) * 40), f"Scraping {getattr(scraper, 'name', type(scraper).__name__)}...")
                if isinstance(scraper, GenericSeleniumScraper) and target_url:
                    rows = scraper.search(
                        start_url=target_url,
                        locate_cards_css="div[role='article'], .result, .v-card, .container__09f24__mpR8_",
                        parse_card=lambda el: self._parse_generic_card(el),
                        next_button_css="a.next, a[aria-label='Next']",
                        max_pages=max_pages,
                    )
                elif isinstance(scraper, GenericHTMLScraper) and target_url:
                    rows = scraper.search(
                        start_url=target_url,
                        select_cards="div[role='article'], .result, .v-card, li",
                        parse_card=lambda s: self._parse_generic_card_soup(s),
                        next_selector="a.next, a[aria-label='Next']",
                        max_pages=max_pages,
                    )
                elif hasattr(scraper, "search"):
                    try:
                        rows = scraper.search(keyword, location, max_pages=max_pages)  # type: ignore[arg-type]
                    except TypeError:
                        rows = scraper.search(keyword, location)
                else:
                    rows = []
                for r in rows:
                    r["source"] = getattr(scraper, "name", type(scraper).__name__)
                    r["status"] = r.get("status", "New")
                    r["notes"] = r.get("notes", "")
                    r["score"] = score_lead(r)
                all_rows.extend(rows)
                self._append_results(rows)
                self._autosave(all_rows)

            self._update_progress(45, "Deduplicating...")
            all_rows = deduplicate_records(all_rows)

            self._update_progress(50, "Enriching websites for emails/phones...")
            from .details import enrich_with_website_details
            enriched = asyncio.run(enrich_with_website_details(all_rows, concurrency=concurrency, delay_seconds=delay))

            for r in enriched:
                r["score"] = score_lead(r)

            self.tree.delete(*self.tree.get_children())
            self._results = []
            self._append_results(enriched)
            self._autosave(enriched)
            self._update_progress(95, "Finalizing...")

            self.status_var.set(f"Done. {len(enriched)} leads found.")
            self.progress_var.set(100)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", f"An error occurred: {exc}")
        finally:
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)

    def _parse_generic_card(self, el) -> Dict[str, str]:
        # Try common selectors from directories; fallback to text
        def safe(css: str) -> str:
            try:
                return el.find_element_by_css_selector(css).text.strip()
            except Exception:
                try:
                    return el.find_element("css selector", css).text.strip()
                except Exception:
                    return ""
        def href(css: str) -> str:
            try:
                return el.find_element("css selector", css).get_attribute("href") or ""
            except Exception:
                return ""
        name = safe("a, h3, h4")
        website = href("a[href^='http']")
        phone = safe(".phone, [data-phone], a[href^='tel:']")
        addr = safe("address, .address")
        return {"name": name, "website": website, "email": "", "phone": phone, "address": addr, "socials": ""}

    def _parse_generic_card_soup(self, soup) -> Dict[str, str]:
        def textsel(sel: str) -> str:
            el = soup.select_one(sel)
            return el.get_text(" ").strip() if el else ""
        def hrefsel(sel: str) -> str:
            el = soup.select_one(sel)
            return el.get("href", "").strip() if el else ""
        name = textsel("a, h3, h4")
        website = hrefsel("a[href^='http']")
        phone = textsel(".phone, .phones, a[href^='tel:']")
        addr = textsel("address, .address, .street-address")
        return {"name": name, "website": website, "email": "", "phone": phone, "address": addr, "socials": ""}

    def export_csv(self) -> None:
        if not self._results:
            messagebox.showinfo("No Data", "There are no results to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", ".csv")])
        if not path:
            return
        export_to_csv(self._results, path)
        messagebox.showinfo("Saved", f"Saved to {path}")

    def export_excel(self) -> None:
        if not self._results:
            messagebox.showinfo("No Data", "There are no results to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", ".xlsx")])
        if not path:
            return
        export_to_excel(self._results, path)
        messagebox.showinfo("Saved", f"Saved to {path}")

    def export_csv_selected(self) -> None:
        if not self._results:
            messagebox.showinfo("No Data", "There are no results to export.")
            return
        selected_rows = export_selected(self.tree, self._results)
        if not selected_rows:
            messagebox.showinfo("No Selection", "No rows selected.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", ".csv")])
        if not path:
            return
        export_to_csv(selected_rows, path)
        messagebox.showinfo("Saved", f"Saved to {path}")

    def export_excel_selected(self) -> None:
        if not self._results:
            messagebox.showinfo("No Data", "There are no results to export.")
            return
        selected_rows = export_selected(self.tree, self._results)
        if not selected_rows:
            messagebox.showinfo("No Selection", "No rows selected.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", ".xlsx")])
        if not path:
            return
        export_to_excel(selected_rows, path)
        messagebox.showinfo("Saved", f"Saved to {path}")

    def apply_filter(self) -> None:
        query = (self.filter_var.get() or "").lower().strip()
        self.tree.delete(*self.tree.get_children())
        if not query:
            self._append_results(self._results)
            return
        filtered = []
        for r in self._results:
            hay = " ".join([
                r.get("name", ""), r.get("website", ""), r.get("email", ""), r.get("phone", ""), r.get("address", ""),
            ]).lower()
            if query in hay:
                filtered.append(r)
        self._append_results(filtered)

    def clear_filter(self) -> None:
        self.filter_var.set("")
        self.tree.delete(*self.tree.get_children())
        self._append_results(self._results)

    def bulk_set_status(self, status: str) -> None:
        changed = 0
        for item in self.tree.selection():
            values = list(self.tree.item(item, "values"))
            values[8] = status  # status column
            self.tree.item(item, values=values)
            # update in _results
            name, website = values[0], values[1]
            for r in self._results:
                if r.get("name") == name and r.get("website") == website:
                    r["status"] = status
                    changed += 1
                    break
        if changed:
            messagebox.showinfo("Updated", f"Updated status for {changed} leads.")

    def add_note_dialog(self) -> None:
        items = self.tree.selection()
        if not items:
            messagebox.showinfo("No Selection", "Select one or more rows first.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Add Note")
        ttk.Label(dlg, text="Note:").pack(padx=10, pady=6)
        note_var = tk.StringVar()
        ttk.Entry(dlg, textvariable=note_var, width=60).pack(padx=10, pady=6)
        def save_note():
            note = note_var.get().strip()
            changed = 0
            for item in items:
                values = list(self.tree.item(item, "values"))
                values[9] = note  # notes column
                self.tree.item(item, values=values)
                name, website = values[0], values[1]
                for r in self._results:
                    if r.get("name") == name and r.get("website") == website:
                        r["notes"] = note
                        changed += 1
                        break
            dlg.destroy()
            if changed:
                messagebox.showinfo("Saved", f"Added notes to {changed} leads.")
        ttk.Button(dlg, text="Save", command=save_note).pack(padx=10, pady=8)


def main() -> None:
    root = tk.Tk()
    app = ScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
