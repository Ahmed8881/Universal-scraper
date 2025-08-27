from __future__ import annotations

import urllib.parse
from typing import Dict, List

from bs4 import BeautifulSoup

from .base import BaseDirectoryScraper
from ..utils import normalize_space


class YelpScraper(BaseDirectoryScraper):
    name = "Yelp"

    def build_search_url(self, keyword: str, location: str, page: int) -> str:
        # Yelp paginates with 'start' param in multiples of 10
        q = urllib.parse.quote_plus(keyword)
        loc = urllib.parse.quote_plus(location)
        start = (page - 1) * 10
        return f"https://www.yelp.com/search?find_desc={q}&find_loc={loc}&start={start}"

    def parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        # Yelp uses 'li' with 'class=css-1ywgf60' or similar; use robust selectors
        for li in soup.select("ul li div.container__09f24__mpR8_"):
            # Skip sponsored/ads
            if li.select_one("[data-testid='adLabel']"):
                continue
            name_el = li.select_one("a.css-1m051bw") or li.select_one("a.css-19v1rkv")
            name = normalize_space(name_el.get_text(" ")) if name_el else ""
            # Yelp often hides website; sometimes available via link labeled 'Website'
            website_el = li.find("a", string=lambda s: s and "website" in s.lower())
            website = website_el.get("href") if website_el else ""
            phone_el = li.select_one("p.css-1p9ibgf")
            phone = normalize_space(phone_el.get_text(" ")) if phone_el else ""
            address_el = li.select_one("address")
            address = normalize_space(address_el.get_text(" ")) if address_el else ""

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
        next_el = soup.find("a", string=lambda s: s and "next" in s.lower())
        return bool(next_el)
