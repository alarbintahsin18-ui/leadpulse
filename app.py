import os
import sys
import io
import csv
import json
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response, redirect
from hunter_engine import (
    HunterIntelligenceEngine,
    clean_phone,
    validate_email_mx,
    generate_email_permutations
)
from storage import HunterStorageManager
from gmaps_scraper import LocalB2BScraper
from email_verifier import verify_email_smtp_ping, bulk_verify_emails, check_domain_deliverability
from outreach_sender import (
    load_accounts,
    save_accounts,
    test_smtp_account,
    send_cold_email,
    send_bulk_cold_emails,
    load_logs,
    AI_PITCH_TEMPLATES,
    generate_personalized_copy,
    generate_all_personalized_emails,
    generate_multi_step_sequence
)
from tech_detector import detect_technologies
import client_manager
import payment_manager
import database
import uddoktapay_gateway
from email_tracker import PIXEL_GIF, record_email_open, record_email_click
from linkedin_scraper import linkedin_navigator

# Initialize production SQLite database and migrations
database.init_database()

app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
storage_mgr = HunterStorageManager(BASE_DIR)
engine = HunterIntelligenceEngine()
local_scraper = LocalB2BScraper()

# ── Helper Functions for Client & Credit System ──
def get_request_client_id():
    """Extract client ID from API key, headers, json body, or query params."""
    # 1. API Key Auth (X-API-Key or Authorization Bearer)
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        auth_hdr = request.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            api_key = auth_hdr.split("Bearer ")[1].strip()
    if not api_key:
        api_key = request.args.get("api_key")

    if api_key:
        cl = client_manager.get_client_by_api_key(api_key.strip())
        if cl:
            return cl.get("id")

    # 2. Direct client ID in headers, body or params
    cid = request.headers.get("X-Client-Id")
    if not cid and request.is_json:
        try:
            cid = (request.json or {}).get("client_id")
        except Exception:
            pass
    if not cid:
        cid = request.args.get("client_id")
    return (cid or "").strip()

def check_and_deduct_credits(cost, reason="Service Usage"):
    """
    Checks if active client has enough credits and deducts them.
    Admins have unlimited credits.
    Guests must log in to get 250 bonus credits.
    Returns (success, balance, message).
    """
    cid = get_request_client_id()
    if cid in ("admin", "superadmin"):
        return True, 999999, "Admin mode (unlimited credits)"
    if not cid:
        return False, 0, "Please sign in with Google to claim your 250 Free Credits and start extracting leads!"
    return client_manager.deduct_credits(cid, cost, reason)

def check_feature_access(feature_name):
    """
    Checks if active client can use the feature.
    Free users (with 250 trial credits) can ONLY use Lead Extractor (GMaps & Hunter).
    Email Verifier and Cold Outreach are locked for free users until upgraded via bKash/Nagad!
    """
    cid = get_request_client_id()
    if cid in ("admin", "superadmin"):
        return True, "Admin mode"
    if not cid:
        return False, "Please sign in with Google to claim your 250 free trial credits."
    cl = client_manager.get_client(cid)
    if not cl:
        return False, "Client account not found."
    
    is_paid = client_manager.is_client_paid(cid)
    if not is_paid:
        if feature_name in ["email_verifier", "outreach_mailer", "sales_navigator"]:
            return False, "🔒 This feature is exclusively for Premium subscribers. Free 250 trial credits only support Lead Extractor. Please upgrade your plan via bKash or Nagad to unlock."
    return True, "OK"

def decode_google_jwt(jwt_token):
    try:
        parts = jwt_token.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            payload += "=" * ((4 - len(payload) % 4) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload)
            return json.loads(decoded_bytes.decode("utf-8"))
    except Exception as e:
        print("[!] JWT decode error:", e)
    return {}

# ── Authentication Endpoints (Google Sign-In & Admin Login) ──
@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    data = request.json or {}
    credential = data.get("credential", "").strip()
    email = data.get("email", "").strip()
    name = data.get("name", "").strip()
    picture = data.get("picture", "").strip()
    
    if credential:
        jwt_info = decode_google_jwt(credential)
        if jwt_info.get("email"):
            email = jwt_info.get("email", "").strip()
            name = jwt_info.get("name", name or "Google User").strip()
            picture = jwt_info.get("picture", picture or "")
            
    if not email:
        return jsonify({"success": False, "message": "Email is required for Google Sign-In."}), 400
        
    device_id = data.get("device_id", "").strip()
    google_uid = data.get("google_uid", "").strip()
    email_verified = data.get("email_verified", True)
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()

    ref_code = data.get("ref_code", "").strip()
    client, is_new, is_admin, trial_abused = client_manager.get_or_create_google_client(
        email, 
        name=name, 
        picture=picture, 
        device_id=device_id, 
        ip_address=ip_address, 
        google_uid=google_uid, 
        email_verified=email_verified,
        ref_code=ref_code
    )
    
    if trial_abused:
        msg = "⚠️ Notice: A free trial (250 credits) has already been claimed on this device or network. To prevent abuse, each user/device is limited to 1 trial. Please purchase a credit pack to recharge your account."
    elif is_new:
        msg = "🎉 Congratulations! 250 Free Bonus Credits have been added to your account!"
    else:
        msg = f"Welcome back, {client.get('name')}!"

    return jsonify({
        "success": True,
        "is_new": is_new,
        "is_admin": is_admin,
        "trial_abused": trial_abused,
        "client": client,
        "message": msg
    })

@app.route("/api/auth/admin-login", methods=["POST"])
def auth_admin_login():
    data = request.json or {}
    passcode = data.get("passcode", "").strip()
    if not client_manager.verify_admin_passcode(passcode):
        return jsonify({"success": False, "message": "Incorrect Admin Passcode. Default is 'admin123'."}), 401
        
    admin_info = client_manager.load_clients_data().get("admin", {})
    return jsonify({
        "success": True,
        "is_admin": True,
        "client": {
            "id": "admin",
            "name": admin_info.get("name", "Super Admin"),
            "email": admin_info.get("email", "admin@leadpulse.ai"),
            "role": "admin",
            "unlimited": True
        },
        "message": "Super Admin access granted."
    })

@app.route("/api/auth/send-email-code", methods=["POST"])
def auth_send_email_code():
    import email_auth_manager
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    ok, msg, dev_code = email_auth_manager.generate_and_send_code(email, password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({
        "success": True,
        "message": msg,
        "dev_code": dev_code
    })

@app.route("/api/auth/verify-email-code", methods=["POST"])
def auth_verify_email_code():
    import email_auth_manager
    data = request.json or {}
    email = data.get("email", "").strip()
    code = data.get("code", "").strip()
    device_id = data.get("device_id", "").strip()
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()

    if not email or not code:
        return jsonify({"success": False, "message": "Email and 6-digit verification code are required."}), 400

    ok, msg, client = email_auth_manager.verify_code_and_login(email, code, device_id=device_id, ip_address=ip_address)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({
        "success": True,
        "message": msg,
        "client": client,
        "client_id": client.get("id")
    })

@app.route("/api/client/my-account-summary", methods=["GET"])
def get_my_account_summary():
    cid = get_request_client_id()
    if not cid or cid in ("admin", "superadmin"):
        if cid in ("admin", "superadmin"):
            return jsonify({
                "success": True,
                "is_admin": True,
                "message": "Admin mode"
            })
        return jsonify({"success": False, "message": "No active client session."}), 401

    summary = client_manager.get_client_usage_summary(cid)
    return jsonify(summary)

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    cid = get_request_client_id()
    if cid in ("admin", "superadmin"):
        admin_info = client_manager.load_clients_data().get("admin", {})
        return jsonify({
            "authenticated": True,
            "is_admin": True,
            "client": {
                "id": "admin",
                "name": admin_info.get("name", "Super Admin"),
                "email": admin_info.get("email", "admin@leadpulse.ai"),
                "unlimited": True
            }
        })
    elif cid:
        cl = client_manager.get_client(cid)
        if cl:
            return jsonify({
                "authenticated": True,
                "is_admin": False,
                "client": cl
            })
    return jsonify({"authenticated": False})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Client-Id"
    return response

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/admin")
def admin_page():
    return redirect("/?admin=1")

@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")

@app.route("/terms")
def terms_page():
    return render_template("terms.html")

# ── Client & Credit Management Endpoints (Admin Protected) ──
@app.route("/api/clients", methods=["GET"])
def get_clients_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        # Client requesting data: only return their own account details
        cl = client_manager.get_client(cid)
        txs = client_manager.get_credit_transactions(client_id=cid, limit=20)
        return jsonify({
            "success": True,
            "is_admin": False,
            "client": cl,
            "transactions": txs
        })

    # Admin requesting data: return full management list and totals
    clients = client_manager.get_all_clients()
    stats = client_manager.get_overview_stats()
    txs = client_manager.get_credit_transactions(limit=25)
    return jsonify({
        "success": True,
        "is_admin": True,
        "clients": clients,
        "stats": stats,
        "transactions": txs
    })

@app.route("/api/clients/create", methods=["POST"])
def create_client_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Access Denied: Only Administrators can create client accounts."}), 403

    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    company = data.get("company", "").strip()
    credits = int(data.get("credits", 250))
    notes = data.get("notes", "").strip()

    if not name or not email:
        return jsonify({"success": False, "message": "Client Name and Email are required."}), 400

    new_client = client_manager.create_client(name, email, company=company, initial_credits=credits, notes=notes)
    return jsonify({
        "success": True,
        "message": f"Client '{new_client['company']}' created with {credits} credits!",
        "client": new_client
    })

@app.route("/api/clients/update-credits", methods=["POST"])
def update_credits_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Access Denied: Only Administrators can adjust or gift credits."}), 403

    data = request.json or {}
    client_id = data.get("client_id", "").strip()
    amount = int(data.get("amount", 0))
    action = data.get("action", "add").strip() # 'add', 'deduct', 'set'
    note = data.get("note", "").strip()
    is_paid = data.get("is_paid")
    plan = data.get("plan")

    if not client_id:
        return jsonify({"success": False, "message": "Client ID is required."}), 400

    ok, new_bal, msg = client_manager.update_client_credits(
        client_id, amount, action=action, note=note, is_paid=is_paid, plan=plan
    )
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({
        "success": True,
        "message": msg,
        "client_id": client_id,
        "new_balance": new_bal
    })

@app.route("/api/clients/delete", methods=["POST"])
def delete_client_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Access Denied: Only Administrators can delete clients."}), 403

    data = request.json or {}
    client_id = data.get("client_id", "").strip()
    if not client_id:
        return jsonify({"success": False, "message": "Client ID is required."}), 400

    ok, msg = client_manager.delete_client(client_id)
    return jsonify({"success": ok, "message": msg})

@app.route("/api/clients/transactions", methods=["GET"])
def get_transactions_route():
    client_id = request.args.get("client_id")
    limit = int(request.args.get("limit", 50))
    txs = client_manager.get_credit_transactions(client_id=client_id, limit=limit)
    return jsonify({"success": True, "transactions": txs})

@app.route("/api/clients/me", methods=["GET"])
def get_me_route():
    client_id = get_request_client_id()
    client = client_manager.get_client(client_id)
    if not client:
        return jsonify({"success": False, "message": "Client not found."}), 404
    return jsonify({"success": True, "client": client})

# ── Core Search & Lead Intel Routes (with Credit Protection) ──
@app.route("/api/search", methods=["POST"])
def search():
    data = request.json or {}
    query = data.get("query", "").strip()
    search_type = data.get("type", "auto").strip().lower()

    if not query:
        return jsonify({"success": False, "message": "Search query is required."}), 400

    # Credit Check & Deduction (1 credit per single search)
    ok, bal, msg = check_and_deduct_credits(1, f"Single Lead Search: {query}")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    # Auto detect query type if not specified
    if search_type == "auto":
        cleaned_digits = "".join(filter(str.isdigit, query))
        if len(cleaned_digits) >= 7 and ("-" in query or "(" in query or query.startswith("+") or cleaned_digits == query):
            search_type = "phone"
        elif "." in query and not " " in query:
            search_type = "domain"
        else:
            search_type = "company"

    result = {}
    if search_type == "phone":
        result = engine.reverse_phone_lookup(query)
    elif search_type == "domain":
        result = engine.domain_intelligence(query)
    else:
        result = engine.company_lookup(query)

    # Save to history & Excel
    storage_mgr.save_lead(result, query=query, query_type=search_type)

    return jsonify({
        "success": True,
        "query": query,
        "type": search_type,
        "data": result,
        "credits_remaining": bal
    })

@app.route("/api/verify-email", methods=["POST"])
def verify_email():
    """Validates email RFC syntax, disposable domains, and DNS MX records."""
    data = request.json or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    intel = validate_email_mx(email)
    return jsonify({
        "success": True,
        "data": intel
    })

@app.route("/api/email-permutations", methods=["POST"])
def email_permutations():
    """Generates corporate B2B email permutations and tests domain MX."""
    data = request.json or {}
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    domain = data.get("domain", "").strip()

    if not domain:
        return jsonify({"success": False, "message": "Domain is required."}), 400

    perms = generate_email_permutations(first_name, last_name, domain)
    return jsonify({
        "success": True,
        "domain": domain,
        "first_name": first_name,
        "last_name": last_name,
        "count": len(perms),
        "data": perms
    })

@app.route("/api/bulk", methods=["POST"])
def bulk_enrich():
    """Enriches a batch of queries (1 credit per item)."""
    queries = []

    if "file" in request.files:
        uploaded_file = request.files["file"]
        if uploaded_file.filename.endswith(".csv"):
            content = uploaded_file.stream.read().decode("utf-8-sig", errors="ignore")
            reader = csv.reader(io.StringIO(content))
            for row in reader:
                if row and row[0].strip():
                    queries.append(row[0].strip())
        elif uploaded_file.filename.endswith((".xlsx", ".xls")):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(uploaded_file)
                ws = wb.active
                for r in ws.iter_rows(values_only=True):
                    if r and r[0] and str(r[0]).strip():
                        queries.append(str(r[0]).strip())
            except Exception as e:
                return jsonify({"success": False, "message": f"Excel read error: {e}"}), 400
    else:
        data = request.json or {}
        queries = data.get("queries", [])
        if isinstance(queries, str):
            queries = [q.strip() for q in queries.splitlines() if q.strip()]

    cid = get_request_client_id()
    is_paid = client_manager.is_client_paid(cid)
    max_batch = 50 if is_paid else 25
    queries = [q for q in queries if q][:max_batch]
    if not queries:
        return jsonify({"success": False, "message": "No valid queries provided."}), 400

    # Credit Check & Deduction (1 credit per item)
    ok, bal, msg = check_and_deduct_credits(len(queries), f"Bulk Lead Enrichment ({len(queries)} items)")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    results = engine.bulk_enrich(queries)
    storage_mgr.save_bulk_leads(results)

    return jsonify({
        "success": True,
        "total": len(results),
        "data": results,
        "credits_remaining": bal
    })

@app.route("/api/history", methods=["GET"])
def history():
    records = storage_mgr.get_history()
    return jsonify({"success": True, "history": records})

@app.route("/api/clear-history", methods=["POST"])
def clear_history():
    storage_mgr.clear_history()
    return jsonify({"success": True, "message": "History cleared successfully."})

@app.route("/api/download/xlsx", methods=["GET"])
def download_xlsx():
    storage_mgr.ensure_files()
    if os.path.exists(storage_mgr.xlsx_path):
        return send_file(storage_mgr.xlsx_path, as_attachment=True, download_name="TS_Hunter_Extracted_Leads.xlsx")
    return jsonify({"success": False, "message": "File not found"}), 404

@app.route("/api/download/csv", methods=["GET"])
def download_csv():
    storage_mgr.ensure_files()
    if os.path.exists(storage_mgr.csv_path):
        return send_file(storage_mgr.csv_path, as_attachment=True, download_name="TS_Hunter_Extracted_Leads.csv", mimetype="text/csv")
    return jsonify({"success": False, "message": "File not found"}), 404

# ── Google Maps & Local B2B Scraper (with Credit Protection) ──
@app.route("/api/gmaps/search", methods=["POST"])
def gmaps_search():
    data = request.json or {}
    query = data.get("query", "").strip()
    location = data.get("location", "").strip()
    limit = int(data.get("limit", 15))

    if not query:
        return jsonify({"success": False, "message": "Search query/category is required."}), 400

    # Preliminary Credit & Plan Check
    cid = get_request_client_id()
    if not cid:
        return jsonify({
            "success": False,
            "message": "Login required! Please sign in with Google to extract leads.",
            "login_required": True
        }), 401

    is_paid = client_manager.is_client_paid(cid)
    
    # FREE PLAN LIMIT: Maximum 25 leads per batch
    if not is_paid and limit > 25:
        limit = 25

    if cid not in ("admin", "superadmin"):
        cl = client_manager.get_client(cid)
        if not cl or cl.get("credits", 0) < 1:
            return jsonify({
                "success": False,
                "message": f"Insufficient credits! Required: at least 1 credit. Available: {cl.get('credits', 0) if cl else 0}. Please recharge.",
                "credits_error": True,
                "balance": cl.get("credits", 0) if cl else 0
            }), 402

    leads = local_scraper.search_local_businesses(query, location=location, limit=limit)

    # Deduct credits for the actual number of leads extracted (1 credit per lead)
    actual_count = len(leads)
    ok, bal, msg = check_and_deduct_credits(actual_count, f"G-Maps Leads Extracted: {query} in {location} ({actual_count} leads)")

    return jsonify({
        "success": True,
        "query": query,
        "location": location,
        "total": len(leads),
        "data": leads,
        "credits_remaining": bal
    })

# ── LinkedIn Sales Navigator Decision Maker Scraper (with Credit Protection) ──
@app.route("/api/linkedin/sales-navigator/search", methods=["POST"])
def linkedin_sales_nav_search():
    data = request.json or {}
    role = data.get("role", "CEO, Founder").strip()
    industry = data.get("industry", "").strip()
    location = data.get("location", "").strip()
    company = data.get("company", "").strip()
    keywords = data.get("keywords", "").strip()
    limit = int(data.get("limit", 25))

    # Preliminary Credit & Plan Check
    cid = get_request_client_id()
    if not cid:
        return jsonify({
            "success": False,
            "message": "Login required! Please sign in with Google to use LinkedIn Sales Navigator.",
            "login_required": True
        }), 401

    is_paid = client_manager.is_client_paid(cid)
    # Strictly locked for free users!
    if cid not in ("admin", "superadmin") and not is_paid:
        return jsonify({
            "success": False,
            "message": "LinkedIn Sales Navigator is a PRO feature. Upgrade to Premium to unlock.",
            "requires_pro": True
        }), 403

    if cid not in ("admin", "superadmin"):
        cl = client_manager.get_client(cid)
        if not cl or cl.get("credits", 0) < 1:
            return jsonify({
                "success": False,
                "message": f"Insufficient credits! Required: at least 1 credit. Available: {cl.get('credits', 0) if cl else 0}. Please recharge.",
                "credits_error": True,
                "balance": cl.get("credits", 0) if cl else 0
            }), 402

    leads = linkedin_navigator.search_decision_makers(
        role=role,
        industry=industry,
        location=location,
        company=company,
        keywords=keywords,
        limit=limit
    )

    actual_count = len(leads)
    ok, bal, msg = check_and_deduct_credits(actual_count, f"LinkedIn Sales Nav Leads: {role} in {industry} ({actual_count} leads)")

    # Save into SQLite database
    try:
        for l in leads:
            database.save_enriched_lead(
                client_id=cid,
                business_name=l.get("company", ""),
                category=l.get("industry", ""),
                location=l.get("location", ""),
                phone=l.get("phone", ""),
                email=l.get("email", ""),
                website=l.get("website", ""),
                rating=l.get("potential_score", 95),
                reviews=100,
                lead_data=l
            )
    except Exception as e:
        print(f"[DB Save Error] {e}", flush=True)

    return jsonify({
        "success": True,
        "role": role,
        "industry": industry,
        "location": location,
        "total": len(leads),
        "data": leads,
        "credits_remaining": bal
    })

# ── Zero Bounce Real-Time SMTP Email Ping (with Credit Protection) ──
@app.route("/api/verify-email-ping", methods=["POST"])
def verify_email_ping():
    # Feature Gate: Premium Only
    ok_feat, msg_feat = check_feature_access("email_verifier")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403

    data = request.json or {}
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    ok, bal, msg = check_and_deduct_credits(1, f"Zero-Bounce Email Ping: {email}")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    result = verify_email_smtp_ping(email)
    return jsonify({
        "success": True,
        "data": result,
        "credits_remaining": bal
    })

@app.route("/api/verify-bulk-emails", methods=["POST"])
def verify_bulk_emails_route():
    # Feature Gate: Premium Only
    ok_feat, msg_feat = check_feature_access("email_verifier")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403
    data = request.json or {}
    emails = data.get("emails", [])
    if not emails:
        return jsonify({"success": False, "message": "No emails provided.", "results": []}), 400

    ok, bal, msg = check_and_deduct_credits(len(emails), f"Bulk Email Verification ({len(emails)} emails)")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    results = bulk_verify_emails(emails)
    return jsonify({
        "success": True,
        "total": len(results),
        "results": results,
        "credits_remaining": bal
    })

# ── Outreach Hub: 10 Domain Mailboxes Management ──
@app.route("/api/outreach/accounts", methods=["GET", "POST"])
def outreach_accounts():
    if request.method == "GET":
        accounts = load_accounts()
        safe_accs = []
        for a in accounts:
            cp = dict(a)
            if cp.get("password"):
                cp["password"] = "••••••••"
            safe_accs.append(cp)
        return jsonify({"success": True, "accounts": safe_accs})

    data = request.json or {}
    new_accounts = data.get("accounts", [])
    if len(new_accounts) > 10:
        return jsonify({"success": False, "message": "Maximum 10 domain mail accounts allowed."}), 400

    existing = load_accounts()
    for acc in new_accounts:
        if acc.get("password") == "••••••••":
            for old in existing:
                if old.get("id") == acc.get("id"):
                    acc["password"] = old.get("password", "")
                    break

    save_accounts(new_accounts)
    return jsonify({"success": True, "message": "Domain mail accounts updated successfully."})

@app.route("/api/outreach/test", methods=["POST"])
def outreach_test():
    data = request.json or {}
    acc = data.get("account", {})
    if acc.get("password") == "••••••••":
        for old in load_accounts():
            if old.get("id") == acc.get("id"):
                acc["password"] = old.get("password", "")
                break
    success, msg = test_smtp_account(acc)
    return jsonify({"success": success, "message": msg})

@app.route("/api/outreach/send", methods=["POST"])
def outreach_send():
    # Feature Gate: Premium Only
    ok_feat, msg_feat = check_feature_access("outreach_mailer")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403

    data = request.json or {}
    to_email = data.get("to_email", "").strip()
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    account_id = data.get("account_id", "auto")
    lead_info = data.get("lead_info", {})

    if not to_email or not subject or not body:
        return jsonify({"success": False, "message": "Recipient, Subject, and Body are required."}), 400

    ok, bal, msg = check_and_deduct_credits(2, f"AI Cold Email Sent to {to_email}")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    track_opens = bool(data.get("track_opens", False))
    track_clicks = bool(data.get("track_clicks", False))
    host_url = request.host_url.rstrip("/")
    cid = get_request_client_id()

    success, send_msg = send_cold_email(
        to_email, 
        subject, 
        body, 
        account_id=account_id, 
        lead_info=lead_info,
        track_opens=track_opens,
        track_clicks=track_clicks,
        host_url=host_url,
        client_id=cid
    )
    return jsonify({"success": success, "message": send_msg, "credits_remaining": bal})

@app.route("/api/outreach/templates", methods=["GET"])
def outreach_templates():
    return jsonify({"success": True, "templates": AI_PITCH_TEMPLATES})

@app.route("/api/outreach/generate-all", methods=["POST"])
def outreach_generate_all():
    # Feature Gate: Premium Only
    ok_feat, msg_feat = check_feature_access("outreach_mailer")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403

    data = request.json or {}
    leads = data.get("leads", [])
    service_info = data.get("service_info", {})
    goal = data.get("goal", "software_b2b")
    if not leads:
        return jsonify({"success": False, "message": "No leads provided.", "leads": []}), 400

    # Deduct 2 credits per personalized lead email copy (2 Cr per AI Cold Email)
    ok, bal, msg = check_and_deduct_credits(len(leads) * 2, f"AI Cold Outreach Copy Generation ({len(leads)} leads)")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    personalized = generate_all_personalized_emails(leads, service_info=service_info, goal=goal)
    return jsonify({
        "success": True,
        "total": len(personalized),
        "leads": personalized,
        "credits_remaining": bal
    })

@app.route("/api/outreach/generate-single", methods=["POST"])
def outreach_generate_single():
    data = request.json or {}
    lead = data.get("lead", {})
    service_info = data.get("service_info", {})
    goal = data.get("goal", "software_b2b")
    if not lead:
        return jsonify({"success": False, "message": "No lead provided."}), 400

    copy = generate_personalized_copy(lead, service_info=service_info, goal=goal)
    return jsonify({"success": True, "copy": copy})

@app.route("/api/outreach/bulk-send", methods=["POST"])
def outreach_bulk_send():
    # Feature Gate: Premium Only
    ok_feat, msg_feat = check_feature_access("outreach_mailer")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403
    data = request.json or {}
    leads = data.get("leads", [])
    fallback_subject = data.get("subject", "").strip()
    fallback_body = data.get("body", "").strip()
    account_id = data.get("account_id", "auto")
    delay = int(data.get("delay_seconds") or data.get("delay", 2))
    track_opens = bool(data.get("track_opens", False))
    track_clicks = bool(data.get("track_clicks", False))
    host_url = request.host_url.rstrip("/")
    cid = get_request_client_id()

    if not leads:
        return jsonify({"success": False, "message": "Leads list is required."}), 400

    # Deduct 2 credits per recipient lead (2 Cr per AI Cold Email)
    ok, bal, msg = check_and_deduct_credits(len(leads) * 2, f"Bulk AI Cold Email Campaign ({len(leads)} leads)")
    if not ok:
        return jsonify({"success": False, "message": msg, "credits_error": True, "balance": bal}), 402

    ok_send, res = send_bulk_cold_emails(
        leads, 
        fallback_subject, 
        fallback_body, 
        account_id=account_id, 
        delay_seconds=delay,
        track_opens=track_opens,
        track_clicks=track_clicks,
        host_url=host_url,
        client_id=cid
    )
    if not ok_send:
        return jsonify({"success": False, "message": str(res)}), 400
    return jsonify({
        "success": True,
        "total": res.get("total", 0),
        "sent_count": res.get("delivered", 0),
        "failed_count": res.get("failed", 0),
        "details": res.get("details", []),
        "credits_remaining": bal
    })

@app.route("/api/outreach/logs", methods=["GET"])
def outreach_logs():
    logs = load_logs()
    return jsonify({"success": True, "logs": logs})

# ── Tech Stack Detector Route ──
@app.route("/api/detect-tech", methods=["POST"])
def detect_tech_route():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "message": "URL is required"}), 400
    if not url.startswith("http"):
        url = "https://" + url

    from hunter_engine import fetch_url
    p = fetch_url(url)
    techs = detect_technologies(p.get("html", ""))
    return jsonify({"success": True, "url": url, "tech_stack": techs})

# ── bKash & Nagad Payment Endpoints ──
@app.route("/api/payment/methods", methods=["GET"])
def payment_methods_route():
    return jsonify({
        "success": True,
        "packages": list(payment_manager.PACKAGES.values()),
        "methods": payment_manager.PAYMENT_METHODS
    })

@app.route("/api/payment/submit", methods=["POST"])
def payment_submit_route():
    data = request.json or {}
    cid = get_request_client_id()
    if not cid:
        return jsonify({"success": False, "message": "Please sign in before submitting payment verification."}), 401
    
    cl = client_manager.get_client(cid)
    if not cl:
        return jsonify({"success": False, "message": "Client account not found."}), 404
        
    gateway = data.get("gateway", "bkash").strip().lower()
    sender_number = data.get("sender_number", "").strip()
    trx_id = data.get("trx_id", "").strip().upper()
    package_id = data.get("package_id", "starter_500").strip()
    
    if not sender_number or len(sender_number) < 11:
        return jsonify({"success": False, "message": "Please enter a valid 11-digit bKash/Nagad sender phone number."}), 400
    if not trx_id or len(trx_id) < 6:
        return jsonify({"success": False, "message": "Please enter a valid Transaction ID (TrxID)."}), 400
        
    pkg = payment_manager.PACKAGES.get(package_id, payment_manager.PACKAGES["starter_500"])
    
    ok, msg, rec = payment_manager.submit_payment(
        client_id=cid,
        client_name=cl.get("name", "User"),
        client_email=cl.get("email", ""),
        gateway=gateway,
        sender_number=sender_number,
        trx_id=trx_id,
        package_id=package_id
    )
    
    if ok and rec and rec.get("status") == "approved":
        # Upgrade client to PREMIUM and credit balance immediately on live SMS match
        client_manager.activate_paid_status(cid, plan="premium", add_credits=pkg["credits"])

    is_approved = bool(ok and rec and rec.get("status") == "approved")
    return jsonify({
        "success": ok,
        "approved": is_approved,
        "status": rec.get("status") if rec else "failed",
        "message": msg,
        "payment": rec,
        "credits_added": pkg["credits"] if is_approved else 0,
        "is_paid": is_approved
    })

@app.route("/api/payment/history", methods=["GET"])
def payment_history_route():
    cid = get_request_client_id()
    payments = payment_manager.load_payments()
    if cid not in ("admin", "superadmin"):
        payments = [p for p in payments if p.get("client_id") == cid]
    return jsonify({"success": True, "payments": payments})

@app.route("/api/admin/payments", methods=["GET"])
def admin_payments_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    payments = payment_manager.load_payments()
    stats = payment_manager.get_payment_stats()
    return jsonify({"success": True, "payments": payments, "stats": stats})

@app.route("/api/admin/revenue-stats", methods=["GET"])
def admin_revenue_stats_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    stats = payment_manager.get_payment_stats()
    return jsonify({"success": True, "stats": stats})

@app.route("/api/admin/payment/approve", methods=["POST"])
def admin_payment_approve_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    pay_id = data.get("payment_id")
    payments = payment_manager.load_payments()
    for p in payments:
        if p.get("id") == pay_id:
            p["status"] = "approved"
            p["verified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payment_manager.save_payments(payments)
            # Add credits & upgrade
            client_manager.activate_paid_status(p["client_id"], plan="premium", add_credits=p.get("credits", 500))
            return jsonify({"success": True, "message": "Payment successfully approved and credits added to client account!"})
    return jsonify({"success": False, "message": "Payment not found."}), 404

@app.route("/api/admin/payment/reject", methods=["POST"])
def admin_payment_reject_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    pay_id = data.get("payment_id")
    reason = data.get("reason", "Invalid TrxID or payment not received")
    ok, p = payment_manager.reject_payment(pay_id, reason=reason)
    if ok:
        return jsonify({"success": True, "message": "Payment rejected."})
    return jsonify({"success": False, "message": "Payment not found."}), 404

@app.route("/api/admin/payment/delete", methods=["POST"])
def admin_payment_delete_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    pay_id = data.get("payment_id")
    ok = payment_manager.delete_payment(pay_id)
    if ok:
        return jsonify({"success": True, "message": "Payment record deleted."})
    return jsonify({"success": False, "message": "Payment not found."}), 404

@app.route("/api/admin/client/toggle-paid", methods=["POST"])
def admin_toggle_paid_route():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    client_id = data.get("client_id")
    ok, is_paid, msg = client_manager.toggle_client_paid_status(client_id)
    return jsonify({"success": ok, "is_paid": is_paid, "message": msg})

# ══════════════════════════════════════════════════════════════════
# UDDOKTAPAY AUTOMATED PAYMENT GATEWAY (BKASH, NAGAD, ROCKET)
# ══════════════════════════════════════════════════════════════════
@app.route("/api/payment/uddoktapay/initiate", methods=["POST"])
def payment_uddoktapay_initiate():
    cid = get_request_client_id()
    if not cid:
        return jsonify({"success": False, "message": "Please sign in with Google to initiate payment."}), 401
    cl = client_manager.get_client(cid)
    if not cl:
        return jsonify({"success": False, "message": "Client account not found."}), 404

    data = request.json or {}
    package_id = data.get("package_id", "starter_500")
    pkg = payment_manager.PACKAGES.get(package_id, payment_manager.PACKAGES["starter_500"])

    host_url = request.host_url.rstrip("/")
    redirect_url = f"{host_url}/?payment=success"
    cancel_url = f"{host_url}/?payment=cancelled"
    webhook_url = f"{host_url}/api/payment/uddoktapay/webhook"

    ok, payment_url = uddoktapay_gateway.create_uddoktapay_charge(
        client=cl,
        package=pkg,
        redirect_url=redirect_url,
        cancel_url=cancel_url,
        webhook_url=webhook_url
    )

    if ok:
        return jsonify({
            "success": True,
            "payment_url": payment_url,
            "amount": pkg["price_bdt"],
            "package_name": pkg["name"]
        })
    return jsonify({"success": False, "message": payment_url}), 400

@app.route("/api/payment/uddoktapay/verify", methods=["POST"])
def payment_uddoktapay_verify():
    """Direct verification of UddoktaPay invoice via v2 API."""
    data = request.json or {}
    invoice_id = data.get("invoice_id", "").strip()
    if not invoice_id:
        return jsonify({"success": False, "message": "invoice_id is required."}), 400

    ok, msg, payload = uddoktapay_gateway.verify_uddoktapay_invoice(invoice_id)
    if ok:
        cid = payload.get("client_id")
        pkg_id = payload.get("package_id")
        trx_id = payload.get("trx_id")
        pkg = payment_manager.PACKAGES.get(pkg_id, payment_manager.PACKAGES.get("starter_500"))
        credits_to_add = pkg.get("credits", 500) if pkg else 500

        # Check if already processed
        payments = payment_manager.load_payments()
        existing = next((p for p in payments if p.get("trx_id") == trx_id or p.get("invoice_id") == invoice_id), None)
        if existing and existing.get("status") == "approved":
            return jsonify({
                "success": True,
                "message": "Payment already verified and credited.",
                "credits_added": credits_to_add
            })

        if cid:
            client_manager.activate_paid_status(cid, plan="premium", add_credits=credits_to_add)
            cl = client_manager.get_client(cid)
            payment_manager.submit_payment(
                client_id=cid,
                client_name=cl.get("name", "UddoktaPay Client") if cl else "UddoktaPay Client",
                client_email=cl.get("email", "") if cl else "",
                gateway="uddoktapay",
                sender_number=payload.get("sender_number", "Automated Checkout"),
                trx_id=trx_id,
                package_id=pkg_id or "starter_500"
            )
            # Auto-approve
            payments = payment_manager.load_payments()
            for p in payments:
                if p.get("trx_id") == trx_id:
                    p["status"] = "approved"
                    p["invoice_id"] = invoice_id
                    p["verified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            payment_manager.save_payments(payments)

            return jsonify({
                "success": True,
                "message": "Payment verified successfully via UddoktaPay!",
                "credits_added": credits_to_add
            })
    return jsonify({"success": False, "message": msg}), 400

@app.route("/api/admin/settings/uddoktapay", methods=["GET", "POST"])
def admin_uddoktapay_settings():
    """Admin configuration for UddoktaPay API credentials."""
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if request.method == "POST":
        data = request.json or {}
        api_key = data.get("api_key", "").strip()
        env = data.get("env", "live").strip()
        uddoktapay_gateway.save_uddoktapay_config(api_key=api_key, env=env)
        return jsonify({"success": True, "message": "UddoktaPay settings updated successfully!"})

    cfg = uddoktapay_gateway.get_uddoktapay_config()
    raw_key = cfg["api_key"]
    masked_key = (raw_key[:4] + "..." + raw_key[-4:]) if len(raw_key) > 8 else ("***" if raw_key else "")
    host_url = request.host_url.rstrip("/")
    return jsonify({
        "success": True,
        "env": cfg["env"],
        "is_configured": cfg["is_configured"],
        "has_api_key": bool(raw_key),
        "masked_api_key": masked_key,
        "webhook_url": f"{host_url}/api/payment/uddoktapay/webhook"
    })

@app.route("/api/payment/uddoktapay/webhook", methods=["POST"])
def payment_uddoktapay_webhook():
    data = request.json or {}
    api_key_header = request.headers.get("RT-UDDOKTAPAY-API-KEY", "")
    ok, msg, payload = uddoktapay_gateway.verify_uddoktapay_webhook(data, api_key_header)

    if ok:
        cid = payload.get("client_id")
        pkg_id = payload.get("package_id")
        trx_id = payload.get("trx_id")
        pkg = payment_manager.PACKAGES.get(pkg_id, payment_manager.PACKAGES["starter_500"])

        if cid:
            client_manager.activate_paid_status(cid, plan="premium", add_credits=pkg["credits"])
            payment_manager.submit_payment(
                client_id=cid,
                client_name="UddoktaPay User",
                client_email="",
                gateway="uddoktapay",
                sender_number=payload.get("sender_number", "Automated"),
                trx_id=trx_id,
                package_id=pkg_id
            )
        return jsonify({"status": True, "message": "Processed successfully"}), 200

    return jsonify({"status": False, "message": msg}), 400

# ══════════════════════════════════════════════════════════════════
# EMAIL OPEN & CLICK TRACKING PIXEL (ZERO-SPAM ARCHITECTURE)
# ══════════════════════════════════════════════════════════════════
@app.route("/api/track/open/<tracking_id>.png", methods=["GET"])
def track_email_open(tracking_id):
    """Returns 1x1 transparent GIF and records email read event."""
    ip = request.remote_addr or ""
    ua = request.user_agent.string if request.user_agent else ""
    record_email_open(tracking_id, ip=ip, user_agent=ua)
    
    resp = Response(PIXEL_GIF, mimetype="image/gif")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.route("/api/track/click/<tracking_id>", methods=["GET"])
def track_email_click(tracking_id):
    """Records click event and redirects cleanly to target destination."""
    url = request.args.get("url") or "https://google.com"
    target = record_email_click(tracking_id, url)
    return redirect(target)

# ══════════════════════════════════════════════════════════════════
# INTEGRATIONS & WEBHOOK EXPORT (GOOGLE SHEETS / ZAPIER / MAKE)
# ══════════════════════════════════════════════════════════════════
@app.route("/api/leads/export/webhook", methods=["POST"])
def export_leads_webhook():
    cid = get_request_client_id()
    data = request.json or {}
    webhook_url = data.get("webhook_url", "").strip()
    leads = data.get("leads", [])

    if not webhook_url or not webhook_url.startswith("http"):
        return jsonify({"success": False, "message": "Please provide a valid Webhook URL (e.g. Zapier or Make)."}), 400
    if not leads:
        return jsonify({"success": False, "message": "No leads found to export."}), 400

    try:
        payload = json.dumps({
            "source": "Leadzio AI",
            "timestamp": datetime.now().isoformat(),
            "client_id": cid,
            "total_leads": len(leads),
            "leads": leads
        }).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "LeadPulse-AI/1.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            return jsonify({
                "success": True,
                "message": f"Successfully dispatched {len(leads)} leads to your Webhook / Google Sheets!"
            })
    except Exception as e:
        return jsonify({"success": False, "message": f"Webhook dispatch error: {str(e)}"}), 500



# ══════════════════════════════════════════════════════════════════
# ADVANCED SAAS EXTENSIONS: REFERRALS, WHITE-LABEL, HEALTH & DRIP
# ══════════════════════════════════════════════════════════════════

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_branding_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("branding", {})
    except Exception:
        return {}

def save_branding_config(branding_dict):
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["branding"] = branding_dict
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

@app.route("/api/branding", methods=["GET"])
def get_branding():
    b = load_branding_config()
    return jsonify({
        "success": True,
        "brand_name": b.get("brand_name", "Leadzio AI"),
        "logo_url": b.get("logo_url", ""),
        "support_contact": b.get("support_contact", "01928668568"),
        "custom_footer": b.get("custom_footer", "Leadzio AI Intelligence Pro &bull; Agency Operating System")
    })

@app.route("/api/admin/settings/branding", methods=["GET", "POST"])
def admin_branding_settings():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if request.method == "POST":
        data = request.json or {}
        branding = {
            "brand_name": data.get("brand_name", "Leadzio AI").strip(),
            "logo_url": data.get("logo_url", "").strip(),
            "support_contact": data.get("support_contact", "").strip(),
            "custom_footer": data.get("custom_footer", "").strip()
        }
        save_branding_config(branding)
        return jsonify({"success": True, "message": "Agency White-Label branding updated successfully!"})

    b = load_branding_config()
    return jsonify({
        "success": True,
        "brand_name": b.get("brand_name", "Leadzio AI"),
        "logo_url": b.get("logo_url", ""),
        "support_contact": b.get("support_contact", "01928668568"),
        "custom_footer": b.get("custom_footer", "Leadzio AI Intelligence Pro &bull; Agency Operating System")
    })

@app.route("/api/client/referral-stats", methods=["GET"])
def client_referral_stats():
    cid = get_request_client_id()
    if not cid:
        return jsonify({"success": False, "message": "Login required."}), 401
    stats = client_manager.get_referral_stats(cid)
    host_url = request.host_url.rstrip("/")
    stats["referral_link"] = f"{host_url}/?ref={stats.get('referral_code', '')}"
    return jsonify({"success": True, "stats": stats})

@app.route("/api/tools/check-domain-health", methods=["POST"])
def tools_check_domain_health():
    # Feature Gate: Premium Only
    ok_feat, msg_feat = check_feature_access("email_verifier")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403
    data = request.json or {}
    domain = data.get("domain", "").strip()
    if not domain:
        return jsonify({"success": False, "message": "Domain is required."}), 400
    res = check_domain_deliverability(domain)
    return jsonify({"success": True, "result": res})

@app.route("/api/outreach/sequence", methods=["POST"])
def outreach_sequence():
    ok_feat, msg_feat = check_feature_access("outreach_mailer")
    if not ok_feat:
        return jsonify({"success": False, "feature_locked": True, "message": msg_feat}), 403
    data = request.json or {}
    lead = data.get("lead", {})
    service_info = data.get("service_info", {})
    goal = data.get("goal", "meta_ads")
    if not lead:
        return jsonify({"success": False, "message": "Lead details are required."}), 400
    seq = generate_multi_step_sequence(lead, service_info=service_info, goal=goal)
    return jsonify({"success": True, "sequence": seq})


# ══════════════════════════════════════════════════════════════════
# CLIENTHUNT PAYSYNC — SELF-HOSTED MOBILE SMS PAYMENT AUTOMATION
# ══════════════════════════════════════════════════════════════════
import sms_payment_sync

@app.route("/api/sms-sync/receive", methods=["POST"])
def sms_sync_receive():
    """Receives live incoming bKash/Nagad SMS from the owner's Android companion app."""
    data = request.json or request.form or {}
    api_key = request.headers.get("X-PaySync-Key") or data.get("api_key") or data.get("sync_key") or ""
    if not sms_payment_sync.verify_sync_key(api_key):
        return jsonify({"success": False, "message": "Invalid PaySync API Key."}), 401

    sender = str(data.get("sender") or data.get("from") or "")
    message = str(data.get("message") or data.get("body") or data.get("text") or "")
    device = str(data.get("device") or data.get("device_name") or "Android Phone")

    ok, msg, rec, auto_approved = sms_payment_sync.record_incoming_sms(
        sender_title=sender,
        message_text=message,
        device_name=device
    )
    return jsonify({
        "success": ok,
        "message": msg,
        "sms": rec,
        "auto_approved_order": auto_approved
    }), 200

@app.route("/api/admin/paysync/status", methods=["GET"])
def admin_paysync_status():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    cfg = sms_payment_sync.get_paysync_config()
    inbox = sms_payment_sync.load_sms_inbox()[:30]
    host_url = request.host_url.rstrip("/")
    return jsonify({
        "success": True,
        "sync_key": cfg.get("sync_key"),
        "enabled": cfg.get("enabled", True),
        "last_sync_at": cfg.get("last_sync_at"),
        "device_name": cfg.get("device_name", "Not Connected Yet"),
        "webhook_url": f"{host_url}/api/sms-sync/receive",
        "sms_inbox": inbox
    })

@app.route("/api/admin/paysync/config", methods=["POST"])
def admin_paysync_config():
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    cfg = sms_payment_sync.save_paysync_config(
        sync_key=data.get("sync_key"),
        enabled=data.get("enabled", True),
        regenerate=bool(data.get("regenerate", False))
    )
    return jsonify({"success": True, "message": "PaySync Mobile Key updated!", "config": cfg})

@app.route("/api/admin/paysync/simulate", methods=["POST"])
def admin_paysync_simulate():
    """Admin-only test simulator to verify live bKash/Nagad SMS parsing & auto-matching."""
    cid = get_request_client_id()
    if cid not in ("admin", "superadmin", ""):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    data = request.json or {}
    gateway = (data.get("gateway") or "bkash").lower()
    amount = data.get("amount", 500)
    sender = (data.get("sender_number") or "01711223344").strip()
    trx_id = (data.get("trx_id") or f"TST{uuid.uuid4().hex[:7].upper()}").strip().upper()
    if gateway == "nagad":
        raw = f"Money Received. Amount: Tk {amount}.00 Sender: {sender} Ref: Leadzio TxnID: {trx_id} Balance: Tk 9500.00"
        title = "NAGAD"
    else:
        raw = f"You have received Tk {amount}.00 from {sender}. Fee Tk 0.00. Balance Tk 9500.00. TrxID {trx_id}"
        title = "bKash"
    ok, msg, rec, auto_app = sms_payment_sync.record_incoming_sms(title, raw, device_name="Admin Test Simulator")
    return jsonify({"success": ok, "message": msg, "sms": rec, "auto_approved_order": auto_app})

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "Leadzio AI", "timestamp": datetime.now().isoformat()}), 200

@app.route("/favicon.ico")
def favicon():
    return Response(b"", mimetype="image/x-icon", status=204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    print(f"[+] Leadzio AI running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
