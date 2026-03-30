"""
Site mapper - discovers all pages and routes in MedLibro website.
"""
import re
import json
import time
from urllib.parse import urljoin, urlparse
from collections import deque
from pathlib import Path
import sys

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:
    print("[ERROR] Missing dependencies. Install with: pip install -r requirements.txt")
    sys.exit(1)

from config import BASE_URL, EMAIL, PASSWORD, HEADLESS, CHROME_VERSION_MAIN, DELAY_BETWEEN_REQUESTS, SKIP_PATTERNS


class SiteMapper:
    def __init__(self):
        self.visited_urls = set()
        self.discovered_urls = set()
        self.url_queue = deque()
        self.driver = None
        self.session_cookies = None
        
    def should_skip_url(self, url):
        """Check if URL should be skipped."""
        parsed = urlparse(url)
        if parsed.netloc and "medlibro.co" not in parsed.netloc:
            return True
        for pattern in SKIP_PATTERNS:
            if pattern in url:
                return True
        return False
    
    def login(self):
        """Login to MedLibro and get session cookies."""
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
            
            # Get cookies
            self.session_cookies = self.driver.get_cookies()
            print("[OK] Login successful!")
            return True
        except Exception as e:
            print(f"[ERROR] Login failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def extract_links(self, html_content, current_url):
        """Extract all links from HTML content."""
        links = set()
        
        # Extract href links
        href_pattern = r'href=["\']([^"\']+)["\']'
        for match in re.finditer(href_pattern, html_content):
            link = match.group(1)
            full_url = urljoin(current_url, link)
            if not self.should_skip_url(full_url):
                links.add(full_url)
        
        # Extract src links (for JS, images, etc.)
        src_pattern = r'src=["\']([^"\']+)["\']'
        for match in re.finditer(src_pattern, html_content):
            link = match.group(1)
            full_url = urljoin(current_url, link)
            if not self.should_skip_url(full_url):
                links.add(full_url)
        
        # Extract data attributes
        data_src_pattern = r'data-src=["\']([^"\']+)["\']'
        for match in re.finditer(data_src_pattern, html_content):
            link = match.group(1)
            full_url = urljoin(current_url, link)
            if not self.should_skip_url(full_url):
                links.add(full_url)
        
        return links
    
    def discover_page(self, url):
        """Discover links on a page."""
        if url in self.visited_urls:
            return set()
        
        if self.should_skip_url(url):
            return set()
        
        print(f"[INFO] Discovering: {url}")
        self.visited_urls.add(url)
        
        try:
            self.driver.get(url)
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Get page source
            html_content = self.driver.page_source
            
            # Extract links
            links = self.extract_links(html_content, url)
            
            # Add to discovered URLs
            for link in links:
                if link not in self.discovered_urls:
                    self.discovered_urls.add(link)
                    if link.startswith(BASE_URL) and link not in self.visited_urls:
                        self.url_queue.append(link)
            
            return links
        except Exception as e:
            print(f"[WARNING] Failed to discover {url}: {e}")
            return set()
    
    def map_site(self, start_urls=None, max_pages=100):
        """Map the entire site starting from given URLs."""
        if not self.login():
            return None
        
        if start_urls is None:
            start_urls = [
                f"{BASE_URL}/",
                f"{BASE_URL}/dashboard",
                f"{BASE_URL}/revision",
                f"{BASE_URL}/courses",
                f"{BASE_URL}/profile",
            ]
        
        # Add start URLs to queue
        for url in start_urls:
            if not self.should_skip_url(url):
                self.url_queue.append(url)
                self.discovered_urls.add(url)
        
        pages_discovered = 0
        while self.url_queue and pages_discovered < max_pages:
            url = self.url_queue.popleft()
            links = self.discover_page(url)
            pages_discovered += 1
            
            if pages_discovered % 10 == 0:
                print(f"[INFO] Discovered {pages_discovered} pages, {len(self.url_queue)} in queue")
        
        return {
            "total_pages": len(self.visited_urls),
            "discovered_urls": list(self.discovered_urls),
            "visited_urls": list(self.visited_urls),
        }
    
    def save_sitemap(self, output_file="sitemap.json"):
        """Save discovered URLs to file."""
        sitemap = {
            "base_url": BASE_URL,
            "total_pages": len(self.discovered_urls),
            "urls": sorted(list(self.discovered_urls)),
        }
        
        output_path = Path(__file__).parent / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sitemap, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Sitemap saved to {output_path}")
        return output_path
    
    def close(self):
        """Close browser."""
        if self.driver:
            self.driver.quit()


if __name__ == "__main__":
    mapper = SiteMapper()
    try:
        print("=" * 70)
        print("MEDLIBRO SITE MAPPER")
        print("=" * 70)
        print()
        
        sitemap = mapper.map_site(max_pages=200)
        
        if sitemap:
            print()
            print(f"[OK] Discovered {sitemap['total_pages']} pages")
            mapper.save_sitemap()
    finally:
        mapper.close()
