import logging
from zeit_on_tolino import env_vars, epub, tolino, web, zeit
import undetected_chromedriver as uc
from pathlib import Path
import sys
import time

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def setup_webdriver():
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
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
    
    # Add language preferences
    options.add_argument('--lang=de-DE')
    
    # Set download directory
    download_path = Path("downloads")
    download_path.mkdir(exist_ok=True)
    
    driver = uc.Chrome(
        options=options,
        version_main=133,  # Match your Chrome version
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
            
            # Keep the browser window open and give instructions
            log.info("\n=== Browser will stay open for inspection ===")
            log.info("1. Press F12 to open DevTools")
            log.info("2. Go to the Network tab")
            log.info("3. Look for requests to webreader.mytolino.com")
            log.info("4. Press Ctrl+C when done to close the browser\n")
            
            # Keep the session alive by refreshing every 30 seconds
            try:
                current_url = webdriver.current_url
                while True:
                    time.sleep(30)
                    webdriver.get(current_url)  # Refresh the page
                    log.info("Refreshed page to keep session alive...")
            except KeyboardInterrupt:
                log.info("\nReceived keyboard interrupt. Closing browser...")
                webdriver.quit()
                
        except Exception as e:
            log.error(f"An error occurred: {e}", exc_info=True)
            log.info("\nBrowser will stay open for 30 seconds for inspection...")
            time.sleep(30)  # Keep window open for 30 seconds on error
            webdriver.quit()
            raise
        
        log.info("done.")
    except Exception as e:
        log.error(f"An error occurred: {e}", exc_info=True)