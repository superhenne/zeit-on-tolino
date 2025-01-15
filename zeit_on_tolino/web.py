import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Union, Optional

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.firefox.webdriver import WebDriver

# Use a persistent directory within the temp directory
DOWNLOAD_PATH = Path(tempfile.gettempdir()) / "selenium_downloads"

@dataclass
class Delay:
    small: int = 3
    medium: int = 10
    large: int = 30
    xlarge: int = 200

def get_webdriver(download_path: Union[Path, str] = DOWNLOAD_PATH, headless: bool = True) -> WebDriver:
    if isinstance(download_path, str):
        download_path = Path(download_path)
    
    options = ChromeOptions()
    prefs = {"download.default_directory" : str(download_path)}
    options.add_experimental_option("prefs", prefs)
    if headless:
        options.add_argument("--headless")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.84 Safari/537.36")

    webdriver = Chrome(options=options)
    setattr(webdriver, "download_dir_path", str(download_path))
    
    return webdriver

# Ensure the download path directory exists
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
