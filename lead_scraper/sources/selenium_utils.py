from __future__ import annotations

from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from ..utils import get_random_user_agent, logger


def build_chrome(headless: bool = True) -> webdriver.Chrome:
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1000")
    options.add_argument("--lang=en-US")
    options.add_argument(f"--user-agent={get_random_user_agent()}")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(40)
    logger.info("Launched Chrome WebDriver")
    return driver


def wait_css(driver: webdriver.Chrome, selector: str, timeout: int = 20):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))


def find_text_safe(element, selector: str) -> str:
    try:
        el = element.find_element(By.CSS_SELECTOR, selector)
        return el.text.strip()
    except Exception:
        return ""


def find_attr_safe(element, selector: str, attr: str) -> str:
    try:
        el = element.find_element(By.CSS_SELECTOR, selector)
        val = el.get_attribute(attr)
        return val.strip() if val else ""
    except Exception:
        return ""
