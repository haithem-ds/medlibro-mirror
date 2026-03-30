# Why Revision (chapters, courses, sources) differ from the real MedLibro site

## Root cause

Your **Data/*.json** files have the **same structure as the real MedLibro API** (each question has `meta.themeId`, `meta.chapterId`, `meta.courseId`, `meta.sourcesYears`). The local mirror was **not** using these fields. It was:

1. **Inventing IDs** – Using slugs from names (e.g. `"anatomie"`, `"théorie"`) instead of the real **UUIDs** from `meta` (`themeId`, `chapterId`, `courseId`).
2. **Confusing courses with chapters** – Returning **chapters as if they were courses** (one “course” per chapter). On the real site, **chapters** and **courses** are different levels: e.g. chapter = “théorie”, course = “Articulation coxo-fémorale”.
3. **Wrong sources** – Returning one source per **data year** (1st, 2nd, …) or stub years. On the real site, **sources** are **exam years** from `meta.sourcesYears` (e.g. 2022, 2021, 2018, 2017).

So the **data is structured like the real website**; the **backend (serve_mirror) was not** using that structure.

---

## Real structure (from your Data JSON)

From `Data/1st.json` (and same pattern in other years), each question has:

```json
"meta": {
  "location": "constantine",
  "locationId": "...",
  "year": "1st",
  "yearId": "45fe4198-1d89-416c-a9dc-5d788cc49d77",
  "theme": "Anatomie",
  "themeId": "d5ceb0a7-7ede-4729-b015-db9903b8acaa",
  "chapter": "théorie",
  "chapterId": "af5644f9-6a93-44b0-b9f4-4ce2ff3401a7",
  "course": "Articulation coxo-fémorale ",
  "courseId": "b9ab9882-e33b-4940-acca-fd8e33c3b6de",
  "sourcesYears": [2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015]
}
```

- **Theme** = e.g. “Anatomie”, id = `themeId` (UUID).
- **Chapter** = e.g. “théorie”, id = `chapterId` (UUID), belongs to a theme.
- **Course** = e.g. “Articulation coxo-fémorale”, id = `courseId` (UUID), belongs to theme (+ chapter).
- **Sources** = exam years: list of years in `sourcesYears` (2022, 2021, 2018, …).

So hierarchy is: **Year → Theme → Chapter → Course**, and **Sources** = which exam years the question appears in.

---

## What was changed in the code

The server was updated to align with this structure:

1. **Themes** – Use `meta.themeId` as `id` when present (else slug). Name from `meta.theme`.
2. **Chapters** – Use `meta.chapterId` as `id`, `meta.chapter` as `title`; filter by `themeId` (UUID or slug).
3. **Courses** – Use `meta.courseId` as `id`, `meta.course` as `title`; filter by `themeId` and optionally `chaptersIds`; **no longer** use chapter names as courses.
4. **Sources** – Build the list from **all unique years** in `meta.sourcesYears` across the dataset (e.g. 2018, 2017, 2016), with counts when available.

Result: same **organization** (theme → chapter → course), same **chapters** and **courses** as in the data, and **sources** = exam years like on the real site.

---

## If something still doesn’t match

- **Order** – Real site may order years/themes/chapters differently; we can add explicit sorting to match.
- **Missing meta** – If some questions lack `themeId` / `chapterId` / `courseId` / `sourcesYears`, we fall back to names/slugs and inferred sources; filling or normalizing meta in the JSON will improve parity.
- **Locations** – Real site may filter by `meta.location` / `locationId`; we can add location-based filtering if needed.
