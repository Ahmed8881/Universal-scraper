from __future__ import annotations

import time
from typing import Dict, List, Callable

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from .selenium_utils import build_chrome, wait_css
from ..utils import logger, sleep_random


class GenericSeleniumScraper:
    name = "Generic Selenium"

    def __init__(self, headless: bool = True, delay_seconds: float = 1.0) -> None:
        self.headless = headless
        self.delay_seconds = delay_seconds

    def search(
        self,
        start_url: str,
        locate_cards_css: str,
        parse_card: Callable[[object], Dict[str, str]],
        next_button_css: str | None = None,
        max_pages: int = 3,
    ) -> List[Dict[str, str]]:
        driver: WebDriver = build_chrome(headless=self.headless)
        rows: List[Dict[str, str]] = []
        try:
            url = start_url
            for page in range(1, max_pages + 1):
                logger.info(f"Navigating: {url}")
                try:
                    driver.get(url)
                    wait_css(driver, locate_cards_css)
                except Exception as e:
                    logger.exception(f"Failed to load {url}: {e}")
                    break
                time.sleep(self.delay_seconds)
                sleep_random(1.0, 5.0)

                cards = driver.find_elements(By.CSS_SELECTOR, locate_cards_css)
                logger.info(f"Found {len(cards)} cards on {url}")
                for card in cards:
                    try:
                        data = parse_card(card)
                        if data.get("name"):
                            rows.append(data)
                    except Exception as e:
                        logger.warning(f"Card parse error on {url}: {e}")

                if not next_button_css:
                    break
                try:
                    nxt = driver.find_element(By.CSS_SELECTOR, next_button_css)
                    driver.execute_script("arguments[0].click();", nxt)
                    time.sleep(self.delay_seconds)
                    sleep_random(1.0, 5.0)
                    url = driver.current_url
                except Exception:
                    break
        finally:
            driver.quit()
        return rows
