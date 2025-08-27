from __future__ import annotations

import time
import urllib.parse
from typing import Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from .selenium_utils import build_chrome, wait_css
from ..utils import logger, sleep_random


class GoogleMapsScraper:
    name = "Google Maps"

    def __init__(self, headless: bool = True, delay_seconds: float = 1.0) -> None:
        self.headless = headless
        self.delay_seconds = delay_seconds

    def build_search_url(self, keyword: str, location: str) -> str:
        q = urllib.parse.quote_plus(f"{keyword} in {location}")
        # Force English interface for selector stability
        return f"https://www.google.com/maps/search/{q}?hl=en"

    def _handle_consent(self, driver: WebDriver) -> None:
        # Try common consent/agree buttons
        candidates = [
            (By.CSS_SELECTOR, "button[aria-label='Accept all']"),
            (By.CSS_SELECTOR, "button[aria-label='I agree']"),
            (By.XPATH, "//button//*[contains(text(),'I agree')]/ancestor::button"),
            (By.XPATH, "//button//*[contains(text(),'Accept all')]/ancestor::button"),
            (By.ID, "introAgreeButton"),
        ]
        for by, sel in candidates:
            try:
                btn = driver.find_element(by, sel)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
                logger.info("Clicked consent banner")
                return
            except Exception:
                continue

    def _scroll_results(self, driver: WebDriver, feed, rounds: int) -> None:
        # Use JS scrollTop and END key presses to load more results
        for i in range(rounds):
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].offsetHeight;", feed)
            try:
                feed.send_keys(Keys.END)
            except Exception:
                pass
            time.sleep(self.delay_seconds)
            sleep_random(1.0, 2.0)
            cards = driver.find_elements(By.CSS_SELECTOR, "div[role='feed'] .Nv2PK")
            logger.info(f"Scroll {i+1}/{rounds}: {len(cards)} cards visible")

    def _extract_details_panel(self, driver: WebDriver) -> Dict[str, str]:
        website = ""
        phone = ""
        address = ""
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, "a[data-item-id]")
            for b in buttons:
                dataid = (b.get_attribute("data-item-id") or "").lower()
                if "authority" in dataid:
                    website = b.get_attribute("href") or website
                if "phone" in dataid:
                    phone = b.get_attribute("aria-label") or phone
        except Exception:
            pass
        try:
            addr_el = driver.find_element(By.CSS_SELECTOR, "button[data-item-id='address']")
            address = addr_el.get_attribute("aria-label") or ""
        except Exception:
            pass
        return {"website": website, "phone": phone, "address": address}

    def search(self, keyword: str, location: str, max_pages: int = 3) -> List[Dict[str, str]]:
        driver: WebDriver = build_chrome(headless=self.headless)
        rows: List[Dict[str, str]] = []
        try:
            url = self.build_search_url(keyword, location)
            logger.info(f"Navigating: {url}")
            try:
                driver.get(url)
                # Consent banner if present
                time.sleep(1.0)
                self._handle_consent(driver)
                wait_css(driver, "div[role='feed']")
            except TimeoutException as e:
                logger.exception(f"Failed to load results container: {e}")
                return rows
            except Exception as e:
                logger.exception(f"Failed to load {url}: {e}")
                return rows

            time.sleep(self.delay_seconds)
            sleep_random(1.0, 2.0)

            feed = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
            # Try to load more by multiple scrolls
            self._scroll_results(driver, feed, rounds=max_pages * 5)

            # Use more stable selector for cards
            cards = driver.find_elements(By.CSS_SELECTOR, "div[role='feed'] .Nv2PK")
            if not cards:
                logger.info("No result cards found after scrolling. Try disabling headless mode or adjust keyword/location.")
                return rows

            seen_names = set()
            for idx, card in enumerate(cards, start=1):
                # Extract name from card list
                name = ""
                try:
                    name_el = card.find_element(By.CSS_SELECTOR, ".qBF1Pd")
                    name = name_el.text.strip()
                except NoSuchElementException:
                    try:
                        name_el = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                        name = name_el.get_attribute("aria-label") or ""
                    except Exception:
                        name = ""
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                # Open details panel by clicking the card title link if available, else the card container
                try:
                    link = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                    driver.execute_script("arguments[0].click();", link)
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", card)
                    except Exception:
                        continue

                time.sleep(self.delay_seconds)
                sleep_random(0.8, 1.5)
                try:
                    wait_css(driver, "div[role='main']")
                except TimeoutException:
                    pass

                details = self._extract_details_panel(driver)
                rows.append({
                    "name": name,
                    "website": details.get("website", ""),
                    "email": "",
                    "phone": details.get("phone", ""),
                    "address": details.get("address", ""),
                    "socials": "",
                })

                # Short pause between cards to reduce blocking
                time.sleep(self.delay_seconds)
                sleep_random(0.5, 1.2)
        finally:
            logger.info(f"Google Maps collected {len(rows)} results")
            driver.quit()
        return rows
