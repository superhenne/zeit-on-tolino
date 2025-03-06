import logging
from zeit_on_tolino import env_vars, epub, tolino, web, zeit
import undetected_chromedriver as uc
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def setup_webdriver():
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    # Remove headless mode for now
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-dev-shm-usage')
    
    # Add persistent profile directory
    profile_dir = Path.home() / ".config" / "chrome-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    options.add_argument(f'--user-data-dir={profile_dir}')
    options.add_argument('--profile-directory=Default')
    
    # Set Chrome binary location for Mac
    if sys.platform == "darwin":  # Mac OS
        options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    
    # Add realistic user agent
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Add language preferences
    options.add_argument('--lang=de-DE')
    
    # Set download directory
    download_path = Path("downloads")
    download_path.mkdir(exist_ok=True)
    prefs = {
        "download.default_directory": str(download_path.absolute()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = uc.Chrome(
        options=options,
        version_main=133,  # Match your Chrome version
        allow_browser_download=True
    )
    
    # Add download_dir_path attribute
    setattr(driver, "download_dir_path", str(download_path.absolute()))
    
    return driver

if __name__ == "__main__":
    try:
        env_vars.verify_env_vars_are_set()
        env_vars.verify_configured_partner_shop_is_supported()

        log.info("logging into ZEIT premium...")
        webdriver = setup_webdriver()
        
        try:
            # download ZEIT
            log.info("downloading most recent ZEIT e-paper...")
            e_paper_path = zeit.download_e_paper(webdriver)
            e_paper_title = epub.get_epub_info(e_paper_path)["title"]
            if not e_paper_path.is_file():
                raise FileNotFoundError(f"Downloaded file not found: {e_paper_path}")
            log.info(f"successfully finished download of '{e_paper_title}'")

            # upload to tolino cloud
            log.info("upload ZEIT e-paper to tolino cloud...")
            tolino.login_and_upload(webdriver, e_paper_path, e_paper_title)
        finally:
            webdriver.quit()
            log.info("WebDriver quit successfully.")
        
        log.info("done.")
    except Exception as e:
        log.error(f"An error occurred: {e}", exc_info=True)