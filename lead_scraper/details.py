from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Optional

import httpx
import tldextract

from .utils import validate_email, normalize_phone, logger

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
SOCIAL_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "t.me",
    "youtube.com",
]


def _absolutize(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        logger.info(f"Enrich fetch: {url}")
        resp = await client.get(url, timeout=15)
        if resp.status_code >= 400:
            logger.error(f"Enrich HTTP {resp.status_code} for {url}")
            return None
        ct = resp.headers.get("content-type", "")
        if "text/html" not in ct and "xml" not in ct:
            return None
        return resp.text
    except Exception as e:
        logger.exception(f"Enrich error fetching {url}: {e}")
        return None


def _extract_emails(text: str) -> List[str]:
    found = []
    for match in EMAIL_PATTERN.findall(text or ""):
        if validate_email(match):
            found.append(match)
    # dedupe preserving order
    return list(dict.fromkeys(found))


def _extract_phones(text: str) -> List[str]:
    found = set()
    for match in PHONE_PATTERN.findall(text or ""):
        normalized = normalize_phone(match)
        if len(normalized) >= 7:
            found.add(normalized)
    return list(found)


def _extract_socials(text: str) -> List[str]:
    urls = set()
    for domain in SOCIAL_DOMAINS:
        pattern = re.compile(rf"https?://(?:www\.)?{re.escape(domain)}[^\s'\"]+", re.IGNORECASE)
        for u in pattern.findall(text or ""):
            urls.add(u)
    return list(urls)


async def enrich_with_website_details(rows: List[Dict[str, str]], concurrency: int = 10, delay_seconds: float = 0.0) -> List[Dict[str, str]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        async def process(row: Dict[str, str]) -> Dict[str, str]:
            website = (row.get("website") or "").strip()
            if not website:
                return row
            async with semaphore:
                html = await _fetch(client, website)
                if delay_seconds:
                    await asyncio.sleep(delay_seconds)
                if not html:
                    return row

                domain = tldextract.extract(website)
                root = f"https://{domain.registered_domain}" if domain.registered_domain else website
                candidate_paths = ["/contact", "/contact-us", "/about", "/about-us"]

                emails = _extract_emails(html)
                phones = _extract_phones(html)
                socials = _extract_socials(html)

                for p in candidate_paths:
                    contact_url = _absolutize(root, p)
                    extra = await _fetch(client, contact_url)
                    if delay_seconds:
                        await asyncio.sleep(delay_seconds)
                    if not extra:
                        continue
                    emails.extend(_extract_emails(extra))
                    phones.extend(_extract_phones(extra))
                    socials.extend(_extract_socials(extra))

                emails = list(dict.fromkeys(emails))
                phones = list(dict.fromkeys(phones))
                socials = list(dict.fromkeys(socials))

                if emails and not row.get("email"):
                    row["email"] = ", ".join(emails[:3])
                if phones and not row.get("phone"):
                    row["phone"] = ", ".join(phones[:3])
                if socials:
                    row["socials"] = ", ".join(socials[:5])
                return row

        return await asyncio.gather(*[process(dict(r)) for r in rows])
