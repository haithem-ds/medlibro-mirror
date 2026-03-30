"""
Extract actual JS/CSS/HTML content from scraped HTML wrappers
"""

import re
from pathlib import Path
from bs4 import BeautifulSoup
import html
import shutil

class AssetExtractor:
    def __init__(self, scraped_dir="scraped_website"):
        self.scraped_dir = Path(scraped_dir)
        self.html_dir = self.scraped_dir / "html"
        self.assets_dir = self.scraped_dir / "assets"
        self.extracted_dir = self.scraped_dir / "extracted_assets"
        
        # Create directories
        self.extracted_dir.mkdir(exist_ok=True)
        (self.extracted_dir / "js").mkdir(exist_ok=True)
        (self.extracted_dir / "css").mkdir(exist_ok=True)
        (self.extracted_dir / "images").mkdir(exist_ok=True, parents=True)
        (self.extracted_dir / "fonts").mkdir(exist_ok=True)
    
    def extract_all(self):
        """Extract all assets"""
        print("=" * 80)
        print("EXTRACTING ASSETS FROM HTML WRAPPERS")
        print("=" * 80)
        
        # Extract JS files
        print("\n[1/4] Extracting JavaScript files...")
        js_files = list(self.html_dir.glob("**/*.js.html"))
        js_count = self.extract_js_files(js_files)
        
        # Extract CSS files
        print("\n[2/4] Extracting CSS files...")
        css_files = list(self.html_dir.glob("**/*.css.html"))
        css_count = self.extract_css_files(css_files)
        
        # Copy image files (already extracted by asset_downloader)
        print("\n[3/4] Copying image files...")
        image_count = self.copy_images()
        
        # Extract HTML pages (actual pages, not assets)
        print("\n[4/4] Extracting HTML pages...")
        html_count = self.extract_html_pages()
        
        print("\n" + "=" * 80)
        print("EXTRACTION SUMMARY")
        print("=" * 80)
        print(f"JavaScript files: {js_count}")
        print(f"CSS files: {css_count}")
        print(f"Image files: {image_count}")
        print(f"HTML pages: {html_count}")
        print(f"\n[OK] Assets extracted to: {self.extracted_dir}")
        print("=" * 80)
    
    def extract_js_files(self, js_files):
        """Extract JavaScript from HTML wrappers"""
        count = 0
        for js_file in js_files:
            try:
                content = js_file.read_text(encoding='utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                pre = soup.find('pre')
                
                if pre:
                    js_content = html.unescape(pre.get_text())
                    # Save to extracted directory
                    relative_path = js_file.relative_to(self.html_dir)
                    output_path = self.extracted_dir / "js" / relative_path.name.replace(".html", "")
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(js_content, encoding='utf-8')
                    count += 1
            except Exception as e:
                print(f"[WARN] Failed to extract {js_file.name}: {e}")
        
        return count
    
    def extract_css_files(self, css_files):
        """Extract CSS from HTML wrappers"""
        count = 0
        for css_file in css_files:
            try:
                content = css_file.read_text(encoding='utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                pre = soup.find('pre')
                
                if pre:
                    css_content = html.unescape(pre.get_text())
                    # Save to extracted directory
                    relative_path = css_file.relative_to(self.html_dir)
                    output_path = self.extracted_dir / "css" / relative_path.name.replace(".html", "")
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(css_content, encoding='utf-8')
                    count += 1
            except Exception as e:
                print(f"[WARN] Failed to extract {css_file.name}: {e}")
        
        return count
    
    def copy_images(self):
        """Copy image files from assets directory"""
        count = 0
        images_dir = self.assets_dir / "images"
        
        if images_dir.exists():
            for img_file in images_dir.rglob("*"):
                if img_file.is_file():
                    try:
                        relative_path = img_file.relative_to(images_dir)
                        output_path = self.extracted_dir / "images" / relative_path
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(img_file, output_path)
                        count += 1
                    except Exception as e:
                        print(f"[WARN] Failed to copy {img_file.name}: {e}")
        
        return count
    
    def extract_html_pages(self):
        """Extract actual HTML pages (not asset wrappers)"""
        count = 0
        
        # Find actual page HTML files (not in assets subdirectory)
        # These should be the root pages like index.html, dashboard.html, etc.
        # But since it's a SPA, we mainly need the index.html
        
        # Check if there's a root index or main HTML file
        # For Vue SPA, we need to find the main HTML entry point
        # It might be saved as "index.html" or similar
        
        # For now, create a basic index.html that loads the Vue app
        index_html = self.create_spa_index()
        output_path = self.extracted_dir / "index.html"
        output_path.write_text(index_html, encoding='utf-8')
        count += 1
        
        return count
    
    def create_spa_index(self):
        """Create the main index.html for Vue SPA"""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MedLibro - Local</title>
    <link rel="icon" href="/assets/images/favicon.ico">
    <!-- Vuetify CSS -->
    <link href="https://cdn.jsdelivr.net/npm/vuetify@2/dist/vuetify.min.css" rel="stylesheet">
    <!-- Material Design Icons -->
    <link href="https://cdn.jsdelivr.net/npm/@mdi/font@6.x/css/materialdesignicons.min.css" rel="stylesheet">
    <!-- Roboto Font -->
    <link href="https://fonts.googleapis.com/css?family=Roboto:100,300,400,500,700,900" rel="stylesheet">
</head>
<body>
    <div id="app"></div>
    
    <!-- Vue.js -->
    <script src="https://cdn.jsdelivr.net/npm/vue@2/dist/vue.js"></script>
    <!-- Vue Router -->
    <script src="https://cdn.jsdelivr.net/npm/vue-router@3/dist/vue-router.js"></script>
    <!-- Vuetify -->
    <script src="https://cdn.jsdelivr.net/npm/vuetify@2/dist/vuetify.js"></script>
    <!-- Axios -->
    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    
    <!-- Application Scripts -->
    <!-- Note: In production, these would be bundled. For local rebuild, -->
    <!-- we'll need to load the extracted JS files or create a simplified version -->
    
    <script>
        // API Base URL - point to local API server
        window.API_BASE_URL = 'http://localhost:5000';
        
        // Initialize Vue app
        // This is a placeholder - actual app initialization would come from extracted JS
        console.log('MedLibro Local - Ready to initialize Vue app');
    </script>
</body>
</html>"""

if __name__ == "__main__":
    extractor = AssetExtractor()
    extractor.extract_all()
