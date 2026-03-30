"""
Build the mirror directory: real HTML + all assets at /assets/ and /cf-fonts/ paths.
Run save_real_pages.py first to get real_pages/index.html.
Downloads all assets from the live site so the mirror matches the current design (fonts, CSS, JS).
"""
import os
import shutil
import re
import time
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    requests = None

from config import BASE_URL

PROJECT = Path(__file__).parent
REAL_PAGES = PROJECT / "real_pages"
EXTRACTED = PROJECT / "scraped_website" / "extracted_assets"
MIRROR = PROJECT / "mirror"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REQUEST_DELAY = 0.3
REQUEST_TIMEOUT = 30


def collect_asset_urls_from_html(html_text):
    """Collect all same-origin asset paths from HTML: /assets/*, /cf-fonts/*, /favicon.ico."""
    paths = set()
    # link href and script src
    for pattern in [
        r'<link[^>]+href=["\']([^"\']+)["\']',
        r'<script[^>]+src=["\']([^"\']+)["\']',
        r'href=["\']([^"\']+)["\']',
        r'src=["\']([^"\']+)["\']',
    ]:
        for m in re.finditer(pattern, html_text, re.IGNORECASE):
            href = m.group(1).strip().split("?")[0]
            if href.startswith("/assets/") or href.startswith("/cf-fonts/") or href == "/favicon.ico":
                paths.add(href)
    # url() in inline styles (fonts, etc.)
    for m in re.finditer(r'url\(["\']?([^"\')\s]+)["\']?\)', html_text):
        u = m.group(1).strip().split("?")[0]
        if u.startswith("/assets/") or u.startswith("/cf-fonts/"):
            paths.add(u)
    return paths


def collect_asset_urls_from_js(assets_dir):
    """Extract lazy-loaded chunk paths from main JS (e.g. __vite__mapDeps, import())."""
    paths = set()
    if not assets_dir.exists():
        return paths
    # Match "assets/XXX.js" or "assets/XXX.css" inside JS (Vite dependency map, dynamic imports)
    pattern = re.compile(r'["\']?(assets/[a-zA-Z0-9_.-]+\.(?:js|css))["\']?')
    for js_file in assets_dir.glob("*.js"):
        try:
            text = js_file.read_text(encoding="utf-8", errors="replace")
            for m in pattern.finditer(text):
                p = m.group(1)
                if p.startswith("assets/"):
                    paths.add("/" + p)
        except Exception:
            pass
    return paths


def download_assets_to_mirror(mirror_dir, asset_paths):
    """Download each asset from BASE_URL to mirror_dir, preserving path. Returns (ok_count, fail_count)."""
    if not requests:
        print("[WARN] requests not installed; skipping live asset download. pip install requests")
        return 0, 0
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    ok, fail = 0, 0
    for path in sorted(asset_paths):
        if not path.startswith("/"):
            continue
        url = urljoin(BASE_URL, path)
        # mirror path: /assets/foo.js -> mirror/assets/foo.js; /cf-fonts/v/... -> mirror/cf-fonts/v/...
        local_path = mirror_dir / path.lstrip("/")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            local_path.write_bytes(r.content)
            ok += 1
            if ok <= 3 or ok % 20 == 0 or ok == len(asset_paths):
                print(f"  [OK] {path}")
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            fail += 1
            print(f"  [WARN] {path}: {e}")
    return ok, fail


def patch_js_for_local_api(assets_dir):
    """Patch JS so API and router stay on mirror: API base -> same origin, router base -> /."""
    patched = 0
    for js_file in assets_dir.glob("*.js"):
        try:
            text = js_file.read_text(encoding="utf-8", errors="replace")
            original = text
            # Full API URL "https://medlibro.co/api/v2/..." or "https://www.medlibro.co/api/..." -> "/api/..."
            text = re.sub(
                r'(["\'])https?://(?:www\.)?medlibro\.co(/api[^"\']*)\1',
                r'\1\2\1',
                text,
                flags=re.IGNORECASE
            )
            # "https://medlibro.co/api" or 'https://medlibro.co/api' (no path) -> "/api"
            text = re.sub(
                r'["\']https?://(?:www\.)?[^"/]*medlibro\.co/api["\']',
                '"/api"',
                text,
                flags=re.IGNORECASE
            )
            # baseURL/baseUrl/any base: "https://medlibro.co" -> "" (so /api/v1, /api/v2 go to same origin)
            text = re.sub(
                r'(baseURL|baseUrl)\s*:\s*["\']https?://[^"/]*medlibro\.co/?["\']',
                r'\1: ""',
                text,
                flags=re.IGNORECASE
            )
            # Any standalone "https://medlibro.co" or 'https://medlibro.co' -> "" (API base in axios/utils)
            def _empty_base(m):
                q = m.group(1)
                return q + q  # same-quote empty string
            text = re.sub(
                r'(["\'])https?://(?:www\.)?medlibro\.co/?\1',
                _empty_base,
                text,
                flags=re.IGNORECASE
            )
            # Vue Router / Vite base: createWebHistory("https://medlibro.co") or with www -> createWebHistory("/")
            text = re.sub(
                r'createWebHistory\s*\(\s*["\']https?://(?:www\.)?[^"/]*medlibro\.co/?["\']\s*\)',
                'createWebHistory("/")',
                text,
                flags=re.IGNORECASE
            )
            # base: "https://medlibro.co" or base: 'https://medlibro.co/' -> base: "/"
            text = re.sub(
                r'(\bbase\s*:\s*)["\']https?://[^"/]*medlibro\.co/?["\']',
                r'\1"/"',
                text,
                flags=re.IGNORECASE
            )
            # Template literals: `https://medlibro.co/api/...` -> `/api/...`
            text = re.sub(
                r'`https?://(?:www\.)?medlibro\.co(/api[^`]*)`',
                r'`\1`',
                text,
                flags=re.IGNORECASE
            )
            # Concatenated strings: "https://medlibro.co" + "/api/..." -> "" + "/api/..."
            text = re.sub(
                r'["\']https?://(?:www\.)?medlibro\.co/?["\']\s*\+\s*["\'](/api[^"\']*)["\']',
                r'"" + "\1"',
                text,
                flags=re.IGNORECASE
            )
            # Any remaining "https://medlibro.co/api/..." even without quotes context -> "/api/..."
            text = re.sub(
                r'https?://(?:www\.)?medlibro\.co(/api/[^"\'\s\)\]\}]+)',
                r'\1',
                text,
                flags=re.IGNORECASE
            )
            if text != original:
                js_file.write_text(text, encoding="utf-8")
                patched += 1
        except Exception:
            pass
    if patched:
        print(f"[OK] Patched {patched} JS file(s) for local API and router")
    return patched


def build():
    # CLEAN BUILD: remove old mirror so no stale files
    if MIRROR.exists():
        print("[INFO] Removing old mirror for clean build...")
        shutil.rmtree(MIRROR)
    MIRROR.mkdir(parents=True, exist_ok=True)
    assets_dir = MIRROR / "assets"
    assets_dir.mkdir(exist_ok=True)

    index_src = REAL_PAGES / "index.html"
    if not index_src.exists():
        print("[ERROR] Run save_real_pages.py first to create real_pages/index.html")
        return False

    # 1. Collect all asset URLs from saved real_pages HTML (full design: JS, CSS, fonts, images)
    all_paths = set()
    for html_file in REAL_PAGES.glob("*.html"):
        all_paths |= collect_asset_urls_from_html(html_file.read_text(encoding="utf-8", errors="replace"))
    print(f"[INFO] Found {len(all_paths)} asset(s) to download from live site (design, fonts, JS, CSS)...")

    # 2. Download all assets from live site so mirror matches current design
    if all_paths:
        ok, fail = download_assets_to_mirror(MIRROR, all_paths)
        print(f"[OK] Downloaded {ok} asset(s) from {BASE_URL} (fail: {fail})")
    else:
        print("[WARN] No asset URLs found in real_pages; will use extracted_assets fallback if present.")
    # 2b. Extract lazy-loaded chunk paths from main JS (LoginPage, SignupPage, etc.) and download them
    assets_dir = MIRROR / "assets"
    chunk_paths = collect_asset_urls_from_js(assets_dir)
    if chunk_paths:
        new_paths = chunk_paths - all_paths
        if new_paths:
            print(f"[INFO] Found {len(new_paths)} lazy-load chunk(s) in JS, downloading...")
            ok2, fail2 = download_assets_to_mirror(MIRROR, new_paths)
            print(f"[OK] Downloaded {ok2} chunk(s) (fail: {fail2})")
        all_paths |= chunk_paths

    # 3. Fallback: copy from extracted_assets any missing files (e.g. if download failed or old run)
    for sub in ["js", "css"]:
        src_dir = EXTRACTED / sub
        if not src_dir.exists():
            continue
        for f in src_dir.iterdir():
            if f.is_file() and not (assets_dir / f.name).exists():
                shutil.copy2(f, assets_dir / f.name)
                print(f"  [fallback] {sub}/{f.name}")
    img_src = EXTRACTED / "images"
    if img_src.exists():
        for f in img_src.rglob("*"):
            if f.is_file() and not (assets_dir / f.name).exists():
                shutil.copy2(f, assets_dir / f.name)
    favicon = EXTRACTED / "images" / "favicon.ico"
    if favicon.exists() and not (MIRROR / "favicon.ico").exists():
        shutil.copy2(favicon, MIRROR / "favicon.ico")

    # 4. Copy real index.html, fix DOCTYPE, strip Cloudflare beacon, optionally mock-auth
    shutil.copy2(index_src, MIRROR / "index.html")
    print(f"[OK] Copied {index_src.name} -> mirror/index.html")
    index_path = MIRROR / "index.html"
    html = index_path.read_text(encoding="utf-8", errors="replace")
    if not html.strip().upper().startswith("<!DOCTYPE"):
        html = "<!DOCTYPE html>\n" + html
        index_path.write_text(html, encoding="utf-8")
        print("[OK] Prepend <!DOCTYPE html> for Standards Mode")
    html = index_path.read_text(encoding="utf-8", errors="replace")
    html2 = re.sub(r'<script[^>]*cloudflareinsights\.com/beacon[^>]*>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
    if html2 != html:
        index_path.write_text(html2, encoding="utf-8")
        print("[OK] Removed Cloudflare beacon script")
    use_mock = os.environ.get("MOCK_USER", "").strip() in ("1", "true", "yes")
    boot_script = """<script>
(function(){
  var t='mock_jwt_token_for_local_development';
  var u=JSON.stringify({id:'mock_user_id',email:'user@example.com',name:'Local User',subscription:'premium',emailVerified:true,email_verified:true,validated:true});
  try{
    if(typeof localStorage!=='undefined'){
      localStorage.setItem('token',t);localStorage.setItem('accessToken',t);localStorage.setItem('jwt',t);
      localStorage.setItem('user',u);
    }
    if(typeof sessionStorage!=='undefined'){
      sessionStorage.setItem('token',t);sessionStorage.setItem('accessToken',t);sessionStorage.setItem('jwt',t);
      sessionStorage.setItem('user',u);
    }
  }catch(e){}
})();
</script>
"""
    # Keep links on mirror: rewrite medlibro.co navigation to relative so buttons/links work
    # Also intercept fetch/XMLHttpRequest to rewrite API URLs to same-origin
    link_rewriter = r"""<script>
(function(){
  // Rewrite links
  var r = /^https?:\/\/[^\/]*medlibro\.co(\/.*)?$/i;
  function fix(el){ if(!el) return; var list = el.querySelectorAll ? el.querySelectorAll('a[href]') : []; for(var i=0;i<list.length;i++){ var a=list[i], h=a.getAttribute('href'); if(h&&r.test(h)){ var m=h.match(r); a.setAttribute('href', (m&&m[1]) ? m[1] : '/'); } } }
  function run(){ fix(document.body); }
  function init(){ run(); if(document.body && typeof MutationObserver!=='undefined'){ var obs=new MutationObserver(run); obs.observe(document.body, {childList:true, subtree:true}); } setInterval(run, 2000); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else setTimeout(init, 0);
  
  // Intercept fetch/XMLHttpRequest to rewrite API URLs to same-origin
  var apiRe = /^https?:\/\/(?:www\.)?medlibro\.co(\/api\/.*)$/i;
  if(typeof fetch !== 'undefined') {
    var origFetch = window.fetch;
    window.fetch = function(url, opts) {
      if(typeof url === 'string') {
        var m = url.match(apiRe);
        if(m) url = m[1];
      }
      return origFetch.call(this, url, opts);
    };
  }
  if(typeof XMLHttpRequest !== 'undefined') {
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
      if(typeof url === 'string') {
        var m = url.match(apiRe);
        if(m) url = m[1];
      }
      return origOpen.call(this, method, url, async, user, password);
    };
  }
})();
</script>
"""
    if use_mock and re.search(r"<head[^>]*>", index_path.read_text(encoding="utf-8", errors="replace")):
        html = index_path.read_text(encoding="utf-8", errors="replace")
        if "mock_jwt_token" not in html:
            html = re.sub(r"(<head[^>]*>)", r"\1\n" + boot_script, html, count=1)
            index_path.write_text(html, encoding="utf-8")
            print("[OK] Injected mock-auth (MOCK_USER=1)")
    elif not use_mock:
        print("[INFO] Login page: local auth (no mock); clearing stored tokens so login shows")
        # When NOT mock: clear only OLD mock token so login page shows; keep token from real login
        clear_auth_script = """<script>
(function(){
  try {
    var oldMock='mock_jwt_token_for_local_development';
    function clearOld(s){ if(s&&s.getItem('token')===oldMock){ s.removeItem('token');s.removeItem('accessToken');s.removeItem('jwt');s.removeItem('user'); } }
    if(typeof localStorage!=='undefined') clearOld(localStorage);
    if(typeof sessionStorage!=='undefined') clearOld(sessionStorage);
  }catch(e){}
})();
</script>
"""
        html = index_path.read_text(encoding="utf-8", errors="replace")
        if "clearOld(s)" not in html and re.search(r"<head[^>]*>", html):
            html = re.sub(r"(<head[^>]*>)", r"\1\n" + clear_auth_script, html, count=1)
            index_path.write_text(html, encoding="utf-8")
            print("[OK] Injected clear-old-mock script (login shows; real login token kept)")
    html = index_path.read_text(encoding="utf-8", errors="replace")
    if "fix(el)" not in html and re.search(r"</head>", html):
        html = re.sub(r"(</head>)", "\n" + link_rewriter + r"\n\1", html, count=1)
        index_path.write_text(html, encoding="utf-8")
        print("[OK] Injected link rewriter (buttons/links stay on mirror)")

    # 5. Patch JS so API base URL is same origin (our server will proxy /api)
    patch_js_for_local_api(assets_dir)

    print()
    print("[OK] Mirror built at:", MIRROR)
    return True


if __name__ == "__main__":
    build()
