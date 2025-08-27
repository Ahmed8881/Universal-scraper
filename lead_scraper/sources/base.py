from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Callable, Dict, List

import requests
from bs4 import BeautifulSoup

from ..utils import logger, get_random_user_agent, sleep_random


class BaseDirectoryScraper(ABC):
    name: str = "base"

    def __init__(self, delay_seconds: float = 1.0) -> None:
        self.delay_seconds = delay_seconds

    @abstractmethod
    def build_search_url(self, keyword: str, location: str, page: int) -> str:
        raise NotImplementedError

    @abstractmethod
    def parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def has_next_page(self, soup: BeautifulSoup, page: int) -> bool:
        raise NotImplementedError

    def search(
        self,
        keyword: str,
        location: str,
        max_pages: int = 5,
        stop_flag: Callable[[], bool] | None = None,
    ) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        session = requests.Session()

        for page in range(1, max_pages + 1):
            if stop_flag and stop_flag():
                break
            url = self.build_search_url(keyword, location, page)
            headers = {
                "User-Agent": get_random_user_agent(),
                "Accept-Language": "en-US,en;q=0.9",
            }
            logger.info(f"Fetching URL: {url}")
            try:
                resp = session.get(url, headers=headers, timeout=20)
                if resp.status_code >= 400:
                    logger.error(f"HTTP {resp.status_code} for {url}")
                    break
                soup = BeautifulSoup(resp.text, "lxml")
                page_results = self.parse_search_results(soup)
                logger.info(f"Parsed {len(page_results)} results from {url}")
                results.extend(page_results)
                if not self.has_next_page(soup, page):
                    break
            except Exception as e:
                logger.exception(f"Error fetching {url}: {e}")
            finally:
                time.sleep(self.delay_seconds)
                sleep_random(1.0, 3.0)
        return results
