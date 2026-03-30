# MedLibro Website Rebuild Guide

This guide explains how to rebuild and run the MedLibro website locally using the scraped data and assets.

## Overview

The MedLibro website is a **Vue.js + Vuetify Single Page Application (SPA)** that:
- Uses Vue Router for navigation
- Uses Vuetify for UI components
- Makes API calls to `/api/v1/*` endpoints
- Displays questions, clinical cases, and revision materials

## Architecture

```
MedLibro Website
├── Frontend (Vue.js SPA)
│   ├── Routes: /dashboard, /revision, /exam, /profile, etc.
│   ├── Components: DashboardPage, RevisionPage, ExamPage, etc.
│   └── UI Library: Vuetify
│
├── Backend API
│   ├── Endpoints: /api/v1/revision, /api/v1/questions/{id}, etc.
│   └── Data Source: JSON files from Data/ folder
│
└── Static Assets
    ├── JavaScript files (extracted from scraped HTML)
    ├── CSS files (extracted from scraped HTML)
    └── Images (downloaded during scraping)
```

## Quick Start

### Option 1: Automated Launcher (Windows)

```bash
launch_local_website.bat
```

This will:
1. Check and install dependencies (Flask, Flask-CORS)
2. Extract assets if needed
3. Start API server on port 5000
4. Start static file server on port 8080
5. Open browser to http://localhost:8080

### Option 2: Manual Steps

#### Step 1: Install Dependencies

```bash
pip install flask flask-cors
```

#### Step 2: Extract Assets

```bash
python extract_assets.py
```

This extracts actual JS/CSS files from the HTML wrappers saved during scraping.

#### Step 3: Start API Server

In one terminal:
```bash
python api_server.py
```

The API server runs on `http://localhost:5000`

#### Step 4: Start Static File Server

In another terminal:
```bash
python static_server.py
```

The static server runs on `http://localhost:8080`

#### Step 5: Open Browser

Navigate to: `http://localhost:8080`

## File Structure

```
medlibro_website_scraper/
├── scraped_website/
│   ├── html/                    # Original scraped HTML files
│   ├── assets/                  # Downloaded assets (images, etc.)
│   └── extracted_assets/       # Clean extracted JS/CSS/HTML
│       ├── index.html          # Main HTML entry point
│       ├── js/                 # JavaScript files
│       ├── css/                # CSS files
│       └── images/             # Image files
│
├── api_server.py               # Mock API server
├── static_server.py            # Static file server
├── extract_assets.py           # Asset extraction script
├── comprehensive_analysis.py   # Website analysis
└── launch_local_website.bat     # Windows launcher

../Data/                        # JSON data files
├── 1st.json
├── 2nd.json
├── 3rd.json
├── 4th.json
├── 5th.json
├── 6th.json
└── residency.json
```

## API Endpoints

The mock API server provides these endpoints:

### Data Endpoints

- `GET /api/v1/years` - Get all available years
- `GET /api/v1/revision` - Get revision data (years, themes, chapters)
- `GET /api/v1/themes?year={year}` - Get themes for a year
- `GET /api/v1/chapters?year={year}&theme={theme}` - Get chapters
- `GET /api/v1/questions/{id}` - Get a specific question
- `GET /api/v1/clinical-cases/{id}` - Get a clinical case

### Auth Endpoints (Mock)

- `POST /api/v1/auth/login` - Mock login (returns mock token)
- `POST /api/v1/auth/logout` - Mock logout
- `GET /api/v1/user/profile` - Get user profile

### Health Check

- `GET /api/v1/health` - Check server status and data load

## Routes

The Vue.js app has these routes:

- `/` - Home page
- `/dashboard` - Dashboard
- `/revision` - Revision/QCM page
- `/exam` - Exam page
- `/courses` - Courses
- `/profile` - User profile
- `/playlists` - Playlists
- `/sessions` - Sessions
- `/memorix` - Memorix
- `/prioritizer` - Prioritizer
- `/pricing` - Pricing
- `/faq` - FAQ

## Data Format

The JSON files in `Data/` contain question objects with this structure:

```json
{
  "id": "question-id",
  "questionId": "question-id",
  "question": "Question text",
  "answers": ["Answer 1", "Answer 2", ...],
  "correctAnswer": 0,
  "explanation": "Explanation text",
  "theme": "Theme name",
  "chapter": "Chapter name",
  "year_label": "1st",
  "meta": {
    "isClinicalCase": false
  }
}
```

For clinical cases:
```json
{
  "id": "clinical-case-id",
  "clinicalCaseId": "clinical-case-id",
  "meta": {
    "isClinicalCase": true
  },
  "questions": [...] // Nested questions array
}
```

## Troubleshooting

### Port Already in Use

If port 5000 or 8080 is already in use:

1. **Change API server port**: Edit `api_server.py`, change `port=5000` to another port
2. **Change static server port**: Run `python static_server.py 8081` (or any port)

### Assets Not Loading

1. Make sure `extract_assets.py` ran successfully
2. Check that `scraped_website/extracted_assets/` exists
3. Verify files in `js/` and `css/` directories

### API Returns 404

1. Check that JSON files exist in `../Data/` directory
2. Verify API server is running on port 5000
3. Check browser console for CORS errors

### Vue App Not Loading

The extracted Vue.js app might need additional configuration:

1. The current `index.html` is a basic template
2. You may need to:
   - Load the actual Vue app bundles from extracted JS files
   - Configure Vue Router
   - Set up Vuex/Pinia state management
   - Configure API base URL

### CORS Errors

The API server has CORS enabled by default. If you still see CORS errors:
1. Check that Flask-CORS is installed: `pip install flask-cors`
2. Verify `CORS(app)` is called in `api_server.py`

## Next Steps

### Full Rebuild

To fully rebuild the website with all functionality:

1. **Analyze Vue App Structure**
   - Examine extracted JS files to understand component structure
   - Identify Vue Router configuration
   - Find state management setup (Vuex/Pinia)

2. **Rebuild Vue App**
   - Create proper Vue.js project structure
   - Set up Vue Router with all routes
   - Implement components based on extracted code
   - Configure API calls to use local API server

3. **Enhance API Server**
   - Add more endpoints as needed
   - Implement filtering, searching, pagination
   - Add user session management if needed

4. **Test Everything**
   - Test all routes
   - Test API endpoints
   - Test question display
   - Test clinical cases
   - Test navigation

## Notes

- The current rebuild is a **basic version** that serves the structure
- Full functionality requires understanding the Vue.js app code
- The extracted JS files are minified/bundled - you may need to:
  - Use source maps if available
  - Reverse engineer component structure
  - Rebuild components from scratch based on functionality

## Support

For issues or questions:
1. Check `comprehensive_analysis.json` for detailed analysis
2. Review scraped HTML/JS files to understand structure
3. Test API endpoints directly: `http://localhost:5000/api/v1/health`
