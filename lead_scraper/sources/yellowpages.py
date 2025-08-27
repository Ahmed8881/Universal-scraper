from __future__ import annotations

import urllib.parse
from typing import Dict, List

from bs4 import BeautifulSoup

from .base import BaseDirectoryScraper
from ..utils import normalize_space


class YellowPagesScraper(BaseDirectoryScraper):
    name = "Yellow Pages"

    def build_search_url(self, keyword: str, location: str, page: int) -> str:
        q = urllib.parse.quote_plus(keyword)
        loc = urllib.parse.quote_plus(location)
        return f"https://www.yellowpages.com/search?search_terms={q}&geo_location_terms={loc}&page={page}"

    def parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        # YellowPages commonly uses 'div.result' or 'div.result-list clearfix'
        cards = soup.select("div.result, div.v-card")
        for c in cards:
            # Skip ads
            if c.select_one(".ad, .ad-label, .adBadge"):
                continue
            name_el = c.select_one("a.business-name, a.track-visit-website[aria-label]")
            if not name_el:
                name_el = c.select_one("a.business-name")
            name = normalize_space(name_el.get_text(" ")) if name_el else ""

            website_el = c.select_one("a.track-visit-website, a.website-link")
            website = website_el.get("href") if website_el else ""
            phone_el = c.select_one(".phones, .phone, .dish-phone")
            phone = normalize_space(phone_el.get_text(" ")) if phone_el else ""
            addr_el = c.select_one(".street-address")
            locality_el = c.select_one(".locality")
            address = normalize_space(
                f"{addr_el.get_text(' ') if addr_el else ''} {locality_el.get_text(' ') if locality_el else ''}"
            )

            if not name:
                continue

            rows.append({
                "name": name,
                "website": website,
                "email": "",
                "phone": phone,
                "address": address,
                "socials": "",
            })
        return rows

    def has_next_page(self, soup: BeautifulSoup, page: int) -> bool:
        next_el = soup.select_one("a.next, a.pagination .next")
        return bool(next_el)
