from __future__ import annotations

import io
import json
from threading import Thread
from typing import List, Dict

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file

from lead_scraper.exporter import export_to_csv, export_to_excel
from lead_scraper.utils import logger, score_lead, deduplicate_records
from lead_scraper.sources.google_maps import GoogleMapsScraper
from lead_scraper.sources.yelp_selenium import YelpSeleniumScraper
from lead_scraper.sources.yelp import YelpScraper
from lead_scraper.sources.yellowpages import YellowPagesScraper
from lead_scraper.sources.generic_html import GenericHTMLScraper
from lead_scraper.sources.generic_selenium import GenericSeleniumScraper
from lead_scraper.details import enrich_with_website_details
import asyncio

bp = Blueprint('main', __name__)

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"


def login_required(view):
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


@bp.route("/", methods=["GET"]) 
def root():
    if session.get("user"):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login"))


@bp.route("/login", methods=["GET", "POST"]) 
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["user"] = username
            return redirect(url_for("main.dashboard"))
        flash("Invalid credentials", "error")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.route("/dashboard", methods=["GET"]) 
@login_required
def dashboard():
    leads = session.get("leads") or []
    return render_template("dashboard.html", leads=leads)


def run_scrape_async(params: Dict):
    try:
        keyword = params.get("keyword", "").strip()
        location = params.get("location", "").strip()
        target_url = params.get("target_url", "").strip()
        headless = params.get("headless", True)
        max_pages = int(params.get("max_pages", 5))
        concurrency = int(params.get("concurrency", 10))
        delay = float(params.get("delay", 0.5))

        selected = []
        if params.get("src_gmaps"):
            selected.append(GoogleMapsScraper(headless=headless))
        if params.get("src_yelp_s"):
            selected.append(YelpSeleniumScraper(headless=headless))
        if params.get("src_yelp_r"):
            selected.append(YelpScraper())
        if params.get("src_yp"):
            selected.append(YellowPagesScraper())
        if params.get("src_gen_s") and target_url:
            selected.append(GenericSeleniumScraper(headless=headless))
        if params.get("src_gen_h") and target_url:
            selected.append(GenericHTMLScraper())

        all_rows: List[Dict[str, str]] = []
        for scraper in selected:
            if isinstance(scraper, GenericSeleniumScraper) and target_url:
                rows = scraper.search(
                    start_url=target_url,
                    locate_cards_css="div[role='article'], .result, .v-card, .container__09f24__mpR8_",
                    parse_card=lambda el: {
                        "name": (el.text or "").split("\n")[0],
                        "website": "",
                        "email": "",
                        "phone": "",
                        "address": "",
                        "socials": "",
                    },
                    next_button_css="a.next, a[aria-label='Next']",
                    max_pages=max_pages,
                )
            elif isinstance(scraper, GenericHTMLScraper) and target_url:
                rows = scraper.search(
                    start_url=target_url,
                    select_cards="div[role='article'], .result, .v-card, li",
                    parse_card=lambda s: {
                        "name": (s.get_text(" ").strip().split("\n")[0]),
                        "website": "",
                        "email": "",
                        "phone": "",
                        "address": "",
                        "socials": "",
                    },
                    next_selector="a.next, a[aria-label='Next']",
                    max_pages=max_pages,
                )
            else:
                try:
                    rows = scraper.search(keyword, location, max_pages=max_pages)  # type: ignore[arg-type]
                except TypeError:
                    rows = scraper.search(keyword, location)
            for r in rows:
                r["source"] = getattr(scraper, "name", type(scraper).__name__)
                r["status"] = r.get("status", "New")
                r["notes"] = r.get("notes", "")
                r["score"] = score_lead(r)
            all_rows.extend(rows)

        all_rows = deduplicate_records(all_rows)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        enriched = loop.run_until_complete(
            enrich_with_website_details(all_rows, concurrency=concurrency, delay_seconds=delay)
        )
        loop.close()
        for r in enriched:
            r["score"] = score_lead(r)
        session["leads"] = enriched
    except Exception as e:
        logger.exception(f"Flask scrape error: {e}")
        session["leads"] = []


@bp.route("/start", methods=["POST"]) 
@login_required
def start_scrape():
    params = {
        "keyword": request.form.get("keyword", ""),
        "location": request.form.get("location", ""),
        "target_url": request.form.get("target_url", ""),
        "headless": request.form.get("headless") == "on",
        "max_pages": request.form.get("max_pages", 5),
        "concurrency": request.form.get("concurrency", 10),
        "delay": request.form.get("delay", 0.5),
        "src_gmaps": bool(request.form.get("src_gmaps")),
        "src_yelp_s": bool(request.form.get("src_yelp_s")),
        "src_yelp_r": bool(request.form.get("src_yelp_r")),
        "src_yp": bool(request.form.get("src_yp")),
        "src_gen_s": bool(request.form.get("src_gen_s")),
        "src_gen_h": bool(request.form.get("src_gen_h")),
    }
    t = Thread(target=run_scrape_async, args=(params,))
    t.daemon = True
    t.start()
    flash("Scraping started. Refresh the dashboard after a bit.", "info")
    return redirect(url_for("main.dashboard"))


@bp.route("/export/csv") 
@login_required
def export_csv_route():
    rows = session.get("leads") or []
    if not rows:
        flash("No data to export", "warning")
        return redirect(url_for("main.dashboard"))
    bio = io.BytesIO()
    # Use pandas writer in memory
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(bio, index=False, encoding="utf-8-sig")
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="leads.csv", mimetype="text/csv")


@bp.route("/export/excel") 
@login_required
def export_excel_route():
    rows = session.get("leads") or []
    if not rows:
        flash("No data to export", "warning")
        return redirect(url_for("main.dashboard"))
    bio = io.BytesIO()
    import pandas as pd
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name="leads.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
