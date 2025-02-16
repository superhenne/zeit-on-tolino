import logging
from zeit_on_tolino import env_vars, epub, tolino, web, zeit

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        env_vars.verify_env_vars_are_set()
        env_vars.verify_configured_partner_shop_is_supported()

        log.info("logging into ZEIT premium...")
        webdriver = web.get_webdriver()
        
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