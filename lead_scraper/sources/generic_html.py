from __future__ import annotations

from typing import Dict, List, Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..utils import logger, get_random_user_agent, retry_request, sleep_random, normalize_space


class GenericHTMLScraper:
    name = "Generic HTML"

    def __init__(self, delay_seconds: float = 1.0) -> None:
        self.delay_seconds = delay_seconds

    def search(
        self,
        start_url: str,
        parse_card: Callable[[BeautifulSoup], Dict[str, str]],
        select_cards: str,
        next_selector: str | None = None,
        max_pages: int = 3,
    ) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        session = requests.Session()
        url = start_url
        pages = 0
        while url and pages < max_pages:
            logger.info(f"Fetching URL: {url}")
            resp = retry_request(lambda: session.get(url, headers={
                "User-Agent": get_random_user_agent(),
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=25))
            if not resp or resp.status_code >= 400:
                logger.error(f"Failed to fetch {url}")
                break
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(select_cards)
            logger.info(f"Parsed {len(cards)} cards from {url}")
            for c in cards:
                try:
                    data = parse_card(BeautifulSoup(str(c), "lxml"))
                    if data.get("name"):
                        results.append(data)
                except Exception as e:
                    logger.warning(f"Card parse error on {url}: {e}")
            pages += 1
            sleep_random(1.0, 5.0)
            if next_selector:
                nxt = soup.select_one(next_selector)
                if nxt and nxt.get("href"):
                    url = urljoin(url, nxt.get("href"))
                else:
                    break
            else:
                break
        return results
