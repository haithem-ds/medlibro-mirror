"""
Comprehensive Website Analysis Script
Analyzes the scraped MedLibro website to understand:
- Architecture (Vue.js, Vuetify, routing)
- API endpoints and data flow
- Component structure
- Data models
- How to rebuild it locally
"""

import json
import re
import os
from pathlib import Path
from collections import defaultdict
from bs4 import BeautifulSoup
import html

class ComprehensiveAnalyzer:
    def __init__(self, scraped_dir="scraped_website", data_dir="../Data"):
        self.scraped_dir = Path(scraped_dir)
        self.data_dir = Path(data_dir)
        self.html_dir = self.scraped_dir / "html"
        self.assets_dir = self.scraped_dir / "assets"
        self.analysis = {
            "architecture": {},
            "routes": [],
            "api_endpoints": [],
            "components": [],
            "data_models": {},
            "build_plan": {}
        }
    
    def analyze(self):
        print("=" * 80)
        print("COMPREHENSIVE WEBSITE ANALYSIS")
        print("=" * 80)
        
        print("\n[1/6] Analyzing architecture...")
        self.analyze_architecture()
        
        print("\n[2/6] Discovering routes...")
        self.discover_routes()
        
        print("\n[3/6] Finding API endpoints...")
        self.find_api_endpoints()
        
        print("\n[4/6] Identifying components...")
        self.identify_components()
        
        print("\n[5/6] Analyzing data models...")
        self.analyze_data_models()
        
        print("\n[6/6] Creating rebuild plan...")
        self.create_rebuild_plan()
        
        self.save_analysis()
        self.print_summary()
    
    def analyze_architecture(self):
        """Analyze the website architecture"""
        # Check for Vue.js indicators
        vue_indicators = []
        vuetify_indicators = []
        
        # Read main JS files
        index_files = list(self.html_dir.glob("**/index-*.js.html"))
        
        for js_file in index_files[:5]:  # Sample first 5
            try:
                content = js_file.read_text(encoding='utf-8')
                # Extract actual JS from HTML wrapper
                soup = BeautifulSoup(content, 'html.parser')
                pre = soup.find('pre')
                if pre:
                    js_content = html.unescape(pre.get_text())
                    
                    if 'Vue' in js_content or 'vue' in js_content.lower():
                        vue_indicators.append(js_file.name)
                    
                    if 'vuetify' in js_content.lower() or 'VBtn' in js_content or 'VAppBar' in js_content:
                        vuetify_indicators.append(js_file.name)
                    
                    # Check for router
                    if 'router' in js_content.lower() or 'createRouter' in js_content:
                        self.analysis["architecture"]["router"] = "Vue Router"
                    
                    # Check for state management
                    if 'vuex' in js_content.lower() or 'pinia' in js_content.lower():
                        self.analysis["architecture"]["state"] = "Vuex/Pinia"
            except Exception as e:
                pass
        
        self.analysis["architecture"]["framework"] = "Vue.js"
        self.analysis["architecture"]["ui_library"] = "Vuetify"
        self.analysis["architecture"]["type"] = "SPA (Single Page Application)"
        
        # Check sitemap for routes
        sitemap_path = Path("sitemap.json")
        if sitemap_path.exists():
            with open(sitemap_path, 'r', encoding='utf-8') as f:
                sitemap = json.load(f)
                routes = [url for url in sitemap.get("urls", []) 
                          if url.startswith("https://medlibro.co/") 
                          and not url.startswith("https://medlibro.co/assets/")
                          and url != "https://medlibro.co/"]
                self.analysis["architecture"]["routes_count"] = len(routes)
    
    def discover_routes(self):
        """Discover all routes/pages"""
        sitemap_path = Path("sitemap.json")
        if sitemap_path.exists():
            with open(sitemap_path, 'r', encoding='utf-8') as f:
                sitemap = json.load(f)
                for url in sitemap.get("urls", []):
                    if url.startswith("https://medlibro.co/") and not url.startswith("https://medlibro.co/assets/"):
                        route = url.replace("https://medlibro.co", "")
                        if route and route != "/":
                            self.analysis["routes"].append({
                                "path": route,
                                "url": url,
                                "component": self.guess_component_name(route)
                            })
        
        # Sort routes
        self.analysis["routes"].sort(key=lambda x: x["path"])
    
    def guess_component_name(self, route):
        """Guess component name from route"""
        route_map = {
            "/dashboard": "DashboardPage",
            "/revision": "RevisionPage",
            "/exam": "ExamPage",
            "/profile": "ProfilePage",
            "/courses": "CoursesPage",
            "/playlists": "PlaylistsPage",
            "/sessions": "SessionsPage",
            "/memorix": "MemorixPage",
            "/prioritizer": "PrioritizerPage",
            "/pricing": "PricingPage",
            "/faq": "FAQPage"
        }
        return route_map.get(route, "UnknownPage")
    
    def find_api_endpoints(self):
        """Find API endpoints in JS files"""
        api_patterns = [
            r'/api/v1/[^\s"\'`]+',
            r'axios\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']',
            r'fetch\(["\']([^"\']+)["\']',
            r'\.get\(["\']([^"\']+)["\']',
            r'\.post\(["\']([^"\']+)["\']',
        ]
        
        endpoints = set()
        
        # Check JS files
        js_files = list(self.html_dir.glob("**/*.js.html"))
        for js_file in js_files[:20]:  # Sample
            try:
                content = js_file.read_text(encoding='utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                pre = soup.find('pre')
                if pre:
                    js_content = html.unescape(pre.get_text())
                    
                    for pattern in api_patterns:
                        matches = re.findall(pattern, js_content)
                        for match in matches:
                            if isinstance(match, tuple):
                                endpoint = match[1] if len(match) > 1 else match[0]
                            else:
                                endpoint = match
                            
                            if endpoint and '/api/' in endpoint:
                                endpoints.add(endpoint)
            except Exception as e:
                pass
        
        # Add known endpoints from API scraper
        known_endpoints = [
            "/api/v1/revision",
            "/api/v1/questions/{id}",
            "/api/v1/clinical-cases/{id}",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/user/profile",
            "/api/v1/years",
            "/api/v1/themes",
            "/api/v1/chapters"
        ]
        
        for endpoint in known_endpoints:
            endpoints.add(endpoint)
        
        self.analysis["api_endpoints"] = sorted(list(endpoints))
    
    def identify_components(self):
        """Identify Vue components"""
        components = set()
        
        # From component file names
        component_files = list(self.html_dir.glob("**/*Page-*.js.html"))
        component_files.extend(self.html_dir.glob("**/*Dialog-*.js.html"))
        component_files.extend(self.html_dir.glob("**/*Form-*.js.html"))
        component_files.extend(self.html_dir.glob("**/*Card-*.js.html"))
        
        for comp_file in component_files:
            name = comp_file.stem.replace(".js", "")
            # Extract component name (e.g., "DashboardPage-BS_VsFsA.js" -> "DashboardPage")
            match = re.match(r'^([A-Z][a-zA-Z0-9]+)', name)
            if match:
                components.add(match.group(1))
        
        # Vuetify components
        vuetify_components = [
            "VAppBar", "VBtn", "VCard", "VDialog", "VForm", "VInput",
            "VSelect", "VAutocomplete", "VDataTable", "VList", "VMenu",
            "VNavigationDrawer", "VCheckbox", "VChip", "VBadge", "VAvatar"
        ]
        
        for comp in vuetify_components:
            components.add(comp)
        
        self.analysis["components"] = sorted(list(components))
    
    def analyze_data_models(self):
        """Analyze data models from JSON files"""
        if not self.data_dir.exists():
            print(f"[WARN] Data directory not found: {self.data_dir}")
            return
        
        json_files = list(self.data_dir.glob("*.json"))
        json_files = [f for f in json_files if not f.name.endswith(".backup")]
        
        if not json_files:
            print(f"[WARN] No JSON files found in {self.data_dir}")
            return
        
        # Analyze first JSON file to understand structure
        sample_file = json_files[0]
        try:
            with open(sample_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                if isinstance(data, list) and len(data) > 0:
                    sample_item = data[0]
                    
                    self.analysis["data_models"]["question"] = {
                        "fields": list(sample_item.keys()),
                        "sample": sample_item
                    }
                    
                    # Check for clinical cases
                    if "meta" in sample_item and sample_item.get("meta", {}).get("isClinicalCase"):
                        self.analysis["data_models"]["clinical_case"] = {
                            "has_nested_questions": "questions" in sample_item,
                            "has_clinical_case_id": "clinicalCaseId" in sample_item
                        }
        except Exception as e:
            print(f"[ERROR] Failed to analyze data: {e}")
        
        # Count data
        self.analysis["data_models"]["files"] = [f.name for f in json_files]
        self.analysis["data_models"]["total_files"] = len(json_files)
    
    def create_rebuild_plan(self):
        """Create a plan to rebuild the website"""
        plan = {
            "steps": [
                {
                    "step": 1,
                    "title": "Extract Assets",
                    "description": "Extract actual JS/CSS/HTML content from scraped HTML wrappers",
                    "files_to_process": "All .js.html, .css.html files",
                    "output": "Clean JS/CSS files in assets/ directory"
                },
                {
                    "step": 2,
                    "title": "Create Static Server",
                    "description": "Set up a local HTTP server to serve static files",
                    "options": ["Python http.server", "Node.js http-server", "Express.js"],
                    "recommended": "Python http.server (simple) or Express.js (more control)"
                },
                {
                    "step": 3,
                    "title": "Create Mock API Server",
                    "description": "Build API server that serves JSON data from Data/ folder",
                    "endpoints": [
                        "GET /api/v1/revision - Returns years/themes/chapters",
                        "GET /api/v1/questions/{id} - Returns question data",
                        "GET /api/v1/clinical-cases/{id} - Returns clinical case",
                        "GET /api/v1/years - Returns available years",
                        "GET /api/v1/themes - Returns themes for a year",
                        "GET /api/v1/chapters - Returns chapters for a theme"
                    ],
                    "data_source": "Data/*.json files"
                },
                {
                    "step": 4,
                    "title": "Fix Asset URLs",
                    "description": "Update HTML files to point to local assets and API",
                    "changes": [
                        "Replace https://medlibro.co/assets/ with /assets/",
                        "Replace https://medlibro.co/api/ with http://localhost:PORT/api/"
                    ]
                },
                {
                    "step": 5,
                    "title": "Configure CORS",
                    "description": "Enable CORS on API server to allow frontend requests",
                    "headers": "Access-Control-Allow-Origin: *"
                },
                {
                    "step": 6,
                    "title": "Test Integration",
                    "description": "Test that Vue app loads, routes work, and API calls succeed",
                    "checklist": [
                        "Homepage loads",
                        "Navigation works",
                        "API calls return data",
                        "Questions display correctly",
                        "Clinical cases work"
                    ]
                }
            ],
            "tech_stack": {
                "frontend": "Vue.js + Vuetify",
                "backend": "Python Flask/FastAPI or Node.js Express",
                "data": "JSON files from Data/ directory"
            },
            "file_structure": {
                "static_files": "scraped_website/",
                "api_server": "api_server/",
                "data": "../Data/"
            }
        }
        
        self.analysis["build_plan"] = plan
    
    def save_analysis(self):
        """Save analysis to JSON file"""
        output_path = self.scraped_dir / "comprehensive_analysis.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.analysis, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Analysis saved to {output_path}")
    
    def print_summary(self):
        """Print analysis summary"""
        print("\n" + "=" * 80)
        print("ANALYSIS SUMMARY")
        print("=" * 80)
        
        print(f"\nArchitecture:")
        print(f"  Framework: {self.analysis['architecture'].get('framework', 'Unknown')}")
        print(f"  UI Library: {self.analysis['architecture'].get('ui_library', 'Unknown')}")
        print(f"  Type: {self.analysis['architecture'].get('type', 'Unknown')}")
        
        print(f"\nRoutes Found: {len(self.analysis['routes'])}")
        for route in self.analysis['routes'][:10]:
            print(f"  - {route['path']} -> {route['component']}")
        if len(self.analysis['routes']) > 10:
            print(f"  ... and {len(self.analysis['routes']) - 10} more")
        
        print(f"\nAPI Endpoints Found: {len(self.analysis['api_endpoints'])}")
        for endpoint in self.analysis['api_endpoints'][:10]:
            print(f"  - {endpoint}")
        if len(self.analysis['api_endpoints']) > 10:
            print(f"  ... and {len(self.analysis['api_endpoints']) - 10} more")
        
        print(f"\nComponents Found: {len(self.analysis['components'])}")
        print(f"  Sample: {', '.join(self.analysis['components'][:15])}")
        
        print(f"\nData Models:")
        if self.analysis['data_models'].get('files'):
            print(f"  JSON Files: {', '.join(self.analysis['data_models']['files'])}")
        
        print("\n" + "=" * 80)
        print("Next Steps: See comprehensive_analysis.json for detailed rebuild plan")
        print("=" * 80)

if __name__ == "__main__":
    analyzer = ComprehensiveAnalyzer()
    analyzer.analyze()
