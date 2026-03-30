# MedLibro – Full site spec (from mirror frontend analysis)

This document is the **detailed spec** of the real MedLibro site as inferred from the **scraped mirror frontend**: every main route, what each page shows, which APIs it calls, and the exact response shapes the UI expects. Use it to align the mirror backend and behavior with the real site.

---

## How this spec was built

- **Source:** Static analysis of the mirror’s JS/CSS/HTML (no live traffic capture).
- **Design:** Same as real site (we serve the same Vue/Vuetify SPA).
- **APIs:** Inferred from axios/fetch URLs and how responses are used (e.g. `.edges`, `.pageInfo`, `.themes`).
- **Limitation:** We did not record real API responses from medlibro.co; shapes are deduced from frontend usage.

---

## 1. Routes and pages (main app)

| Path | Name | Component | Purpose |
|------|------|-----------|---------|
| `/` | home | HomePage | Landing: hero, features, pricing, footer |
| `/dashboard` | dashboard | DashboardPage | Main dashboard (shortcuts, Memorix, playlists, heatmap, activity) |
| `/sessions` | sessions | SessionsPage | List/create/manage sessions |
| `/filter` | filter | FilterPage | Build filter sets → create session (revision or explore) |
| `/session/:id` | session | SessionPage | Single session: questions/cases, progress, explore mode |
| `/memorix` | memorix | MemorixPage | Memorix: due cards by year/theme |
| `/playlists` | playlists | PlaylistsPage | List playlists, search, pin, play |
| `/revision` | revision | RevisionPage | Révision: year/theme/chapter/source → start practice |
| `/exam` | exam | ExamPage | Examen: mode, year, theme/source → start exam |
| `/profile` | profile | ProfilePage | User profile, license, preferences |
| `/cards/:themeId` | cards | CardsPage | Memorix cards for one theme |
| `/login` | login | LoginPage | Login |
| `/signup` | signup | SignupPage | Signup |
| `/pricing` | pricing | PricingPage | Pricing |
| `/faq` | faq | FAQPage | FAQ |
| `/activate` | activate | ActivatePage | Activate license key |
| `/forgot-password` | forgot-password | ForgotPasswordPage | Forgot password |
| `/question/:id` | question | QuestionPage | Single question view |
| `/case/:id` | case | CasePage | Clinical case view |
| `/users` | users | UsersPage | Admin: users (if isAdmin/isModerator) |
| `/x/statistics` | – | StatisticsPage | Stats (admin) |
| `/prioritizer` | prioritizer | PrioritizerPage | Prioritizer |
| `/reports` | reports | ReportsPage | Reports |

---

## 2. Dashboard (`/dashboard`)

**What it shows (design):**

1. Optional Telegram alert (dismissible).
2. **Account validation card** (hidden when user is validated; we patch to always hide).
3. **Upgrade shortcut** (hidden when premium; we patch to hide).
4. **Four shortcuts:** Sessions, Examen, Memorix, Playlists (locked by isValid/isPremium; we patch to unlock).
5. **Memorix top themes card** (themes with newCount, reviewCount, link to `/cards/:themeId`).
6. **Pinned playlists** (list, play, unpin).
7. **Answers heatmap** (calendar of correct answers per day).
8. **Activity card** (list of modules with correct/partiallyCorrect/incorrect counts, range + sort).
9. Footer.

**APIs used:**

| Method | Path | Expected response | Implemented |
|--------|------|-------------------|-------------|
| GET | `/api/v1/auth/authenticated` or `/me` | `{ user, authenticated }`, user has validated/premium flags | ✅ |
| GET | `/api/v1/preferences` | preferences object | ✅ (empty) |
| GET | `/api/v2/cards/themes/top?sortBy=urgency` | `{ themes: [{ id, name, newCount, reviewCount, displayCount }] }` | ✅ from Data |
| GET | `/api/v1/playlists/pinned` | `[]` or array of `{ id, label, questionsCount, clinicalCasesCount }` | ✅ |
| GET | `/api/v2/answers` | Array of `{ date, count }` for heatmap | ✅ (empty []) |
| GET | `/api/v2/answers/modules?range=&status=&cursor=` | `{ edges: [{ label, name, correct, partiallyCorrect, incorrect }], pageInfo: { hasNextPage, nextPage } }` | ✅ (empty edges) |

**Store/computed:** `preferences`, `isValid`, `isPremium` from auth/preferences.

---

## 3. Sessions (`/sessions`)

**What it shows:**

- “Create” → navigates to `/filter`.
- Tabs: Active / Archived.
- List of sessions: title, last opened, total QST/CAS, progress %, actions (details, edit title, sort, reset highlights, reset session, archive/activate, delete).
- “Start” / “Explore” → `/session/:id` (query t, qc, cc, cqc).
- Load more (pagination).

**APIs used:**

| Method | Path | Expected response | Implemented |
|--------|------|-------------------|-------------|
| GET | `/api/v2/sessions?status=active|archived&cursor=` | `{ edges: [session], pageInfo: { hasNextPage, nextPage } }` | ✅ |
| GET | `/api/v2/sessions/:id/details` | `[{ year, theme?, unit?, chapters, courses, sources }]` | ✅ ([]) |
| GET | `/api/v2/sessions/:id/items-count` | `{ total, totalQuestions, totalCases, totalCasesQuestions }` | ✅ |
| PATCH | `/api/v2/sessions/:id` | success | ✅ |
| DELETE | `/api/v2/sessions/:id` | 204 | ✅ |
| PATCH | `/api/v2/sessions/:id/highlights` | body `{ highlights: {} }`, success | ✅ |
| POST | `/api/v2/answer-sets` | body `{ sessionId }`, returns `{ id, sessionId }` | ✅ |

**Session object shape (edges item):** id, title, lastOpened, status, totalQuestions, totalCases, totalCasesQuestions, answerSets, canAccess, itemsOrderDirection, etc.

---

## 4. Filter (`/filter`) → Create session

**What it shows:**

- Up to 5 “sets”; each set is a FilterForm (year, theme, sources).
- Delete set / Add set.
- “Explore” / “Revision” → createSession(title, options) then redirect to `/session/:id` or `/session/:id?e=1`.

**APIs used:**

| Method | Path | Expected response | Implemented |
|--------|------|-------------------|-------------|
| POST | `/api/v2/sessions` | body `{ title, options }` → session object with `id` (and title, answerSets, etc.) | ✅ |

**Flow:** createSession builds `options` from each set’s form; POST sessions; then `this.$router.push({ name: "session", params: { id: r.id } })`.

---

## 5. Session page (`/session/:id`)

**What it shows:**

- App bar, home button.
- Session content: questions/clinical cases, progress, notes, highlights, explore vs revision mode.
- Uses **items store** (ids, items), question/case loading, answer submission.

**APIs used (from SessionPage + items store):**

- Session data and items are loaded by the session/id flow (likely GET session, GET session items or similar).
- Single question: `GET /api/v1/questions/:id`.
- Single case: `GET /api/v1/clinical-cases/:id` (or v2).
- Submit answer: `POST /api/v2/answers` (body: input, questionId, answerSetId, status, isPartiallyCorrect).
- Cards (Memorix): `POST /api/v2/cards` with `{ questionId }` (when answering).

We have questions and catch‑all for answers/cards; session-specific item loading may hit catch‑all.

---

## 6. Memorix (`/memorix`)

**What it shows:**

- List of themes by year (from “due” API).
- Each theme: name, count, menu (delete cards), “Play” → `/cards/:themeId`.
- Empty state if no due themes.

**APIs used:**

| Method | Path | Expected response | Implemented |
|--------|------|-------------------|-------------|
| GET | `/api/v2/themes/due` | `{ "<yearLabel>": [ { id, name, count, yearLabel } ], ... }` | ✅ from Data |
| DELETE | `/api/v2/cards/modules/:id` | 204 | ✅ |

---

## 7. Playlists (`/playlists`)

**What it shows:**

- Search, “Add playlist”.
- Pinned playlists block (same as dashboard).
- List of playlists: label, subtitle (QST/CAS), description; play, pin, edit, delete.
- Infinite scroll (load more).

**APIs used:**

| Method | Path | Expected response | Implemented |
|--------|------|-------------------|-------------|
| GET | `/api/v1/playlists/pinned` | array | ✅ |
| GET | `/api/v1/playlists?cursor=&direction=` | `{ edges: [], pageInfo: { hasNextPage, nextPage } }` | ✅ |
| GET | `/api/v1/playlists/search?input=` | array or list (filterPlaylists sets playlists = data) | ✅ ([]) |
| POST | `/api/v1/playlists/playlist` | new playlist | catch‑all |
| PATCH | `/api/v1/playlists/playlist/:id` | updated playlist | catch‑all |
| DELETE | `/api/v1/playlists/playlist/:id` | success | catch‑all |
| PATCH | `/api/v1/playlists/playlist/:id/pin` | toggle pin | catch‑all |

---

## 8. Revision (`/revision`)

**What it shows:**

- Revision mode toggle (e.g. practice).
- Year → theme → chapters → courses → sources (PrimaryAutocomplete).
- “Start” → fetchItems() then open AnswerDialog.
- Link to Sessions.

**APIs used (from items/revision store):**

| Method | Path | Expected response | Implemented |
|--------|------|-------------------|-------------|
| GET | `/api/v1/years` | list of years | ✅ from Data |
| GET | `/api/v1/revision` | years + themes + chapters + counts | ✅ from Data |
| GET | (locations) | list of locations | store/catch‑all |
| GET | (themes for year) | from revision or dedicated themes API | ✅ via revision |
| GET | (chapters, courses, sources) | from revision/filter APIs | ✅ via revision |
| GET | (items for practice) | list of question/case ids or items | items store / catch‑all |
| GET | `/api/v1/questions/:id` | question | ✅ from Data |

---

## 9. Exam (`/exam`)

**What it shows:**

- Exam mode: adaptive / replica.
- Options: threshold per chapter, seconds per question, year, filter by (exam/module/unit), theme, chapters, courses, sources.
- “Start” → fetchItems() then exam flow.

**APIs used:** Same items store as revision (fetchLocations, fetchYears, fetchThemes, fetchChapters, fetchCourses, fetchSources, fetchItems). We have years/revision; locations and exam-specific configs are stubbed/catch‑all.

---

## 10. Profile (`/profile`)

**What it shows:**

- User info, email, license, preferences, activity.
- Dialogs: edit user, email, etc.

**APIs used:**

| Method | Path | Implemented |
|--------|------|-------------|
| GET | `/api/v1/auth/authenticated` or `/me` | ✅ |
| GET | `/api/v2/licenses/expiry` | ✅ |
| GET | `/api/v1/preferences` | ✅ |

---

## 11. Cards page (`/cards/:themeId`) (Memorix theme)

**What it shows:** Cards (questions) for one Memorix theme; answer flow, link back to Memorix.

**APIs:** Likely GET cards for theme (or use items store); GET question by id; POST answers; POST cards. We have questions from Data; rest can be catch‑all.

---

## 12. Auth and global

**Login:** POST `/api/v1/auth/login` → token + user; we set cookies and return mock validated premium user.

**Authenticated:** GET `/api/v1/auth/authenticated`, `/api/v1/auth/me`, `/api/v1/user/me`, `/api/v1/user` → user + authenticated. We return mock user when cookie/token is our local JWT.

**Logout:** POST `/api/v1/auth/logout`.

**Validate account / request code:** POST/PATCH `/api/v1/auth/validate-account`, `/api/v1/auth/request-validation-code` → stubbed.

**Activate page:** POST `/api/v2/tickets/activate` with `{ key }` → we don’t implement; catch‑all.

---

## 13. Response shapes summary (for backend)

- **Paginated list:** `{ edges: [], pageInfo: { hasNextPage: boolean, nextPage: number|null } }`.
- **Heatmap:** `[ { date: string, count: number } ]`.
- **Memorix top themes:** `{ themes: [ { id, name, newCount, reviewCount, displayCount } ] }`.
- **Memorix due:** `{ "<year>": [ { id, name, count, yearLabel } ] }`.
- **Pinned playlists:** `[ { id, label, questionsCount, clinicalCasesCount, pinned } ]`.
- **Activity modules:** `edges`: `[ { label, name, correct, partiallyCorrect, incorrect } ]`.
- **Session (create):** `{ id, title, lastOpened, status, answerSets, totalQuestions, totalCases, totalCasesQuestions, canAccess, itemsOrderDirection }`.
- **Session details:** `[ { year, theme?, unit?, chapters, courses, sources } ]`.
- **Session items-count:** `{ total, totalQuestions, totalCases, totalCasesQuestions }`.

---

## 14. What’s implemented vs stubbed

- **Implemented with real data (Data/*.json):** years, revision, questions, cards/themes/top, themes/due (from same data).
- **Implemented with correct shape (no persistence):** auth, preferences, sessions (GET/POST/PATCH/DELETE, details, items-count, highlights), answer-sets, playlists (list, pinned, search), answers (heatmap + modules), licenses/expiry.
- **Catch‑all (safe empty/success):** playlists CRUD/pin, tickets/activate, other v1/v2 routes.

To make the mirror **match the real site in behavior**: keep these shapes, add persistence where you want (sessions, playlists), and optionally capture real HAR from medlibro.co and align any remaining endpoints to those responses.
