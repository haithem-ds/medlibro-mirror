# Quick Start Guide

## Step-by-Step Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Scraper

**Option A: Using Batch File (Windows)**
```bash
run_scraper.bat
```

**Option B: Manual Steps**

**Step 1: Map the Site**
```bash
python site_mapper.py
```
This discovers all pages and saves them to `sitemap.json`.

**Step 2: Scrape the Website**
```bash
python website_scraper.py
```
This downloads all HTML pages and assets.

**Step 3: Analyze Structure**
```bash
python analyze_structure.py
```
This analyzes the scraped website and creates `analysis.json`.

### 3. Review Results

After scraping, you'll find:

- `scraped_website/html/` - All HTML pages
- `scraped_website/assets/` - All CSS, JS, images, fonts
- `sitemap.json` - List of all discovered URLs
- `scrape_index.json` - Index of scraped pages
- `analysis.json` - Analysis of website structure

## Understanding the Website

The analysis script will tell you:
- What JavaScript frameworks are used (React, Next.js, etc.)
- What CSS frameworks are used (Bootstrap, Tailwind, etc.)
- What API endpoints are called
- What routes/pages exist
- What features are present

## Next Steps

1. Review `analysis.json` to understand the architecture
2. Open HTML files in browser to see the structure
3. Check JavaScript files to understand functionality
4. Review CSS to understand styling approach
5. Map API endpoints to understand data flow

## Tips

- Start with a small number of pages (set `MAX_PAGES` in `config.py`)
- Use headless mode for faster scraping (`HEADLESS = True` in `config.py`)
- Check `sitemap.json` before scraping to see what will be downloaded
- Review `scrape_index.json` after scraping to see what was downloaded
