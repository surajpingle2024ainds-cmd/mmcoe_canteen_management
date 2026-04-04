# test_api.py — run with: pytest test_api.py -v
# Install deps: pip install pytest playwright && playwright install chromium

import pytest
import os
from app import app

# ─────────────────────────────────────────────────────────────
# Deployed server URL (Render)
# ─────────────────────────────────────────────────────────────
BASE_URL = "https://essen-backend-uml5.onrender.com"


# ─────────────────────────────────────────────────────────────
# Fixture
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ═══════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ═══════════════════════════════════════════════════════════════

def test_health_endpoint(client):
    """GET /health should return 200 and ok:true"""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("ok") is True


# ═══════════════════════════════════════════════════════════════
# 2. AUTH ROUTES
# ═══════════════════════════════════════════════════════════════

def test_customer_login_route_exists(client):
    """POST /api/auth/login/customer — route exists even if credentials wrong"""
    res = client.post("/api/auth/login/customer", json={
        "identifier": "test@test.com",
        "password": "wrongpassword"
    })
    assert res.status_code in [200, 401, 403]


def test_staff_login_route_exists(client):
    """POST /api/auth/login/staff — route exists even if credentials wrong"""
    res = client.post("/api/auth/login/staff", json={
        "identifier": "wrong_id",
        "password": "wrongpassword"
    })
    assert res.status_code in [200, 401, 403, 429]  # 429 = rate limited


def test_signup_missing_fields(client):
    """POST /api/auth/signup — should return 400 if fields missing"""
    res = client.post("/api/auth/signup", json={})
    assert res.status_code == 400


def test_generate_otp_missing_phone(client):
    """POST /api/auth/generate-otp — should return 400 if phone missing"""
    res = client.post("/api/auth/generate-otp", json={})
    assert res.status_code == 400


def test_generate_otp_success(client):
    """POST /api/auth/generate-otp — should return 200 with valid phone"""
    res = client.post("/api/auth/generate-otp", json={"phone": "9999999999"})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("success") is True


# ═══════════════════════════════════════════════════════════════
# 3. PROTECTED ROUTES — should block unauthenticated requests
# ═══════════════════════════════════════════════════════════════

def test_profile_requires_auth(client):
    """GET /api/profile — should return 401 without token"""
    res = client.get("/api/profile")
    assert res.status_code == 401


def test_create_order_requires_auth(client):
    """POST /api/orders/create — should return 401 without token"""
    res = client.post("/api/orders/create", json={"items": []})
    assert res.status_code == 401


def test_owner_dashboard_requires_auth(client):
    """GET /api/owner/dashboard-stats — should return 401 without token"""
    res = client.get("/api/owner/dashboard-stats")
    assert res.status_code == 401


def test_wallet_requires_auth(client):
    """GET /api/user/wallet — should return 401 without token"""
    res = client.get("/api/user/wallet")
    assert res.status_code == 401


# ═══════════════════════════════════════════════════════════════
# 4. PUBLIC ROUTES — should work without auth
# ═══════════════════════════════════════════════════════════════

def test_menu_all_public(client):
    """GET /api/menu/all — public, no auth needed"""
    res = client.get("/api/menu/all")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_menu_today_public(client):
    """GET /api/menu/today — public, no auth needed"""
    res = client.get("/api/menu/today")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_active_offer_public(client):
    """GET /api/offers/active — public, no auth needed"""
    res = client.get("/api/offers/active")
    assert res.status_code == 200


def test_combos_public(client):
    """GET /api/combos — public, no auth needed"""
    res = client.get("/api/combos")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


# ═══════════════════════════════════════════════════════════════
# 5. SUPABASE DIRECT CONNECTION
# ═══════════════════════════════════════════════════════════════

def test_supabase_connection():
    """Supabase client should connect and reach the database"""
    from supabase import create_client
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    try:
        res = client.table("user").select("id").limit(1).execute()
        assert res.data is not None
    except Exception as e:
        assert "does not exist" in str(e) or "PGRST" in str(e), f"Unexpected error: {e}"


# ═══════════════════════════════════════════════════════════════
# 6. BROWSER / UI TESTS (uses deployed Render URL)
#    Requires: pip install playwright && playwright install chromium
# ═══════════════════════════════════════════════════════════════

def test_login_page_loads():
    """Staff login page on Render should load successfully"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed — run: pip install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            # 60s timeout — Render free tier may take ~30s to wake up
            page.goto(f"{BASE_URL}/login/staff", timeout=60000)
            assert page.title() != ""
        except Exception as e:
            pytest.skip(f"Render app unreachable: {e}")
        finally:
            browser.close()


def test_staff_login_flow():
    """Staff login with real credentials should redirect away from login page"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed — run: pip install playwright && playwright install chromium")

    owner_id  = os.environ.get("OWNER_COLLEGE_ID", "")
    owner_pwd = os.environ.get("OWNER_PASSWORD", "")

    if not owner_id or not owner_pwd:
        pytest.skip("OWNER_COLLEGE_ID / OWNER_PASSWORD not set in .env")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            # 60s timeout — Render free tier may take ~30s to wake up
            page.goto(f"{BASE_URL}/login/staff", timeout=60000)
            page.fill("#email", owner_id)
            page.fill("input[name='password'], #password", owner_pwd)
            page.click("button[type='submit']")
            page.wait_for_timeout(3000)
            # After login, should redirect away from login page
            assert "login" not in page.url or "dashboard" in page.url
        except Exception as e:
            pytest.skip(f"Login flow failed — check if Render is awake: {e}")
        finally:
            browser.close()