"""
Mock API Server for MedLibro
Serves JSON data from Data/ folder to mimic the original API
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from pathlib import Path
import json
import os
from collections import defaultdict

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "Data"

# Cache for loaded data
_data_cache = {}
_year_mapping = {
    "1st": "1st.json",
    "2nd": "2nd.json",
    "3rd": "3rd.json",
    "4th": "4th.json",
    "5th": "5th.json",
    "6th": "6th.json",
    "residency": "residency.json"
}

def load_data():
    """Load all JSON data files"""
    global _data_cache
    
    if _data_cache:
        return _data_cache
    
    print(f"[INFO] Loading data from {DATA_DIR}")
    
    for year_key, filename in _year_mapping.items():
        filepath = DATA_DIR / filename
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    _data_cache[year_key] = json.load(f)
                print(f"[OK] Loaded {filename}: {len(_data_cache[year_key])} items")
            except Exception as e:
                print(f"[ERROR] Failed to load {filename}: {e}")
        else:
            print(f"[WARN] File not found: {filename}")
    
    return _data_cache

def find_question_by_id(question_id):
    """Find a question by ID across all years"""
    data = load_data()
    
    for year_data in data.values():
        if isinstance(year_data, list):
            for item in year_data:
                if isinstance(item, dict):
                    # Check various ID fields
                    if item.get('id') == question_id:
                        return item
                    if item.get('questionId') == question_id:
                        return item
                    if item.get('_id') == question_id:
                        return item
    
    return None

def find_clinical_case_by_id(clinical_case_id):
    """Find a clinical case by ID"""
    data = load_data()
    
    for year_data in data.values():
        if isinstance(year_data, list):
            for item in year_data:
                if isinstance(item, dict):
                    # Check if it's a clinical case
                    meta = item.get('meta', {})
                    if meta.get('isClinicalCase'):
                        if item.get('id') == clinical_case_id:
                            return item
                        if item.get('clinicalCaseId') == clinical_case_id:
                            return item
    
    return None

@app.route('/api/v1/years', methods=['GET'])
def get_years():
    """Get all available years"""
    data = load_data()
    years = []
    
    for year_key in _year_mapping.keys():
        if year_key in data:
            year_data = data[year_key]
            if isinstance(year_data, list) and len(year_data) > 0:
                # Get year info from first item
                first_item = year_data[0]
                year_info = {
                    "id": year_key,
                    "label": first_item.get('year_label', year_key),
                    "name": first_item.get('year_name', year_key)
                }
                years.append(year_info)
    
    return jsonify(years)

@app.route('/api/v1/revision', methods=['GET'])
def get_revision():
    """Get revision data (years, themes, chapters)"""
    data = load_data()
    result = []
    
    for year_key, year_data in data.items():
        if not isinstance(year_data, list):
            continue
        
        # Group by theme
        themes_dict = defaultdict(lambda: {"chapters": set(), "questions": []})
        
        for item in year_data:
            if isinstance(item, dict):
                theme = item.get('theme', item.get('theme_label', 'Unknown'))
                chapter = item.get('chapter', item.get('chapter_label', 'Unknown'))
                
                themes_dict[theme]["chapters"].add(chapter)
                themes_dict[theme]["questions"].append(item)
        
        # Convert to list format
        themes = []
        for theme_name, theme_data in themes_dict.items():
            themes.append({
                "id": theme_name.lower().replace(' ', '_'),
                "name": theme_name,
                "chapters": sorted(list(theme_data["chapters"])),
                "questions_count": len(theme_data["questions"])
            })
        
        result.append({
            "year": year_key,
            "year_label": year_data[0].get('year_label', year_key) if year_data else year_key,
            "themes": themes
        })
    
    return jsonify(result)

@app.route('/api/v1/themes', methods=['GET'])
def get_themes():
    """Get themes for a specific year"""
    year = request.args.get('year')
    if not year:
        return jsonify({"error": "Year parameter required"}), 400
    
    data = load_data()
    if year not in data:
        return jsonify({"error": f"Year '{year}' not found"}), 404
    
    year_data = data[year]
    if not isinstance(year_data, list):
        return jsonify({"error": "Invalid data format"}), 500
    
    # Group by theme
    themes_dict = defaultdict(lambda: {"chapters": set(), "questions": []})
    
    for item in year_data:
        if isinstance(item, dict):
            theme = item.get('theme', item.get('theme_label', 'Unknown'))
            chapter = item.get('chapter', item.get('chapter_label', 'Unknown'))
            
            themes_dict[theme]["chapters"].add(chapter)
            themes_dict[theme]["questions"].append(item)
    
    themes = []
    for theme_name, theme_data in themes_dict.items():
        themes.append({
            "id": theme_name.lower().replace(' ', '_'),
            "name": theme_name,
            "chapters": sorted(list(theme_data["chapters"])),
            "questions_count": len(theme_data["questions"])
        })
    
    return jsonify(themes)

@app.route('/api/v1/chapters', methods=['GET'])
def get_chapters():
    """Get chapters for a specific theme/year"""
    year = request.args.get('year')
    theme = request.args.get('theme')
    
    if not year:
        return jsonify({"error": "Year parameter required"}), 400
    
    data = load_data()
    if year not in data:
        return jsonify({"error": f"Year '{year}' not found"}), 404
    
    year_data = data[year]
    if not isinstance(year_data, list):
        return jsonify({"error": "Invalid data format"}), 500
    
    # Filter by theme if provided
    chapters_set = set()
    for item in year_data:
        if isinstance(item, dict):
            item_theme = item.get('theme', item.get('theme_label', ''))
            if not theme or item_theme == theme:
                chapter = item.get('chapter', item.get('chapter_label', 'Unknown'))
                chapters_set.add(chapter)
    
    chapters = [{"id": ch.lower().replace(' ', '_'), "name": ch} for ch in sorted(chapters_set)]
    
    return jsonify(chapters)

@app.route('/api/v1/questions/<question_id>', methods=['GET'])
def get_question(question_id):
    """Get a specific question by ID"""
    question = find_question_by_id(question_id)
    
    if not question:
        return jsonify({"error": "Question not found"}), 404
    
    return jsonify(question)

@app.route('/api/v1/clinical-cases/<clinical_case_id>', methods=['GET'])
def get_clinical_case(clinical_case_id):
    """Get a specific clinical case by ID"""
    clinical_case = find_clinical_case_by_id(clinical_case_id)
    
    if not clinical_case:
        return jsonify({"error": "Clinical case not found"}), 404
    
    return jsonify(clinical_case)

@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    """Mock login endpoint - returns same validated premium user for any credentials."""
    return jsonify({
        "token": "mock_jwt_token_for_local_development",
        "user": {**MOCK_USER}
    })


@app.route('/api/v1/auth/validate', methods=['POST'])
@app.route('/api/v1/auth/validate-account', methods=['POST'])
@app.route('/api/v2/auth/validate', methods=['POST'])
def validate_account():
    """Mock email validation - always success so app unlocks (local mirror)."""
    return jsonify({"success": True, "user": {**MOCK_USER}})


@app.route('/api/v1/auth/request-validation-code', methods=['POST'])
@app.route('/api/v2/auth/request-validation-code', methods=['POST'])
def request_validation_code():
    """Mock request validation code - no-op success (local mirror)."""
    return jsonify({"success": True, "message": "Code sent"})

@app.route('/api/v1/auth/logout', methods=['POST'])
def logout():
    """Mock logout endpoint"""
    return jsonify({"message": "Logged out successfully"})

@app.route('/api/v1/user/profile', methods=['GET'])
def get_profile():
    """Get user profile (same as MOCK_USER so validated/premium)."""
    return jsonify({**MOCK_USER})

# Common "current user" endpoints - emailVerified/validated so dashboard unlocks (no email validation step)
MOCK_USER = {
    "id": "mock_user_id",
    "email": "user@example.com",
    "name": "Local User",
    "subscription": "premium",
    "emailVerified": True,
    "email_verified": True,
    "validated": True,
}

@app.route('/api/v1/me', methods=['GET'])
@app.route('/api/v1/user/me', methods=['GET'])
@app.route('/api/v1/user', methods=['GET'])  # GET /api/v1/user = current user (no trailing path)
@app.route('/api/v1/auth/me', methods=['GET'])
@app.route('/api/v1/auth/user', methods=['GET'])
@app.route('/api/v1/auth/authenticated', methods=['GET'])
def get_me():
    """Current user / auth check - so app auth checks pass and connectedUser is set."""
    return jsonify({"user": MOCK_USER, **MOCK_USER, "authenticated": True})

@app.route('/api/v1/questions/count', methods=['GET'])
def get_questions_count():
    """Question count for homepage."""
    data = load_data()
    total = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
    return jsonify(total)

@app.route('/api/v2/sources/count', methods=['GET'])
def get_v2_sources_count():
    """V2 API: sources count (same as questions count)."""
    data = load_data()
    total = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
    return jsonify(total)

@app.route('/api/v2/sources/latest', methods=['GET'])
def get_v2_sources_latest():
    """V2 API: latest sources/exams."""
    return jsonify([])

@app.route('/api/v2/plans', methods=['GET'])
def get_v2_plans():
    """V2 API: plans (pricing)."""
    return jsonify([])

@app.route('/api/v1/health', methods=['GET'])
def health():
    """Health check endpoint"""
    data = load_data()
    return jsonify({
        "status": "ok",
        "years_loaded": len(data),
        "total_questions": sum(len(v) if isinstance(v, list) else 0 for v in data.values())
    })

if __name__ == '__main__':
    print("=" * 80)
    print("MEDLIBRO MOCK API SERVER")
    print("=" * 80)
    print(f"Data directory: {DATA_DIR}")
    print(f"Starting server on http://localhost:5000")
    print("=" * 80)
    
    # Load data on startup
    load_data()
    
    # Run server
    app.run(host='0.0.0.0', port=5000, debug=True)
