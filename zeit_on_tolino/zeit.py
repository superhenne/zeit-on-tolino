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
        username, password = _get_credentials()
        log.info(f"ZEIT_PREMIUM_USER is {'set' if username else 'not set'}")
        log.info(f"ZEIT_PREMIUM_PASSWORD is {'set' if password else 'not set'}")
        
        screenshots_dir = Path(os.getenv('GITHUB_WORKSPACE', '.')) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        
        webdriver.get(ZEIT_LOGIN_URL)
        time.sleep(Delay.medium)
        
        # Take screenshot to check for Friendly Captcha
        screenshot_path = screenshots_dir / "zeit_captcha_check.png"
        webdriver.save_screenshot(str(screenshot_path))
        log.info(f"Current URL: {webdriver.current_url}")
        
        # Wait for Friendly Captcha to complete
        try:
            WebDriverWait(webdriver, Delay.medium).until(
                EC.presence_of_element_located((By.CLASS_NAME, "frc-captcha"))
            )
            log.info("Friendly Captcha widget found, waiting for completion...")
            
            # Wait for the captcha to be solved (when data-callback attribute appears)
            WebDriverWait(webdriver, Delay.large).until(
                lambda driver: driver.execute_script("""
                    return document.querySelector('.frc-captcha').getAttribute('data-callback') !== null
                """)
            )
            log.info("Friendly Captcha completed")
        except Exception as e:
            log.info(f"No Friendly Captcha found or already completed: {e}")
        
        # Now proceed with login
        username_field = webdriver.find_element(By.ID, "login_email")
        password_field = webdriver.find_element(By.ID, "login_pass")
        
        # Type slowly to appear more human-like
        for char in username:
            username_field.send_keys(char)
            time.sleep(0.1)
        time.sleep(0.5)
        for char in password:
            password_field.send_keys(char)
            time.sleep(0.1)
        
        btn = webdriver.find_element(By.CLASS_NAME, "submit-button.log")
        btn.click()
        time.sleep(Delay.medium)

        # Take screenshot after login attempt
        screenshot_path = screenshots_dir / "zeit_after_login.png"
        webdriver.save_screenshot(str(screenshot_path))
        
        if "anmelden" in webdriver.current_url:
            log.error("Still on login page after submission")
            raise RuntimeError("Failed to login, check your login credentials.")

        WebDriverWait(webdriver, Delay.medium).until(
            EC.presence_of_element_located((By.CLASS_NAME, "page-section-header"))
        )
        
    except Exception as e:
        log.error(f"Login failed: {e}")
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
