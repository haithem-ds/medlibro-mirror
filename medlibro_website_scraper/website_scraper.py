"""
Main website scraper - downloads HTML pages and all assets.
"""
import re
import json
import time
from urllib.parse import urljoin, urlparse, unquote
from pathlib import Path
from tqdm import tqdm
import sys

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] Missing dependencies. Install with: pip install -r requirements.txt")
    sys.exit(1)

from config import (
    BASE_URL, EMAIL, PASSWORD, HTML_DIR, ASSETS_DIR,
    HEADLESS, CHROME_VERSION_MAIN, DELAY_BETWEEN_REQUESTS, TIMEOUT,
    SKIP_PATTERNS, USER_AGENT, MAX_PAGES
)
from asset_downloader import AssetDownloader


class WebsiteScraper:
    def __init__(self):
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.asset_downloader = None
        self.scraped_pages = set()
        self.page_info = []
        
    def login(self):
        """Login to MedLibro."""
        print("[INFO] Logging in to MedLibro...")
        try:
            options = uc.ChromeOptions()
            if HEADLESS:
                options.add_argument("--headless=new")
            # Match API scraper exactly - don't use --no-sandbox or --disable-dev-shm-usage
            options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
            
            # Get version from environment or use config default (same as API scraper)
            version_main = CHROME_VERSION_MAIN
            try:
                import os
                v = os.environ.get("CHROME_VERSION_MAIN", "").strip()
                if v:
                    version_main = int(v)
            except (ValueError, TypeError):
                pass
            
            print(f"[INFO] Starting Chrome (version {version_main}). Set CHROME_VERSION_MAIN if your Chrome is different.")
            self.driver = uc.Chrome(options=options, version_main=version_main)
            self.driver.execute_cdp_cmd("Network.enable", {})
            self.driver.get(f"{BASE_URL}/login")
            
            # Wait for login form (and Cloudflare to finish) - match API scraper exactly
            email_selectors = "input[type='email'], input[name='identifier'], input[name='email'], input[type='text']"
            wait = WebDriverWait(self.driver, 45)
            email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, email_selectors)))
            time.sleep(0.5)  # Small delay like API scraper
            password_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            
            email_input.clear()
            email_input.send_keys(EMAIL)
            password_input.clear()
            password_input.send_keys(PASSWORD)
            
            # Submit (form submit or button click) - match API scraper
            try:
                password_input.submit()
            except Exception:
                btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button.btn-primary, a[type='submit']")
                btn.click()
            
            # Wait for success: URL contains revision/dashboard or token in storage - match API scraper
            def _success(d):
                url = d.current_url or ""
                if "revision" in url or "dashboard" in url or "/app" in url:
                    return True
                tok = d.execute_script(
                    "return (typeof localStorage !== 'undefined' && (localStorage.getItem('token') || localStorage.getItem('accessToken') || localStorage.getItem('jwt'))) "
                    "|| (typeof sessionStorage !== 'undefined' && (sessionStorage.getItem('token') || sessionStorage.getItem('accessToken') || sessionStorage.getItem('jwt')));"
                )
                return bool(tok)
            
            wait.until(_success)
            time.sleep(1)
            
            # Get cookies for requests session
            for cookie in self.driver.get_cookies():
                self.session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", ".medlibro.co"))
            
            # Initialize asset downloader with cookies
            self.asset_downloader = AssetDownloader(self.driver.get_cookies())
            
            print("[OK] Login successful!")
            return True
        except Exception as e:
            print(f"[ERROR] Login failed: {e}")
            return False
    
    def should_skip_url(self, url):
        """Check if URL should be skipped."""
        parsed = urlparse(url)
        if parsed.netloc and "medlibro.co" not in parsed.netloc:
            return True
        for pattern in SKIP_PATTERNS:
            if pattern in url:
                return True
        return False
    
    def get_page_filename(self, url):
        """Get filename for saving HTML page."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        
        if not path:
            path = "index"
        
        # Clean path
        path = path.replace("..", "").replace("//", "/")
        path = unquote(path)
        
        # Replace invalid characters
        path = re.sub(r'[<>:"|?*]', '_', path)
        
        # Ensure .html extension
        if not path.endswith(".html"):
            if path.endswith("/"):
                path = path[:-1]
            path += ".html"
        
        return HTML_DIR / path
    
    def fix_asset_urls(self, html_content, base_url, saved_assets):
        """Fix asset URLs in HTML to point to local files."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Fix CSS links
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href")
            if href:
                full_url = urljoin(base_url, href)
                if full_url in saved_assets:
                    # Convert to relative path
                    asset_path = saved_assets[full_url]
                    relative_path = Path("../assets") / asset_path.relative_to(ASSETS_DIR)
                    link["href"] = str(relative_path).replace("\\", "/")
        
        # Fix JS scripts
        for script in soup.find_all("script", src=True):
            src = script.get("src")
            if src:
                full_url = urljoin(base_url, src)
                if full_url in saved_assets:
                    asset_path = saved_assets[full_url]
                    relative_path = Path("../assets") / asset_path.relative_to(ASSETS_DIR)
                    script["src"] = str(relative_path).replace("\\", "/")
        
        # Fix images
        for img in soup.find_all("img", src=True):
            src = img.get("src")
            if src:
                full_url = urljoin(base_url, src)
                if full_url in saved_assets:
                    asset_path = saved_assets[full_url]
                    relative_path = Path("../assets") / asset_path.relative_to(ASSETS_DIR)
                    img["src"] = str(relative_path).replace("\\", "/")
        
        return str(soup)
    
    def scrape_page(self, url):
        """Scrape a single page."""
        if url in self.scraped_pages:
            return None
        
        if self.should_skip_url(url):
            return None
        
        print(f"[INFO] Scraping: {url}")
        self.scraped_pages.add(url)
        
        try:
            # Navigate to page
            self.driver.get(url)
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Wait a bit more for dynamic content
            time.sleep(1)
            
            # Get page source
            html_content = self.driver.page_source
            
            # Extract assets
            assets = self.asset_downloader.extract_assets_from_html(html_content, url)
            
            # Download assets
            saved_assets = {}
            for asset_url in assets:
                saved_path = self.asset_downloader.download_asset(asset_url)
                if saved_path:
                    saved_assets[asset_url] = saved_path
            
            # Fix asset URLs in HTML
            fixed_html = self.fix_asset_urls(html_content, url, saved_assets)
            
            # Save HTML
            html_path = self.get_page_filename(url)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(fixed_html)
            
            page_info = {
                "url": url,
                "html_path": str(html_path.relative_to(HTML_DIR.parent)),
                "assets_count": len(saved_assets),
                "title": self.driver.title,
            }
            
            self.page_info.append(page_info)
            return page_info
        except Exception as e:
            print(f"[WARNING] Failed to scrape {url}: {e}")
            return None
    
    def scrape_site(self, urls_to_scrape):
        """Scrape multiple pages."""
        if not self.login():
            return None
        
        print()
        print("=" * 70)
        print("SCRAPING WEBSITE")
        print("=" * 70)
        print()
        
        scraped = []
        for url in tqdm(urls_to_scrape[:MAX_PAGES], desc="Scraping pages"):
            info = self.scrape_page(url)
            if info:
                scraped.append(info)
            time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # Save index
        index_path = HTML_DIR.parent / "scrape_index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump({
                "base_url": BASE_URL,
                "total_pages": len(scraped),
                "pages": scraped
            }, f, indent=2, ensure_ascii=False)
        
        print()
        print(f"[OK] Scraped {len(scraped)} pages")
        print(f"[OK] Index saved to {index_path}")
        
        return scraped
    
    def close(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()


if __name__ == "__main__":
    # Load sitemap if exists
    sitemap_path = Path(__file__).parent / "sitemap.json"
    urls_to_scrape = []
    
    if sitemap_path.exists():
        print(f"[INFO] Loading sitemap from {sitemap_path}")
        with open(sitemap_path, "r", encoding="utf-8") as f:
            sitemap = json.load(f)
            urls_to_scrape = sitemap.get("urls", [])
    else:
        print("[INFO] No sitemap found. Using default URLs.")
        urls_to_scrape = [
            f"{BASE_URL}/",
            f"{BASE_URL}/dashboard",
            f"{BASE_URL}/revision",
            f"{BASE_URL}/courses",
            f"{BASE_URL}/profile",
        ]
    
    scraper = WebsiteScraper()
    try:
        scraper.scrape_site(urls_to_scrape)
    finally:
        scraper.close()
