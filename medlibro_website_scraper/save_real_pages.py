"""
Save the REAL MedLibro HTML pages (after login).
This gets the exact index/revision/dashboard HTML with correct script/link tags
so we can serve an identical copy locally.
"""
import time
from pathlib import Path
import sys
import re

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("[ERROR] Install: pip install undetected-chromedriver selenium")
    sys.exit(1)

from config import BASE_URL, EMAIL, PASSWORD, CHROME_VERSION_MAIN
import os

REAL_PAGES_DIR = Path(__file__).parent / "real_pages"
PAGES_TO_SAVE = [
    ("/", "index.html"),
    ("/dashboard", "dashboard.html"),
    ("/revision", "revision.html"),
    ("/exam", "exam.html"),
    ("/courses", "courses.html"),
    ("/profile", "profile.html"),
    ("/playlists", "playlists.html"),
    ("/sessions", "sessions.html"),
]


def login(driver):
    """Login to MedLibro. Returns True on success."""
    print("[INFO] Opening login page...")
    driver.get(f"{BASE_URL}/login")
    time.sleep(2)  # Let login page and any redirects (e.g. www) settle
    wait = WebDriverWait(driver, 25)
    # Wait for email/identifier field (Vue may render it after load)
    email_selectors = "input[type='email'], input[name='identifier'], input[name='email'], input[placeholder*='mail'], input[type='text']"
    email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, email_selectors)))
    time.sleep(0.8)
    password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
    email_input.clear()
    email_input.send_keys(EMAIL)
    time.sleep(0.3)
    password_input.clear()
    password_input.send_keys(PASSWORD)
    time.sleep(0.5)
    # Prefer clicking submit button (more reliable than form.submit() for SPAs)
    submit_selectors = "button[type='submit'], button.btn-primary, input[type='submit'], [type='submit']"
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, submit_selectors))
        )
        btn.click()
    except Exception:
        try:
            password_input.submit()
        except Exception:
            driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button.btn-primary").click()

    # Success = left login URL (any app page or token present). Allow up to 60s for redirect.
    login_wait = WebDriverWait(driver, 60)

    def _success(d):
        url = (d.current_url or "").lower()
        # Still on login path? (e.g. .../login or .../login?error=)
        path_part = url.split("?", 1)[0].rstrip("/")
        if path_part.endswith("/login"):
            # Token might already be set before redirect
            tok = d.execute_script(
                "return (typeof localStorage !== 'undefined' && (localStorage.getItem('token') || localStorage.getItem('accessToken') || localStorage.getItem('jwt'))) "
                "|| (typeof sessionStorage !== 'undefined' && (sessionStorage.getItem('token') || sessionStorage.getItem('accessToken') || sessionStorage.getItem('jwt')));"
            )
            if tok:
                return True
            return False
        # Any other path = we left login (dashboard, revision, home, validate-email, etc.)
        return True

    try:
        login_wait.until(_success)
    except Exception as e:
        url = driver.current_url or ""
        title = driver.title or ""
        print("[ERROR] Login timed out.")
        print(f"  Current URL: {url}")
        print(f"  Page title: {title}")
        try:
            body = driver.find_element(By.TAG_NAME, "body").text[:500]
            if body.strip():
                print(f"  Page text (first 500 chars): {body.strip()[:500]}")
        except Exception:
            pass
        raise
    time.sleep(2)
    print("[OK] Login successful")
    return True


def rewrite_asset_urls(html, base_domain="medlibro.co"):
    """Rewrite absolute URLs to relative so they load from our server and API from our proxy."""
    base = rf'https?://[^"/]*{re.escape(base_domain)}'
    # /assets/ -> same origin so our server serves them
    html = re.sub(base + r'/assets/', '/assets/', html, flags=re.IGNORECASE)
    # /api -> same origin so our proxy can forward to local API
    html = re.sub(base + r'/api', '/api', html, flags=re.IGNORECASE)
    # Any other https://medlibro.co/ -> /
    html = re.sub(base + r'/', '/', html, flags=re.IGNORECASE)
    return html


def main():
    REAL_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("SAVE REAL MEDLIBRO PAGES")
    print("=" * 60)

    version_main = CHROME_VERSION_MAIN
    try:
        v = os.environ.get("CHROME_VERSION_MAIN", "").strip()
        if v:
            version_main = int(v)
    except ValueError:
        pass

    options = uc.ChromeOptions()
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = uc.Chrome(options=options, version_main=version_main)
    driver.execute_cdp_cmd("Network.enable", {})

    try:
        if not login(driver):
            print("[ERROR] Login failed")
            return
        
        # Verify we're logged in before saving pages
        print("[INFO] Verifying login session...")
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)
        current_url = driver.current_url
        if "/login" in current_url:
            print("[ERROR] Not logged in - redirected to login page")
            return
        
        print("[OK] Session verified - logged in successfully")
        print()

        for path, filename in PAGES_TO_SAVE:
            url = BASE_URL + path
            print(f"[INFO] Saving {url} -> {filename}")
            driver.get(url)
            
            # Wait for Vue app to load (check for #app and that it's populated)
            wait = WebDriverWait(driver, 45)
            try:
                # Wait for #app to exist and have content (Vue has rendered)
                wait.until(lambda d: d.execute_script(
                    "return document.getElementById('app') && "
                    "document.getElementById('app').children.length > 0;"
                ))
                # Wait for document fully loaded (scripts, styles)
                wait.until(lambda d: d.execute_script("return document.readyState === 'complete';"))
                time.sleep(2)
                # Wait for fonts to load so design matches exactly (Noto Sans, icons, etc.)
                try:
                    driver.execute_script("""
                        return document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
                    """)
                    driver.execute_async_script("""
                        var done = arguments[arguments.length - 1];
                        if (document.fonts && document.fonts.ready) {
                            document.fonts.ready.then(function(){ done(); }).catch(function(){ done(); });
                        } else { done(); }
                    """)
                    time.sleep(1)
                except Exception:
                    time.sleep(2)
                # Scroll to bottom to trigger lazy-loaded content (Vue dynamic imports, images)
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                except Exception:
                    pass
                # Wait for images inside #app to finish loading
                try:
                    driver.execute_script("""
                        var app = document.getElementById('app');
                        if (app) {
                            var imgs = app.querySelectorAll('img');
                            [].forEach.call(imgs, function(img) {
                                if (!img.complete) img.addEventListener('load', function(){});
                            });
                        }
                    """)
                    time.sleep(2)
                except Exception:
                    pass
                # Network idle: give time for any late script/style/link tags injected by Vue
                time.sleep(3)
                # Extra time for CSS animations and final paint so copy looks exactly like real page
                time.sleep(4)
            except Exception as e:
                print(f"  [WARN] Page might not be fully loaded: {e}")
                time.sleep(5)
            
            # Check if we're still logged in (not redirected to login)
            current_url = driver.current_url
            if "/login" in current_url:
                print(f"  [ERROR] Redirected to login page! Session might have expired.")
                print(f"  Current URL: {current_url}")
                continue
            
            html = driver.page_source
            
            # Verify we got actual content, not just login page
            if "login" in html.lower() and "password" in html.lower() and len(html) < 5000:
                print(f"  [ERROR] Got login page instead of {path}. Skipping.")
                continue
            
            html = rewrite_asset_urls(html)
            out = REAL_PAGES_DIR / filename
            out.write_text(html, encoding="utf-8")
            print(f"  [OK] Saved {len(html)} bytes -> {out}")

        print()
        print("=" * 60)
        print("[OK] Real pages saved to:", REAL_PAGES_DIR)
        print()
        saved_files = list(REAL_PAGES_DIR.glob("*.html"))
        print(f"Saved {len(saved_files)} page(s):")
        for f in saved_files:
            size = f.stat().st_size
            print(f"  - {f.name} ({size:,} bytes)")
        print()
        print("Next steps:")
        print("  1. Run: python build_mirror.py")
        print("  2. Run: python api_server.py  (in one terminal)")
        print("  3. Run: python serve_mirror.py  (in another terminal)")
        print("  4. Open: http://localhost:8080")
        print("=" * 60)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
