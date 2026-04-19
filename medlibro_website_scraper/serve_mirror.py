"""
Serve the exact MedLibro mirror: static files + LOCAL API server (fully local, no external calls).

*** THIS IS NOT A STATIC SITE ***
You MUST run this server (python serve_mirror.py). The app will NOT work if you just
open mirror/index.html in the browser (no API, no auth). Run run_exact_copy.bat or
launch_servers.bat, then the browser will open automatically (default http://localhost:8080).

Optional environment (Docker / Render):
  MEDLIBRO_DATA_DIR   — path to folder with 1st.json, 2nd.json, … (default: ../Data)
  MEDLIBRO_STATE_DIR  — writable dir for mirror_users.json & mirror_sessions.json (default: this package dir)
  PORT                — HTTP port for `python serve_mirror.py` (default: 8080; Render sets this for gunicorn)

  MEDLIBRO_YEAR_KEYS   — comma list overrides year set (e.g. all years for production tests).
  MEDLIBRO_ALL_YEARS   — if 1/true, expose full curriculum (same as all keys).
  Default deploy: 1st, 2nd, 3rd, residency only (4th–6th skipped for small-RAM test hosts).
  MEDLIBRO_PREFER_JSONL — if 1/true, use *.jsonl when both .json and .jsonl exist (slower, lower peak RAM).
  MEDLIBRO_JSON_CACHE_YEARS — max parsed .json roots kept in RAM (default: all active years, cap 8). Set 1 for minimal RAM.
  MEDLIBRO_SKIP_JSON_WARMUP — if 1, do not preload .json years at startup (faster boot, slower first revision).

  The SPA main script is read from mirror/index.html (e.g. assets/index-<hash>.js). Patching a single
  hardcoded filename breaks after each MedLibro front-end build; we resolve the name at runtime.
"""
from pathlib import Path
import os
import re
import sys
import json
import uuid
import secrets
import copy
import threading
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone

try:
    from flask import Flask, send_from_directory, request, jsonify, redirect
    from flask_cors import CORS
    from werkzeug.security import generate_password_hash, check_password_hash
except ImportError:
    print("[ERROR] Install: pip install flask flask-cors")
    sys.exit(1)

PROJECT = Path(__file__).parent
MIRROR = PROJECT / "mirror"


def _spa_main_js_relpath():
    """Entry chunk path from mirror/index.html (hash changes each MedLibro build — never hardcode one name)."""
    idx = MIRROR / "index.html"
    if not idx.exists():
        return "assets/index-AtrV5JHa.js"
    try:
        html = idx.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "assets/index-AtrV5JHa.js"
    m = re.search(r'src="(/assets/index-[^"\s]+\.js)"', html)
    if m:
        return m.group(1).lstrip("/").replace("//", "/")
    return "assets/index-AtrV5JHa.js"


def _request_json_dict():
    """Parse JSON body even when Content-Type is missing or axios sends raw bytes."""
    d = request.get_json(silent=True)
    if isinstance(d, dict) and d:
        return d
    try:
        raw = request.get_data(as_text=True)
        if raw and raw.strip().startswith("{"):
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return {}


def _path_from_env(name: str, default: Path) -> Path:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw).resolve() if raw else default


DATA_DIR = _path_from_env("MEDLIBRO_DATA_DIR", PROJECT.parent / "Data")
_STATE_DIR = _path_from_env("MEDLIBRO_STATE_DIR", PROJECT)
try:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

app = Flask(__name__, static_folder=None)
CORS(app)  # Enable CORS for local API


def _patch_user_role_dict(u):
    """Ensure MedLibro user object has role.label, role.permissions[], and premium flags."""
    if not isinstance(u, dict):
        return
    if "role" not in u or not isinstance(u.get("role"), dict):
        u["role"] = {"label": "user", "permissions": []}
    else:
        if u["role"].get("permissions") is None:
            u["role"]["permissions"] = []
        if u["role"].get("label") is None:
            u["role"]["label"] = "user"
    # SaveToPlaylistDialog only fetches playlists when isPremium is true (auth store getter)
    if u.get("isPremium") is None:
        sub = (u.get("subscription") or "").lower()
        u["isPremium"] = sub in ("premium", "pro", "paid")
    if u.get("isValid") is None and u.get("status") == "valid":
        u["isValid"] = True


@app.after_request
def _ensure_user_role(response):
    """Ensure every JSON response that carries a user has user.role.permissions so connectedUser.role is never undefined."""
    if not response.content_type or "application/json" not in response.content_type:
        return response
    try:
        data = json.loads(response.get_data(as_text=True))
    except Exception:
        return response
    if not isinstance(data, dict):
        return response
    if "user" in data and isinstance(data["user"], dict):
        _patch_user_role_dict(data["user"])
    nested = data.get("data")
    if isinstance(nested, dict) and isinstance(nested.get("user"), dict):
        _patch_user_role_dict(nested["user"])
    # Patch root if it looks like the user object (e.g. authenticated spreads profile at root)
    if "id" in data and "email" in data and "status" in data:
        _patch_user_role_dict(data)
    try:
        response.set_data(json.dumps(data))
    except Exception:
        pass
    return response

_year_mapping = {
    "1st": "1st.json",
    "2nd": "2nd.json",
    "3rd": "3rd.json",
    "4th": "4th.json",
    "5th": "5th.json",
    "6th": "6th.json",
    "residency": "residency.json"
}
# French labels for years dropdown (screenshot: 3ème, 4ème, Résidanat, etc.)
YEAR_LABELS = {
    "1st": "1er",
    "2nd": "2ème",
    "3rd": "3ème",
    "4th": "4ème",
    "5th": "5ème",
    "6th": "6ème",
    "residency": "Résidanat",
}

# Excluded from default test deploy (4th–6th are the heavy externat years for many mirrors).
_HEAVY_YEAR_KEYS = frozenset({"4th", "5th", "6th"})


def _resolve_curriculum_year_key(yr):
    """Normalize UI value to a curriculum key present in active_year_mapping (1st, 2nd, …)."""
    if yr is None or yr == "":
        return None
    if isinstance(yr, bool):
        return None
    # Plain 1990–2100 values are QCM exam years in many client payloads — not curriculum slugs.
    if isinstance(yr, (int, float)):
        yi = int(yr)
        if 1990 <= yi <= 2100:
            return None
    s = str(yr).strip()
    if s.isdigit():
        yi = int(s)
        if 1990 <= yi <= 2100:
            return None
    allowed = active_year_mapping()
    if s in allowed:
        return s
    sl = s.lower()
    for k in allowed.keys():
        if sl == str(k).lower():
            return k
    for k, fn in allowed.items():
        stem = Path(fn).stem
        if sl == stem.lower() or sl == str(fn).lower():
            return k
    for k, lbl in YEAR_LABELS.items():
        if k in allowed and (sl == str(lbl).lower() or s == lbl):
            return k
    return s


def _exam_years_from_value(val):
    """Parse QCM exam years (2018, …) from int, '2018', 'source-2018', {id: 'source-2018'}."""
    out = []
    if val is None or isinstance(val, bool):
        return out
    if isinstance(val, dict):
        val = val.get("id") or val.get("year") or val.get("value") or val.get("label")
        if val is None:
            return out
    if isinstance(val, (int, float)):
        y = int(val)
        if 1990 <= y <= 2100:
            out.append(y)
        return out
    s = str(val).strip()
    if not s:
        return out
    m = re.search(r"(?:source-)?(\d{4})\b", s)
    if m:
        y = int(m.group(1))
        if 1990 <= y <= 2100:
            out.append(y)
        return out
    if s.replace("-", "").lstrip("-").isdigit():
        try:
            y = int(s)
            if 1990 <= y <= 2100:
                out.append(y)
        except ValueError:
            pass
    return out


def _dedupe_year_ints(acc):
    seen = set()
    out = []
    for y in acc:
        if y not in seen:
            seen.add(y)
            out.append(y)
    return out


def _merged_exam_source_years(body, depth=0):
    """Merge exam-year filters from flat keys and nested filter/request/options (stock SPA nests filters)."""
    acc = []
    if not isinstance(body, dict) or depth > 14:
        return acc
    for key in (
        "sourcesYears",
        "sources_years",
        "sourceYears",
        "years",
        "examYears",
        "selectedExamYears",
        "qcmYears",
        "sourcesYear",
        "examSourcesYears",
        # Stock app sometimes sends the picked exam year as selectedYear (numeric 2018–2100).
        "selectedYear",
        "selectedSourceYear",
    ):
        v = body.get(key)
        if v is None:
            continue
        if isinstance(v, (list, tuple, set)):
            for it in v:
                if isinstance(it, dict):
                    acc.extend(_merged_exam_source_years(it, depth + 1))
                acc.extend(_exam_years_from_value(it))
        elif isinstance(v, str):
            for part in re.split(r"[\s,;]+", v.strip()):
                acc.extend(_exam_years_from_value(part))
        else:
            acc.extend(_exam_years_from_value(v))
    for key in ("sources", "sourceIds", "selectedSources", "examSources", "selectedSourceIds", "sourceList"):
        for it in (body.get(key) or []):
            if isinstance(it, dict):
                acc.extend(_merged_exam_source_years(it, depth + 1))
            acc.extend(_exam_years_from_value(it))
    for key in ("sourceId", "examYear", "selectedSourceYear", "qcmYear"):
        if body.get(key) is not None:
            acc.extend(_exam_years_from_value(body.get(key)))
    # Body field "year" is often the selected QCM year (2018, …), not curriculum.
    if body.get("year") is not None:
        acc.extend(_exam_years_from_value(body.get("year")))
    # Nested payloads (Vue/Pinia often wrap filters here)
    for nest_key in (
        "filter",
        "filters",
        "request",
        "payload",
        "params",
        "selection",
        "input",
        "variables",
        "graphql",
        "data",
        "criteria",
        "session",
        "meta",
        "context",
        "attributes",
        "option",
    ):
        nested = body.get(nest_key)
        if isinstance(nested, dict):
            acc.extend(_merged_exam_source_years(nested, depth + 1))
        elif isinstance(nested, list):
            for el in nested:
                if isinstance(el, dict):
                    acc.extend(_merged_exam_source_years(el, depth + 1))
    opts = body.get("options")
    if isinstance(opts, list):
        for el in opts:
            if isinstance(el, dict):
                acc.extend(_merged_exam_source_years(el, depth + 1))
    return _dedupe_year_ints(acc)


def _question_sources_exam_years_ints(item):
    """Return exam years from question.sources[].year only (MedLibro API row shape).

    Scraped data often sets meta.sourcesYears to a long cumulative list so that field
    makes year filters useless; the per-source ``year`` on each question row is the
    value the real app uses for source-year filtering.
    """
    if not isinstance(item, dict):
        return None
    q = item.get("question")
    if not isinstance(q, dict):
        return None
    acc = []
    for src in (q.get("sources") or []):
        if isinstance(src, dict) and src.get("year") is not None:
            acc.extend(_exam_years_from_value(src.get("year")))
    if not acc:
        return None
    return _dedupe_year_ints(acc)


def _item_exam_year_ints(meta, item):
    """Flatten QCM exam years from meta.sourcesYears, question.sources, etc."""
    prim = _question_sources_exam_years_ints(item)
    if prim is not None:
        return prim
    iy = []
    if isinstance(meta, dict):
        for y in meta.get("sourcesYears") or []:
            iy.extend(_exam_years_from_value(y))
        if meta.get("sourceYear") is not None:
            iy.extend(_exam_years_from_value(meta.get("sourceYear")))
        for lbl_key in ("sourceLabel", "examSource", "sourceTitle", "rattLabel", "examLabel", "qcmSource"):
            if meta.get(lbl_key):
                iy.extend(_exam_years_from_value(meta.get(lbl_key)))
        srcm = meta.get("sources")
        if isinstance(srcm, list):
            for x in srcm:
                iy.extend(_exam_years_from_value(x))
        if isinstance(meta.get("source"), str):
            iy.extend(_exam_years_from_value(meta.get("source")))
    if isinstance(item, dict):
        for top_k in ("source", "sourceName", "sourceText", "sourceLabel", "rattSource"):
            v = item.get(top_k)
            if isinstance(v, str) and v.strip():
                iy.extend(_exam_years_from_value(v))
        q = item.get("question")
        if isinstance(q, dict):
            for y in q.get("sourcesYears") or []:
                iy.extend(_exam_years_from_value(y))
            if q.get("sourceYear") is not None:
                iy.extend(_exam_years_from_value(q.get("sourceYear")))
            for src in q.get("sources") or []:
                iy.extend(_exam_years_from_value(src))
            if q.get("year") is not None:
                iy.extend(_exam_years_from_value(q.get("year")))
            for lbl_key in ("sourceLabel", "examSource", "sourceTitle", "rattLabel"):
                if q.get(lbl_key):
                    iy.extend(_exam_years_from_value(q.get(lbl_key)))
    seen = set()
    out = []
    for y in iy:
        if y not in seen:
            seen.add(y)
            out.append(y)
    return out


# Keys copied from POST /sessions body into each option so filters (e.g. sourcesYears) apply when the client only sends them once.
_SESSION_FILTER_DEFAULT_KEYS = frozenset({
    "sourcesYears", "sources_years", "sourceYears", "years", "examYears", "selectedExamYears", "qcmYears",
    "sources", "sourceIds", "selectedSources", "examSources", "selectedSourceIds",
    "sourceId", "examYear", "selectedSourceYear", "selectedSourceYears", "qcmYear", "year",
    "yearId", "year_id", "selectedYear", "selectedYearId", "educationYearId",
    "curriculumYearId", "curriculumYear", "curriculum_year",
})


def _session_filter_defaults(body):
    if not isinstance(body, dict):
        return {}
    d = {k: v for k, v in body.items() if k in _SESSION_FILTER_DEFAULT_KEYS}
    # Whole nested filter blobs (sourcesYears often only under filter / request)
    for k in ("filter", "filters", "request", "selection", "payload", "criteria"):
        if isinstance(body.get(k), dict):
            d[k] = body[k]
    return d


def _revision_body_merge_query(body):
    """Merge relevant query-string params into POST body (clients sometimes send filters only as ?args)."""
    from flask import request

    body = dict(body or {})
    # Rare: filters sent as application/x-www-form-urlencoded instead of JSON
    if request.form:
        for fk in request.form.keys():
            if body.get(fk) not in (None, "", []):
                continue
            vals = request.form.getlist(fk)
            if len(vals) == 1:
                body[fk] = vals[0]
            elif len(vals) > 1:
                body[fk] = vals
    for k in (
        "yearId", "year_id", "selectedYear", "selectedYearId", "educationYearId",
        "curriculumYearId", "curriculumYear", "curriculum_year",
    ):
        if body.get(k) in (None, ""):
            v = request.args.get(k)
            if v not in (None, ""):
                body[k] = v.strip() if isinstance(v, str) else v
    if not body.get("sourcesYears") and not body.get("sources"):
        sy = request.args.getlist("sourcesYears") or request.args.getlist("sources_years")
        if not sy:
            ss = request.args.get("sourcesYears") or request.args.get("sources_years")
            if ss:
                sy = [x.strip() for x in re.split(r"[\s,;]+", str(ss).strip()) if x.strip()]
        if sy:
            body["sourcesYears"] = sy
    return body


_MEMORIX_RE = re.compile(r"m[eé]morix", re.IGNORECASE)


def _bundle_contains_memorix(js: str) -> bool:
    """Match Memorix / Mémorix in minified bundles."""
    return _MEMORIX_RE.search(js or "") is not None


def _strip_js_route_object_at_needle(js: str, needle: str) -> str:
    """Remove outermost `{ ... needle ... }` balanced object starting at `{` before needle."""
    for _ in range(80):
        try:
            i = js.index(needle)
        except ValueError:
            break
        j = i
        while j >= 0 and js[j] != "{":
            j -= 1
        if j < 0 or js[j] != "{":
            break
        start = j
        depth = 0
        end = None
        for k in range(start, len(js)):
            if js[k] == "{":
                depth += 1
            elif js[k] == "}":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
        if end is None:
            break
        rm0 = start
        if rm0 > 0 and js[rm0 - 1] == ",":
            rm0 -= 1
        elif end < len(js) and js[end] == ",":
            end += 1
        js = js[:rm0] + js[end:]
    return js


def _strip_memorix_from_js_bundle(js: str) -> str:
    """Remove Vue-router routes and labels for Memorix/Mémorix from minified bundles."""
    if not _bundle_contains_memorix(js):
        return js
    # Drop Memorix chunks from Vite dep arrays (quoted "assets/Memorix….js").
    js = re.sub(r',"(?:assets/)?MemorixPage-[^"]+\.js"', "", js)
    js = re.sub(r',"(?:assets/)?MemorixTopThemesCard-[^"]+\.js"', "", js)
    js = re.sub(r'import\("\./MemorixPage-[^"]+\.js"\)', 'import("./index-BjaFTGv8.js")', js)
    needles = (
        'path:"/memorix"',
        "path:'/memorix'",
        'path:"/mémorix"',
        "path:'/mémorix'",
        'path:"/memorix/:themeId"',
        "path:'/memorix/:themeId'",
    )
    for needle in needles:
        for _ in range(80):
            if needle not in js:
                break
            try:
                i = js.index(needle)
            except ValueError:
                break
            j = i
            while j >= 0 and js[j] != "{":
                j -= 1
            if j < 0 or js[j] != "{":
                break
            start = j
            depth = 0
            end = None
            for k in range(start, len(js)):
                if js[k] == "{":
                    depth += 1
                elif js[k] == "}":
                    depth -= 1
                    if depth == 0:
                        end = k + 1
                        break
            if end is None:
                break
            rm0 = start
            if rm0 > 0 and js[rm0 - 1] == ",":
                rm0 -= 1
            elif end < len(js) and js[end] == ",":
                end += 1
            js = js[:rm0] + js[end:]
    for needle in (
        'name:"memorix"',
        "name:'memorix'",
        'name: "memorix"',
        'name:"Memorix"',
        'name:"Mémorix"',
        "name:'Mémorix'",
    ):
        js = _strip_js_route_object_at_needle(js, needle)
    js = js.replace('"/memorix"', '"/dashboard"')
    js = js.replace("'/memorix'", "'/dashboard'")
    js = js.replace('path:"/memorix"', 'path:"/dashboard"')
    js = js.replace('"/mémorix"', '"/dashboard"')
    return js


def _strip_memorix_from_clientlayout_js(js: str) -> str:
    """Remove Memorix item from ClientLayout sidebar navigationItems (built SPA)."""
    if not js or "memorix" not in js.lower():
        return js
    # Exact shape from stock ClientLayout (MedLibro): one nav object with to:"memorix".
    js = re.sub(
        r',\{to:"memorix",icon:"mdi-brain",title:"memorix",available:this\.isAuthenticated,'
        r"disabled:!this\.isValid\|\|!this\.isPremium,new:!1,test:!1\}",
        "",
        js,
        count=1,
    )
    return js


def _strip_memorix_from_dashboard_js(js: str) -> str:
    """Remove Memorix shortcut card + Memorix themes card from DashboardPage chunk."""
    if not js or "memorix" not in js.lower():
        return js
    js = js.replace(
        'i("PrimaryShortcut",{staticClass:"flex-grow-1",attrs:{locked:!t.isValid||!t.isPremium,'
        '"leading-icon":"mdi-brain",title:"memorix",to:"memorix","trailing-icon":"mdi-chevron-right"}}),',
        "",
        1,
    )
    js = re.sub(
        r"y=\(\)=>[a-zA-Z_$][a-zA-Z0-9_$]*\(\(\)=>import\(\"\./MemorixTopThemesCard-[^\"]+\.js\"\),__vite__mapDeps\(\[[^\]]+\]\)\),",
        "",
        js,
        count=1,
    )
    js = js.replace("MemorixTopThemesCard:y,", "").replace(",MemorixTopThemesCard:y", "")
    js = js.replace('t.isPremium?i("memorix-top-themes-card"):t._e(),', "")
    js = re.sub(r',"(?:assets/)?MemorixTopThemesCard-[^"]+\.js"', "", js)
    return js


def _memorix_stub_esm() -> str:
    """Minimal Vue component stub so imports stay valid after Memorix chunks are gutted."""
    return "export default{name:\"MLStub\",render:function(){return null}};\n"


def _env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def active_year_mapping():
    """
    Which year keys are exposed for this deployment (API + data paths).

    - MEDLIBRO_YEAR_KEYS: explicit comma list (e.g. 1st,2nd,3rd,4th,5th,6th,residency) wins if set.
    - MEDLIBRO_ALL_YEARS=1: full curriculum (same as all keys in _year_mapping).
    - Default (test / free tier): 1st, 2nd, 3rd, residency only (4th–6th omitted).

    Memory: *.json is cached for multiple years (see MEDLIBRO_JSON_CACHE_YEARS); set MEDLIBRO_PREFER_JSONL=1 for JSONL.
    """
    explicit = (os.environ.get("MEDLIBRO_YEAR_KEYS") or "").strip()
    if explicit:
        allow = {x.strip() for x in explicit.split(",") if x.strip()}
        m = {k: v for k, v in _year_mapping.items() if k in allow}
        if not m:
            print("[WARN] MEDLIBRO_YEAR_KEYS matched no known years; using full year mapping")
            return dict(_year_mapping)
        return m
    if _env_truthy("MEDLIBRO_ALL_YEARS"):
        return dict(_year_mapping)
    return {k: v for k, v in _year_mapping.items() if k not in _HEAVY_YEAR_KEYS}


# Parsed .json roots: year_key -> object graph. Multi-slot LRU so /revision can hit all test years without re-parse.
_year_data_lock = threading.Lock()
_year_json_cache: OrderedDict = OrderedDict()
_year_load_logged = set()


def _year_json_cache_capacity():
    """How many full JSON roots to keep in RAM. Default fits all active keys (max 8); lower for huge full-curriculum deploys."""
    ex = (os.environ.get("MEDLIBRO_JSON_CACHE_YEARS") or "").strip()
    if ex.isdigit():
        return max(1, int(ex))
    n = len(active_year_mapping())
    return min(8, max(1, n))


def _get_year_parsed_lru(year_key):
    """Parse one year JSON and store in an LRU shared across years (so revision iterates stay hot)."""
    mapping = active_year_mapping()
    filename = mapping.get(year_key)
    if not filename:
        raise KeyError(year_key)
    filepath = DATA_DIR / filename
    if not filepath.exists():
        raise KeyError(year_key)
    cap = _year_json_cache_capacity()
    with _year_data_lock:
        if year_key in _year_json_cache:
            _year_json_cache.move_to_end(year_key)
            return _year_json_cache[year_key]
        while len(_year_json_cache) >= cap:
            _year_json_cache.popitem(last=False)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                parsed = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load {filename}: {e}")
            raise
        _year_json_cache[year_key] = parsed
        if filename not in _year_load_logged:
            _year_load_logged.add(filename)
            items = _year_items(parsed)
            print(
                f"[OK] Loaded {filename}: {len(items)} items (json cache {len(_year_json_cache)}/{cap} years)"
            )
        return parsed


def _warm_year_json_cache():
    """Preload each year’s .json so first /revision is fast (no-op for JSONL-only or if skipped)."""
    if _env_truthy("MEDLIBRO_SKIP_JSON_WARMUP") or _env_truthy("MEDLIBRO_PREFER_JSONL"):
        return
    for yk in list(active_year_mapping().keys()):
        kind, _ = _year_resolve_paths(yk)
        if kind != "json":
            continue
        try:
            _get_year_parsed_lru(yk)
        except Exception as ex:
            print(f"[WARN] JSON warm skipped for {yk}: {ex}")


def _year_resolve_paths(year_key):
    """Return ('json', path) or ('jsonl', path) or (None, None). Prefer .json for LRU speed unless MEDLIBRO_PREFER_JSONL=1."""
    m = active_year_mapping()
    fn = m.get(year_key)
    if not fn:
        return None, None
    stem = Path(fn).stem
    jsonl = DATA_DIR / f"{stem}.jsonl"
    jsonp = DATA_DIR / fn
    prefer_jsonl = _env_truthy("MEDLIBRO_PREFER_JSONL")
    if prefer_jsonl:
        if jsonl.is_file():
            return "jsonl", jsonl
        if jsonp.is_file():
            return "json", jsonp
    else:
        if jsonp.is_file():
            return "json", jsonp
        if jsonl.is_file():
            return "jsonl", jsonl
    return None, None


class _JsonlQuestionList:
    """Lazy view over one JSONL file: stream iterations; single-pass cached stats for len/get_years."""

    __slots__ = ("_path", "_scan")

    def __init__(self, path):
        self._path = Path(path)
        self._scan = None  # (mtime_ns, first_item, (q_st, cc_n, cc_q), n_items)

    def _ensure_scan(self):
        st = self._path.stat()
        if self._scan and self._scan[0] == st.st_mtime_ns:
            return
        first = None
        acc = _qst_cc_acc_new()
        n = 0
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if first is None:
                    first = item
                _qst_cc_acc_add(acc, item)
                n += 1
        self._scan = (st.st_mtime_ns, first, _qst_cc_acc_totals(acc), n)

    def scan_meta(self):
        """One full pass (cached): first question dict or None, QST/CC totals tuple, row count."""
        self._ensure_scan()
        return self._scan[1], self._scan[2], self._scan[3]

    def __len__(self):
        self._ensure_scan()
        return self._scan[3]

    def __iter__(self):
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def __getitem__(self, idx):
        if idx == 0:
            for item in self:
                return item
            raise IndexError(0)
        for i, item in enumerate(self):
            if i == idx:
                return item
        raise IndexError(idx)


class _YearDatasetView:
    """year_key -> either streaming JSONL wrapper dict or parsed JSON (LRU 1 for .json only)."""

    def keys(self):
        return [k for k in active_year_mapping().keys() if _year_resolve_paths(k)[0]]

    def __contains__(self, year_key):
        return _year_resolve_paths(year_key)[0] is not None

    def __getitem__(self, year_key):
        kind, path = _year_resolve_paths(year_key)
        if kind == "jsonl":
            return {"questions": _JsonlQuestionList(path), "year": None}
        if kind == "json":
            return _get_year_parsed_lru(year_key)
        raise KeyError(year_key)

    def items(self):
        for k in self.keys():
            yield k, self[k]

    def values(self):
        for k in self.keys():
            yield self[k]


_DATASET_SINGLETON = _YearDatasetView()

# Session tokens issued after successful login (prefix must match inline auth script in index.html)
TOKEN_PREFIX = "mloc_"
USERS_STORE_PATH = _STATE_DIR / "mirror_users.json"
SESSIONS_STORE_PATH = _STATE_DIR / "mirror_sessions.json"
SEED_USERS_PATH = PROJECT / "mirror_users_seed.json"

_users_by_email = {}
_sessions_by_token = {}


def _normalize_email(value):
    return (value or "").strip().lower()


def _new_profile_payload(email, first_name, last_name, year=None, gender=None, *, fully_validated=True):
    full = f"{first_name} {last_name}".strip() or email.split("@")[0]
    user_part = email.split("@")[0] if "@" in email else email
    if fully_validated:
        profile = {
            "id": str(uuid.uuid4()),
            "email": email,
            "username": user_part,
            "name": full,
            "fullName": full,
            "firstName": first_name or "",
            "lastName": last_name or "",
            "phoneNumber": None,
            "subscription": "premium",
            "isPremium": True,
            "isValid": True,
            "status": "valid",
            "emailVerified": True,
            "email_verified": True,
            "validated": True,
            "isEmailVerified": True,
            "accountValidated": True,
            "email_validated": True,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "role": {"label": "user", "permissions": []},
        }
    else:
        profile = {
            "id": str(uuid.uuid4()),
            "email": email,
            "username": user_part,
            "name": full,
            "fullName": full,
            "firstName": first_name or "",
            "lastName": last_name or "",
            "phoneNumber": None,
            "subscription": "free",
            "isPremium": False,
            "isValid": False,
            "status": "pending",
            "emailVerified": False,
            "email_verified": False,
            "validated": False,
            "isEmailVerified": False,
            "accountValidated": False,
            "email_validated": False,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "role": {"label": "user", "permissions": []},
        }
    if year is not None:
        profile["year"] = year
    if gender is not None:
        profile["gender"] = gender
    _patch_user_role_dict(profile)
    return profile


def _gen_validation_code():
    return f"{secrets.randbelow(1000000):06d}"


def _migrate_stored_user(rec):
    """Fill fields added after first mirror versions; default legacy accounts to validated."""
    if not isinstance(rec, dict) or "profile" not in rec:
        return
    p = rec["profile"]
    if not isinstance(p, dict):
        return
    em = p.get("email") or ""
    if em and p.get("username") in (None, ""):
        p["username"] = em.split("@")[0]
    if "phoneNumber" not in p:
        p["phoneNumber"] = None
    if not p.get("status"):
        p["status"] = "valid"
    if p.get("status") == "valid":
        p.setdefault("isValid", True)
        p.setdefault("isPremium", True)
        p.setdefault("subscription", "premium")
        p.setdefault("emailVerified", True)
        p.setdefault("email_verified", True)
        p.setdefault("validated", True)
        rec.pop("email_validation_code", None)
    _patch_user_role_dict(p)


def _load_users_from_disk():
    global _users_by_email
    if not USERS_STORE_PATH.exists():
        _users_by_email = {}
        return
    try:
        raw = json.loads(USERS_STORE_PATH.read_text(encoding="utf-8"))
        _users_by_email = raw.get("users") or {}
        for rec in _users_by_email.values():
            _migrate_stored_user(rec)
    except Exception as ex:
        print(f"[WARN] Could not load {USERS_STORE_PATH}: {ex}")
        _users_by_email = {}


def _save_users_to_disk():
    USERS_STORE_PATH.write_text(
        json.dumps({"users": _users_by_email}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _merge_seed_if_empty_store():
    """First-time: optional mirror_users_seed.json with pre-created accounts."""
    if _users_by_email or not SEED_USERS_PATH.exists():
        return
    try:
        raw = json.loads(SEED_USERS_PATH.read_text(encoding="utf-8"))
        added = 0
        for u in raw.get("users", []):
            em = _normalize_email(u.get("email"))
            if not em:
                continue
            pw = u.get("password") or ""
            if len(pw) < 8:
                print(f"[WARN] Seed skip {em}: password must be at least 8 characters")
                continue
            if em in _users_by_email:
                continue
            seed_valid = u.get("emailVerified", True)
            if not isinstance(seed_valid, bool):
                seed_valid = True
            prof = _new_profile_payload(
                em,
                (u.get("firstName") or "").strip(),
                (u.get("lastName") or "").strip(),
                year=u.get("year"),
                gender=u.get("gender"),
                fully_validated=seed_valid,
            )
            rec = {
                "password_hash": generate_password_hash(pw),
                "profile": prof,
            }
            if not seed_valid:
                code = _gen_validation_code()
                rec["email_validation_code"] = code
                print(f"[INFO] Seed account {em} pending validation. Code: {code}")
            _users_by_email[em] = rec
            added += 1
        if added:
            _save_users_to_disk()
            print(f"[INFO] Imported {added} account(s) from {SEED_USERS_PATH.name}")
    except Exception as ex:
        print(f"[WARN] Could not read seed file {SEED_USERS_PATH}: {ex}")


def _load_sessions_from_disk():
    global _sessions_by_token
    if not SESSIONS_STORE_PATH.exists():
        _sessions_by_token = {}
        return
    try:
        data = json.loads(SESSIONS_STORE_PATH.read_text(encoding="utf-8"))
        _sessions_by_token = data.get("sessions") or {}
    except Exception:
        _sessions_by_token = {}
    # Drop sessions for unknown users
    dead = [t for t, em in _sessions_by_token.items() if _normalize_email(em) not in _users_by_email]
    for t in dead:
        del _sessions_by_token[t]
    if dead:
        _save_sessions_to_disk()


def _save_sessions_to_disk():
    SESSIONS_STORE_PATH.write_text(
        json.dumps({"sessions": _sessions_by_token}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _init_local_auth():
    _load_users_from_disk()
    _merge_seed_if_empty_store()
    _load_sessions_from_disk()
    n = len(_users_by_email)
    print(f"[INFO] Local auth: {n} account(s) in {USERS_STORE_PATH.name}")
    if n == 0:
        print(
            "[INFO] No accounts yet: sign up on /signup, or copy mirror_users_seed.json.example "
            f"to {SEED_USERS_PATH.name} and restart (seed is loaded only while the account list is empty)."
        )


def _issue_session_token():
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def _get_raw_session_token():
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return (request.cookies.get("token") or request.cookies.get("authToken") or "").strip()


def _current_user_record():
    tok = _get_raw_session_token()
    if not tok or not tok.startswith(TOKEN_PREFIX):
        return None, None
    email = _sessions_by_token.get(tok)
    if not email:
        return None, None
    key = _normalize_email(email)
    rec = _users_by_email.get(key)
    if not rec:
        return None, None
    return rec.get("profile"), tok


def _session_triple():
    """(profile, email_key, rec) or (None, None, None)."""
    tok = _get_raw_session_token()
    if not tok or not tok.startswith(TOKEN_PREFIX):
        return None, None, None
    email = _sessions_by_token.get(tok)
    if not email:
        return None, None, None
    key = _normalize_email(email)
    rec = _users_by_email.get(key)
    if not rec or not isinstance(rec.get("profile"), dict):
        return None, None, None
    return rec["profile"], key, rec


def _public_user_response(profile):
    """Response shape MedLibro client expects on login / authenticated."""
    p = copy.deepcopy(profile)
    return {
        "user": p,
        "data": {"user": p},
        "authenticated": True,
        **p,
    }


_init_local_auth()

def _year_items(year_data):
    """Return list of question items from a year. Handles both { questions: [...] } and raw list."""
    if year_data is None:
        return []
    if isinstance(year_data, list):
        return year_data
    if isinstance(year_data, dict) and "questions" in year_data:
        return year_data["questions"]
    return []

_load_data_logged = False
_years_api_payload_cache = None
_years_api_payload_lock = threading.Lock()


def _build_years_api_payload_list():
    """Scan data for curriculum-year stats (Révision › Année d'étude); called once then cached."""
    data = load_data()
    years = []
    for year_key in active_year_mapping().keys():
        if year_key not in data:
            continue
        year_data = data[year_key]
        items = _year_items(year_data)
        if isinstance(items, _JsonlQuestionList):
            first_item, (q_st, cc_n, cc_q), n = items.scan_meta()
            if n <= 0:
                continue
            meta = first_item.get("meta", first_item) if isinstance(first_item, dict) else {}
            label = meta.get("year_label") or YEAR_LABELS.get(year_key) or year_key
            years.append({
                "id": year_key,
                "label": label,
                "name": meta.get("year_name", year_key),
                "forSale": True,
                "questionsCount": q_st,
                "clinicalCasesCount": cc_n,
                "clinicalCasesQuestionsCount": cc_q,
            })
        elif len(items) > 0:
            first_item = items[0]
            meta = first_item.get("meta", first_item)
            label = meta.get('year_label') or YEAR_LABELS.get(year_key) or (year_data.get('year') if isinstance(year_data, dict) else None) or year_key
            q_st, cc_n, cc_q = _count_qst_cc_from_items(items)
            years.append({
                "id": year_key,
                "label": label,
                "name": meta.get('year_name', year_key),
                "forSale": True,
                "questionsCount": q_st,
                "clinicalCasesCount": cc_n,
                "clinicalCasesQuestionsCount": cc_q,
            })
    return years


def _prime_years_api_payload_cache():
    """After JSON warm, precompute /api/v1/years so the dropdown is instant on Révision."""
    global _years_api_payload_cache
    try:
        with _years_api_payload_lock:
            if _years_api_payload_cache is None:
                _years_api_payload_cache = _build_years_api_payload_list()
                print("[INFO] Pre-cached /api/v1/years for revision year dropdown.")
    except Exception as ex:
        print(f"[WARN] Pre-cache /api/v1/years failed: {ex}")


def load_data():
    """Return the lazy year view; parsed .json years stay in a multi-entry cache (see MEDLIBRO_JSON_CACHE_YEARS)."""
    global _load_data_logged
    if not _load_data_logged:
        keys = ", ".join(active_year_mapping().keys())
        cap = _year_json_cache_capacity()
        print(
            f"[INFO] Question data: {DATA_DIR} (years: {keys}; json cache up to {cap} years; "
            f"prefer .json unless MEDLIBRO_PREFER_JSONL=1)"
        )
        _warm_year_json_cache()
        _load_data_logged = True
        _prime_years_api_payload_cache()
    return _DATASET_SINGLETON

def find_question_by_id(question_id):
    """Find a question by ID across all years (uses json cache / LRU)."""
    data = load_data()
    for year_key in data.keys():
        for item in _year_items(data[year_key]):
            if isinstance(item, dict):
                q = item.get("question", item)
                rid = item.get('id') or q.get('id') or item.get('questionId') or q.get('questionId') or item.get('_id')
                if rid == question_id:
                    return item
    return None


def _question_id(item):
    """Same id resolution as find_question_by_id (used for revision items)."""
    if not isinstance(item, dict):
        return None
    q = item.get("question", item)
    return item.get('id') or q.get('id') or item.get('questionId') or q.get('questionId') or item.get('_id')


def _clinical_case_id(item):
    """UUID of clinical case for this row, or None for standalone QST."""
    if not isinstance(item, dict):
        return None
    meta = item.get("meta")
    q = item.get("question", item)
    cid = None
    if isinstance(meta, dict):
        cid = meta.get("clinicalCaseId")
    if cid is None and isinstance(q, dict):
        cid = q.get("clinicalCaseId")
    if cid is None:
        cid = item.get("clinicalCaseId")
    if cid is None or cid == "":
        return None
    s = str(cid).strip()
    return s if s else None


def _qst_cc_acc_new():
    return {"standalone": 0, "cc_ids": set(), "cc_q_rows": 0}


def _qst_cc_acc_add(acc, item):
    if not isinstance(item, dict):
        return
    cid = _clinical_case_id(item)
    if cid:
        acc["cc_ids"].add(cid)
        acc["cc_q_rows"] += 1
    else:
        acc["standalone"] += 1


def _qst_cc_acc_totals(acc):
    return acc["standalone"], len(acc["cc_ids"]), acc["cc_q_rows"]


def _count_qst_cc_from_items(items):
    """
    Counts for FilterForm formatStats (mirror assets FilterField.formatStats):
    questionsCount → standalone QST; clinicalCasesCount → distinct CC;
    clinicalCasesQuestionsCount → QST rows that belong to a CC (parenthetical).
    """
    acc = _qst_cc_acc_new()
    for item in items or []:
        _qst_cc_acc_add(acc, item)
    return _qst_cc_acc_totals(acc)


# ============================================================================
# LOCAL API ENDPOINTS (all handled locally, no external calls)
# ============================================================================

def _set_auth_cookies(response, token):
    response.set_cookie("token", token, max_age=60 * 60 * 24 * 7, samesite="Lax", path="/")
    response.set_cookie("authToken", token, max_age=60 * 60 * 24 * 7, samesite="Lax", path="/")


def _clear_auth_cookies(response):
    response.set_cookie("token", "", max_age=0, path="/")
    response.set_cookie("authToken", "", max_age=0, path="/")


@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    """Login only for emails present in mirror_users.json (signup or seed file)."""
    body = request.get_json(silent=True) or {}
    ident = _normalize_email(body.get("identifier") or body.get("email"))
    password = body.get("password") or ""
    if not ident or not password:
        return jsonify({"message": "E-mail et mot de passe requis."}), 401
    rec = _users_by_email.get(ident)
    if not rec or not check_password_hash(rec["password_hash"], password):
        return jsonify({"message": "E-mail ou mot de passe incorrect."}), 401
    token = _issue_session_token()
    _sessions_by_token[token] = ident
    _save_sessions_to_disk()
    profile = rec["profile"]
    payload = {"token": token, **_public_user_response(profile)}
    resp = jsonify(payload)
    _set_auth_cookies(resp, token)
    return resp


@app.route('/api/v1/auth/authenticated', methods=['GET'])
@app.route('/api/v1/auth/me', methods=['GET'])
@app.route('/api/v1/user/me', methods=['GET'])
@app.route('/api/v1/user', methods=['GET'])
def get_authenticated():
    """Return the logged-in user profile, or 401."""
    profile, _tok = _current_user_record()
    if profile:
        return jsonify(_public_user_response(profile))
    return jsonify({"authenticated": False}), 401


@app.route('/api/v1/auth/logout', methods=['POST'])
def logout():
    """Invalidate server session and clear cookies."""
    tok = _get_raw_session_token()
    if tok and tok in _sessions_by_token:
        del _sessions_by_token[tok]
        _save_sessions_to_disk()
    resp = jsonify({"message": "Logged out successfully"})
    _clear_auth_cookies(resp)
    return resp


@app.route('/api/v1/auth/signup', methods=['POST'])
def signup():
    """Register new account (stored in mirror_users.json); does not log the user in."""
    body = request.get_json(silent=True) or {}
    email = _normalize_email(body.get("email"))
    first = (body.get("firstName") or "").strip()
    last = (body.get("lastName") or "").strip()
    password = body.get("password") or ""
    year = body.get("year")
    gender = body.get("gender")
    if not email or not first or not last or not password:
        return jsonify({"message": "Tous les champs obligatoires doivent être remplis."}), 400
    if year is None or year == "" or gender is None or gender == "":
        return jsonify({"message": "Veuillez compléter année d'étude et sexe."}), 400
    if len(password) < 8:
        return jsonify({"message": "Le mot de passe doit contenir au moins 8 caractères."}), 400
    if email in _users_by_email:
        return jsonify({"message": "Un compte existe déjà avec cet e-mail."}), 400
    code = _gen_validation_code()
    _users_by_email[email] = {
        "password_hash": generate_password_hash(password),
        "profile": _new_profile_payload(
            email, first, last, year=year, gender=gender, fully_validated=False
        ),
        "email_validation_code": code,
    }
    _save_users_to_disk()
    print(
        f"[INFO] Nouveau compte {email} — code de validation e-mail (ou bouton RENVOYER après connexion): {code}"
    )
    return jsonify({"message": "Compte créé. Vous pouvez vous connecter.", "authenticated": False}), 201


@app.route('/api/v1/auth/validate', methods=['POST', 'PATCH'])
@app.route('/api/v1/auth/validate-account', methods=['POST', 'PATCH'])
def validate_account():
    """Submit e-mail validation code; unlocks premium / valid status (dashboard card)."""
    body = request.get_json(silent=True) or {}
    identifier = _normalize_email(body.get("identifier"))
    token = str(body.get("token") or "").strip()
    profile, key, rec = _session_triple()
    if not profile or key != identifier:
        return jsonify({"message": "Non authentifié."}), 401
    if profile.get("status") == "valid":
        return jsonify({"message": "Compte déjà validé."}), 400
    if str(rec.get("email_validation_code") or "") != token:
        return jsonify({"message": "Code invalide."}), 400
    p = rec["profile"]
    p["status"] = "valid"
    p["isValid"] = True
    p["isPremium"] = True
    p["subscription"] = "premium"
    p["emailVerified"] = True
    p["email_verified"] = True
    p["validated"] = True
    p["isEmailVerified"] = True
    p["accountValidated"] = True
    p["email_validated"] = True
    rec["email_validation_code"] = None
    _patch_user_role_dict(p)
    _save_users_to_disk()
    return jsonify({**_public_user_response(p)})


@app.route('/api/v1/auth/request-validation-code', methods=['POST'])
def request_validation_code():
    """
    - Same e-mail as connected user: resend account validation code (pending accounts).
    - Different e-mail: request code to confirm an e-mail change (validated accounts only).
    """
    body = request.get_json(silent=True) or {}
    target = _normalize_email(body.get("email"))
    profile, key, rec = _session_triple()
    if not profile:
        return jsonify({"message": "Non authentifié."}), 401
    if not target:
        return jsonify({"message": "E-mail requis."}), 400
    if target == key:
        if profile.get("status") == "valid":
            return jsonify({"message": "Compte déjà validé."}), 400
        code = _gen_validation_code()
        rec["email_validation_code"] = code
        _save_users_to_disk()
        print(f"[INFO] Code validation compte pour {key}: {code}")
        return jsonify(
            {
                "success": True,
                "message": "Code généré. En local, ouvrez la console du serveur pour le voir.",
            }
        )
    if profile.get("status") != "valid":
        return jsonify({"message": "Validez d'abord votre compte avec votre e-mail actuel."}), 400
    if target in _users_by_email:
        return jsonify({"message": "Cet e-mail est déjà utilisé."}), 400
    code = _gen_validation_code()
    rec["pending_email"] = target
    rec["pending_email_code"] = code
    _save_users_to_disk()
    print(f"[INFO] Changement e-mail {key} → {target}: code = {code}")
    return jsonify(
        {
            "success": True,
            "message": "Code généré. En local, consultez la console du serveur.",
        }
    )


@app.route('/api/v1/auth/request-reset-code', methods=['POST'])
def request_reset_password_code():
    """Forgot password step 1 — MedLibro POST body: { identifier: email }."""
    body = request.get_json(silent=True) or {}
    ident = _normalize_email(body.get("identifier") or body.get("email"))
    if not ident:
        return jsonify({"message": "E-mail requis."}), 400
    rec = _users_by_email.get(ident)
    if not rec:
        print(f"[INFO] Demande réinit. mot de passe — aucun compte pour: {ident}")
        return jsonify(
            {
                "success": True,
                "message": "Si cette adresse est enregistrée, la suite est indiquée sur le serveur (miroir local).",
            }
        )
    code = _gen_validation_code()
    rec["password_reset_code"] = code
    _save_users_to_disk()
    print(f"[INFO] Réinitialisation mot de passe pour {ident} — code: {code}")
    return jsonify(
        {
            "success": True,
            "message": "Code généré. Consultez la console du serveur (miroir local), puis saisissez le code ci-dessous.",
        }
    )


@app.route('/api/v1/auth/reset-password', methods=['PATCH', 'POST'])
def reset_password():
    """Forgot password step 2 — PATCH body: { identifier, token, password }."""
    body = request.get_json(silent=True) or {}
    ident = _normalize_email(body.get("identifier") or body.get("email"))
    token = str(body.get("token") or "").strip()
    password = body.get("password") or ""
    if not ident or not token or not password:
        return jsonify({"message": "E-mail, code et mot de passe requis."}), 400
    if len(password) < 8:
        return jsonify({"message": "Le mot de passe doit contenir au moins 8 caractères."}), 400
    rec = _users_by_email.get(ident)
    if not rec:
        return jsonify({"message": "Code invalide ou expiré."}), 400
    if str(rec.get("password_reset_code") or "") != token:
        return jsonify({"message": "Code invalide."}), 400
    rec["password_hash"] = generate_password_hash(password)
    rec["password_reset_code"] = None
    _save_users_to_disk()
    dead = [t for t, em in list(_sessions_by_token.items()) if _normalize_email(em) == ident]
    for t in dead:
        del _sessions_by_token[t]
    if dead:
        _save_sessions_to_disk()
    return jsonify({"success": True, "message": "Mot de passe mis à jour. Vous pouvez vous connecter."})


@app.route('/api/v1/users/user/profile', methods=['PATCH'])
def patch_user_profile():
    profile, key, rec = _session_triple()
    if not profile:
        return jsonify({"message": "Non authentifié."}), 401
    body = request.get_json(silent=True) or {}
    fn = (body.get("firstName") or "").strip()
    ln = (body.get("lastName") or "").strip()
    if not fn or not ln:
        return jsonify({"message": "Prénom et nom requis."}), 400
    phone = body.get("phoneNumber")
    if phone is not None:
        phone = str(phone).strip() or None
    p = rec["profile"]
    p["firstName"] = fn
    p["lastName"] = ln
    p["fullName"] = f"{fn} {ln}".strip()
    p["name"] = p["fullName"]
    if phone is not None:
        p["phoneNumber"] = phone
    un = body.get("username")
    if un is not None and str(un).strip():
        p["username"] = str(un).strip()
    _save_users_to_disk()
    return jsonify(copy.deepcopy(p))


@app.route('/api/v1/users/user/profile/email', methods=['PATCH'])
def patch_user_email():
    profile, key, rec = _session_triple()
    if not profile:
        return jsonify({"message": "Non authentifié."}), 401
    body = request.get_json(silent=True) or {}
    old = _normalize_email(body.get("email"))
    new = _normalize_email(body.get("newEmail"))
    token = str(body.get("token") or "").strip()
    if old != key:
        return jsonify({"message": "E-mail actuel incorrect."}), 400
    if profile.get("status") != "valid":
        return jsonify({"message": "Validez d'abord votre compte."}), 400
    if not new:
        return jsonify({"message": "Nouvel e-mail requis."}), 400
    if new in _users_by_email and new != key:
        return jsonify({"message": "Cet e-mail est déjà utilisé."}), 400
    if _normalize_email(rec.get("pending_email") or "") != new:
        return jsonify({"message": "Demandez d'abord un code pour cette adresse."}), 400
    if str(rec.get("pending_email_code") or "") != token:
        return jsonify({"message": "Code invalide."}), 400
    p = rec["profile"]
    p["email"] = new
    del _users_by_email[key]
    _users_by_email[new] = rec
    rec["pending_email"] = None
    rec["pending_email_code"] = None
    for t, em in list(_sessions_by_token.items()):
        if _normalize_email(em) == key:
            _sessions_by_token[t] = new
    _save_users_to_disk()
    _save_sessions_to_disk()
    return jsonify(copy.deepcopy(p))


@app.route('/api/v1/users/user/profile/update-password', methods=['PATCH'])
def patch_user_password():
    profile, key, rec = _session_triple()
    if not profile:
        return jsonify({"message": "Non authentifié."}), 401
    body = request.get_json(silent=True) or {}
    old = body.get("password") or ""
    new_pw = body.get("newPassword") or ""
    if not check_password_hash(rec["password_hash"], old):
        return jsonify({"message": "Ancien mot de passe incorrect."}), 400
    if len(new_pw) < 8:
        return jsonify({"message": "Le nouveau mot de passe doit contenir au moins 8 caractères."}), 400
    rec["password_hash"] = generate_password_hash(new_pw)
    _save_users_to_disk()
    return jsonify(copy.deepcopy(rec["profile"]))

@app.route('/api/v1/questions/count', methods=['GET'])
def get_questions_count():
    """Question count."""
    data = load_data()
    total = sum(len(_year_items(v)) for v in data.values())
    return jsonify(total)

@app.route('/api/v2/sources/count', methods=['GET'])
def get_v2_sources_count():
    """V2 API: sources count."""
    data = load_data()
    total = sum(len(_year_items(v)) for v in data.values())
    return jsonify(total)

@app.route('/api/v2/sources/latest', methods=['GET'])
def get_v2_sources_latest():
    """V2 API: latest sources."""
    return jsonify([])

@app.route('/api/v2/plans', methods=['GET'])
def get_v2_plans():
    """V2 API: pricing plans."""
    return jsonify([])

@app.route('/api/v1/years', methods=['GET', 'POST'])
def get_years():
    """Get all available years with QST/CC counts for dropdown (e.g. '3ème → 1,152 QST et 594 CC (3,224 QST)')."""
    global _years_api_payload_cache
    load_data()
    with _years_api_payload_lock:
        if _years_api_payload_cache is not None:
            return jsonify(_years_api_payload_cache)
    years = _build_years_api_payload_list()
    with _years_api_payload_lock:
        _years_api_payload_cache = years
    return jsonify(years)


@app.route('/api/v1/years/public', methods=['GET'])
def get_years_public():
    """Signup page: curriculum years with forSale for year dropdown."""
    # Do not call load_data() here — parsing multi‑GB JSON on signup was OOM‑killing small instances.
    out = []
    for year_key, _ in active_year_mapping().items():
        if _year_resolve_paths(year_key)[0] is None:
            continue
        out.append({
            "id": year_key,
            "label": YEAR_LABELS.get(year_key, year_key),
            "name": year_key,
            "forSale": True,
        })
    if not out:
        for year_key, lbl in YEAR_LABELS.items():
            out.append({"id": year_key, "label": lbl, "name": year_key, "forSale": True})
    return jsonify(out)


# Revision/Exam pages call POST /api/v1/locations to load location dropdowns
SAMPLE_LOCATIONS = [
    {"id": "externat", "label": "Externat", "name": "Externat"},
    {"id": "residency", "label": "Résidanat", "name": "Résidanat"},
]


@app.route('/api/v1/locations', methods=['GET', 'POST'])
def get_locations():
    """Get locations for Revision/Exam filters."""
    return jsonify(SAMPLE_LOCATIONS)


def _theme_matches(meta, theme_id):
    """True if this item's theme matches theme_id (UUID or slug). Comparison is case-insensitive for slugs."""
    if not theme_id:
        return False
    theme_id = str(theme_id).strip()
    tid_uuid = (meta.get("themeId") or "").strip()
    theme_name = meta.get("theme") or meta.get("theme_label") or ""
    slug = (theme_name.lower().replace(" ", "_").replace("'", "")) if theme_name else ""
    theme_id_slug = theme_id.lower().replace(" ", "_").replace("'", "") if theme_id else ""
    return tid_uuid == theme_id or slug == theme_id or (slug and slug == theme_id_slug)


def _chapters_for_request():
    """Chapters list for GET/POST /api/v1/chapters. Use real meta.chapterId + meta.chapter so structure matches MedLibro."""
    data = load_data()
    theme_id = None
    if request.method == "GET":
        theme_id = request.args.get("themeId") or request.args.get("theme_id")
    else:
        body = request.get_json(silent=True) or {}
        theme_id = body.get("themeId") or body.get("theme_id")
    if not theme_id:
        return []
    # chapter_id (UUID or slug) -> { title, count } (aggregate across years)
    chapters_map = {}
    for year_key, year_data in data.items():
        items = _year_items(year_data)
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            if not _theme_matches(meta, theme_id):
                continue
            ch_title = meta.get("chapter") or meta.get("chapter_label")
            ch_uuid = meta.get("chapterId")
            if not ch_title and not ch_uuid:
                continue
            cid = ch_uuid or (ch_title.lower().replace(" ", "_").replace("'", "")[:50] if ch_title else "chapter")
            if cid not in chapters_map:
                chapters_map[cid] = {"title": ch_title or "", "acc": _qst_cc_acc_new()}
            _qst_cc_acc_add(chapters_map[cid]["acc"], item)
    result = []
    for cid, info in sorted(chapters_map.items(), key=lambda x: (x[1]["title"] or "")):
        q_st, cc_n, cc_q = _qst_cc_acc_totals(info["acc"])
        result.append({
            "id": cid,
            "title": info["title"],
            "name": info["title"],
            "questionsCount": q_st,
            "clinicalCasesCount": cc_n,
            "clinicalCasesQuestionsCount": cc_q,
        })
    return result


def _themes_for_request():
    """Themes list for GET or POST. Use real meta.themeId + meta.theme. Reads yearId from args (GET) or body (POST)."""
    data = load_data()
    if request.method == "GET":
        year_id = request.args.get("yearId") or request.args.get("year_id")
    else:
        body = request.get_json(silent=True) or {}
        year_id = body.get("yearId") or body.get("year") or body.get("year_id")
    # theme_id (UUID or slug) -> { name, questions, chapter_ids }
    seen = {}
    for year_key, year_data in data.items():
        if year_id and year_key != year_id:
            continue
        items = _year_items(year_data)
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            theme_name = meta.get("theme") or meta.get("theme_label") or "Unknown"
            theme_uuid = meta.get("themeId")
            tid = theme_uuid or (theme_name.lower().replace(" ", "_").replace("'", ""))
            if tid not in seen:
                seen[tid] = {"name": theme_name, "acc": _qst_cc_acc_new(), "chapters": set()}
            _qst_cc_acc_add(seen[tid]["acc"], item)
            ch = meta.get("chapter") or meta.get("chapter_label")
            if ch:
                seen[tid]["chapters"].add(ch)
        if year_id:
            break
    result = []
    for tid, info in sorted(seen.items(), key=lambda x: (x[1]["name"] or "")):
        q_st, cc_n, cc_q = _qst_cc_acc_totals(info["acc"])
        result.append({
            "id": tid,
            "name": info["name"],
            "label": info["name"],
            "chapters": sorted(info["chapters"]),
            "questions_count": q_st,
            "questionsCount": q_st,
            "clinicalCasesCount": cc_n,
            "clinicalCasesQuestionsCount": cc_q,
        })
    return result


@app.route('/api/v1/themes', methods=['GET', 'POST'])
def get_or_post_themes():
    """Exam/Revision pages: themes (GET with yearId in query, or POST with yearId in body)."""
    return jsonify(_themes_for_request())


@app.route('/api/v1/chapters', methods=['GET', 'POST'])
def get_or_post_chapters():
    """Revision/Exam FilterForm: chapters for selected theme (mainAttribute=title)."""
    return jsonify(_chapters_for_request())


def _courses_for_request():
    """Courses list for GET/POST /api/v1/courses. Use real meta.courseId + meta.course (not chapters) so structure matches MedLibro."""
    data = load_data()
    theme_id = None
    chapters_ids = []
    if request.method == "GET":
        theme_id = request.args.get("themeId") or request.args.get("theme_id") or request.args.get("themeID") or request.args.get("theme")
        if not theme_id and request.args:
            for k, v in request.args.items():
                if v and (k.lower() in ("themeid", "theme_id", "theme") or "theme" in k.lower()):
                    theme_id = v
                    break
        ch = request.args.getlist("chaptersIds") or request.args.getlist("chapters_ids") or request.args.getlist("chapters") or request.args.get("chaptersIds") or request.args.get("chapters_ids") or request.args.get("chapters")
        if ch:
            flat = []
            for x in (ch if isinstance(ch, list) else [ch]):
                if isinstance(x, str) and "," in x:
                    flat.extend(x.split(","))
                else:
                    flat.append(x)
            chapters_ids = [str(x).strip() for x in flat if x]
    else:
        body = request.get_json(silent=True) or {}
        if not body and request.content_type and "form" in (request.content_type or ""):
            body = request.form
        theme_id = (body.get("themeId") or body.get("theme_id") or body.get("themeID") or body.get("theme") or "").strip() or None
        ch = body.get("chaptersIds") or body.get("chapters_ids") or body.get("chapters")
        if ch:
            chapters_ids = ch if isinstance(ch, list) else ([c.strip() for c in str(ch).split(",")] if ch else [])
    if theme_id:
        theme_id = str(theme_id).strip()
    if not theme_id:
        return []
    # course_id (UUID or slug) -> { title, items[] }; filter by theme and optionally by chapter IDs
    courses_map = {}
    for year_key, year_data in data.items():
        items = _year_items(year_data)
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            if not _theme_matches(meta, theme_id):
                continue
            ch_id = meta.get("chapterId")
            ch_slug = (meta.get("chapter") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("chapter") else None
            if chapters_ids:
                ch_id_str = (ch_id or "").strip() if ch_id else None
                chapters_ids_norm = [str(x).strip() for x in chapters_ids]
                chapters_slugs = [x.lower().replace(" ", "_").replace("'", "")[:50] for x in chapters_ids_norm if x]
                if ch_id_str not in chapters_ids_norm and ch_slug not in chapters_slugs and ch_slug not in chapters_ids_norm and ch_id_str not in chapters_slugs:
                    continue
            course_title = meta.get("course") or meta.get("course_label")
            course_uuid = meta.get("courseId")
            if not course_title and not course_uuid:
                continue
            cid = course_uuid or (course_title.lower().replace(" ", "_").replace("'", "")[:50] if course_title else "course")
            if cid not in courses_map:
                courses_map[cid] = {"title": course_title or "Cours", "acc": _qst_cc_acc_new()}
            _qst_cc_acc_add(courses_map[cid]["acc"], item)
    result = []
    for cid, info in sorted(courses_map.items(), key=lambda x: (x[1]["title"] or "")):
        q_st, cc_n, cc_q = _qst_cc_acc_totals(info["acc"])
        result.append({
            "id": cid,
            "title": info["title"],
            "name": info["title"],
            "questionsCount": q_st,
            "clinicalCasesCount": cc_n,
            "clinicalCasesQuestionsCount": cc_q,
        })
    # If filtering by chapters returned nothing, return all courses for the theme so dropdown is not empty
    if not result and chapters_ids:
        courses_map = {}
        for year_key, year_data in data.items():
            items = _year_items(year_data)
            if not items:
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                meta = item.get("meta", item)
                if not _theme_matches(meta, theme_id):
                    continue
                course_title = meta.get("course") or meta.get("course_label")
                course_uuid = meta.get("courseId")
                if not course_title and not course_uuid:
                    continue
                cid = course_uuid or (course_title.lower().replace(" ", "_").replace("'", "")[:50] if course_title else "course")
                if cid not in courses_map:
                    courses_map[cid] = {"title": course_title or "Cours", "acc": _qst_cc_acc_new()}
                _qst_cc_acc_add(courses_map[cid]["acc"], item)
        result = []
        for cid, info in sorted(courses_map.items(), key=lambda x: (x[1]["title"] or "")):
            q_st, cc_n, cc_q = _qst_cc_acc_totals(info["acc"])
            result.append({
                "id": cid,
                "title": info["title"],
                "name": info["title"],
                "questionsCount": q_st,
                "clinicalCasesCount": cc_n,
                "clinicalCasesQuestionsCount": cc_q,
            })
    # Final fallback: if we still have no courses but theme was set, return all courses from all data
    if not result and theme_id:
        courses_map = {}
        for year_key, year_data in data.items():
            items = _year_items(year_data)
            if not items:
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                meta = item.get("meta", item)
                course_title = meta.get("course") or meta.get("course_label")
                course_uuid = meta.get("courseId")
                if not course_title and not course_uuid:
                    continue
                cid = course_uuid or (course_title.lower().replace(" ", "_").replace("'", "")[:50] if course_title else "course")
                if cid not in courses_map:
                    courses_map[cid] = {"title": course_title or "Cours", "acc": _qst_cc_acc_new()}
                _qst_cc_acc_add(courses_map[cid]["acc"], item)
        result = []
        for cid, info in sorted(courses_map.items(), key=lambda x: (x[1]["title"] or "")):
            q_st, cc_n, cc_q = _qst_cc_acc_totals(info["acc"])
            result.append({
                "id": cid,
                "title": info["title"],
                "name": info["title"],
                "questionsCount": q_st,
                "clinicalCasesCount": cc_n,
                "clinicalCasesQuestionsCount": cc_q,
            })
    return result


@app.route('/api/v1/courses', methods=['GET', 'POST'])
def get_or_post_courses():
    """Revision/Exam FilterForm: courses for selected theme+chapters (mainAttribute=title, with QST/CC counts)."""
    return jsonify(_courses_for_request())


def _sources_with_counts(year_label, total_q, total_cc=0, total_cc_q=0):
    """Build source items with QST/CC counts for Sources dropdown (screenshot: '2018 → X QST et Y CC (Z QST)')."""
    return [
        {
            "id": f"source-{year_label}",
            "year": year_label,
            "label": "QCM",
            "name": "QCM",
            "questionsCount": total_q,
            "clinicalCasesCount": total_cc,
            "clinicalCasesQuestionsCount": total_cc_q,
        }
    ]


@app.route('/api/v1/sources/theme/<theme_id>', methods=['GET'])
def get_sources_by_theme(theme_id):
    """Exam/Revision: sources per theme from meta.sourcesYears (exam years) for questions in this theme."""
    data = load_data()
    year_buckets = defaultdict(_qst_cc_acc_new)
    for year_key, year_data in data.items():
        items = _year_items(year_data)
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            if not _theme_matches(meta, theme_id):
                continue
            for yr in _item_exam_year_ints(meta, item):
                _qst_cc_acc_add(year_buckets[yr], item)
    result = []
    for yr in sorted(year_buckets.keys(), reverse=True):
        q_st, cc_n, cc_q = _qst_cc_acc_totals(year_buckets[yr])
        result.append({
            "id": f"source-{yr}",
            "year": str(yr),
            "label": "QCM",
            "name": "QCM",
            "questionsCount": q_st,
            "clinicalCasesCount": cc_n,
            "clinicalCasesQuestionsCount": cc_q,
        })
    if not result:
        result = _sources_with_counts("2018", 0)
    return jsonify(result)


@app.route('/api/v1/sources', methods=['POST'])
def post_sources():
    """FilterForm fetchSources: return sources from meta.sourcesYears (exam years 2018, 2017, ...) like real MedLibro."""
    data = load_data()
    # Bucket question rows per exam year from meta.sourcesYears (real MedLibro structure)
    year_buckets = defaultdict(_qst_cc_acc_new)
    for year_key, year_data in data.items():
        items = _year_items(year_data)
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            for yr in _item_exam_year_ints(meta, item):
                _qst_cc_acc_add(year_buckets[yr], item)
    # One source per exam year, sorted descending (2022, 2021, 2018, ...)
    result = []
    for yr in sorted(year_buckets.keys(), reverse=True):
        q_st, cc_n, cc_q = _qst_cc_acc_totals(year_buckets[yr])
        result.append({
            "id": f"source-{yr}",
            "year": str(yr),
            "label": "QCM",
            "name": "QCM",
            "questionsCount": q_st,
            "clinicalCasesCount": cc_n,
            "clinicalCasesQuestionsCount": cc_q,
        })
    # If no sourcesYears in data, fallback to stub exam years
    if not result:
        for yr in ["2018", "2017", "2016", "2015", "2014", "2013"]:
            result.append({
                "id": f"source-{yr}",
                "year": yr,
                "label": "QCM",
                "name": "QCM",
                "questionsCount": 0,
                "clinicalCasesCount": 0,
                "clinicalCasesQuestionsCount": 0,
            })
    return jsonify(result if isinstance(result, list) else [])


@app.route('/api/v1/sources/learn', methods=['POST'])
def post_sources_learn():
    """POST /api/v1/sources/learn: body { location, theme, chapters[], courses[] }. Returns [{ year: 2021 }, { year: 2020 }, ...] like MedLibro."""
    data = load_data()
    body = _request_json_dict()
    body = _revision_body_merge_query(body)
    body = _revision_body_flat(body)
    theme_id = (body.get("themeId") or body.get("theme_id") or body.get("theme") or "").strip() or None
    chapters = body.get("chaptersIds") or body.get("chapters_ids") or body.get("chapters") or []
    courses = body.get("coursesIds") or body.get("courses_ids") or body.get("courses") or []
    if isinstance(chapters, str):
        chapters = [c.strip() for c in chapters.split(",")] if chapters else []
    if isinstance(courses, str):
        courses = [c.strip() for c in courses.split(",")] if courses else []
    year_counts = defaultdict(int)
    for year_key, year_data in data.items():
        items = _year_items(year_data)
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            if theme_id and not _theme_matches(meta, theme_id):
                continue
            if chapters:
                ch_id = (meta.get("chapterId") or "").strip() if meta.get("chapterId") else None
                ch_slug = (meta.get("chapter") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("chapter") else None
                chapters_norm = [str(x).strip() for x in chapters]
                slugs = [x.lower().replace(" ", "_").replace("'", "")[:50] for x in chapters_norm if x]
                if ch_id not in chapters_norm and ch_slug not in slugs and ch_slug not in chapters_norm and ch_id not in slugs:
                    continue
            if courses:
                cid = (meta.get("courseId") or "").strip() if meta.get("courseId") else None
                cslug = (meta.get("course") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("course") else None
                courses_norm = [str(x).strip() for x in courses]
                cslugs = [x.lower().replace(" ", "_").replace("'", "")[:50] for x in courses_norm if x]
                if cid not in courses_norm and cslug not in cslugs and cslug not in courses_norm and cid not in cslugs:
                    continue
            for yr in _item_exam_year_ints(meta, item):
                year_counts[yr] += 1
    years_sorted = sorted(year_counts.keys(), reverse=True)
    if not years_sorted:
        years_sorted = [2018, 2017, 2016, 2015, 2014, 2013]
    return jsonify([{"year": int(yr)} for yr in years_sorted])


# ----- v2 API (FilterForm uses o("locations",2), o("years",2), o("themes",2), o("chapters",2), o("courses",2), o("sources",2)) -----
@app.route('/api/v2/locations', methods=['GET', 'POST'])
def locations_v2():
    return get_locations()


@app.route('/api/v2/years', methods=['GET', 'POST'])
def years_v2():
    return get_years()


@app.route('/api/v2/themes', methods=['GET', 'POST'])
def themes_v2():
    return get_or_post_themes()


@app.route('/api/v2/chapters', methods=['GET', 'POST'])
def chapters_v2():
    return get_or_post_chapters()


@app.route('/api/v2/courses', methods=['GET', 'POST'])
def courses_v2():
    return get_or_post_courses()


@app.route('/api/v2/sources', methods=['POST'])
def sources_v2():
    return post_sources()


@app.route('/api/v1/revision', methods=['GET'])
def get_revision():
    """Get revision data (years + themes + chapters). Uses meta.themeId/chapter so structure matches MedLibro."""
    data = load_data()
    result = []
    for year_key, year_data in data.items():
        items = _year_items(year_data)
        if not items:
            continue
        themes_dict = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            theme_name = meta.get("theme") or meta.get("theme_label") or "Unknown"
            theme_uuid = meta.get("themeId")
            tid = theme_uuid or (theme_name.lower().replace(" ", "_").replace("'", ""))
            if tid not in themes_dict:
                themes_dict[tid] = {"name": theme_name, "chapters": set(), "acc": _qst_cc_acc_new()}
            themes_dict[tid]["chapters"].add(meta.get("chapter") or meta.get("chapter_label") or "")
            _qst_cc_acc_add(themes_dict[tid]["acc"], item)
        themes = []
        for tid, theme_data in sorted(themes_dict.items(), key=lambda x: x[1]["name"] or ""):
            q_st, cc_n, cc_q = _qst_cc_acc_totals(theme_data["acc"])
            themes.append({
                "id": tid,
                "name": theme_data["name"],
                "chapters": sorted(x for x in theme_data["chapters"] if x),
                "questions_count": q_st,
                "questionsCount": q_st,
                "clinicalCasesCount": cc_n,
                "clinicalCasesQuestionsCount": cc_q,
            })
        first_meta = items[0].get("meta", items[0]) if items else {}
        year_label = first_meta.get("year_label") or YEAR_LABELS.get(year_key) or (year_data.get("year") if isinstance(year_data, dict) else None) or year_key
        result.append({
            "year": year_key,
            "year_label": year_label,
            "themes": themes
        })
    return jsonify(result)


def _collect_question_edges(
    theme_id=None,
    chapters_ids=None,
    courses_ids=None,
    sources_years=None,
    curriculum_year_key=None,
):
    """Build [{entity, id}, ...] for revision / exam start (same filters as legacy POST /revision)."""
    data = load_data()
    ch_list = list(chapters_ids or [])
    co_list = list(courses_ids or [])
    if isinstance(co_list, str):
        co_list = [c.strip() for c in co_list.split(",")] if co_list else []
    sy_list = list(sources_years or [])
    if isinstance(sy_list, str):
        sy_list = [int(x) for x in str(sy_list).split(",") if str(x).strip().isdigit()]
    sy_set = set()
    for y in sy_list:
        for iy in _exam_years_from_value(y):
            sy_set.add(iy)
    ck = _resolve_curriculum_year_key(curriculum_year_key) if curriculum_year_key not in (None, "") else None
    items_out = []
    for year_key, year_data in data.items():
        if ck is not None and ck != "" and str(year_key) != str(ck):
            continue
        for item in _year_items(year_data):
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            if theme_id and not _theme_matches(meta, theme_id):
                continue
            if ch_list:
                ch_id = (meta.get("chapterId") or "").strip() if meta.get("chapterId") else None
                ch_slug = (meta.get("chapter") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("chapter") else None
                ok_ch = False
                for ch_norm in ch_list:
                    cn = str(ch_norm).strip()
                    cslug_norm = cn.lower().replace(" ", "_").replace("'", "")[:50]
                    if ch_id == cn or ch_slug == cslug_norm or ch_id == cslug_norm or ch_slug == cn:
                        ok_ch = True
                        break
                if not ok_ch:
                    continue
            if co_list:
                cid = (meta.get("courseId") or "").strip() if meta.get("courseId") else None
                cslug = (meta.get("course") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("course") else None
                courses_norm = [str(x).strip() for x in co_list]
                cslugs = [x.lower().replace(" ", "_").replace("'", "")[:50] for x in courses_norm if x]
                if cid not in courses_norm and cslug not in cslugs and cslug not in courses_norm and cid not in cslugs:
                    continue
            if sy_set:
                iy = _item_exam_year_ints(meta, item)
                if not any(y in sy_set for y in iy):
                    continue
            qid = _question_id(item)
            if qid:
                items_out.append({"entity": "question", "id": str(qid)})
    return items_out


def _revision_body_flat(body):
    """Merge nested filter objects (some clients POST { filter: { ... } })."""
    if not isinstance(body, dict):
        return {}
    out = dict(body)
    for key in ("filter", "filters", "request", "payload", "criteria", "selection", "data"):
        nested = body.get(key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                if k not in out or out.get(k) in (None, [], ""):
                    out[k] = v
    return out


def _collect_question_edges_from_body(body, curriculum_year_key=None):
    """Normalize revision/adaptive exam POST body (must scope by curriculum year when provided)."""
    body = _revision_body_flat(body or {})
    theme_id = (body.get("themeId") or body.get("theme_id") or body.get("theme") or "").strip() or None
    chapter_id = (body.get("chapterId") or body.get("chapter_id") or body.get("chapter") or "").strip() or None
    chapters_ids = body.get("chaptersIds") or body.get("chapters_ids") or []
    if isinstance(chapters_ids, str):
        chapters_ids = [chapters_ids]
    if chapter_id and not chapters_ids:
        chapters_ids = [chapter_id]
    courses_ids = body.get("coursesIds") or body.get("courses_ids") or body.get("courses") or []
    if isinstance(courses_ids, str):
        courses_ids = [c.strip() for c in courses_ids.split(",")] if courses_ids else []
    cid_one = body.get("courseId") or body.get("course_id")
    if cid_one and not courses_ids:
        courses_ids = [cid_one]
    sources_years = _merged_exam_source_years(body)
    yr = (
        curriculum_year_key
        or body.get("yearId")
        or body.get("year_id")
        or body.get("selectedYear")
        or body.get("selectedYearId")
        or body.get("educationYearId")
        or body.get("curriculumYearId")
        or body.get("curriculumYear")
        or body.get("curriculum_year")
    )
    yr = _resolve_curriculum_year_key(yr) if yr not in (None, "") else None
    return _collect_question_edges(
        theme_id=theme_id,
        chapters_ids=chapters_ids,
        courses_ids=courses_ids,
        sources_years=sources_years,
        curriculum_year_key=yr,
    )


@app.route('/api/v1/revision', methods=['POST'])
def post_revision():
    """POST /api/v1/revision: body { yearId, themeId, chaptersIds[], coursesIds[], sources / sourcesYears[] }. Returns { items, totalQuestionsCounter }."""
    body = _request_json_dict()
    if not isinstance(body, dict):
        body = {}
    body = _revision_body_merge_query(body)
    has_ck = (
        body.get("yearId")
        or body.get("year_id")
        or body.get("selectedYear")
        or body.get("selectedYearId")
        or body.get("educationYearId")
        or body.get("curriculumYearId")
        or body.get("curriculumYear")
        or body.get("curriculum_year")
    )
    if not has_ck:
        qy = request.args.get("yearId") or request.args.get("year_id")
        if qy:
            body = dict(body)
            body["yearId"] = str(qy).strip()
    items_out = _collect_question_edges_from_body(body)
    return jsonify({"items": items_out, "totalQuestionsCounter": len(items_out)})


@app.route('/api/v1/exam', methods=['POST'])
def post_exam_adaptive():
    """Exam adaptive mode: POST with same filter fields as revision (+ exam source years)."""
    body = _request_json_dict()
    if not isinstance(body, dict):
        body = {}
    body = _revision_body_merge_query(body)
    has_ck = (
        body.get("yearId")
        or body.get("year_id")
        or body.get("selectedYear")
        or body.get("selectedYearId")
        or body.get("educationYearId")
        or body.get("curriculumYearId")
        or body.get("curriculumYear")
        or body.get("curriculum_year")
    )
    if not has_ck:
        qy = request.args.get("yearId") or request.args.get("year_id")
        if qy:
            body = dict(body)
            body["yearId"] = str(qy).strip()
    items_out = _collect_question_edges_from_body(body)
    return jsonify({"items": items_out, "totalQuestionsCounter": len(items_out)})


@app.route('/api/v2/revision', methods=['GET', 'POST'])
def revision_v2():
    """Stock SPA often calls v2 revision — delegate to v1."""
    if request.method == 'GET':
        return get_revision()
    return post_revision()


@app.route('/api/v2/exam', methods=['POST'])
def exam_v2():
    """Stock SPA may POST exam filters to v2."""
    return post_exam_adaptive()


@app.route('/api/v1/exam/source/<path:source_id>', methods=['GET'])
def get_exam_replica_source(source_id):
    """Exam replica: GET /api/v1/exam/source/:id?themeId= (id like source-2018)."""
    theme_id = (request.args.get('themeId') or request.args.get('theme_id') or "").strip() or None
    s = (source_id or "").strip()
    exam_year = s[7:] if s.startswith("source-") else s
    sy = []
    if exam_year and str(exam_year).replace("-", "").lstrip("-").isdigit():
        sy = [int(exam_year)]
    body = {"themeId": theme_id, "sourcesYears": sy}
    yr = (request.args.get("yearId") or request.args.get("year_id") or "").strip()
    if yr:
        body["yearId"] = yr
    items_out = _collect_question_edges_from_body(body)
    return jsonify({"items": items_out, "totalQuestionsCounter": len(items_out)})


@app.route('/api/v1/exam/year/<curriculum_year>/source/<path:exam_year>', methods=['GET'])
def get_exam_replica_year_source(curriculum_year, exam_year):
    """Residency replica: .../exam/year/:yearKey/source/:examYear?unitId= (unitId is theme id in the Vue app)."""
    theme_from_unit = (request.args.get('unitId') or "").strip() or None
    theme_id = (request.args.get('themeId') or request.args.get('theme_id') or "").strip() or None
    effective_theme = theme_id or theme_from_unit
    sy = []
    ey = str(exam_year).strip()
    if ey.replace("-", "").lstrip("-").isdigit():
        sy = [int(ey)]
    items_out = _collect_question_edges(
        theme_id=effective_theme,
        chapters_ids=None,
        courses_ids=None,
        sources_years=sy,
        curriculum_year_key=curriculum_year,
    )
    return jsonify({"items": items_out, "totalQuestionsCounter": len(items_out)})


def _session_preferred_exam_years(session_id):
    """Exam (QCM) years from stored session defaults + options — same sourcesYears as POST /revision on live site."""
    rs = _runtime_sessions.get(session_id)
    if not rs:
        return None
    defaults = rs.get("filter_defaults") or {}
    opts = rs.get("options") or []
    acc = []
    for opt in opts:
        merged = dict(defaults)
        if isinstance(opt, dict):
            merged.update(opt)
        merged = _revision_body_flat(merged)
        acc.extend(_merged_exam_source_years(merged))
    return frozenset(acc) if acc else None


def _prepare_question_dict(raw, preferred_exam_years=None):
    """Build MedLibro flat question dict from raw item (same shape as GET /api/v1/questions/:id)."""
    if not raw or not isinstance(raw, dict):
        return None
    raw_copy = json.loads(json.dumps(raw))
    meta = raw_copy.get("meta") or raw_copy
    q = raw_copy.get("question") or raw_copy
    if not isinstance(q, dict):
        return None
    if isinstance(meta, dict):
        for k in ("locationId", "themeId", "location", "year", "yearId"):
            if k in meta and k not in q:
                q[k] = meta[k]
        if "sourcesYears" in meta and not q.get("sources"):
            q["sources"] = [{"id": str(y), "label": "QCM", "year": int(y)} for y in (meta["sourcesYears"] or [])[:5]]
        if "chapterId" in meta and not q.get("chapters"):
            q["chapters"] = [{"id": meta["chapterId"], "title": meta.get("chapter") or ""}]
        if "courseId" in meta and not q.get("courses"):
            q["courses"] = [{"id": meta["courseId"], "title": meta.get("course") or ""}]
    theme_id = (meta.get("themeId") or "").strip() if isinstance(meta, dict) else ""
    theme_name = meta.get("theme") or meta.get("theme_label") or "" if isinstance(meta, dict) else ""
    year_label = meta.get("year") or (YEAR_LABELS.get(str(meta.get("year"))) if isinstance(meta, dict) else None) or "2nd"
    year_id = (meta.get("yearId") or "").strip() if isinstance(meta, dict) else ""
    year_ints = []
    src_prim = _question_sources_exam_years_ints(raw_copy)
    if src_prim:
        year_ints = list(src_prim)
    else:
        years = meta.get("sourcesYears") if isinstance(meta, dict) else None
        if isinstance(years, list):
            for y in years:
                year_ints.extend(_exam_years_from_value(y))
    chosen_year = None
    if preferred_exam_years and year_ints:
        inter = [y for y in year_ints if y in preferred_exam_years]
        if inter:
            chosen_year = min(inter)
    if chosen_year is None and year_ints:
        # Unfiltered / general: show latest exam year on card (matches typical sourcesYears ordering).
        chosen_year = max(year_ints)
    if chosen_year is not None:
        year_id = str(chosen_year)
    elif not year_id and years:
        year_id = str(years[0])
    q["theme"] = {
        "id": theme_id,
        "name": theme_name,
        "year": {"id": year_id, "label": str(year_label)}
    }
    q["notes"] = q.get("notes") if isinstance(q.get("notes"), list) else []
    q["attachedTo"] = q.get("attachedTo") if isinstance(q.get("attachedTo"), (int, float)) else 0
    return q


@app.route('/api/v1/questions/<question_id>', methods=['GET'])
def get_question(question_id):
    """Return question in MedLibro flat shape: root = question with theme: { id, name, year: { id, label } }, notes, attachedTo."""
    raw = find_question_by_id(question_id)
    if not raw:
        return jsonify({"error": "Question not found"}), 404
    q = _prepare_question_dict(raw)
    if q is None:
        return jsonify(json.loads(json.dumps(raw)))
    return jsonify(q)

# Preferences: store expects an array (uses .find()); items have id, label, value
DEFAULT_PREFERENCES = [
    {"id": "pref-hide-notes", "label": "hide-notes-in-exam", "value": "false"},
    {"id": "pref-scoring", "label": "scoring-mode", "value": "binary-mode"},
]

@app.route('/api/v1/preferences', methods=['GET'])
def get_preferences():
    return jsonify(DEFAULT_PREFERENCES)

@app.route('/api/v1/preferences', methods=['POST'])
def post_preference():
    data = request.get_json() or {}
    label = data.get("label") or "pref"
    value = data.get("value") or ""
    pref = {"id": f"pref-{label}", "label": label, "value": str(value)}
    return jsonify(pref), 201

@app.route('/api/v1/preferences/<pref_id>', methods=['PATCH', 'PUT'])
def patch_preference(pref_id):
    data = request.get_json() or {}
    return jsonify({"id": pref_id, "value": data.get("value", "")})

@app.route('/api/v2/licenses/expiry', methods=['GET'])
def get_licenses_expiry():
    profile, _k, _r = _session_triple()
    if profile and profile.get("status") == "valid" and profile.get("isPremium"):
        return jsonify({
            "valid": True,
            "expiry": "2099-12-31T23:59:59Z",
            "hasAccess": True,
        })
    return jsonify({"valid": False, "expiry": None, "hasAccess": False})

@app.route('/api/v2/answers/modules', methods=['GET'])
def get_answers_modules():
    # Dashboard activity graph — no flashcard/streak edges in local mirror.
    return jsonify({
        "edges": [],
        "pageInfo": {"hasNextPage": False, "nextPage": None}
    })

@app.route('/api/v2/answers', methods=['GET'])
def get_answers():
    # Heatmap expects response.data to be an array (for .map())
    return jsonify([])


@app.route('/api/v2/answers', methods=['POST'])
def post_answers():
    """After VÉRIFIER: client logs answer (utils-fK4_zk7F.postAnswer). Body: input, questionId, answerSetId, status, isPartiallyCorrect."""
    body = request.get_json(silent=True) or {}
    return jsonify({
        "id": str(uuid.uuid4())[:16],
        "questionId": body.get("questionId"),
        "answerSetId": body.get("answerSetId"),
        "status": body.get("status"),
        "isPartiallyCorrect": body.get("isPartiallyCorrect", False),
        "input": body.get("input"),
    }), 201


@app.route('/api/v1/cards', methods=['POST'])
def post_cards():
    """Flashcards/Memorix disabled in mirror (no-op)."""
    return jsonify({"ok": True}), 200


@app.route('/api/v1/cards/due/<path:theme_slug>', methods=['GET'])
def get_cards_due_for_theme(theme_slug):
    """Flashcards queue disabled — empty."""
    return jsonify([])


@app.route('/api/v1/cards/<path:card_id>', methods=['PATCH', 'PUT', 'DELETE'])
def patch_or_delete_card(card_id):
    if request.method == "DELETE":
        return "", 204
    return jsonify({"success": True, "id": card_id})


@app.route('/api/v1/playlists/pinned', methods=['GET'])
def get_playlists_pinned():
    pinned = [pl for pl in _runtime_playlists if pl.get("pinned")]
    return jsonify(pinned)


# ----- Sessions (v2) – stubs + SessionPage GET session / items / position -----
# Filter POST stores { title, options } here so GET .../items can build question list
_runtime_sessions = {}
# Session highlights sync (GET/PATCH /api/v2/sessions/<id>/highlights)
_runtime_session_highlights = {}
# Notes: AnswerDialog uses /api/v1/notes/note; NotesCard uses /api/v2/notes/... — same in-memory bucket.
LOCAL_NOTE_USER_ID = "local-mirror-user"


def _note_utc_z():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_note_document(question_id, value):
    nid = str(uuid.uuid4())
    now = _note_utc_z()
    return {
        "id": nid,
        "value": value,
        "date": now,
        "version": 0,
        "createdAt": now,
        "updatedAt": now,
        "userId": LOCAL_NOTE_USER_ID,
        "questionId": str(question_id),
    }


def _note_apply_patch(note, new_value):
    now = _note_utc_z()
    note["value"] = new_value
    note["date"] = now
    note["updatedAt"] = now
    note["version"] = int(note.get("version") or 0) + 1
    return note


_runtime_notes_v2 = defaultdict(list)


def _embedded_notes_list(item):
    if not isinstance(item, dict):
        return []
    q = item.get("question", item)
    if not isinstance(q, dict):
        return []
    notes = q.get("notes")
    return notes if isinstance(notes, list) else []


def _question_notes_merged_for_api(item, pq):
    """Attach embedded + runtime notes to prepared question dict."""
    qid = _question_id(item)
    embedded = pq.get("notes") if isinstance(pq.get("notes"), list) else []
    out = list(embedded)
    if qid is not None:
        for n in _runtime_notes_v2.get(str(qid), []):
            out.append({
                "id": n.get("id"),
                "value": n.get("value"),
                "date": n.get("date"),
                "createdAt": n.get("createdAt"),
                "updatedAt": n.get("updatedAt"),
            })
    return out


@app.route('/api/v2/cards/themes/top', methods=['GET'])
def get_cards_themes_top():
    """Flashcards themes disabled in mirror."""
    return jsonify({"themes": []})


# No bundled sample sessions — users only see sessions they create.
SAMPLE_SESSIONS = []


def _all_question_raw_items_ordered(limit=None):
    """Collect question rows in curriculum order; stop once `limit` items found (avoid OOM on huge corpora)."""
    data = load_data()
    flat = []
    for year_key in sorted(data.keys()):
        for item in _year_items(data[year_key]):
            if isinstance(item, dict) and _question_id(item):
                flat.append(item)
                if limit is not None and len(flat) >= limit:
                    return flat
    return flat


def _items_matching_session_option(opt, datum):
    """One row from FilterForm session options[].request."""
    opt = _revision_body_flat(opt) if isinstance(opt, dict) else opt
    if not isinstance(opt, dict):
        return []
    yr_raw = opt.get("yearId") or opt.get("year_id") or opt.get("year")
    year_filter = _resolve_curriculum_year_key(yr_raw) if yr_raw not in (None, "") else None
    theme_id = opt.get("themeId") or opt.get("theme_id")
    filter_by = (opt.get("filterBy") or "theme").lower()
    chapters_ids = opt.get("chaptersIds") or []
    courses_ids = opt.get("coursesIds") or []
    src_set = set(_merged_exam_source_years(opt))
    out = []
    for year_key, year_data in datum.items():
        if year_filter is not None and year_filter != "" and str(year_key) != str(year_filter):
            continue
        for item in _year_items(year_data):
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", item)
            if filter_by in ("theme", "chapters", "courses", "unit"):
                if theme_id and not _theme_matches(meta, theme_id):
                    continue
            if filter_by in ("chapters", "courses") and chapters_ids:
                ch_id = (meta.get("chapterId") or "").strip()
                ch_slug = (meta.get("chapter") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("chapter") else ""
                ok_ch = False
                for c in chapters_ids:
                    cn = str(c).strip()
                    cslug = cn.lower().replace(" ", "_").replace("'", "")[:50]
                    if cn == ch_id or cslug == ch_slug or cn == ch_slug or ch_id == cn:
                        ok_ch = True
                        break
                if not ok_ch:
                    continue
            if filter_by == "courses" and courses_ids:
                cid = (meta.get("courseId") or "").strip()
                cslug = (meta.get("course") or "").lower().replace(" ", "_").replace("'", "")[:50] if meta.get("course") else ""
                courses_norm = [str(x).strip() for x in courses_ids]
                cslugs = [x.lower().replace(" ", "_").replace("'", "")[:50] for x in courses_norm]
                if cid not in courses_norm and cslug not in cslugs and cslug not in courses_norm and cid not in cslugs:
                    continue
            if src_set:
                iy_flat = _item_exam_year_ints(meta, item)
                if not any(y in src_set for y in iy_flat):
                    continue
            out.append(item)
    return out


def _session_raw_items(session_id):
    """Ordered raw question rows for a session (SessionPage items). Filters only — no bulk fallback."""
    data = load_data()
    if session_id in _runtime_sessions:
        rs = _runtime_sessions[session_id]
        opts = rs.get("options") or []
        defaults = rs.get("filter_defaults") or {}
        if not opts:
            return []
        seen = []
        seen_ids = set()
        for opt in opts:
            opt = _revision_body_flat(opt) if isinstance(opt, dict) else opt
            if not isinstance(opt, dict):
                continue
            merged = dict(defaults)
            merged.update(opt)
            merged = _revision_body_flat(merged)
            for item in _items_matching_session_option(merged, data):
                qid = _question_id(item)
                key = str(qid) if qid else None
                if key and key not in seen_ids:
                    seen_ids.add(key)
                    seen.append(item)
        return seen
    return []


def _session_question_payload(raw, session_id=None):
    pref = _session_preferred_exam_years(session_id) if session_id else None
    q = _prepare_question_dict(raw, preferred_exam_years=pref)
    if not q:
        return None
    out = dict(q)
    out["isQuestion"] = True
    return out


def _runtime_session_edge(sid, meta):
    n = len(_session_raw_items(sid))
    return {
        "id": sid,
        "title": meta.get("title") or "Session",
        "lastOpened": None,
        "status": "active",
        "totalQuestions": n,
        "totalCases": 0,
        "totalCasesQuestions": 0,
        "answerSets": [{"id": f"as-{sid}", "sessionId": sid}],
        "canAccess": True,
        "itemsOrderDirection": "asc",
    }


@app.route('/api/v2/sessions', methods=['POST'])
def post_sessions():
    body = _request_json_dict()
    title = body.get("title") or "Session"
    sid = str(uuid.uuid4())[:8]
    # Curriculum year only — never use body["year"] here (often the selected QCM year, e.g. 2023).
    year_top = (
        body.get("yearId")
        or body.get("year_id")
        or body.get("selectedYear")
        or body.get("selectedYearId")
        or body.get("educationYearId")
        or body.get("curriculumYearId")
        or body.get("curriculumYear")
        or body.get("curriculum_year")
        or request.args.get("yearId")
        or request.args.get("year_id")
    )
    filter_defaults = _session_filter_defaults(body)
    opts_in = body.get("options") or []
    opts_norm = []
    for o in opts_in:
        o = _revision_body_flat(o) if isinstance(o, dict) else o
        if isinstance(o, dict):
            o = dict(o)
            if year_top and not (
                o.get("yearId")
                or o.get("year_id")
                or o.get("selectedYear")
                or o.get("curriculumYear")
                or o.get("curriculum_year")
            ):
                o["yearId"] = year_top
        opts_norm.append(o)
    _runtime_sessions[sid] = {
        "title": title,
        "options": opts_norm,
        "filter_defaults": filter_defaults,
    }
    n = len(_session_raw_items(sid))
    ans = f"as-{sid}"
    return jsonify({
        "id": sid,
        "title": title,
        "lastOpened": None,
        "status": "active",
        "answerSets": [{"id": ans, "sessionId": sid}],
        "totalQuestions": n,
        "totalCases": 0,
        "totalCasesQuestions": 0,
        "canAccess": True,
        "itemsOrderDirection": "asc",
    })


def _empty_playlist(**kwargs):
    base = {
        "questionsCount": 0,
        "clinicalCasesCount": 0,
        "clinicalCasesQuestionsCount": 0,
        "totalQuestionsCount": 0,
        "questions": [],
        "clinicalCases": [],
    }
    base.update(kwargs)
    return base


# No bundled playlists — new accounts start empty; only POST-created playlists appear.
SAMPLE_PLAYLISTS = []

# Playlists created via POST /api/v1/playlists/playlist (persists until server restart)
_runtime_playlists = []


def _find_playlist(playlist_id):
    """Return playlist dict from runtime or sample lists."""
    for pl in _runtime_playlists:
        if pl.get("id") == playlist_id:
            return pl
    for pl in SAMPLE_PLAYLISTS:
        if pl.get("id") == playlist_id:
            return pl
    return None


def _playlist_contains_question(pl, question_id):
    for q in pl.get("questions") or []:
        qid = q.get("id") if isinstance(q, dict) else q
        if qid == question_id:
            return True
    return False


def _playlist_contains_clinical_case(pl, case_id):
    for c in pl.get("clinicalCases") or []:
        cid = c.get("id") if isinstance(c, dict) else c
        if cid == case_id:
            return True
    return False


@app.route('/api/v2/sessions', methods=['GET'])
def get_sessions():
    # SessionsPage expects { edges: [], pageInfo: { hasNextPage, nextPage } }
    edges = []
    for sid, meta in reversed(list(_runtime_sessions.items())):
        edges.append(_runtime_session_edge(sid, meta))
    edges.extend(SAMPLE_SESSIONS)
    return jsonify({
        "edges": edges,
        "pageInfo": {"hasNextPage": False, "nextPage": None}
    })


@app.route('/api/v2/sessions/<session_id>/details', methods=['GET'])
def get_session_details(session_id):
    # SessionDetailsDialog expects array of { year, theme?, unit?, chapters, courses, sources }
    return jsonify([])


@app.route('/api/v2/sessions/<session_id>/items-count', methods=['GET'])
def get_session_items_count(session_id):
    tq = len(_session_raw_items(session_id))
    return jsonify({
        "total": tq,
        "totalQuestions": tq,
        "totalCases": 0,
        "totalCasesQuestions": 0,
    })


@app.route('/api/v2/sessions/<session_id>/items', methods=['GET'])
def get_session_items(session_id):
    """SessionPage: GET .../items?position=&direction=current|next|prev — returns { items, position, sessionMeta, pageInfo }."""
    _ = request.args.get("position", "0")
    items_out = []
    for raw in _session_raw_items(session_id):
        pq = _session_question_payload(raw, session_id=session_id)
        if pq:
            items_out.append(pq)
    total = len(items_out)
    return jsonify({
        "items": items_out,
        "position": {"absoluteStartIndex": 0},
        "sessionMeta": {"totalItems": total},
        "pageInfo": {
            "hasNextPage": False,
            "setIndex": 0,
            "type": "questions",
            "page": 1,
        },
    })


@app.route('/api/v2/sessions/<session_id>/position', methods=['PATCH'])
def patch_session_position(session_id):
    return jsonify({"success": True})


@app.route('/api/v2/sessions/<session_id>/score', methods=['GET'])
def get_session_score(session_id):
    """SessionPage ScoreDialog: ?s=binary-mode|fractional-mode"""
    return jsonify({
        "score": 0,
        "max": 20,
        "stats": {"correct": 0, "partiallyCorrect": 0, "incorrect": 0, "skipped": 0, "missed": 0},
    })


@app.route('/api/v2/sessions/<session_id>', methods=['GET'])
def get_session_one(session_id):
    """Session load before items (answerSets[0].userAnswers for replay)."""
    ans_id = f"as-{session_id}"
    if session_id in _runtime_sessions:
        rs = _runtime_sessions[session_id]
        n = len(_session_raw_items(session_id))
        return jsonify({
            "id": session_id,
            "title": rs.get("title") or "Session",
            "lastOpened": None,
            "status": "active",
            "totalQuestions": n,
            "totalCases": 0,
            "totalCasesQuestions": 0,
            "answerSets": [{"id": ans_id, "sessionId": session_id, "userAnswers": []}],
            "canAccess": True,
            "itemsOrderDirection": "asc",
        })
    for s in SAMPLE_SESSIONS:
        if s["id"] == session_id:
            out = dict(s)
            out["answerSets"] = [{"id": ans_id, "sessionId": session_id, "userAnswers": []}]
            return jsonify(out)
    n = len(_session_raw_items(session_id))
    return jsonify({
        "id": session_id,
        "title": "Session",
        "lastOpened": None,
        "status": "active",
        "totalQuestions": n,
        "totalCases": 0,
        "totalCasesQuestions": 0,
        "answerSets": [{"id": ans_id, "sessionId": session_id, "userAnswers": []}],
        "canAccess": True,
        "itemsOrderDirection": "asc",
    })


@app.route('/api/v2/sessions/<session_id>', methods=['PATCH'])
def patch_session(session_id):
    return jsonify({"success": True})


@app.route('/api/v2/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    return "", 204


@app.route('/api/v2/sessions/<session_id>/highlights', methods=['GET', 'PATCH'])
def session_highlights(session_id):
    """Save-to-playlist / exam UI: highlights-BbN8vXOS syncs localStorage with this endpoint (v2)."""
    if request.method == 'GET':
        h = _runtime_session_highlights.get(session_id) or {}
        return jsonify({"highlights": dict(h) if isinstance(h, dict) else {}})
    body = request.get_json(silent=True) or {}
    incoming = body.get("highlights")
    if isinstance(incoming, dict):
        _runtime_session_highlights[session_id] = incoming
    return jsonify({"success": True})


@app.route('/api/v2/answer-sets', methods=['POST'])
def post_answer_sets():
    # SessionsPage reset calls this with { sessionId }; expect new answer set
    body = request.get_json(silent=True) or {}
    return jsonify({
        "id": "local-answer-set",
        "sessionId": body.get("sessionId"),
    })


@app.route('/api/v1/themes/due', methods=['GET'])
def get_v1_themes_due():
    """Due themes (flashcards) disabled."""
    return jsonify({})


@app.route('/api/v2/themes/due', methods=['GET'])
def get_themes_due():
    """Due themes (flashcards) disabled."""
    return jsonify({})


@app.route('/api/v2/cards/modules/<module_id>', methods=['DELETE'])
def delete_cards_module(module_id):
    return "", 204


# ----- Playlists & notes (v2) — AddToPlaylistDialog + NotesCard use SC(path, 2) → /api/v2/... -----
def _playlists_v2_unpinned_response():
    all_pl = list(_runtime_playlists) + SAMPLE_PLAYLISTS
    edges = [p for p in all_pl if not p.get("pinned")]
    return jsonify({
        "edges": edges,
        "pageInfo": {"hasNextPage": False, "nextPage": None},
    })


def _playlist_ids_containing_question(question_id):
    qid = str(question_id)
    ids = []
    for pl in list(_runtime_playlists) + SAMPLE_PLAYLISTS:
        if _playlist_contains_question(pl, qid):
            pid = pl.get("id")
            if pid is not None:
                ids.append(pid)
    return ids


@app.route('/api/v2/playlists/questions/<question_id>', methods=['GET'])
def v2_playlists_for_question(question_id):
    """belongsTo: array of playlist ids (NotesDialog fetchItemPlaylists)."""
    return jsonify(_playlist_ids_containing_question(question_id))


@app.route('/api/v2/playlists/cases/<case_id>', methods=['GET'])
def v2_playlists_for_case(case_id):
    return jsonify([])


@app.route('/api/v2/playlists/<playlist_id>/questions/<question_id>', methods=['PATCH', 'DELETE'])
def v2_playlist_question(playlist_id, question_id):
    return playlist_question(playlist_id, question_id)


@app.route('/api/v2/playlists/<playlist_id>/cases/<case_id>', methods=['PATCH', 'DELETE'])
def v2_playlist_case(playlist_id, case_id):
    return playlist_clinical_case(playlist_id, case_id)


@app.route('/api/v2/playlists', methods=['GET', 'POST'])
def v2_playlists_collection():
    """GET ?pinned=true → [] (prod); GET ?cursor= → { edges, pageInfo }; POST { label } creates playlist."""
    if request.method == 'POST':
        return post_playlist()
    if request.args.get('pinned') in ('true', '1', 'yes'):
        return jsonify([])
    return _playlists_v2_unpinned_response()


def _note_v2_create(question_id, value):
    note = _new_note_document(question_id, value)
    _runtime_notes_v2[str(question_id)].append(note)
    return note


def _note_v2_find(note_id):
    for qid, lst in _runtime_notes_v2.items():
        for n in lst:
            if n.get("id") == note_id:
                return qid, n
    return None, None


@app.route('/api/v2/notes/questions/<question_id>/count', methods=['GET'])
def v2_notes_question_count(question_id):
    n = len(_runtime_notes_v2.get(str(question_id), []))
    raw = find_question_by_id(question_id)
    if raw:
        for note in _embedded_notes_list(raw):
            if isinstance(note, dict) and str(note.get("value") or "").strip():
                n += 1
            elif isinstance(note, str) and note.strip():
                n += 1
    return jsonify(n)


@app.route('/api/v2/notes/questions/<question_id>', methods=['GET'])
def v2_notes_question_list(question_id):
    edges = list(_runtime_notes_v2.get(str(question_id), []))
    return jsonify({
        "edges": edges,
        "pageInfo": {"hasNextPage": False, "nextPage": None},
    })


@app.route('/api/v2/notes', methods=['POST'])
def v2_notes_post():
    body = request.get_json(silent=True) or {}
    qid = body.get("questionId") or body.get("question_id")
    value = (body.get("value") or "").strip()
    if not qid or not value:
        return jsonify({"message": "Invalid note"}), 400
    return jsonify(_note_v2_create(qid, value)), 201


@app.route('/api/v2/notes/<note_id>', methods=['PATCH', 'DELETE'])
def v2_notes_one(note_id):
    qid, note = _note_v2_find(note_id)
    if not note:
        return jsonify({"message": "Note not found"}), 404
    if request.method == 'DELETE':
        _runtime_notes_v2[qid] = [n for n in _runtime_notes_v2[qid] if n.get("id") != note_id]
        return "", 204
    body = request.get_json(silent=True) or {}
    val = body.get("value")
    if val is not None:
        _note_apply_patch(note, str(val).strip())
    return jsonify(note)


@app.route('/api/v1/notes/note', methods=['POST'])
def v1_notes_post_note():
    """AnswerDialog: POST { value, question } — same as medlibro.co (201 + full note)."""
    body = request.get_json(silent=True) or {}
    value = (body.get("value") or "").strip()
    qid = body.get("question") or body.get("questionId") or body.get("question_id")
    if not qid or not value:
        return jsonify({"message": "Invalid note"}), 400
    note = _note_v2_create(qid, value)
    return jsonify(note), 201


@app.route('/api/v1/notes/note/<note_id>', methods=['PATCH', 'DELETE'])
def v1_notes_note_one(note_id):
    qid, note = _note_v2_find(note_id)
    if not note:
        return jsonify({"message": "Note not found"}), 404
    if request.method == 'DELETE':
        _runtime_notes_v2[qid] = [n for n in _runtime_notes_v2[qid] if n.get("id") != note_id]
        return "", 204
    body = request.get_json(silent=True) or {}
    val = body.get("value")
    if val is None:
        return jsonify(note)
    _note_apply_patch(note, str(val).strip())
    return jsonify(note)


# ----- Playlists (v1) – list/search with edges + pageInfo -----
@app.route('/api/v1/playlists', methods=['GET'])
def get_playlists():
    # PlaylistsPage store expects { edges: [], pageInfo: { hasNextPage, nextPage } }
    # Omit pinned: they come from GET /playlists/pinned (duplicate IDs break SaveToPlaylistDialog)
    all_pl = list(_runtime_playlists) + SAMPLE_PLAYLISTS
    edges = [p for p in all_pl if not p.get("pinned")]
    return jsonify({
        "edges": edges,
        "pageInfo": {"hasNextPage": False, "nextPage": None}
    })


@app.route('/api/v1/playlists/playlist', methods=['POST'])
def post_playlist():
    """Create playlist (PlaylistDialog addPlaylist). Body: { label, description }."""
    body = request.get_json(silent=True) or {}
    pid = str(uuid.uuid4())
    pl = {
        "id": pid,
        "label": body.get("label") or "Playlist",
        "description": body.get("description") or "",
        "questionsCount": 0,
        "clinicalCasesCount": 0,
        "clinicalCasesQuestionsCount": 0,
        "totalQuestionsCount": 0,
        "pinned": False,
        "questions": [],
        "clinicalCases": [],
    }
    _runtime_playlists.insert(0, pl)
    return jsonify(pl), 201


@app.route(
    '/api/v1/playlists/playlist/<playlist_id>/question/<question_id>',
    methods=['PATCH', 'DELETE'],
)
def playlist_question(playlist_id, question_id):
    """Add (PATCH) or remove (DELETE) a question on a playlist — playlists store (addQuestionToPlaylist)."""
    pl = _find_playlist(playlist_id)
    if not pl:
        return jsonify({"message": "Playlist not found"}), 404
    qs = pl.setdefault("questions", [])
    if request.method == 'PATCH':
        if not _playlist_contains_question(pl, question_id):
            qs.append({"id": question_id})
            pl["questionsCount"] = int(pl.get("questionsCount") or 0) + 1
            if "totalQuestionsCount" in pl:
                pl["totalQuestionsCount"] = int(pl.get("totalQuestionsCount") or 0) + 1
        return jsonify({"success": True})
    # DELETE
    new_qs = [q for q in qs if (q.get("id") if isinstance(q, dict) else q) != question_id]
    if len(new_qs) != len(qs):
        pl["questions"] = new_qs
        pl["questionsCount"] = max(0, int(pl.get("questionsCount") or 0) - 1)
        if "totalQuestionsCount" in pl:
            pl["totalQuestionsCount"] = max(0, int(pl.get("totalQuestionsCount") or 0) - 1)
    return jsonify({"success": True})


@app.route(
    '/api/v1/playlists/playlist/<playlist_id>/clinical-case/<case_id>',
    methods=['PATCH', 'DELETE'],
)
def playlist_clinical_case(playlist_id, case_id):
    pl = _find_playlist(playlist_id)
    if not pl:
        return jsonify({"message": "Playlist not found"}), 404
    cs = pl.setdefault("clinicalCases", [])
    if request.method == 'PATCH':
        if not _playlist_contains_clinical_case(pl, case_id):
            cs.append({"id": case_id})
            pl["clinicalCasesCount"] = int(pl.get("clinicalCasesCount") or 0) + 1
            if "totalQuestionsCount" in pl:
                pl["totalQuestionsCount"] = int(pl.get("totalQuestionsCount") or 0) + 1
        return jsonify({"success": True})
    new_cs = [c for c in cs if (c.get("id") if isinstance(c, dict) else c) != case_id]
    if len(new_cs) != len(cs):
        pl["clinicalCases"] = new_cs
        pl["clinicalCasesCount"] = max(0, int(pl.get("clinicalCasesCount") or 0) - 1)
        if "totalQuestionsCount" in pl:
            pl["totalQuestionsCount"] = max(0, int(pl.get("totalQuestionsCount") or 0) - 1)
    return jsonify({"success": True})


@app.route('/api/v1/playlists/search', methods=['GET'])
def get_playlists_search():
    # filterPlaylists sets playlists = data, pageInfo = null
    return jsonify([])


# Catch-all for any other /api/* routes
@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def api_catchall(path):
    """Catch-all for undefined API routes. Return safe stub shapes so dashboard cards don't crash."""
    if request.method == "OPTIONS":
        return "", 200
    # Return correct shape for known dashboard routes (in case they hit catch-all)
    norm = path.split("?")[0].rstrip("/")
    if request.method == "GET":
        if norm == "v2/cards/themes/top":
            return jsonify({"themes": []})
        if norm == "v1/playlists/pinned":
            return jsonify([])
    if request.method in ("GET", "PATCH"):
        if request.method == "GET" and norm not in ("v2/cards/themes/top", "v1/playlists/pinned"):
            print(f"[WARN] Unhandled API route: /api/{path} ({request.method})")
        return jsonify({} if request.method == "GET" else {"success": True})
    print(f"[WARN] Unhandled API route: /api/{path} ({request.method})")
    return jsonify({"error": f"Route /api/{path} not implemented"}), 404


@app.route("/", defaults={"path": ""}, methods=["GET"])
@app.route("/<path:path>", methods=["GET"])
def serve(path):
    """Serve static file from mirror, or index.html for SPA routes."""
    if path.startswith("api"):
        return "", 404
    # Prevent path traversal
    if ".." in path or path.startswith("/"):
        path = ""
    # Deep-link / bookmark to Memorix → dashboard (feature removed locally).
    if path:
        hit = path.split("?", 1)[0].strip("/").lower()
        if hit == "memorix" or hit.startswith("memorix/"):
            return redirect("/dashboard", code=302)
    # Always serve SPA for / so the marketing landing renders; client script sends logged-in users to /dashboard.
    # Static file?
    file_path = (MIRROR / path).resolve()
    if not str(file_path).startswith(str(MIRROR.resolve())):
        path = ""
    if path and file_path.is_file():
        from flask import Response
        # Gut Memorix-only lazy chunks (hash in filename); keeps dashboard import graph valid.
        lp = path.replace("\\", "/").lower()
        if (
            path.startswith("assets/")
            and path.endswith(".js")
            and ("memorixpage-" in lp or "memorixtopthemescard-" in lp or "memorixmodule-" in lp)
        ):
            r = Response(_memorix_stub_esm(), mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        # Remove Memorix from sidebar navigation (built ClientLayout chunk).
        if path.startswith("assets/ClientLayout-") and path.endswith(".js"):
            js = file_path.read_text(encoding="utf-8", errors="replace")
            js = _strip_memorix_from_clientlayout_js(js)
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        # Dashboard: remove Memorix shortcut row + Memorix themes card (hash in filename).
        if path.startswith("assets/DashboardPage-") and path.endswith(".js"):
            js = file_path.read_text(encoding="utf-8", errors="replace")
            js = _strip_memorix_from_dashboard_js(js)
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        # Patch SPA entry bundle (filename from index.html — hash varies per MedLibro release)
        if path == _spa_main_js_relpath():
            js = file_path.read_text(encoding="utf-8", errors="replace")
            # When authenticated, always allow navigation (don't redirect to dashboard when Ze() is false)
            js = js.replace(
                'Ze()?n():n({name:"dashboard"})',
                "n()",
            )
            js = js.replace(
                'Ze()?(await Ge(),n()):n({name:"dashboard"})',
                "(await Ge(),n())",
            )
            js = js.replace(
                'Ze()&&bn()?(await Ge(),n()):n({name:"dashboard"})',
                "(await Ge(),n())",
            )
            js = js.replace(
                '!e.params.play&&Ze()&&bn()?(await Ge(),n()):n({name:"dashboard"})',
                "(await Ge(),n())",
            )
            # AnswerDialog / revision: canDo() assumes connectedUser.role.permissions exists
            js = js.replace(
                'canDo:function(e){if(this.connectedUser){if(["pending","disabled"].includes(this.connectedUser.status))return!1;const[t,n]=e.split("."),r=this.connectedUser.role.permissions.find(s=>s.module===t&&s.action===n);if(r)return r.value}return!1}',
                'canDo:function(e){if(this.connectedUser){if(["pending","disabled"].includes(this.connectedUser.status))return!1;const[t,n]=e.split("."),r=((this.connectedUser.role&&this.connectedUser.role.permissions)||[]).find(s=>s.module===t&&s.action===n);if(r)return r.value}return!1}',
                1,
            )
            # Store getters: ternary allowed role access when role was undefined (throws)
            js = js.replace(
                'getters:{isAuthenticated:e=>!!e.connectedUser,isAdmin:e=>e.connectedUser?e.connectedUser.role.label==="admin":!1,isModerator:e=>e.connectedUser?e.connectedUser.role.label==="moderator":!1,isEditor:e=>e.connectedUser?e.connectedUser.role.label==="editor":!1,isPremium:e=>e.connectedUser?e.connectedUser.isPremium:!1}',
                'getters:{isAuthenticated:e=>!!e.connectedUser,isAdmin:e=>e.connectedUser&&e.connectedUser.role?e.connectedUser.role.label==="admin":!1,isModerator:e=>e.connectedUser&&e.connectedUser.role?e.connectedUser.role.label==="moderator":!1,isEditor:e=>e.connectedUser&&e.connectedUser.role?e.connectedUser.role.label==="editor":!1,isPremium:e=>e.connectedUser?!!(e.connectedUser.isPremium||String(e.connectedUser.subscription||"").toLowerCase()==="premium"):!1}',
                1,
            )
            # Revision (non-exam): Next disabled until VÉRIFIER sets done. Exam uses practice mode too but
            # must allow Suivant without verify (real exam UX); only gate on having a next item / queue.
            js = js.replace(
                "hideNext(e){return!this.nextMainItem&&!this.nextSecondaryItem&&e.itemsIds.length===0}",
                "hideNext(e){if(this.revisionMode!==\"explore\"&&!e.isExam){if(this.currentMainItem&&!this.currentMainItem.done)return!0;if(this.currentSecondaryItem&&!this.currentSecondaryItem.done)return!0}return!this.nextMainItem&&!this.nextSecondaryItem&&e.itemsIds.length===0}",
                1,
            )
            # Exam / revision: stock app loads one question every 300ms, so items[mainIndex+1] is missing and
            # "Suivant" can stay enabled while navigateToNextItem no-ops. Preload all items inside getItemAction
            # so await getItemAction() in fetchItems fills items[] before AnswerDialog opens.
            js = js.replace(
                "const t=this,n=setInterval(async function(){if(navigator.onLine)if(t.itemsIds.length>0){t.loadingNewItem=!0;const s=t.itemsIds.splice(0,1).pop();await e(s),t.loadingNewItem=!1}else clearInterval(n);else clearInterval(n)},300)}",
                "const t=this;if(navigator.onLine)for(;t.itemsIds.length>0;){t.loadingNewItem=!0;const s=t.itemsIds.splice(0,1).pop();await e(s);t.loadingNewItem=!1}}",
                1,
            )
            # After e-mail validation, Pinia only set status=valid; sync premium fields from our API response shape
            js = js.replace(
                'validateAccount(e){const{error:t,message:n}=await _n(`${J("auth")}/validate-account`,e,{withCredentials:!0});if(!t){const r=this.connectedUser;return r.status="valid",this.connectedUser=r,{error:!1}}return{error:!0,message:n}}',
                'validateAccount(e){const{error:t,message:n}=await _n(`${J("auth")}/validate-account`,e,{withCredentials:!0});if(!t){const r=this.connectedUser;return r.status="valid",r.isValid=!0,r.isPremium=!0,r.subscription="premium",r.emailVerified=!0,r.email_verified=!0,r.accountValidated=!0,r.isEmailVerified=!0,r.email_validated=!0,r.validated=!0,this.connectedUser=r,{error:!1}}return{error:!0,message:n}}',
                1,
            )
            js = _strip_memorix_from_js_bundle(js)
            from flask import Response
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        # SaveToPlaylist: template uses disabled:!t.isPremium — undefined isPremium disables the button permanently
        if path == "assets/AnswerDialog-BfjbLpTp.js":
            js = file_path.read_text(encoding="utf-8", errors="replace")
            js = js.replace("{disabled:!t.isPremium,", "{disabled:!1,", 1)
            from flask import Response
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        if path == "assets/SignupPage-CJZ4d7hS.js":
            js = file_path.read_text(encoding="utf-8", errors="replace")
            # After successful signup, go to login (not home) so users sign in explicitly
            js = js.replace(
                'await this.$router.push({name:"/"})',
                'await this.$router.push({name:"login"})',
                1,
            )
            from flask import Response
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        if path == "assets/UserDialog-DdrvNLnA.js":
            js = file_path.read_text(encoding="utf-8", errors="replace")
            js = js.replace(
                "created(){this.username=this.connectedUser.username,this.phoneNumber=this.connectedUser.phoneNumber,this.firstName=this.connectedUser.firstName,this.lastName=this.connectedUser.lastName}",
                "created(){this.username=this.connectedUser.username||\"\",this.phoneNumber=this.connectedUser.phoneNumber||null,this.firstName=this.connectedUser.firstName,this.lastName=this.connectedUser.lastName}",
                1,
            )
            js = js.replace(
                "await this.editProfile({firstName:this.firstName,lastName:this.lastName,phoneNumber:this.phoneNumber})",
                "await this.editProfile({username:this.username,firstName:this.firstName,lastName:this.lastName,phoneNumber:this.phoneNumber})",
                1,
            )
            js = js.replace(
                'attrs:{rules:[t.validationRules.required,t.validationRules.username],dense:"",disabled:"","hide-details":"auto",outlined:""}',
                'attrs:{rules:[t.validationRules.required,t.validationRules.username],dense:"","hide-details":"auto",outlined:""}',
                1,
            )
            from flask import Response
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        if path == "assets/ProfilePage-CJMwJY0h.js":
            js = file_path.read_text(encoding="utf-8", errors="replace")
            # Guard connectedUser/email so Profile doesn't crash when store not yet populated
            js = js.replace(
                "t.connectedUser.email.toLowerCase()",
                "(t.connectedUser&&t.connectedUser.email||'').toLowerCase()",
                1,
            )
            js = js.replace(
                "t.connectedUser.fullName",
                "(t.connectedUser&&t.connectedUser.fullName||'')",
                1,
            )
            js = js.replace(
                "t.dayMonthYearFormat(t.connectedUser.createdAt)",
                "t.dayMonthYearFormat(t.connectedUser&&t.connectedUser.createdAt)",
                1,
            )
            from flask import Response
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        if path == "assets/PreferencesDialog-CDw24Iob.js":
            js = file_path.read_text(encoding="utf-8", errors="replace")
            # preferences must be an array (uses .find()); guard non-array so no "t.find is not a function"
            js = js.replace(
                "(t=this.preferences)==null?void 0:t.find(i=>i.label===\"hide-notes-in-exam\")",
                "(t=this.preferences)==null?void 0:(Array.isArray(t)?t:[]).find(i=>i.label===\"hide-notes-in-exam\")",
                1,
            )
            js = js.replace(
                "(s=this.preferences)==null?void 0:s.find(i=>i.label===\"scoring-mode\")",
                "(s=this.preferences)==null?void 0:(Array.isArray(s)?s:[]).find(i=>i.label===\"scoring-mode\")",
                1,
            )
            js = js.replace(
                "(s=this.preferences)==null?void 0:s.find(r=>r.label===a)",
                "(s=this.preferences)==null?void 0:(Array.isArray(s)?s:[]).find(r=>r.label===a)",
                1,
            )
            # Guard .map() in onPreferenceChange: this.preferences.map -> (Array.isArray(this.preferences)?this.preferences:[]).map
            js = js.replace(
                "this.preferences.map(i=>i.label===a?",
                "(Array.isArray(this.preferences)?this.preferences:[]).map(i=>i.label===a?",
                1,
            )
            js = js.replace(
                "this.setPreferences([...this.preferences,i])",
                "this.setPreferences([...(Array.isArray(this.preferences)?this.preferences:[]),i])",
                1,
            )
            from flask import Response
            r = Response(js, mimetype="application/javascript")
            r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            return r
        if path.startswith("assets/") and path.endswith(".js"):
            try:
                _raw = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                _raw = ""
            if _bundle_contains_memorix(_raw):
                _raw = _strip_memorix_from_js_bundle(_raw)
                from flask import Response
                r = Response(_raw, mimetype="application/javascript")
                r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                return r
        return send_from_directory(MIRROR, path)
    # Never serve index.html for /assets/ - missing JS/CSS must 404 (not HTML)
    if path.startswith("assets/") or path.startswith("cf-fonts/"):
        return "Asset not found. Re-run build_mirror.py to download all chunks.", 404
    # Directory? try index.html inside
    if file_path.is_dir() and (file_path / "index.html").exists():
        return send_from_directory(str(file_path), "index.html")
    # SPA fallback: any other path (e.g. /revision, /dashboard) -> index.html
    index = MIRROR / "index.html"
    if index.exists():
        html = index.read_text(encoding="utf-8", errors="replace")
        # Auth script: MUST run FIRST before any Vue code loads
        # Clear any token that is NOT our local JWT, then redirect to login if not authenticated
        auth_script = """<script>
(function(){
// 1) Force ALL API calls to this origin (so login/authenticated hit our server, not production)
var apiRe=/^https?:\\/\\/(?:[^\\/]*\\.)?medlibro\\.co(\\/api\\/.*)$/i;
function rewriteApiUrl(url){
  if(typeof url!=='string') return url;
  var m=url.match(apiRe);
  if(m) return window.location.origin + m[1];
  return url;
}
if(typeof fetch!=='undefined'){
  var origFetch=window.fetch;
  window.fetch=function(url,opts){
    url=rewriteApiUrl(url);
    return origFetch.call(this,url,opts);
  };
}
if(typeof XMLHttpRequest!=='undefined'){
  var origOpen=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(method,url,async,user,pass){
    url=rewriteApiUrl(url);
    return origOpen.call(this,method,url,async,user,pass);
  };
}
// 2) Auth: clear foreign tokens; keep only server-issued mloc_* session tokens
try {
  function isOurSessionToken(x){
    return !!(x && String(x).indexOf('mloc_')===0);
  }
  function clearNonLocal(s){
    if(!s) return;
    var t=s.getItem('token')||s.getItem('accessToken')||s.getItem('jwt');
    if(t && !isOurSessionToken(t)){
      s.removeItem('token'); s.removeItem('accessToken'); s.removeItem('jwt');
      s.removeItem('user'); s.removeItem('authToken');
    }
  }
  if(typeof localStorage!=='undefined') clearNonLocal(localStorage);
  if(typeof sessionStorage!=='undefined') clearNonLocal(sessionStorage);
  function readCookie(name){
    var k='; '+document.cookie;
    var p=k.split('; '+name+'=');
    if(p.length<2)return null;
    return decodeURIComponent(p.pop().split(';').shift()||'');
  }
  var token=(typeof localStorage!=='undefined'&&localStorage.getItem('token'))||(typeof sessionStorage!=='undefined'&&sessionStorage.getItem('token'));
  var cookieTok=readCookie('token')||readCookie('authToken');
  var ok=isOurSessionToken(token)||isOurSessionToken(cookieTok);
  var path=window.location.pathname;
  var publicPaths=['/','/pricing','/faq','/activate','/login','/signup','/forgot-password'];
  var isPublic=publicPaths.indexOf(path)!==-1 || path==='' || path==='/';
  if(!ok && !isPublic) { window.location.replace('/login'); return; }
  if(ok && (path===''||path==='/')) { window.location.replace('/dashboard'); return; }
}catch(e){}
})();
</script>
<script>
(function(){
  function ensure(u){
    if(!u||typeof u!=='object')return;
    if(!u.role||typeof u.role!=='object')u.role={label:'user',permissions:[]};
    if(!Array.isArray(u.role.permissions))u.role.permissions=[];
    if(u.role.label==null)u.role.label='user';
    var sub=String(u.subscription||'').toLowerCase();
    if(u.isPremium!==true&&(sub==='premium'||sub==='pro'||sub==='paid'))u.isPremium=true;
    if(u.status==='valid'&&u.isValid!==true)u.isValid=true;
    if(u.email&&u.status==='valid')u.isPremium=true;
  }
  function patchStore(s){if(s&&s.connectedUser!==undefined){ensure(s.connectedUser);if(s.$patch)s.$patch(function(st){ensure(st.connectedUser);});}}
  function run(){
    try{
      var el=document.getElementById('app');if(!el)return;
      var app=el.__vue_app__||(el._vnode&&el._vnode.appContext&&el._vnode.appContext.app);
      if(!app&&el.__vueParentComponent){var c=el.__vueParentComponent;while(c&&!app){app=c.appContext&&c.appContext.app;c=c.parent;} }
      if(!app)return;
      var pinia=app.config&&app.config.globalProperties&&app.config.globalProperties.$pinia;
      if(!pinia||!pinia._s)return;
      pinia._s.forEach(patchStore);
    }catch(e){}
  }
  function start(){var n=0;var t=setInterval(function(){run();n++;if(n>50)clearInterval(t);},200);}
  if(document.readyState==='complete')start();else window.addEventListener('load',start);
})();
</script>
<style id="ml-hide-memorix">a[href*="memorix"],a[href*="Memorix"],a[href*="mémorix"],a[href*="Mémorix"]{display:none!important}</style>
<script>
(function(){
function memorixHref(h){return h&&String(h).toLowerCase().indexOf('memorix')>=0;}
function memorixText(t){t=(t||'').replace(/\\s+/g,' ').trim();return/^m[eé]morix$/i.test(t)||t==='Memorix'||t==='Mémorix';}
function nuke(){
  try{
    document.querySelectorAll('a[href], .v-list-item, .v-card, .v-btn, .v-tab').forEach(function(el){
      if(memorixHref(el.getAttribute('href'))){el.remove();return;}
      var tx=(el.textContent||'').replace(/\\s+/g,' ').trim();
      if(memorixText(tx)&&tx.length<24){el.remove();return;}
      if(el.classList&&el.classList.contains('v-card')){
        var snippet=(el.textContent||'').slice(0,900);
        if(/\\bm[eé]morix\\b/i.test(snippet)) el.remove();
      }
    });
  }catch(e){}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',nuke);else nuke();
try{new MutationObserver(function(){nuke();}).observe(document.documentElement,{childList:true,subtree:true});}catch(e){}
setInterval(nuke,1200);
})();
</script>"""
        # Strategy: Remove ALL existing <script> tags in <head> that contain clearOld or auth logic
        # Then inject our script IMMEDIATELY after <head> tag (before any other scripts)
        html = re.sub(r"<script[^>]*>.*?clearOld.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<script[^>]*>.*?local_jwt_token.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Inject our script RIGHT after <head> tag (before any other content)
        if "<head" in html:
            # Callable replacement: auth_script contains "\\" for JS regex; if concatenated into a re.sub
            # replacement template, "\\s" etc. are interpreted as invalid regex escapes (re.error).
            html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + auth_script, html, count=1)
        else:
            # Fallback: inject at very beginning of HTML
            html = auth_script + "\n" + html
        print(f"[SERVE] Injected auth script into index.html for path: {path}")
        from flask import Response
        resp = Response(html, mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return "Mirror not built. Run save_real_pages.py then build_mirror.py.", 404


def main():
    if not (MIRROR / "index.html").exists():
        print("[ERROR] Mirror not found. Run:")
        print("  1. python save_real_pages.py")
        print("  2. python build_mirror.py")
        sys.exit(1)
    print("=" * 60)
    print("MEDLIBRO LOCAL MIRROR SERVER (backend + static)")
    print("=" * 60)
    print("Serving:", MIRROR)
    print("Local API: /api/* (all handled locally, no external calls)")
    print("Data directory:", DATA_DIR)
    print("State directory:", _STATE_DIR)
    print("SPA entry script (patched):", _spa_main_js_relpath())
    print("=" * 60)
    port = int(os.environ.get("PORT", "8080"))
    print(f"Open in browser: http://localhost:{port}")
    print("Accounts: sign up at /signup, or add mirror_users_seed.json (see .example).")
    print("=" * 60)
    load_data()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
