import logging
import glob
import os
import time
from pathlib import Path
from typing import Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from zeit_on_tolino.env_vars import EnvVars, MissingEnvironmentVariable
from zeit_on_tolino.web import Delay

ZEIT_LOGIN_URL = "https://epaper.zeit.de/abo/diezeit"
ZEIT_DATE_FORMAT = "%d.%m.%Y"

BUTTON_TEXT_TO_RECENT_EDITION = "ZUR AKTUELLEN AUSGABE"
BUTTON_TEXT_DOWNLOAD_EPUB = "EPUB FÜR E-READER LADEN"
BUTTON_TEXT_EPUB_DOWNLOAD_IS_PENDING = "EPUB FOLGT IN KÜRZE"

log = logging.getLogger(__name__)

def _get_credentials() -> Tuple[str, str]:
    try:
        username = os.environ[EnvVars.ZEIT_PREMIUM_USER]
        password = os.environ[EnvVars.ZEIT_PREMIUM_PASSWORD]
        return username, password
    except KeyError:
        raise MissingEnvironmentVariable(
            f"Ensure to export your ZEIT username and password as environment variables "
            f"'{EnvVars.ZEIT_PREMIUM_USER}' and '{EnvVars.ZEIT_PREMIUM_PASSWORD}'. For "
            "Github Actions, use repository secrets."
        )


def _login(webdriver: WebDriver) -> None:
    try:
        webdriver.get(ZEIT_LOGIN_URL)
        time.sleep(Delay.medium)
        
        log.info(f"Current URL: {webdriver.current_url}")
        
        # First check if we're already logged in by looking for the download button
        try:
            if BUTTON_TEXT_TO_RECENT_EDITION in webdriver.page_source:
                log.info("Already logged into ZEIT")
                # Dump cookies in detail for setting up GitHub Actions
                cookies = webdriver.get_cookies()
                log.info("Current cookies (full details):")
                for cookie in cookies:
                    log.info(f"""
Cookie details:
  Name: {cookie['name']}
  Value: {cookie['value']}
  Domain: {cookie.get('domain')}
  Path: {cookie.get('path')}
  Secure: {cookie.get('secure')}
  HttpOnly: {cookie.get('httpOnly')}
  Expiry: {cookie.get('expiry')}
""")
                return
        except Exception as e:
            log.info(f"Error checking login state: {e}")
        
        # If we get here, we need to log in
        username, password = _get_credentials()
        log.info(f"ZEIT_PREMIUM_USER is {'set' if username else 'not set'}")
        log.info(f"ZEIT_PREMIUM_PASSWORD is {'set' if password else 'not set'}")
        
        # Wait for page to be fully loaded
        try:
            WebDriverWait(webdriver, Delay.large).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            log.info("Page fully loaded")
        except Exception as e:
            log.error(f"Page did not finish loading: {e}")
            log.info(f"Current URL: {webdriver.current_url}")
            raise
            
        # Look for login form or download button
        try:
            # First check if we're already on the e-paper page with download button
            if BUTTON_TEXT_TO_RECENT_EDITION in webdriver.page_source:
                log.info("Found download button - already logged in")
                return
                
            # If not, look for login form
            username_field = WebDriverWait(webdriver, Delay.medium).until(
                EC.presence_of_element_located((By.ID, "login_email"))
            )
            password_field = webdriver.find_element(By.ID, "login_pass")
            
            # Fill in credentials
            username_field.send_keys(username)
            password_field.send_keys(password)
            
            # Click login button
            btn = webdriver.find_element(By.CLASS_NAME, "submit-button.log")
            btn.click()
            time.sleep(Delay.medium)
            
            # Check if we're still on login page
            if "anmelden" in webdriver.current_url:
                log.error("Still on login page after submission")
                log.info("Current URL: " + webdriver.current_url)
                log.info("Page source: " + webdriver.page_source[:500])
                raise RuntimeError("Failed to login, check your login credentials.")
            
            # Wait for successful login
            WebDriverWait(webdriver, Delay.medium).until(
                EC.presence_of_element_located((By.CLASS_NAME, "page-section-header"))
            )
            
        except Exception as e:
            log.error(f"Login failed: {e}")
            log.info("Page source: " + webdriver.page_source[:500])
            raise
            
    except Exception as e:
        log.error(f"Login failed: {e}")
        screenshots_dir = Path(os.getenv('GITHUB_WORKSPACE', '.')) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        screenshot_path = screenshots_dir / "zeit_login_failure.png"
        webdriver.save_screenshot(str(screenshot_path))
        raise


def _get_latest_downloaded_file_path(download_dir: str) -> Path:
    download_dir_files = glob.glob(f"{download_dir}/*")
    latest_file = max(download_dir_files, key=os.path.getctime)
    return Path(latest_file)


def wait_for_downloads(path):
    time.sleep(Delay.small)
    start = time.time()
    while any([filename.endswith(".crdownload") for filename in os.listdir(path)]):
        now = time.time()
        if now > start + Delay.large:
            raise TimeoutError(f"Did not manage to download file within {Delay.large} seconds.")
        else:
            log.info(f"waiting for download to be finished...")
            time.sleep(2)


def download_e_paper(webdriver: WebDriver) -> str:
    _login(webdriver)

    time.sleep(Delay.small)
    for link in webdriver.find_elements(By.TAG_NAME, "a"):
        if link.text == BUTTON_TEXT_TO_RECENT_EDITION:
            link.click()
            break

    if BUTTON_TEXT_EPUB_DOWNLOAD_IS_PENDING in webdriver.page_source:
        raise RuntimeError("New ZEIT release is available, however, EPUB version is not. Retry again later.")

    time.sleep(Delay.small)
    for link in webdriver.find_elements(By.TAG_NAME, "a"):
        if link.text == BUTTON_TEXT_DOWNLOAD_EPUB:
            log.info("clicking download button now...")
            link.click()
            break

    wait_for_downloads(webdriver.download_dir_path)
    e_paper_path = _get_latest_downloaded_file_path(webdriver.download_dir_path)

    if not e_paper_path.is_file():
        raise RuntimeError("Could not download e paper, check your login credentials.")

    return e_paper_path
