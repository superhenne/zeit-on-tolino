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


def _get_all_cookies(webdriver: WebDriver) -> list:
    """Get all cookies from all domains we care about"""
    all_cookies = []
    
    # First get cookies from current domain
    all_cookies.extend(webdriver.get_cookies())
    
    # Then explicitly check thalia.de domain
    webdriver.get("https://www.thalia.de")
    time.sleep(Delay.small)
    all_cookies.extend(webdriver.get_cookies())
    
    return all_cookies


def _log_storage(webdriver: WebDriver, location: str) -> None:
    """Helper function to log cookies, local storage, session storage, and IndexedDB at a specific location"""
    log.info(f"\n\n===== TOLINO STORAGE AT: {location} =====")
    current_url = webdriver.current_url
    log.info(f"Current URL: {current_url}")
    
    # Log cookies with special attention to OAUTH-JSESSIONID
    cookies = _get_all_cookies(webdriver)
    if not cookies:
        log.info("No cookies found!")
    else:
        log.info("=== Cookies ===")
        oauth_cookie = None
        for cookie in cookies:
            if cookie['name'] == 'OAUTH-JSESSIONID':
                oauth_cookie = cookie
            log.info(f"""
Cookie details for {cookie['name']}:
  Name: {cookie['name']}
  Value: {cookie['value']}
  Domain: {cookie.get('domain', 'N/A')}
  Path: {cookie.get('path', 'N/A')}
  Secure: {cookie.get('secure', False)}
  HttpOnly: {cookie.get('httpOnly', False)}
  Expiry: {cookie.get('expiry', 'N/A')}
----------------------------------------""")
        if oauth_cookie:
            log.info("\n!!! FOUND OAUTH-JSESSIONID COOKIE !!!")
            log.info(f"Domain: {oauth_cookie.get('domain', 'N/A')}")
            log.info(f"Value: {oauth_cookie['value']}")
    
    # Return to original URL if we navigated away
    if webdriver.current_url != current_url:
        webdriver.get(current_url)
        time.sleep(Delay.small)
    
    # Log local storage
    log.info("\n=== Local Storage ===")
    local_storage = webdriver.execute_script("""
        let items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
        }
        return items;
    """)
    if not local_storage:
        log.info("No local storage items found!")
    else:
        for key, value in local_storage.items():
            log.info(f"Key: {key}")
            log.info(f"Value: {value[:200]}..." if len(str(value)) > 200 else f"Value: {value}")
            log.info("----------------------------------------")
    
    # Log session storage
    log.info("\n=== Session Storage ===")
    session_storage = webdriver.execute_script("""
        let items = {};
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            items[key] = sessionStorage.getItem(key);
        }
        return items;
    """)
    if not session_storage:
        log.info("No session storage items found!")
    else:
        for key, value in session_storage.items():
            log.info(f"Key: {key}")
            log.info(f"Value: {value[:200]}..." if len(str(value)) > 200 else f"Value: {value}")
            log.info("----------------------------------------")
            
    # Log IndexedDB contents with focus on tolino-related stores
    log.info("\n=== IndexedDB ===")
    indexed_db = webdriver.execute_script("""
        return new Promise((resolve, reject) => {
            const databases = {};
            const request = window.indexedDB.open('tolino-user');
            
            request.onerror = () => {
                resolve({'error': 'Could not open tolino-user IndexedDB'});
            };
            
            request.onsuccess = (event) => {
                const db = event.target.result;
                const stores = Array.from(db.objectStoreNames);
                let completed = 0;
                
                if (stores.length === 0) {
                    resolve({'info': 'No object stores found in tolino-user'});
                    return;
                }
                
                stores.forEach(storeName => {
                    const transaction = db.transaction(storeName, 'readonly');
                    const store = transaction.objectStore(storeName);
                    const items = [];
                    
                    store.openCursor().onsuccess = (event) => {
                        const cursor = event.target.result;
                        if (cursor) {
                            items.push({
                                key: cursor.key,
                                value: cursor.value
                            });
                            cursor.continue();
                        } else {
                            databases[storeName] = items;
                            completed++;
                            if (completed === stores.length) {
                                resolve(databases);
                            }
                        }
                    };
                });
            };
        });
    """)
    
    if indexed_db:
        if isinstance(indexed_db, dict):
            for store_name, items in indexed_db.items():
                if store_name == 'error':
                    log.info(f"IndexedDB error: {items}")
                    continue
                if store_name == 'info':
                    log.info(items)
                    continue
                log.info(f"\nStore: {store_name}")
                for item in items:
                    log.info(f"Key: {item['key']}")
                    value = str(item['value'])
                    log.info(f"Value: {value[:200]}..." if len(value) > 200 else f"Value: {value}")
                    log.info("----------------------------------------")
    else:
        log.info("No IndexedDB data found!")
        
    # Also try to list all IndexedDB databases
    log.info("\n=== All IndexedDB Databases ===")
    all_dbs = webdriver.execute_script("""
        return window.indexedDB.databases().then(dbs => {
            return dbs.map(db => ({ name: db.name, version: db.version }));
        }).catch(err => ({ error: 'Could not list databases' }));
    """)
    if isinstance(all_dbs, list):
        for db in all_dbs:
            log.info(f"Database: {db['name']}, Version: {db['version']}")
    else:
        log.info("Could not list IndexedDB databases")


def _login(webdriver: WebDriver) -> None:
    try:
        log.info("Starting Tolino login process...")
        
        # Navigate to Tolino and wait for page load
        webdriver.get(TOLINO_CLOUD_LOGIN_URL)
        time.sleep(Delay.large)
        log.info(f"Current URL: {webdriver.current_url}")
        
        # Wait for page to be fully loaded
        try:
            WebDriverWait(webdriver, Delay.large).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            log.info("Page fully loaded")
        except Exception as e:
            log.error(f"Page did not finish loading: {e}")
            raise
            
        # First check if we're already logged in by looking for elements that only appear when logged in
        try:
            # Try to find any of these elements that indicate we're logged in
            selectors = [
                'span[data-test-id="library-drawer-labelLoggedIn"]',
                'span[data-test-id="library-drawer-MyBooks"]',
                'div[data-test-id="library-headerBar-overflowMenu-button"]'
            ]
            
            for selector in selectors:
                try:
                    element = WebDriverWait(webdriver, Delay.small).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    log.info(f"Found logged-in indicator: {selector}")
                    log.info("Already logged into Tolino")
                    _log_storage(webdriver, "ALREADY LOGGED IN")
                    return
                except Exception:
                    continue
                    
            log.info("No logged-in indicators found, proceeding with login...")
        except Exception as e:
            log.info(f"Error checking login state: {e}, proceeding with login...")
        
        # If we get here, we need to log in
        username, password, partner_shop = _get_credentials()
        
        # Try to find the country selector
        log.info("Looking for country selector...")
        country_selector = WebDriverWait(webdriver, Delay.medium).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-test-id="countrySelector"]'))
        )
        log.info("Found country selector, clicking...")
        country_selector.click()
        time.sleep(Delay.small)
        
        # Select Germany
        log.info("Looking for Germany option...")
        germany_option = WebDriverWait(webdriver, Delay.medium).until(
            EC.presence_of_element_located((By.XPATH, f"//div[contains(text(), '{TOLINO_COUNTRY_TO_SELECT}')]"))
        )
        log.info("Found Germany option, clicking...")
        germany_option.click()
        time.sleep(Delay.small)
        
        # Wait for and click the partner shop
        log.info(f"Looking for partner shop: {partner_shop}...")
        partner_selector = WebDriverWait(webdriver, Delay.medium).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f'div[data-test-id="partnerShop-{partner_shop}"]'))
        )
        log.info("Found partner shop, clicking...")
        partner_selector.click()
        time.sleep(Delay.small)
        
        # Wait for login form
        log.info("Looking for login form...")
        username_field = WebDriverWait(webdriver, Delay.medium).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-test-id="email"]'))
        )
        password_field = webdriver.find_element(By.CSS_SELECTOR, 'input[data-test-id="password"]')
        
        # Fill in credentials
        log.info("Entering credentials...")
        username_field.send_keys(username)
        password_field.send_keys(password)
        
        # Click login button
        log.info("Clicking login button...")
        login_button = webdriver.find_element(By.CSS_SELECTOR, 'button[data-test-id="submit"]')
        login_button.click()
        
        # Wait for successful login
        log.info("Waiting for successful login...")
        WebDriverWait(webdriver, Delay.large).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span[data-test-id="library-drawer-labelLoggedIn"]'))
        )
        time.sleep(Delay.medium)
        
        log.info("Successfully logged into Tolino")
        _log_storage(webdriver, "AFTER SUCCESSFUL LOGIN")
        
    except Exception as e:
        log.error(f"Login failed: {e}")
        screenshots_dir = Path(os.getenv('GITHUB_WORKSPACE', '.')) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        screenshot_path = screenshots_dir / "tolino_login_failure.png"
        webdriver.save_screenshot(str(screenshot_path))
        log.error(f"Saved error screenshot to {screenshot_path}")
        raise


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
    
    _log_storage(webdriver, "START OF UPLOAD")

    # dismiss advertisement popup
    popup_button_css = 'div[data-test-id="dialogButton-0"]'
    if element_exists(webdriver, by=By.CSS_SELECTOR, value=popup_button_css):
        WebDriverWait(webdriver, Delay.small).until(EC.presence_of_element_located((By.CSS_SELECTOR, popup_button_css)))
        WebDriverWait(webdriver, Delay.small).until(EC.element_to_be_clickable((By.CSS_SELECTOR, popup_button_css)))
        popup_button = webdriver.find_element(By.CSS_SELECTOR, popup_button_css)
        time.sleep(Delay.small)
        popup_button.click()
        _log_storage(webdriver, "AFTER POPUP DISMISS")

    # click on 'my books'
    my_books_button_css = 'span[data-test-id="library-drawer-MyBooks"]'
    WebDriverWait(webdriver, Delay.small).until(EC.presence_of_element_located((By.CSS_SELECTOR, my_books_button_css)))
    WebDriverWait(webdriver, Delay.small).until(EC.element_to_be_clickable((By.CSS_SELECTOR, my_books_button_css)))
    my_books_button = webdriver.find_element(By.CSS_SELECTOR, my_books_button_css)
    time.sleep(Delay.small)
    my_books_button.click()
    time.sleep(Delay.medium)  # Give it a moment to process the click
    _log_storage(webdriver, "AFTER MY BOOKS CLICK")

    menu_css = 'div[data-test-id="library-headerBar-overflowMenu-button"]'
    WebDriverWait(webdriver, Delay.medium).until(EC.presence_of_element_located((By.CSS_SELECTOR, menu_css)))
    if e_paper_title in webdriver.page_source:
        log.info(f"The title '{e_paper_title}' is already present in tolino cloud. Skipping upload.")
        _log_storage(webdriver, "BEFORE EXIT")
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
    
    # Take final screenshot after successful upload
    screenshots_dir = Path(os.getenv('GITHUB_WORKSPACE', '.')) / "screenshots"
    screenshot_path = screenshots_dir / "upload_success.png"
    webdriver.save_screenshot(str(screenshot_path))
    log.info(f"Saved post-upload screenshot to {screenshot_path}")
    
    log.info("successfully uploaded ZEIT e-paper to tolino cloud.")
    _log_storage(webdriver, "AFTER UPLOAD")


def login_and_upload(webdriver: WebDriver, file_path: Path, e_paper_title: str) -> None:
    _login(webdriver)
    _upload(webdriver, file_path, e_paper_title)
