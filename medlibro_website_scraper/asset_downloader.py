"""
Asset downloader - downloads CSS, JS, images, fonts, and other assets.
"""
import os
import re
import requests
from urllib.parse import urljoin, urlparse
from pathlib import Path
from tqdm import tqdm
import time

from config import (
    BASE_URL, ASSETS_DIR, CSS_DIR, JS_DIR, IMAGES_DIR, FONTS_DIR, DATA_DIR,
    ASSET_EXTENSIONS, DELAY_BETWEEN_REQUESTS, TIMEOUT, USER_AGENT
)


class AssetDownloader:
    def __init__(self, session_cookies=None):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.downloaded_assets = set()
        
        # Set cookies if provided
        if session_cookies:
            for cookie in session_cookies:
                self.session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", ".medlibro.co"))
    
    def get_asset_type(self, url):
        """Determine asset type from URL."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        for asset_type, extensions in ASSET_EXTENSIONS.items():
            for ext in extensions:
                if path.endswith(ext):
                    return asset_type
        return None
    
    def get_save_path(self, url, asset_type):
        """Get save path for asset."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        
        # Clean path
        path = path.replace("..", "").replace("//", "/")
        
        if asset_type == "css":
            return CSS_DIR / path
        elif asset_type == "js":
            return JS_DIR / path
        elif asset_type == "images":
            return IMAGES_DIR / path
        elif asset_type == "fonts":
            return FONTS_DIR / path
        elif asset_type == "data":
            return DATA_DIR / path
        else:
            return ASSETS_DIR / path
    
    def download_asset(self, url):
        """Download a single asset."""
        if url in self.downloaded_assets:
            return None
        
        # Make absolute URL
        if not url.startswith("http"):
            url = urljoin(BASE_URL, url)
        
        asset_type = self.get_asset_type(url)
        if not asset_type:
            return None
        
        save_path = self.get_save_path(url, asset_type)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            response = self.session.get(url, timeout=TIMEOUT, stream=True)
            response.raise_for_status()
            
            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            self.downloaded_assets.add(url)
            return save_path
        except Exception as e:
            print(f"[WARNING] Failed to download {url}: {e}")
            return None
    
    def extract_assets_from_html(self, html_content, base_url):
        """Extract asset URLs from HTML content."""
        assets = set()
        
        # CSS files
        css_pattern = r'href=["\']([^"\']+\.css[^"\']*)["\']'
        for match in re.finditer(css_pattern, html_content):
            url = urljoin(base_url, match.group(1))
            assets.add(url)
        
        # JS files
        js_pattern = r'src=["\']([^"\']+\.js[^"\']*)["\']'
        for match in re.finditer(js_pattern, html_content):
            url = urljoin(base_url, match.group(1))
            assets.add(url)
        
        # Images
        img_pattern = r'src=["\']([^"\']+\.(?:jpg|jpeg|png|gif|svg|webp|ico)[^"\']*)["\']'
        for match in re.finditer(img_pattern, html_content):
            url = urljoin(base_url, match.group(1))
            assets.add(url)
        
        # Background images in CSS
        bg_pattern = r'url\(["\']?([^"\']+)["\']?\)'
        for match in re.finditer(bg_pattern, html_content):
            url = urljoin(base_url, match.group(1))
            if any(url.lower().endswith(ext) for ext in ASSET_EXTENSIONS["images"] + ASSET_EXTENSIONS["fonts"]):
                assets.add(url)
        
        # Fonts
        font_pattern = r'src:\s*url\(["\']?([^"\']+\.(?:woff|woff2|ttf|otf|eot)[^"\']*)["\']?\)'
        for match in re.finditer(font_pattern, html_content):
            url = urljoin(base_url, match.group(1))
            assets.add(url)
        
        return assets
    
    def download_assets(self, asset_urls, show_progress=True):
        """Download multiple assets."""
        if show_progress:
            iterator = tqdm(asset_urls, desc="Downloading assets")
        else:
            iterator = asset_urls
        
        downloaded = []
        for url in iterator:
            path = self.download_asset(url)
            if path:
                downloaded.append(path)
            time.sleep(DELAY_BETWEEN_REQUESTS)
        
        return downloaded
