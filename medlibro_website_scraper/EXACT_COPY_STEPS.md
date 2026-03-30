# Make the Local Site Look and Work Exactly Like the Real MedLibro

To get an **exact copy** (same look, design, functionality), do these steps in order.

---

## Step 1: Save the real HTML pages

This opens the real MedLibro site in Chrome (you log in), then saves the **exact** HTML for the main pages (including all script/link tags).

```bash
cd medlibro_website_scraper
python save_real_pages.py
```

- Chrome will open, you may need to complete login if prompted.
- Saves `real_pages/index.html`, `real_pages/dashboard.html`, `real_pages/revision.html`.
- Asset URLs in the HTML are rewritten to `/assets/...` and `/api` so they work locally.

**Requires:** Chrome, Python, `undetected-chromedriver`, `selenium`.  
If login fails, set `CHROME_VERSION_MAIN` to your Chrome major version (e.g. 131).

---

## Step 2: Build the mirror

This builds the `mirror/` folder: real HTML + all extracted JS/CSS/images at the paths the real site expects, and patches JS so API calls go to your local server.

```bash
python build_mirror.py
```

- Copies `real_pages/index.html` → `mirror/index.html`.
- Copies all files from `scraped_website/extracted_assets/js/` and `.../css/` → `mirror/assets/`.
- Copies images → `mirror/assets/`.
- Patches JS so API base URL is same-origin (so `/api` is used and we can proxy it).

**Requires:** Step 1 must be done first (so `real_pages/index.html` exists).

---

## Step 3: Start the API server (your data)

In a **first terminal**, start the mock API that serves your JSON data:

```bash
cd medlibro_website_scraper
python api_server.py
```

Leave it running (port 5000).

---

## Step 4: Start the mirror server

In a **second terminal**, start the server that serves the exact copy and proxies API to the one above:

```bash
cd medlibro_website_scraper
python serve_mirror.py
```

- Serves static files from `mirror/`.
- Proxies `/api/*` to `http://127.0.0.1:5000` (your API server).
- Any route that doesn’t match a file (e.g. `/revision`, `/dashboard`) returns `index.html` (SPA).

Open: **http://localhost:8080**

---

## Summary

| Step | Command | What it does |
|------|--------|---------------|
| 1 | `python save_real_pages.py` | Saves real MedLibro HTML (after login) to `real_pages/` |
| 2 | `python build_mirror.py` | Builds `mirror/` with real HTML + assets + API patch |
| 3 | `python api_server.py` | Runs mock API on port 5000 (your Data/*.json) |
| 4 | `python serve_mirror.py` | Serves mirror on 8080, proxies /api to 5000 |

Result: the same HTML, same JS/CSS, same structure as the real site, with your local data from the API server.

---

## If something doesn’t match

- **Layout/design still wrong:** Make sure you ran Step 1 and 2 again after any change on the real site, so `real_pages/` and `mirror/` are up to date.
- **API errors / no data:** Ensure `api_server.py` is running on port 5000 and that `Data/*.json` exist next to the project (e.g. `../Data/`).
- **Blank or broken page:** Open DevTools (F12) → Console and Network. Check for 404s on `/assets/...` (missing file in `mirror/assets/`) or failed `/api/...` (proxy or API server down).
- **Login/auth:** The real app may expect a token. For local use, you may need to set a mock token in localStorage (e.g. in DevTools) or adjust the app’s auth check; the exact step depends on how the app checks auth.
