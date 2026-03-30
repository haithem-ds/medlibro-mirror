"""
DEPRECATED: Old "MedLibro - Local" app (extracted_assets).
Use serve_mirror.py instead for the exact MedLibro design with login.

This script serves the OLD dashboard ("Welcome. This version uses your scraped data").
To get the real MedLibro design + login page, run: python serve_mirror.py
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os
import sys

class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Custom handler with CORS and proper MIME types"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / "scraped_website" / "extracted_assets"), **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def guess_type(self, path):
        """Override to set proper MIME types. Python 3.10+ returns a single string, not (type, encoding)."""
        ctype = super().guess_type(path)
        if isinstance(ctype, tuple):
            ctype = ctype[0]

        if path.endswith('.js'):
            return 'application/javascript'
        if path.endswith('.css'):
            return 'text/css'
        if path.endswith('.json'):
            return 'application/json'

        return ctype

def run_server(port=8080):
    """Run the static file server"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    
    print("=" * 80)
    print("MEDLIBRO STATIC FILE SERVER")
    print("=" * 80)
    print(f"Serving files from: {Path(__file__).parent / 'scraped_website' / 'extracted_assets'}")
    print(f"Server running on: http://localhost:{port}")
    print("=" * 80)
    print("Press Ctrl+C to stop the server")
    print("=" * 80)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Server stopped")
        httpd.shutdown()

if __name__ == '__main__':
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"[WARN] Invalid port '{sys.argv[1]}', using default 8080")
    
    run_server(port)
