# Real MedLibro site vs local mirror – what we have and what we did

This document answers: **Was the real website actually analyzed (design, APIs, behavior)?** and what the mirror has vs what’s missing.

---

## 1. What we have from the real site

### Design and frontend (yes – from scraping)

- **Source:** The mirror is the **real MedLibro SPA** (HTML, JS, CSS) downloaded by the project’s scrapers (`website_scraper.py`, `save_real_pages.py`, `build_mirror.py`). The same Vue/Vuetify app that runs on medlibro.co runs locally.
- **So:** Layout, sidebar, dashboard structure, styles, and component behavior (e.g. dialogs, filters) are the **same as the real site** – we serve the same frontend.

### API list (inferred from frontend JS – not from live traffic)

- **Source:** API endpoints were **inferred from the mirror’s JavaScript** (regex/search in JS bundles and in `comprehensive_analysis.py`). We did **not** open the real site in a browser and record network traffic (no HAR, no proxy log).
- **So:** We know **which URLs the frontend calls** (e.g. `/api/v1/years`, `/api/v2/sessions`, `/api/v2/themes/due`), but we do **not** have a guaranteed “exact” request/response spec from the real backend. Response shapes were deduced from how the JS uses the data (e.g. `edges`/`pageInfo`, `themes`, etc.).

### Data

- **Source:** Question bank comes from your **local `Data/*.json`** files (e.g. `1st.json`, `2nd.json`). These are **not** scraped from the real site’s API in this project; they are your own dumps or separate scraping.
- **So:** Revision, Memorix “top themes” counts, and question content in the mirror come from **your Data**, not from live MedLibro.

---

## 2. What we did *not* do

- **No step‑by‑step pass on the live site** with DevTools Network tab to log every API call per page.
- **No HAR or proxy recording** of real request/response bodies.
- **No screen‑by‑screen checklist** comparing real site vs mirror (we didn’t document “dashboard heatmap has N cells” etc.).
- **No recording of real API response shapes** (e.g. exact fields for sessions, playlists, exam configs).

So: **design/frontend = real site; API behavior = inferred from JS + stubs**, not from a full “analyze real site then build” spec.

---

## 3. APIs the frontend actually uses (from mirror JS)

Below are the endpoints we see in the mirror’s assets (by page/store). This is the **source of truth** for what the mirror expects.

### Auth (implemented in `serve_mirror.py`)

| Method | Path | Purpose |
|--------|------|--------|
| POST   | `/api/v1/auth/login` | Login → token + user |
| GET    | `/api/v1/auth/authenticated`, `/api/v1/auth/me`, `/api/v1/user/me`, `/api/v1/user` | Current user |
| POST   | `/api/v1/auth/logout` | Logout |
| POST/PATCH | `/api/v1/auth/validate`, `/api/v1/auth/validate-account`, `/api/v1/auth/request-validation-code` | Validation (stubbed) |

### Dashboard

| Method | Path | Expected shape | Status |
|--------|------|----------------|--------|
| GET | `/api/v1/auth/authenticated` | `{ user, authenticated }` | ✅ |
| GET | `/api/v1/preferences` | preferences object | ✅ (empty) |
| GET | `/api/v2/cards/themes/top?sortBy=urgency` | `{ themes: [{ id, name, newCount, reviewCount, displayCount }] }` | ✅ from Data |
| GET | `/api/v1/playlists/pinned` | `[]` or array | ✅ |
| GET | `/api/v2/answers/modules`, `/api/v2/answers` | heatmap data | ✅ (empty) |

### Sessions (SessionsPage)

| Method | Path | Expected shape | Status |
|--------|------|----------------|--------|
| GET | `/api/v2/sessions?status=active\|archived&cursor=` | `{ edges: [], pageInfo: { hasNextPage, nextPage } }` | ✅ stubbed |
| GET | `/api/v2/sessions/<id>/details` | `[{ year, theme?, unit?, chapters, courses, sources }]` | ✅ stubbed |
| GET | `/api/v2/sessions/<id>/items-count` | `{ total, totalQuestions, totalCases, totalCasesQuestions }` | ✅ stubbed |
| PATCH | `/api/v2/sessions/<id>` | success | ✅ stubbed |
| DELETE | `/api/v2/sessions/<id>` | success | ✅ stubbed |
| POST | `/api/v2/answer-sets` | body `{ sessionId }`, returns new answer set | ✅ stubbed |
| PATCH | `/api/v2/sessions/<id>/highlights` | body `{ highlights: {} }` | ✅ stubbed |

### Memorix (MemorixPage)

| Method | Path | Expected shape | Status |
|--------|------|----------------|--------|
| GET | `/api/v2/themes/due` | `{ "<yearLabel>": [ { id, name, count, yearLabel } ], ... }` | ✅ stubbed (from Data) |
| DELETE | `/api/v2/cards/modules/<id>` | success | ✅ stubbed |

Dashboard Memorix card uses `GET /api/v2/cards/themes/top` (already implemented).

### Playlists (PlaylistsPage, store `playlists-CAej7X3U.js`)

| Method | Path | Expected shape | Status |
|--------|------|----------------|--------|
| GET | `/api/v1/playlists/pinned` | array | ✅ |
| GET | `/api/v1/playlists?cursor=&direction=` | `{ edges: [], pageInfo: { hasNextPage, nextPage } }` | ✅ stubbed |
| GET | `/api/v1/playlists/search?input=` | list/array (or same as list) | ✅ stubbed |
| POST | `/api/v1/playlists/playlist` | new playlist | catch‑all |
| PATCH | `/api/v1/playlists/playlist/<id>` | updated playlist | catch‑all |
| DELETE | `/api/v1/playlists/playlist/<id>` | success | catch‑all |
| PATCH | `/api/v1/playlists/playlist/<id>/pin` | toggle pin | catch‑all |

### Révision (Revision)

| Method | Path | Expected shape | Status |
|--------|------|----------------|--------|
| GET | `/api/v1/years` | list of years | ✅ from Data |
| GET | `/api/v1/revision` | years + themes + chapters + counts | ✅ from Data |
| GET | `/api/v1/questions/<id>` | question object | ✅ from Data |

### Examen (ExamPage)

Uses the same “items” store as Révision/Playlists: **locations, years, themes, chapters, courses, sources, items**. These come from APIs like:

- Locations (e.g. `/api/v2/.../locations` or similar)
- Years, themes, chapters, courses, sources (likely revision or filter endpoints)

We have **years/revision** from Data; locations and exam-specific configs are **not** implemented. The exam page may show filters but “Start” can fail or show empty if the store expects specific API responses.

### Profile

| Method | Path | Status |
|--------|------|--------|
| GET | `/api/v1/auth/authenticated` or `/me` | ✅ |
| GET | `/api/v2/licenses/expiry` | ✅ |

---

## 4. Summary: real site vs mirror

| Aspect | Real site | Mirror |
|--------|-----------|--------|
| **UI / design** | MedLibro SPA | Same SPA (scraped and served locally) |
| **API list** | Real backend | Inferred from JS; no HAR/live capture |
| **API responses** | Real data | Stubs + your `Data/*.json` where wired |
| **Sessions** | Stored per user | Stubbed: empty list, no persistence |
| **Memorix (due cards)** | Real spaced‑repetition | Stubbed: themes/due from Data or empty |
| **Playlists** | Stored per user | Stubbed: empty list, correct shape |
| **Révision** | Real question bank | Your Data + same API shapes |
| **Examen** | Real exam configs | Partially stubbed; may be incomplete |
| **Dashboard** | Real heatmap, real counts | Themes/counts from Data; heatmap empty |

---

## 5. How to get “exact same” behavior later

1. **Capture real API traffic:** Open the real site, go through each sidebar page (Dashboard, Sessions, Memorix, Playlists, Révision, Examen, Profil), and record all API calls (e.g. “Export HAR” in DevTools). That gives exact URLs, methods, and response shapes.
2. **Implement or stub each endpoint** in `serve_mirror.py` to match those shapes (and, where you want real data, feed from `Data/*.json` or local DB).
3. **Optionally:** Add a short “mirror architecture” doc (rewrite, cookies, patched JS, which routes are real vs stubbed) so future changes stay consistent.

Until then, the mirror is **same design, same frontend, API behavior inferred and stubbed** – not built from a full “analyzed real site then replicated” spec.
