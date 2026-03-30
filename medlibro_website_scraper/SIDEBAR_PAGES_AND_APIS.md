# Sidebar pages and APIs (local mirror)

This file documents **each sidebar page**, which APIs it calls, and why the local mirror shows (or doesn’t show) data like the real website.

---

## 1. Tableau de bord (Dashboard)

**What it is:** Main dashboard with shortcuts (Sessions, Examen, Memorix, Playlists), Memorix “top themes” card, Pinned Playlists, and activity heatmap.

**APIs used:**
- `GET /api/v1/auth/authenticated` – user + validated/premium → **implemented**
- `GET /api/v1/preferences` – preferences → **implemented** (empty)
- `GET /api/v2/cards/themes/top?sortBy=urgency` – Memorix themes (id, name, newCount, reviewCount, displayCount) → **implemented** (from Data/*.json; newCount/reviewCount set so “VIDE” becomes “X à réviser”)
- `GET /api/v1/playlists/pinned` – pinned playlists → **implemented** (empty array)
- `GET /api/v2/answers/modules`, `GET /api/v2/answers` – heatmap → **implemented** (empty)

**Why it can look different:** Real site has real user progress (heatmap, Memorix due cards). We use local Data and stubs, so heatmap is empty and Memorix shows “questions to review” counts from your JSON, not real spaced-repetition state.

---

## 2. Sessions

**What it is:** List of saved “sessions” (progress: which questions, filters, etc.). Real site stores these per user.

**APIs used:** All stubbed with correct shapes so the page doesn’t crash:
- `GET /api/v2/sessions?status=&cursor=` → `{ edges: [], pageInfo: { hasNextPage, nextPage } }` ✅
- `GET /api/v2/sessions/<id>/details` → `[]` ✅
- `GET /api/v2/sessions/<id>/items-count` → `{ total, totalQuestions, totalCases, totalCasesQuestions }` ✅
- `PATCH /api/v2/sessions/<id>`, `DELETE`, `PATCH .../highlights`, `POST /api/v2/answer-sets` ✅

**Why it’s empty:** No session storage; we return empty list. UI shows “no sessions” instead of errors.

---

## 3. Memorix

**What it is:** Spaced-repetition: “cards” (questions) due for review, by theme. Real site uses a Memorix backend (due dates, difficulty, etc.).

**APIs used:**
- Dashboard: `GET /api/v2/cards/themes/top` → **implemented** (from Data)
- Memorix page: `GET /api/v2/themes/due` → **implemented** (from Data: `{ "<year>": [ { id, name, count, yearLabel } ] }`)
- `DELETE /api/v2/cards/modules/<id>` → **stubbed** (204)

**Why it can show data:** Themes/due is built from your Data/*.json (same themes as revision). No real spaced-repetition state; counts come from question counts per theme.

---

## 4. Playlists

**What it is:** User-created playlists of questions. Real site stores them per user.

**APIs used:**
- `GET /api/v1/playlists/pinned` → **implemented** (empty array)
- `GET /api/v1/playlists?cursor=&direction=` → **implemented** `{ edges: [], pageInfo: { hasNextPage, nextPage } }`
- `GET /api/v1/playlists/search?input=` → **implemented** (empty array)
- Add/edit/delete/pin → **catch-all** (stubbed)

**Why it’s empty:** No playlist storage; we return empty list with correct shape so the page renders “no playlists” instead of errors.

---

## 5. Révision (Revision)

**What it is:** Choose year/theme/chapter and do a “revision” (practice questions). Uses same question bank as the real site.

**APIs used:**
- `GET /api/v1/years` – list of years → **implemented** (from Data)
- `GET /api/v1/revision` – years + themes + chapters + questions_count → **implemented** (from Data)
- `GET /api/v1/questions/<id>` – single question → **implemented** (from Data)

**Why it can work:** Revision page should show years and themes from your Data. If it’s empty, check that Data/*.json exist and `_year_items()` is used (we fixed this). Clicking a theme should load questions; answering may call `POST /api/v2/answers` or similar (we have catch-all; may need a proper stub).

---

## 6. Examen (Exam)

**What it is:** Timed exams (e.g. by module/source). Real site has exam configs and timers.

**APIs used:** Likely exam list, exam config, and question set for an exam. **Not implemented** – we’d need to stub exam list and exam “start” so the page shows something.

---

## 7. Profil (Profile)

**What it is:** User profile, license, settings.

**APIs used:**
- `GET /api/v1/auth/authenticated` or `/me` → **implemented**
- `GET /api/v2/licenses/expiry` → **implemented** (valid license)
- Preferences, etc. → **implemented** (empty or stubbed)

**Why it works:** We return a valid user and license so the profile page can render.

---

## Summary

| Page        | Main APIs                          | Implemented? | Why empty / different      |
|------------|-------------------------------------|--------------|----------------------------|
| Dashboard  | auth, preferences, cards/themes/top, playlists/pinned, answers | Yes          | Heatmap/pinned empty; themes show “X à réviser” from Data |
| Sessions   | v2/sessions, details, items-count   | Yes (stubbed)| Empty list; correct shape  |
| Memorix    | cards/themes/top, themes/due        | Yes          | Due themes from Data       |
| Playlists  | playlists, playlists/pinned, search | Yes (stubbed)| Empty list; edges/pageInfo |
| Révision   | years, revision, questions         | Yes          | Data from Data/*.json      |
| Examen     | exams list, config                 | No           | No exam stubs              |
| Profil     | auth, licenses                     | Yes          | Works                      |

To make the mirror “like the real website” for each sidebar page you need to implement (or stub) the APIs that page calls and return the expected response shape. This file is the map for that.
