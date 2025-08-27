from __future__ import annotations

import time
import urllib.parse
from typing import Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from .selenium_utils import build_chrome, wait_css
from ..utils import logger, sleep_random


class YelpSeleniumScraper:
    name = "Yelp (Selenium)"

    def __init__(self, headless: bool = True, delay_seconds: float = 1.0) -> None:
        self.headless = headless
        self.delay_seconds = delay_seconds

    def build_search_url(self, keyword: str, location: str, page: int) -> str:
        q = urllib.parse.quote_plus(keyword)
        loc = urllib.parse.quote_plus(location)
        start = (page - 1) * 10
        return f"https://www.yelp.com/search?find_desc={q}&find_loc={loc}&start={start}"

    def search(self, keyword: str, location: str, max_pages: int = 3) -> List[Dict[str, str]]:
        driver: WebDriver = build_chrome(headless=self.headless)
        rows: List[Dict[str, str]] = []
        try:
            for page in range(1, max_pages + 1):
                url = self.build_search_url(keyword, location, page)
                logger.info(f"Navigating: {url}")
                try:
                    driver.get(url)
                    wait_css(driver, "main ul")
                except Exception as e:
                    logger.exception(f"Failed to load {url}: {e}")
                    continue
                time.sleep(self.delay_seconds)
                sleep_random(1.0, 3.0)

                cards = driver.find_elements(By.CSS_SELECTOR, "main ul li div.container__09f24__mpR8_")
                logger.info(f"Found {len(cards)} cards on {url}")
                if not cards:
                    break
                for card in cards:
                    try:
                        name = card.find_element(By.CSS_SELECTOR, "a.css-1m051bw, a.css-19v1rkv").text.strip()
                    except Exception:
                        continue
                    website = ""
                    try:
                        website_link = card.find_element(By.XPATH, ".//a[translate(text(),'WEBSITE','website')='website']")
                        website = website_link.get_attribute("href") or ""
                    except Exception:
                        pass
                    phone = ""
                    try:
                        phone = card.find_element(By.CSS_SELECTOR, "p.css-1p9ibgf").text.strip()
                    except Exception:
                        pass
                    address = ""
                    try:
                        address = card.find_element(By.CSS_SELECTOR, "address").text.strip()
                    except Exception:
                        pass
                    rows.append({
                        "name": name,
                        "website": website,
                        "email": "",
                        "phone": phone,
                        "address": address,
                        "socials": "",
                    })
                if len(cards) < 5:
                    break
        finally:
            driver.quit()
        return rows
