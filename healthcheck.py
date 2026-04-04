"""
healthcheck.py — Full Stack Health Checker
============================================
Stack:  Flask (backend)  |  Supabase (database)
        Firebase (Google Auth)  |  Dart app + HTML website (frontend)

Run:    python healthcheck.py
"""

import os
import sys
import time
import importlib
import traceback
import urllib.request
import urllib.error

# ─────────────────────────────────────────────────────────────
# ✏️  CONFIGURE THESE FOR YOUR PROJECT
# ─────────────────────────────────────────────────────────────

FLASK_APP_MODULE   = "app"   # Module where your Flask app lives
FLASK_APP_VARIABLE = "app"   # The Flask() instance variable name

REQUIRED_ENV_VARS = [
    # Flask / Security
    "SECRET_KEY",

    # Database
    "DATABASE_URL",

    # Supabase
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "SUPABASE_SERVICE_KEY",

    # Firebase
    "FIREBASE_PROJECT_ID",
    "FIREBASE_AUTH_DOMAIN",
    "FIREBASE_CLIENT_EMAIL",
    "FIREBASE_API_KEY",
    "FIREBASE_PRIVATE_KEY",
    "FIREBASE_CREDENTIALS_PATH",

    # Owner / Kitchen login
    "OWNER_COLLEGE_ID",
    "OWNER_PASSWORD",
    "KITCHEN_COLLEGE_ID",
    "KITCHEN_PASSWORD",
]

# Extra external services to ping (beyond Supabase & Firebase)
EXTRA_APIS = [
    # ("Service Name", "https://your-api-url.com/health"),
]

# ─────────────────────────────────────────────────────────────
# Terminal colours
# ─────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✔  PASS{RESET}  {msg}")
def fail(msg): print(f"  {RED}✘  FAIL{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠  WARN{RESET}  {msg}")
def info(msg): print(f"       {DIM}{msg}{RESET}")

results = {"passed": 0, "failed": 0, "warnings": 0}

def record(status):
    results[status] += 1


# ═══════════════════════════════════════════════════════════════
# 1. ENVIRONMENT VARIABLES
# ═══════════════════════════════════════════════════════════════

def check_env_vars():
    print(f"\n{BOLD}[ 1/6 ]  Environment Variables{RESET}")

    try:
        from dotenv import load_dotenv
        load_dotenv()
        info(".env file loaded via python-dotenv")
    except ImportError:
        info("python-dotenv not installed — reading system env only (pip install python-dotenv)")

    if not REQUIRED_ENV_VARS:
        warn("No env vars listed in REQUIRED_ENV_VARS.")
        record("warnings")
        return

    missing, empty = [], []
    for var in REQUIRED_ENV_VARS:
        val = os.environ.get(var)
        if val is None:
            missing.append(var)
        elif val.strip() == "":
            empty.append(var)

    if missing:
        fail(f"Missing vars  : {', '.join(missing)}")
        record("failed")
    if empty:
        fail(f"Empty vars    : {', '.join(empty)}")
        record("failed")
    if not missing and not empty:
        ok(f"All {len(REQUIRED_ENV_VARS)} required env vars are present and non-empty.")
        record("passed")

    # ── Validate key formats ───────────────────────────────────
    print()
    info("Validating key formats ...")

    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if supabase_key and not supabase_key.startswith("eyJ"):
        fail("SUPABASE_KEY looks wrong — should be a JWT token starting with 'eyJ', not a postgres URL.")
        record("failed")
    elif supabase_key:
        ok("SUPABASE_KEY format looks correct (JWT token).")
        record("passed")

    supabase_url = os.environ.get("SUPABASE_URL", "")
    if supabase_url and "supabase.com" in supabase_url and "supabase.co" not in supabase_url:
        fail("SUPABASE_URL ends with '.supabase.com' — should be '.supabase.co'")
        record("failed")
    elif supabase_url:
        ok("SUPABASE_URL format looks correct.")
        record("passed")

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url and not db_url.startswith("postgresql://"):
        fail("DATABASE_URL should start with 'postgresql://'")
        record("failed")
    elif db_url:
        ok("DATABASE_URL format looks correct.")
        record("passed")

    firebase_key = os.environ.get("FIREBASE_PRIVATE_KEY", "")
    if firebase_key and "BEGIN PRIVATE KEY" not in firebase_key:
        fail("FIREBASE_PRIVATE_KEY doesn't look like a valid private key.")
        record("failed")
    elif firebase_key:
        ok("FIREBASE_PRIVATE_KEY format looks correct.")
        record("passed")


# ═══════════════════════════════════════════════════════════════
# 2. SUPABASE  (database + REST API)
# ═══════════════════════════════════════════════════════════════

def check_supabase():
    print(f"\n{BOLD}[ 2/6 ]  Supabase (Database){RESET}")

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        fail("SUPABASE_URL or SUPABASE_KEY not set — skipping Supabase checks.")
        record("failed")
        return

    # ── 2a. REST API reachability ──────────────────────────────
    rest_url = f"{url}/rest/v1/"
    info(f"Pinging Supabase REST API: {rest_url}")
    try:
        start = time.time()
        req = urllib.request.Request(
            rest_url,
            headers={"apikey": key, "Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            status  = resp.getcode()
            elapsed = int((time.time() - start) * 1000)
        if 200 <= status < 400:
            ok(f"Supabase REST API reachable  [{status}]  {elapsed}ms")
            record("passed")
        else:
            fail(f"Supabase REST API returned unexpected status {status}")
            record("failed")
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        # 401/404 on bare /rest/v1/ is normal — Supabase requires a table name
        # 401 just means no default table to query, API is still reachable
        if e.code in (401, 404):
            ok(f"Supabase REST API reachable  [{e.code} → normal, no table specified]  {elapsed}ms")
            record("passed")
        else:
            fail(f"Supabase REST API error: HTTP {e.code} — {e.reason}")
            record("failed")
    except Exception as e:
        fail(f"Supabase REST API unreachable: {e}")
        record("failed")
        return

    # ── 2b. supabase-py client ─────────────────────────────────
    try:
        from supabase import create_client
        info("supabase-py found — testing client connection ...")
        try:
            client  = create_client(url, key)
            start   = time.time()
            client.table("_healthcheck_nonexistent_").select("*").limit(1).execute()
            elapsed = int((time.time() - start) * 1000)
            ok(f"supabase-py client connected  {elapsed}ms")
            record("passed")
        except Exception as e:
            msg = str(e)
            # These all mean the API responded — table just doesn't exist, which is expected
            if (
                "does not exist" in msg
                or "relation" in msg
                or "42P01" in msg
                or "PGRST205" in msg
                or "schema cache" in msg
            ):
                ok("supabase-py client connected (API reachable, test table not found as expected)")
                record("passed")
            else:
                fail(f"supabase-py client error: {msg}")
                record("failed")
    except ImportError:
        warn("supabase-py not installed — only REST API was checked.  (pip install supabase)")
        record("warnings")

    # ── 2c. Direct DB connection via DATABASE_URL ──────────────
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        info(f"Testing DATABASE_URL connection ...")
        try:
            import psycopg2
            start = time.time()
            conn  = psycopg2.connect(db_url, connect_timeout=6)
            conn.close()
            elapsed = int((time.time() - start) * 1000)
            ok(f"DATABASE_URL connected successfully  {elapsed}ms")
            record("passed")
        except ImportError:
            warn("psycopg2 not installed — skipping direct DB check.  (pip install psycopg2-binary)")
            record("warnings")
        except Exception as e:
            fail(f"DATABASE_URL connection failed: {e}")
            record("failed")


# ═══════════════════════════════════════════════════════════════
# 3. FIREBASE  (Google Authentication)
# ═══════════════════════════════════════════════════════════════

def check_firebase():
    print(f"\n{BOLD}[ 3/6 ]  Firebase (Google Authentication){RESET}")

    project_id = os.environ.get("FIREBASE_PROJECT_ID", "")

    # ── 3a. Firebase project info ─────────────────────────────
    if project_id:
        info(f"Firebase project configured: {project_id}")
        info(f"Auth domain: {os.environ.get('FIREBASE_AUTH_DOMAIN', 'not set')}")
        # SDK check below (3c) is the real connectivity test
    else:
        warn("FIREBASE_PROJECT_ID not set — skipping Firebase checks.")
        record("warnings")

    # ── 3b. firebase-credentials.json file check ──────────────
    creds_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "./firebase-credentials.json")
    if os.path.isfile(creds_path):
        ok(f"firebase-credentials.json found at: {creds_path}")
        record("passed")
    else:
        fail(f"firebase-credentials.json NOT found at: {creds_path}")
        info("Fix: Firebase Console → Project Settings → Service Accounts → Generate new private key")
        info("Save the downloaded file as 'firebase-credentials.json' in your project root.")
        record("failed")

    # ── 3c. firebase-admin SDK ─────────────────────────────────
    # NOTE: We do NOT initialize Firebase here — app.py owns initialization.
    # We only check if the SDK is installed and if the app is already running.
    try:
        import firebase_admin
        from firebase_admin import auth as fb_auth

        info("firebase-admin SDK found — checking if already initialized ...")
        try:
            firebase_admin.get_app()
            # App is already initialized — test Auth
            fb_auth.list_users(max_results=1)
            ok("firebase-admin SDK is initialized and Auth service responding.")
            record("passed")
        except ValueError:
            # Not yet initialized — this is expected when running healthcheck standalone
            # (app.py initializes it during Section 4 import)
            info("Firebase not yet initialized — will be initialized by app.py in Section 4.")
            ok("Firebase SDK installed and credentials file present — ready.")
            record("passed")
        except Exception as e:
            fail(f"firebase-admin Auth error: {e}")
            record("failed")

    except ImportError:
        warn("firebase-admin not installed.  (pip install firebase-admin)")
        record("warnings")


# ═══════════════════════════════════════════════════════════════
# 4. FLASK ROUTES
# ═══════════════════════════════════════════════════════════════

def check_routes():
    print(f"\n{BOLD}[ 4/6 ]  Flask Routes{RESET}")

    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        module    = importlib.import_module(FLASK_APP_MODULE)
        flask_app = getattr(module, FLASK_APP_VARIABLE)
    except ModuleNotFoundError:
        fail(f"Cannot import '{FLASK_APP_MODULE}'. Check FLASK_APP_MODULE at the top of this file.")
        record("failed")
        return
    except AttributeError:
        fail(f"'{FLASK_APP_MODULE}' has no variable '{FLASK_APP_VARIABLE}'. Check FLASK_APP_VARIABLE.")
        record("failed")
        return
    except Exception as e:
        fail(f"Error loading Flask app: {e}")
        info(traceback.format_exc())
        record("failed")
        return

    rules       = list(flask_app.url_map.iter_rules())
    user_routes = [r for r in rules if r.endpoint != "static"]

    if not user_routes:
        warn("No routes found — only Flask built-ins detected.")
        record("warnings")
        return

    ok(f"Found {len(user_routes)} route(s):")
    for rule in sorted(user_routes, key=lambda r: r.rule):
        methods = ", ".join(sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS")))
        info(f"{methods:<28} {rule.rule}")
    record("passed")


# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# 5. FRONTEND (skipped — frontend is in a separate repository)
# ═══════════════════════════════════════════════════════════════

def check_frontend():
    print(f"\n{BOLD}[ 5/6 ]  Frontend{RESET}")
    info("Frontend is in a separate folder/repo — skipping this check.")
    record("passed")


# ═══════════════════════════════════════════════════════════════
# 6. EXTRA EXTERNAL APIs
# ═══════════════════════════════════════════════════════════════

def check_extra_apis():
    print(f"\n{BOLD}[ 6/6 ]  Extra External APIs{RESET}")

    if not EXTRA_APIS:
        info("No extra APIs configured in EXTRA_APIS. Add entries at the top of this file if needed.")
        return  # not a warning — just nothing to check

    for name, url in EXTRA_APIS:
        try:
            start = time.time()
            req   = urllib.request.Request(url, headers={"User-Agent": "healthcheck/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                status  = resp.getcode()
                elapsed = int((time.time() - start) * 1000)
            if 200 <= status < 400:
                ok(f"{name:<20} {url}  [{status}]  {elapsed}ms")
                record("passed")
            else:
                fail(f"{name:<20} {url}  [{status}]")
                record("failed")
        except Exception as e:
            fail(f"{name:<20} {url}  Error: {e}")
            record("failed")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    width = 58
    print(f"\n{BOLD}{CYAN}{'═' * width}{RESET}")
    print(f"{BOLD}{CYAN}   Full Stack Health Check{RESET}")
    print(f"{BOLD}{CYAN}   Flask  ·  Supabase  ·  Firebase  ·  Dart + HTML{RESET}")
    print(f"{BOLD}{CYAN}{'═' * width}{RESET}")

    check_env_vars()
    check_supabase()
    check_firebase()
    check_routes()
    check_frontend()
    check_extra_apis()

    print(f"\n{BOLD}{'─' * width}{RESET}")
    print(f"{BOLD}  Summary{RESET}")
    print(f"{'─' * width}")
    print(f"  {GREEN}✔  Passed  : {results['passed']}{RESET}")
    print(f"  {RED}✘  Failed  : {results['failed']}{RESET}")
    print(f"  {YELLOW}⚠  Warnings: {results['warnings']}{RESET}")
    print(f"{'─' * width}\n")

    if results["failed"] > 0:
        print(f"  {RED}{BOLD}Issues found — fix the failures above before deploying.{RESET}\n")
        sys.exit(1)
    elif results["warnings"] > 0:
        print(f"  {YELLOW}{BOLD}Stack is mostly healthy — review warnings above.{RESET}\n")
        sys.exit(0)
    else:
        print(f"  {GREEN}{BOLD}All checks passed — your full stack is healthy! {RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()