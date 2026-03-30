# MedLibro Website Scraper

Complete website scraper for MedLibro that downloads HTML, CSS, JS, images, fonts, and all assets to create a local mirror of the website.

## Features

- **Site Mapping**: Discovers all pages and routes in the website
- **HTML Scraping**: Downloads all HTML pages with proper structure
- **Asset Download**: Downloads CSS, JS, images, fonts, and other assets
- **URL Fixing**: Automatically fixes asset URLs in HTML to point to local files
- **Authentication**: Handles login and maintains session
- **Structure Preservation**: Maintains directory structure similar to original site

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Step 1: Map the Site (Discover All Pages)

```bash
python site_mapper.py
```

This will:
- Login to MedLibro
- Navigate through pages
- Discover all links
- Save `sitemap.json` with all discovered URLs

### Step 2: Scrape the Website

```bash
python website_scraper.py
```

This will:
- Load URLs from `sitemap.json` (or use default URLs)
- Download HTML for each page
- Download all CSS, JS, images, fonts, and assets
- Fix URLs in HTML to point to local assets
- Save everything to `scraped_website/` directory

### Step 3: Analyze Structure

The scraper creates:
- `scraped_website/html/` - All HTML pages
- `scraped_website/assets/css/` - CSS files
- `scraped_website/assets/js/` - JavaScript files
- `scraped_website/assets/images/` - Images
- `scraped_website/assets/fonts/` - Fonts
- `scraped_website/scrape_index.json` - Index of all scraped pages

## Configuration

Edit `config.py` to customize:
- `MAX_PAGES` - Maximum pages to scrape
- `DELAY_BETWEEN_REQUESTS` - Delay between requests
- `HEADLESS` - Run browser in headless mode
- `SKIP_PATTERNS` - URL patterns to skip

## Output Structure

```
scraped_website/
├── html/
│   ├── index.html
│   ├── dashboard.html
│   ├── revision.html
│   └── ...
├── assets/
│   ├── css/
│   ├── js/
│   ├── images/
│   └── fonts/
└── scrape_index.json
```

## Notes

- The scraper uses Selenium to handle JavaScript-heavy pages
- All asset URLs in HTML are automatically fixed to point to local files
- Session cookies are maintained throughout the scraping process
- Large sites may take a while to scrape completely
