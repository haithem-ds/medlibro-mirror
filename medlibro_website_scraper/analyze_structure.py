"""
Analyze scraped website structure to understand functionality and architecture.
"""
import json
import re
from pathlib import Path
from collections import defaultdict
from bs4 import BeautifulSoup
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class WebsiteAnalyzer:
    def __init__(self, html_dir, assets_dir):
        self.html_dir = Path(html_dir)
        self.assets_dir = Path(assets_dir)
        self.analysis = {
            "pages": [],
            "routes": [],
            "components": [],
            "api_endpoints": [],
            "javascript_frameworks": [],
            "css_frameworks": [],
            "features": [],
        }
    
    def analyze_html_file(self, html_path):
        """Analyze a single HTML file."""
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            soup = BeautifulSoup(content, "html.parser")
            
            page_info = {
                "file": str(html_path.relative_to(self.html_dir)),
                "title": soup.title.string if soup.title else "No title",
                "scripts": [],
                "stylesheets": [],
                "api_calls": [],
                "routes": [],
                "components": [],
            }
            
            # Extract scripts
            for script in soup.find_all("script"):
                src = script.get("src")
                if src:
                    page_info["scripts"].append(src)
                elif script.string:
                    # Check for API calls in inline scripts
                    api_pattern = r'["\'](/api/[^"\']+)["\']'
                    api_calls = re.findall(api_pattern, script.string)
                    page_info["api_calls"].extend(api_calls)
                    
                    # Check for routes
                    route_pattern = r'["\'](/[^"\']+)["\']'
                    routes = re.findall(route_pattern, script.string)
                    page_info["routes"].extend([r for r in routes if not r.startswith("/api/")])
            
            # Extract stylesheets
            for link in soup.find_all("link", rel="stylesheet"):
                href = link.get("href")
                if href:
                    page_info["stylesheets"].append(href)
            
            # Detect frameworks
            if "next.js" in content.lower() or "_next" in content:
                self.analysis["javascript_frameworks"].append("Next.js")
            if "react" in content.lower():
                self.analysis["javascript_frameworks"].append("React")
            if "vue" in content.lower():
                self.analysis["javascript_frameworks"].append("Vue.js")
            if "angular" in content.lower():
                self.analysis["javascript_frameworks"].append("Angular")
            
            if "bootstrap" in content.lower():
                self.analysis["css_frameworks"].append("Bootstrap")
            if "tailwind" in content.lower():
                self.analysis["css_frameworks"].append("Tailwind CSS")
            if "material" in content.lower():
                self.analysis["css_frameworks"].append("Material Design")
            
            # Detect features
            if "revision" in html_path.name.lower():
                self.analysis["features"].append("Revision/QCM System")
            if "dashboard" in html_path.name.lower():
                self.analysis["features"].append("Dashboard")
            if "courses" in html_path.name.lower():
                self.analysis["features"].append("Courses")
            if "profile" in html_path.name.lower():
                self.analysis["features"].append("User Profile")
            
            return page_info
        except Exception as e:
            print(f"[WARNING] Failed to analyze {html_path}: {e}")
            return None
    
    def analyze_all(self):
        """Analyze all HTML files."""
        print("=" * 70)
        print("ANALYZING WEBSITE STRUCTURE")
        print("=" * 70)
        print()
        
        html_files = list(self.html_dir.rglob("*.html"))
        print(f"[INFO] Found {len(html_files)} HTML files")
        print()
        
        all_api_endpoints = set()
        all_routes = set()
        
        for html_file in html_files:
            page_info = self.analyze_html_file(html_file)
            if page_info:
                self.analysis["pages"].append(page_info)
                all_api_endpoints.update(page_info["api_calls"])
                all_routes.update(page_info["routes"])
        
        self.analysis["api_endpoints"] = sorted(list(all_api_endpoints))
        self.analysis["routes"] = sorted(list(all_routes))
        self.analysis["javascript_frameworks"] = list(set(self.analysis["javascript_frameworks"]))
        self.analysis["css_frameworks"] = list(set(self.analysis["css_frameworks"]))
        self.analysis["features"] = list(set(self.analysis["features"]))
        
        return self.analysis
    
    def print_summary(self):
        """Print analysis summary."""
        print("=" * 70)
        print("ANALYSIS SUMMARY")
        print("=" * 70)
        print()
        
        print(f"Total Pages: {len(self.analysis['pages'])}")
        print()
        
        print("JavaScript Frameworks:")
        for fw in self.analysis["javascript_frameworks"]:
            print(f"  - {fw}")
        print()
        
        print("CSS Frameworks:")
        for fw in self.analysis["css_frameworks"]:
            print(f"  - {fw}")
        print()
        
        print("Features Detected:")
        for feature in self.analysis["features"]:
            print(f"  - {feature}")
        print()
        
        print(f"API Endpoints Found: {len(self.analysis['api_endpoints'])}")
        if self.analysis["api_endpoints"]:
            print("  Sample endpoints:")
            for endpoint in self.analysis["api_endpoints"][:10]:
                print(f"    - {endpoint}")
            if len(self.analysis["api_endpoints"]) > 10:
                print(f"    ... and {len(self.analysis['api_endpoints']) - 10} more")
        print()
        
        print(f"Routes Found: {len(self.analysis['routes'])}")
        if self.analysis["routes"]:
            print("  Sample routes:")
            for route in self.analysis["routes"][:10]:
                print(f"    - {route}")
            if len(self.analysis["routes"]) > 10:
                print(f"    ... and {len(self.analysis['routes']) - 10} more")
        print()
    
    def save_analysis(self, output_file="analysis.json"):
        """Save analysis to JSON file."""
        output_path = Path(__file__).parent / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.analysis, f, indent=2, ensure_ascii=False)
        print(f"[OK] Analysis saved to {output_path}")
        return output_path


if __name__ == "__main__":
    from config import HTML_DIR, ASSETS_DIR
    
    analyzer = WebsiteAnalyzer(HTML_DIR, ASSETS_DIR)
    analyzer.analyze_all()
    analyzer.print_summary()
    analyzer.save_analysis()
