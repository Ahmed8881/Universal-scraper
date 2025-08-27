from __future__ import annotations

import logging
import random
import re
import time
from typing import Dict, List, Callable, Optional

import tldextract
import requests


# Basic logging config for console output
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(name)s - %(message)s",
)
logger = logging.getLogger("lead_scraper")

# A small pool of realistic desktop Chrome user-agents
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com",
    "proton.me", "protonmail.com", "yandex.com", "live.com",
}


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def sleep_random(min_seconds: float = 1.0, max_seconds: float = 5.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def normalize_space(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def validate_email(email: str) -> bool:
    if not email:
        return False
    email = email.strip()
    if len(email) > 254:
        return False
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    if not re.match(pattern, email):
        return False
    if any(x in email for x in ["example.com", "test@", "no-reply", "noreply"]):
        return False
    return True


def is_business_email(email: str) -> bool:
    if not validate_email(email):
        return False
    domain = email.split("@")[-1].lower()
    return domain not in FREE_EMAIL_DOMAINS


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"[^0-9+]", "", phone)
    return digits[:20]


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    ext = tldextract.extract(url)
    return ext.registered_domain or ""


def score_lead(row: Dict[str, str]) -> int:
    score = 0
    if (row.get("website") or "").strip():
        score += 30
    if row.get("email"):
        emails = [e.strip() for e in (row.get("email") or "").split(",") if e.strip()]
        if any(validate_email(e) for e in emails):
            score += 50
    if (row.get("phone") or "").strip():
        score += 20
    if (row.get("address") or "").strip():
        score += 10
    if (row.get("socials") or "").strip():
        score += 5
    return score


def deduplicate_records(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[tuple] = set()
    unique: List[Dict[str, str]] = []
    for r in rows:
        domain = domain_from_url((r.get("website") or "").lower().strip().rstrip("/"))
        key = (
            (r.get("name") or "").lower(),
            domain,
            (r.get("phone") or "").replace(" ", ""),
            (r.get("address") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique


def retry_request(
    func: Callable[[], requests.Response],
    retries: int = 3,
    backoff_base: float = 1.0,
) -> Optional[requests.Response]:
    for attempt in range(1, retries + 1):
        try:
            resp = func()
            if resp.status_code < 500:
                return resp
            logger.warning(f"Server error {resp.status_code}, attempt {attempt}/{retries}")
        except Exception as e:
            logger.warning(f"Request failed: {e}, attempt {attempt}/{retries}")
        time.sleep(backoff_base * (2 ** (attempt - 1)))
    return None
