import logging
import os
import time
from pathlib import Path
from typing import Tuple

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
import random

from zeit_on_tolino.env_vars import EnvVars, MissingEnvironmentVariable
from zeit_on_tolino.tolino_partner import PartnerDetails
from zeit_on_tolino.web import Delay

TOLINO_CLOUD_LOGIN_URL = "https://webreader.mytolino.com/"
TOLINO_COUNTRY_TO_SELECT = "Deutschland"  # TODO make country a partner shop detail depending on selected partner shop

BUTTON_PLEASE_SELECT_YOUR_COUNTRY = "Bitte wähle Dein Land aus"
BUTTON_LOGIN = "Anmelden"
BUTTON_UPLOAD = "Hochladen"


log = logging.getLogger(__name__)


def _get_credentials() -> Tuple[str, str, str]:
    try:
        username = os.environ[EnvVars.TOLINO_USER]
        password = os.environ[EnvVars.TOLINO_PASSWORD]
        partner_shop = os.environ[EnvVars.TOLINO_PARTNER_SHOP].lower()
        return username, password, partner_shop
    except KeyError:
        raise MissingEnvironmentVariable(
            f"Ensure to export your tolino username, password and partner shop as environment variables "
            f"'{EnvVars.TOLINO_USER}', '{EnvVars.TOLINO_PASSWORD}' and '{EnvVars.TOLINO_PARTNER_SHOP}'. "
            f"For Github Actions, use repository secrets."
        )


def _login(webdriver: WebDriver) -> None:
    log.info("logging into tolino cloud...")

    username, password, partner_shop = _get_credentials()
    shop = getattr(PartnerDetails, partner_shop.lower()).value
    
    # Add some randomization to appear more human-like
    def random_sleep():
        time.sleep(random.uniform(1, 3))

    def move_mouse_randomly(element):
        try:
            action = ActionChains(element._parent)
            # Get element size and location
            size = element.size
            location = element.location
            
            # Calculate a point within the element's bounds
            x = location['x'] + size['width'] / 2
            y = location['y'] + size['height'] / 2
            
            # Move to the center of the element instead of random position
            action.move_to_element(element)
            action.perform()
        except Exception as e:
            log.warning(f"Mouse movement failed: {e}. Continuing without mouse movement.")
            # Continue without mouse movement if it fails

    webdriver.get(TOLINO_CLOUD_LOGIN_URL)
    random_sleep()

    # select country
    country_selector = WebDriverWait(webdriver, Delay.medium).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-test-id="ftu-countrySelection-countryList"]'))
    )
    
    country_element = WebDriverWait(webdriver, Delay.medium).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-test-id="ftu-country-de-DE"]'))
    )
    
    random_sleep()
    
    for div in webdriver.find_elements(By.TAG_NAME, "div"):
        if div.text == TOLINO_COUNTRY_TO_SELECT:
            move_mouse_randomly(div)
            random_sleep()
            div.click()
            break
    else:
        # Take screenshot before raising error
        screenshots_dir = Path(os.getenv('GITHUB_WORKSPACE', '.')) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        screenshot_path = screenshots_dir / "country_selection_error.png"
        webdriver.save_screenshot(str(screenshot_path))
        raise RuntimeError(f"Could not select desired country '{TOLINO_COUNTRY_TO_SELECT}'.")

    # select partner shop
    time.sleep(Delay.small)
    WebDriverWait(webdriver, Delay.large).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-test-id="ftu-resellerSelection-resellerList"]'))
    )
    for div in webdriver.find_elements(By.TAG_NAME, "div"):
        if shop.shop_image_keyword in div.get_attribute("style"):
            try:
                move_mouse_randomly(div)
            except Exception as e:
                log.warning(f"Mouse movement skipped: {e}")
            div.click()
            break
    else:
        raise RuntimeError(f"Could not select desired partner shop '{shop.shop_image_keyword}'.")

    # click on login button
    WebDriverWait(webdriver, Delay.medium).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-test-id="library-selection-headerBar"]'))
    )
    for span in webdriver.find_elements(By.TAG_NAME, "span"):
        if span.text == BUTTON_LOGIN:
            span.click()
            break
    else:
        raise RuntimeError("Could not find login button.")

    # login with partner shop credentials
    WebDriverWait(webdriver, Delay.medium).until(EC.presence_of_element_located((shop.user.by, shop.user.value)))
    username_field = webdriver.find_element(shop.user.by, shop.user.value)

    username_field.send_keys(username)
    password_field = webdriver.find_element(shop.password.by, shop.password.value)
    password_field.send_keys(password)

    btn = webdriver.find_element(shop.login_button.by, shop.login_button.value)
    btn.click()

    # Create screenshots directory in GitHub workspace
    workspace = os.getenv('GITHUB_WORKSPACE', '.')
    screenshots_dir = Path(workspace) / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    
    # Take screenshot after login
    screenshot_path = screenshots_dir / "tolino_login.png"
    webdriver.save_screenshot(str(screenshot_path))
    log.info(f"Saved login screenshot to {screenshot_path}")


def element_exists(webdriver: WebDriver, by: str, value: str) -> bool:
    try:
        webdriver.find_element(by, value)
    except NoSuchElementException:
        return False
    return True


def _upload(webdriver: WebDriver, file_path: Path, e_paper_title: str) -> None:
    # wait until logged in
    WebDriverWait(webdriver, Delay.large).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'span[data-test-id="library-drawer-labelLoggedIn"]'))
    )

    # dismiss advertisement popup
    popup_button_css = 'div[data-test-id="dialogButton-0"]'
    if element_exists(webdriver, by=By.CSS_SELECTOR, value=popup_button_css):
        WebDriverWait(webdriver, Delay.small).until(EC.presence_of_element_located((By.CSS_SELECTOR, popup_button_css)))
        WebDriverWait(webdriver, Delay.small).until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_button_css)))
        popup_button = webdriver.find_element(By.CSS_SELECTOR, popup_button_css)
        time.sleep(Delay.small)
        popup_button.click()

    # click on 'my books'
    my_books_button_css = 'span[data-test-id="library-drawer-MyBooks"]'
    WebDriverWait(webdriver, Delay.small).until(EC.presence_of_element_located((By.CSS_SELECTOR, my_books_button_css)))
    WebDriverWait(webdriver, Delay.small).until(EC.element_to_be_clickable((By.CSS_SELECTOR, my_books_button_css)))
    my_books_button = webdriver.find_element(By.CSS_SELECTOR, my_books_button_css)
    time.sleep(Delay.small)
    my_books_button.click()

    menu_css = 'div[data-test-id="library-headerBar-overflowMenu-button"]'
    WebDriverWait(webdriver, Delay.medium).until(EC.presence_of_element_located((By.CSS_SELECTOR, menu_css)))
    if e_paper_title in webdriver.page_source:
        log.info(f"The title '{e_paper_title}' is already present in tolino cloud. Skipping upload.")
        return

    # click on vertical ellipsis to get to drop down menu
    menu = webdriver.find_element(By.CSS_SELECTOR, menu_css)
    menu.click()

    # upload file
    WebDriverWait(webdriver, Delay.small).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-test-id="library-headerBar-menu-item-upload"]'))
    )
    upload = webdriver.find_element(By.XPATH, "//input[@type='file']")
    upload.send_keys(str(file_path))

    # wait for upload status field to appear
    log.info("waiting for upload status bar to appear...")
    WebDriverWait(webdriver, Delay.medium).until(EC.presence_of_element_located((By.CLASS_NAME, "_sep8tp")))
    log.info("upload status bar appeared.")
    # wait for upload status field to disappear
    log.info("waiting for upload status bar to disappear...")
    upload_status_bar = webdriver.find_element(By.CLASS_NAME, "_sep8tp")
    WebDriverWait(webdriver, Delay.xlarge).until(EC.staleness_of(upload_status_bar))
    log.info("upload status bar disappeared.")
    time.sleep(Delay.medium)

    webdriver.refresh()
    log.info("waiting for book to be present...")
    WebDriverWait(webdriver, Delay.medium).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'span[data-test-id="library-myBooks-titles-list-0-title"]'))
    )
    assert e_paper_title in webdriver.page_source, f"Title '{e_paper_title}' not found in page source!"
    log.info(f"book title '{e_paper_title}' is present.")
    log.info("successfully uploaded ZEIT e-paper to tolino cloud.")


def login_and_upload(webdriver: WebDriver, file_path: Path, e_paper_title: str) -> None:
    _login(webdriver)
    _upload(webdriver, file_path, e_paper_title)
