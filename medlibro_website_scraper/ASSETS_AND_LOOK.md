# MedLibro assets and why the local site looked different

## What we actually scraped

- **We did get the site’s assets.** The scraper downloaded:
  - **89 JavaScript files** (Vue/Vuetify bundles, components)
  - **45 CSS files** (layout, Vuetify components, MedLibro styles)
  - **10 images** (icons, favicon, logos)

  They are in:
  - `scraped_website/html/assets/*.html` (original HTML-wrapped responses)
  - `scraped_website/extracted_assets/js/` and `extracted_assets/css/` (extracted JS/CSS)

- **We did not scrape the main page HTML** for `/`, `/dashboard`, or `/revision`.  
  The sitemap contained both page URLs and asset URLs; the scraper ran over the list and only the asset URLs ended up being saved as “pages” in the index. So we never saved the real index/dashboard/revision HTML, only the asset files.

## What we did to match the real look

1. **Use the scraped CSS**  
   The local `index.html` now loads the **real MedLibro CSS** from `extracted_assets/css/`:
   - `index-0wFbg7uQ.css` (global layout, cards, scroll)
   - `VAppBar`, `VBtn`, `VMain`, `VSelect`, `VInput`, `VTextField`
   - `FilterForm`, `VNavigationDrawer`, `VList`, `VDivider`, `VAlert`

   So colors, spacing, cards, inputs, and layout should match the live site.

2. **Layout and labels**  
   - Navigation drawer (sidebar) with icons
   - French labels: Accueil, Tableau de bord, Révision
   - Revision page: filter card (“Filtres”, “Année”) and theme cards with question counts

3. **Same tech stack**  
   Vue 2, Vue Router, Vuetify, Axios, same structure as the real app, but a **simplified** app that uses our local API and your JSON data.

## Result

- **Look:** Should now be close to the real site (same CSS, same components, French UI).
- **Data:** Comes from your `Data/*.json` via the local API server.
- **Limitation:** We are not running the original MedLibro Vue app (that would need their exact HTML + JS and their API). We run a small clone that uses their styling and your data.

If you want the **exact** original look and behavior, the next step would be to scrape the real page HTML for `/` (and optionally `/revision`, `/dashboard`) once, then serve that HTML and point its script/link tags to our extracted assets and a proxy to our local API.
