# How to run the MedLibro mirror (exact copy + local API)

## Is this a static website? Do I need a server?

**No – it is not static.** You must run the **server** (`serve_mirror.py`). It does two things:

1. **Serves** the mirror files (HTML, JS, CSS) like a normal web server.
2. **Handles all API calls** locally (login, auth, questions, etc.). There is no separate “backend” – this one process is the backend.

If you just open `mirror/index.html` in the browser, **nothing will work** (no API, no login). Always run the server, then use the URL it prints (or the browser will open automatically).

## Why did nothing open?

The server only **starts** the backend; it does not open the browser. After you run `run_exact_copy.bat` or `launch_servers.bat`, **open your browser yourself** and go to **http://localhost:8080**.

---

## Why was I always logged in / no login page?

- The app was treating you as logged in because:
  1. **Stored token** – A token was left in the browser (e.g. from an old mock build). The app trusts that and goes straight to the dashboard.
  2. **API always said “authenticated”** – The API was returning “authenticated” even before login.

- **What we changed:**
  1. The API now returns **not authenticated** until you log in (then it returns premium user).
  2. The mirror build injects a **clear-auth script** that removes any stored token/user on each page load, so the app always starts on the **login page** (no auto-login).

## You must rebuild the mirror once

So that the clear-auth script is in the HTML, run (from this folder):

```bat
python build_mirror.py
```

Do **not** set `MOCK_USER=1`. Then start the server:

```bat
python serve_mirror.py
```

## Which app am I seeing?

- **"MedLibro - Local" / "Welcome. This version uses your scraped data"**  
  That is the **old** app (static_server). Do **not** run `static_server.py`.

- **Real MedLibro design with "La référence des QCM..." and login**  
  That is the **correct** mirror.

## Steps (only these)

1. **Rebuild once** (so login page shows):  
   `python build_mirror.py` (without MOCK_USER).

2. **Close all** server terminals, then run **one** of:
   - `run_exact_copy.bat quick` — build + start server  
   - `launch_servers.bat` — only start server  

3. Open **one** URL: `http://localhost:8080` or `http://127.0.0.1:8080` (same).

4. You should see the **login page**. Use **any** email/password (e.g. `test@test.com` / `password`). After login you get the dashboard. If you **refresh** the page, you’ll see the login page again (by design).

## 127.0.0.1 vs localhost

They are the **same** server. If you see different content, use one URL and hard-refresh (Ctrl+F5) or clear cache.
