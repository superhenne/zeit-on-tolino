import logging
from zeit_on_tolino import env_vars, epub, tolino, web, zeit
import undetected_chromedriver as uc
from pathlib import Path

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def setup_webdriver():
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-dev-shm-usage')
    
    # Add realistic user agent
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
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
    
    # Specify Chrome version
    driver = uc.Chrome(
        options=options, 
        version_main=133,  # Match the installed Chrome version
        allow_browser_download=True
    )
    
    # Set common headers
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        "platform": "Windows",
        "acceptLanguage": "de-DE"
    })
    
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