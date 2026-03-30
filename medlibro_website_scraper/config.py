"""
Configuration for MedLibro website scraper.
"""
import os
from pathlib import Path

# Base URL
BASE_URL = "https://medlibro.co"

# Credentials (same as API scraper)
EMAIL = "M.world@hotmail.fr"
PASSWORD = "medlibro"

# Output directories
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "scraped_website"
HTML_DIR = OUTPUT_DIR / "html"
ASSETS_DIR = OUTPUT_DIR / "assets"
CSS_DIR = ASSETS_DIR / "css"
JS_DIR = ASSETS_DIR / "js"
IMAGES_DIR = ASSETS_DIR / "images"
FONTS_DIR = ASSETS_DIR / "fonts"
DATA_DIR = ASSETS_DIR / "data"

# Create directories
for dir_path in [OUTPUT_DIR, HTML_DIR, ASSETS_DIR, CSS_DIR, JS_DIR, IMAGES_DIR, FONTS_DIR, DATA_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Scraping settings
MAX_DEPTH = 10  # Maximum depth to crawl
MAX_PAGES = 1000  # Maximum number of pages to scrape
DELAY_BETWEEN_REQUESTS = 1.0  # Seconds to wait between requests
TIMEOUT = 30  # Request timeout in seconds

# Browser settings
HEADLESS = os.environ.get("HEADLESS", "").strip().lower() in ("1", "true", "yes")
CHROME_VERSION_MAIN = 144  # Chrome version

# File extensions to download
ASSET_EXTENSIONS = {
    "css": [".css"],
    "js": [".js", ".mjs"],
    "images": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp"],
    "fonts": [".woff", ".woff2", ".ttf", ".otf", ".eot"],
    "data": [".json", ".xml", ".csv"],
}

# URLs to skip (patterns)
SKIP_PATTERNS = [
    "/logout",
    "/api/",  # API endpoints (we already have data)
    "/socket.io/",
    "/_next/",  # Next.js internal
    "/static/chunks/",  # Next.js chunks
]

# User agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
