import os
import json
import uuid
import secrets
from datetime import datetime

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL"):
    import shutil as _shutil
    CLIENTS_FILE = "/tmp/clients.json"
    _seed_clients = os.path.join(_BASE_DIR, "clients.json")
    if not os.path.exists(CLIENTS_FILE) and os.path.exists(_seed_clients):
        try:
            _shutil.copy2(_seed_clients, CLIENTS_FILE)
        except Exception:
            pass
else:
    CLIENTS_FILE = os.path.join(_BASE_DIR, "clients.json")

def generate_api_key():
    return f"tsh_live_{secrets.token_hex(16)}"

def get_default_clients_data():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "admin": {
            "name": "Super Admin",
            "email": "admin@tshunter.io",
            "role": "admin",
            "unlimited": True
        },
        "clients": [
            {
                "id": "cli_acme_01",
                "name": "Sarah Jenkins",
                "company": "Acme Growth Media",
                "email": "sarah@acmegrowth.com",
                "api_key": f"tsh_live_{secrets.token_hex(12)}",
                "credits": 250,
                "total_spent": 140,
                "status": "active",
                "created_at": now_str,
                "notes": "VIP B2B Outreach Client"
            },
            {
                "id": "cli_global_02",
                "name": "David Miller",
                "company": "Global Nexus Tech",
                "email": "dmiller@globalnexus.io",
                "api_key": f"tsh_live_{secrets.token_hex(12)}",
                "credits": 85,
                "total_spent": 65,
                "status": "active",
                "created_at": now_str,
                "notes": "Email Scraping Tier"
            },
            {
                "id": "cli_apex_03",
                "name": "Tariq Rahman",
                "company": "Apex Sales Studio",
                "email": "tariq@apexsales.net",
                "api_key": f"tsh_live_{secrets.token_hex(12)}",
                "credits": 15,
                "total_spent": 185,
                "status": "active",
                "created_at": now_str,
                "notes": "Low balance account"
            }
        ],
        "transactions": [
            {
                "id": str(uuid.uuid4())[:8],
                "client_id": "cli_acme_01",
                "client_name": "Acme Growth Media",
                "type": "credit_add",
                "amount": 250,
                "balance_after": 250,
                "reason": "Initial Admin Credit Allocation",
                "timestamp": now_str
            },
            {
                "id": str(uuid.uuid4())[:8],
                "client_id": "cli_global_02",
                "client_name": "Global Nexus Tech",
                "type": "credit_add",
                "amount": 100,
                "balance_after": 100,
                "reason": "Monthly Recharge by Admin",
                "timestamp": now_str
            },
            {
                "id": str(uuid.uuid4())[:8],
                "client_id": "cli_global_02",
                "client_name": "Global Nexus Tech",
                "type": "credit_deduct",
                "amount": 15,
                "balance_after": 85,
                "reason": "Google Maps Scraping (15 Leads)",
                "timestamp": now_str
            }
        ]
    }

def load_clients_data():
    if not os.path.exists(CLIENTS_FILE):
        data = get_default_clients_data()
        save_clients_data(data)
        return data
    try:
        with open(CLIENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Error loading clients.json: {e}, falling back to defaults")
        return get_default_clients_data()

def save_clients_data(data):
    temp_file = CLIENTS_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if os.path.exists(CLIENTS_FILE):
        try:
            os.remove(CLIENTS_FILE)
        except Exception:
            pass
    os.rename(temp_file, CLIENTS_FILE)

def get_all_clients():
    data = load_clients_data()
    return data.get("clients", [])

def get_client(client_id):
    if client_id in ("admin", "superadmin"):
        return {
            "id": "admin",
            "name": "Super Admin",
            "company": "System Administrator",
            "email": "admin@tshunter.io",
            "credits": 999999,
            "unlimited": True,
            "status": "active"
        }
    data = load_clients_data()
    for c in data.get("clients", []):
        if c.get("id") == client_id:
            return c
    return None

def get_client_by_api_key(api_key):
    if not api_key:
        return None
    data = load_clients_data()
    for c in data.get("clients", []):
        if c.get("api_key") == api_key:
            return c
    return None

def create_client(name, email, company="", initial_credits=100, notes=""):
    data = load_clients_data()
    client_id = f"cli_{uuid.uuid4().hex[:8]}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    new_client = {
        "id": client_id,
        "name": name.strip() or "New Client",
        "company": company.strip() or name.strip(),
        "email": email.strip(),
        "api_key": generate_api_key(),
        "credits": max(0, int(initial_credits)),
        "total_spent": 0,
        "status": "active",
        "created_at": now_str,
        "notes": notes.strip()
    }
    
    data.setdefault("clients", []).append(new_client)
    
    if initial_credits > 0:
        data.setdefault("transactions", []).insert(0, {
            "id": str(uuid.uuid4())[:8],
            "client_id": client_id,
            "client_name": new_client["company"],
            "type": "credit_add",
            "amount": int(initial_credits),
            "balance_after": int(initial_credits),
            "reason": "Welcome Initial Credit Balance",
            "timestamp": now_str
        })
        
    save_clients_data(data)
    return new_client

def update_client_credits(client_id, amount, action="add", note="Admin adjustment", is_paid=None, plan=None):
    data = load_clients_data()
    clients = data.get("clients", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    amount = int(amount)
    
    for c in clients:
        if c.get("id") == client_id:
            old_credits = c.get("credits", 0)
            if action == "add":
                new_credits = old_credits + abs(amount)
                tx_type = "credit_add"
            elif action == "deduct":
                new_credits = max(0, old_credits - abs(amount))
                tx_type = "credit_deduct"
                c["total_spent"] = c.get("total_spent", 0) + (old_credits - new_credits)
            elif action == "set":
                new_credits = max(0, amount)
                tx_type = "credit_set"
            else:
                return False, old_credits, "Invalid action specified."

            c["credits"] = new_credits
            if is_paid is not None:
                c["is_paid"] = bool(is_paid)
            if plan:
                c["plan"] = plan

            data.setdefault("transactions", []).insert(0, {
                "id": str(uuid.uuid4())[:8],
                "client_id": client_id,
                "client_name": c.get("company") or c.get("name"),
                "type": tx_type,
                "amount": amount,
                "balance_after": new_credits,
                "reason": note.strip() or "Admin Balance Adjustment",
                "timestamp": now_str
            })
            
            save_clients_data(data)
            return True, new_credits, f"Credits updated to {new_credits} successfully."
            
    return False, 0, f"Client with ID '{client_id}' not found."

def toggle_client_paid_status(client_id):
    data = load_clients_data()
    clients = data.get("clients", [])
    for c in clients:
        if c.get("id") == client_id:
            current = c.get("is_paid", False)
            c["is_paid"] = not current
            c["plan"] = "premium" if c["is_paid"] else "free_trial"
            save_clients_data(data)
            status_text = "Premium" if c["is_paid"] else "Free Trial"
            return True, c["is_paid"], f"Client status changed to {status_text}."
    return False, False, f"Client '{client_id}' not found."

def deduct_credits(client_id, amount, reason="Service Usage"):
    """
    Deducts credits when a client performs an action.
    Returns (success, current_balance, message).
    """
    if not client_id or client_id in ("admin", "superadmin", "all"):
        return True, 999999, "Admin mode (unlimited credits)"
        
    data = load_clients_data()
    clients = data.get("clients", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    amount = max(1, int(amount))
    
    for c in clients:
        if c.get("id") == client_id:
            if c.get("status") != "active":
                return False, c.get("credits", 0), "Client account is suspended."
                
            current = c.get("credits", 0)
            if current < amount:
                return False, current, f"Insufficient credits! Required: {amount}, Available: {current}. Contact Admin to recharge."
                
            new_balance = current - amount
            c["credits"] = new_balance
            c["total_spent"] = c.get("total_spent", 0) + amount
            
            data.setdefault("transactions", []).insert(0, {
                "id": str(uuid.uuid4())[:8],
                "client_id": client_id,
                "client_name": c.get("company") or c.get("name"),
                "type": "credit_deduct",
                "amount": amount,
                "balance_after": new_balance,
                "reason": reason,
                "timestamp": now_str
            })
            
            save_clients_data(data)
            return True, new_balance, f"Deducted {amount} credits. Remaining: {new_balance}"
            
    return False, 0, "Client account not found."

def delete_client(client_id):
    data = load_clients_data()
    clients = data.get("clients", [])
    filtered = [c for c in clients if c.get("id") != client_id]
    if len(filtered) == len(clients):
        return False, "Client not found"
    data["clients"] = filtered
    save_clients_data(data)
    return True, "Client deleted successfully"

def get_credit_transactions(client_id=None, limit=50):
    data = load_clients_data()
    txs = data.get("transactions", [])
    if client_id and client_id not in ("admin", "superadmin"):
        txs = [t for t in txs if t.get("client_id") == client_id]
    return txs[:limit]

def get_overview_stats():
    clients = get_all_clients()
    total_clients = len(clients)
    active_clients = len([c for c in clients if c.get("status") == "active"])
    total_credits = sum(c.get("credits", 0) for c in clients)
    total_spent = sum(c.get("total_spent", 0) for c in clients)
    return {
        "total_clients": total_clients,
        "active_clients": active_clients,
        "total_credits_in_circulation": total_credits,
        "total_credits_consumed": total_spent
    }

def get_client_by_email(email):
    if not email:
        return None
    data = load_clients_data()
    email_clean = email.strip().lower()
    for c in data.get("clients", []):
        if c.get("email", "").strip().lower() == email_clean:
            return c
    return None

def verify_admin_passcode(passcode):
    data = load_clients_data()
    admin_info = data.get("admin", {})
    actual_code = admin_info.get("passcode", "admin123")
    return passcode.strip() == actual_code

def get_or_create_google_client(email, name="", picture="", device_id="", ip_address="", google_uid="", email_verified=True, ref_code=""):
    data = load_clients_data()
    email_clean = email.strip().lower()
    
    # 1. Check if email belongs to the Super Admin
    admin_info = data.get("admin", {})
    if admin_info.get("email", "").strip().lower() == email_clean:
        return {
            "id": "admin",
            "name": admin_info.get("name", "Super Admin"),
            "email": email_clean,
            "role": "admin",
            "unlimited": True,
            "is_admin": True,
            "avatar": picture or ""
        }, False, True, False  # client, is_new, is_admin, abuse_detected

    clients = data.setdefault("clients", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Check if client already exists by email
    for c in clients:
        if c.get("email", "").strip().lower() == email_clean:
            if picture and not c.get("avatar"):
                c["avatar"] = picture
            if device_id and not c.get("device_id"):
                c["device_id"] = device_id
            save_clients_data(data)
            return c, False, False, False

    # 3. ANTI-ABUSE CHECK: Has this device or network already claimed the free 250 trial bonus?
    trial_claims = data.setdefault("free_trial_claims", [])
    
    device_claimed = any(c.get("device_id") == device_id for c in trial_claims if device_id)
    # Device/IP trial blocking disabled per owner request — every new user gets live admin-configured free trial credits
    is_trial_abuser = False
    try:
        import payment_manager as _pm
        _st = _pm._load_site_settings()
    except Exception:
        _st = {}
    initial_credits = max(0, int(_st.get("free_trial_credits", 250)))
    ref_inviter_bonus = max(0, int(_st.get("referral_inviter_bonus", 100)))
    ref_friend_bonus = max(0, int(_st.get("referral_friend_bonus", 50)))

    # 4. Check Referral Partner Code
    referrer = None
    if ref_code:
        clean_ref = ref_code.strip().upper()
        referrer = next((c for c in clients if c.get("referral_code", "").upper() == clean_ref or f"LP-{c.get('id', '')[-6:].upper()}" == clean_ref), None)

    # Register new client
    client_id = f"cli_{uuid.uuid4().hex[:8]}"
    referral_code = f"LP-{client_id[-6:].upper()}"
    company_name = f"{name}'s Team" if name else "Personal Workspace"
    new_client = {
        "id": client_id,
        "name": name.strip() or "Google User",
        "company": company_name,
        "email": email_clean,
        "avatar": picture or "",
        "api_key": generate_api_key(),
        "credits": initial_credits,
        "is_paid": False,
        "plan": "free_trial",
        "total_spent": 0,
        "status": "active",
        "auth_provider": "google",
        "device_id": device_id,
        "ip_address": ip_address,
        "google_uid": google_uid,
        "email_verified": email_verified,
        "referral_code": referral_code,
        "referred_by": referrer["id"] if referrer else None,
        "created_at": now_str,
        "notes": f"Google Sign-In (Free Trial {initial_credits} Credits awarded)"
    }
    clients.append(new_client)

    if not is_trial_abuser:
        # Referral Welcome Bonus (admin-configured)
        if referrer:
            new_client["credits"] += ref_friend_bonus
            # Reward Referrer
            referrer["credits"] = int(referrer.get("credits", 0)) + ref_inviter_bonus
            data.setdefault("transactions", []).insert(0, {
                "id": str(uuid.uuid4())[:8],
                "client_id": referrer["id"],
                "client_name": referrer.get("company", referrer.get("name")),
                "type": "credit_add",
                "amount": ref_inviter_bonus,
                "balance_after": referrer["credits"],
                "reason": f"🎁 Referral Bonus: {new_client['name']} signed up with your invite link!",
                "timestamp": now_str
            })

        # Record free trial claim
        trial_claims.append({
            "client_id": client_id,
            "email": email_clean,
            "device_id": device_id,
            "ip_address": ip_address,
            "google_uid": google_uid,
            "claimed_at": now_str
        })
        # Record welcome bonus in credit transaction ledger
        data.setdefault("transactions", []).insert(0, {
            "id": str(uuid.uuid4())[:8],
            "client_id": client_id,
            "client_name": new_client["company"],
            "type": "credit_add",
            "amount": initial_credits,
            "balance_after": new_client["credits"],
            "reason": f"🎁 Welcome Bonus: {initial_credits} Free Credits",
            "timestamp": now_str
        })
    else:
        # Record zero allocation note
        data.setdefault("transactions", []).insert(0, {
            "id": str(uuid.uuid4())[:8],
            "client_id": client_id,
            "client_name": new_client["company"],
            "type": "credit_info",
            "amount": 0,
            "balance_after": 0,
            "reason": "⚠️ Free Trial Duplicate Blocked (Device/IP already claimed trial)",
            "timestamp": now_str
        })

    save_clients_data(data)
    return new_client, True, False, is_trial_abuser

def get_client_usage_summary(client_id):
    """
    Returns comprehensive analytics, credit consumption breakdown, and extracted data history for a client.
    """
    client = get_client(client_id)
    if not client:
        return {
            "success": False,
            "message": "Client not found"
        }

    data = load_clients_data()
    all_txs = data.get("transactions", [])
    client_txs = [t for t in all_txs if t.get("client_id") == client_id]

    total_added = sum(t.get("amount", 0) for t in client_txs if t.get("type") == "credit_add")
    total_spent = sum(t.get("amount", 0) for t in client_txs if t.get("type") == "credit_deduct")
    current_credits = client.get("credits", 0)

    # Detailed service breakdown analysis
    breakdown = {
        "gmaps": {"name": "Google Maps Leads", "count": 0, "credits": 0, "icon": "fa-map-location-dot", "color": "text-emerald-400"},
        "email_verifier": {"name": "Email Verifications", "count": 0, "credits": 0, "icon": "fa-shield-halved", "color": "text-purple-400"},
        "outreach": {"name": "AI Cold Outreach", "count": 0, "credits": 0, "icon": "fa-paper-plane", "color": "text-cyan-400"},
        "lead_finder": {"name": "Lead Searches (Single/Bulk)", "count": 0, "credits": 0, "icon": "fa-magnifying-glass", "color": "text-orange-400"}
    }

    for t in client_txs:
        if t.get("type") == "credit_deduct":
            reason = (t.get("reason") or "").lower()
            amt = t.get("amount", 1)
            if "map" in reason or "gmaps" in reason:
                breakdown["gmaps"]["credits"] += amt
                breakdown["gmaps"]["count"] += amt
            elif "verif" in reason or "bounce" in reason or "smtp" in reason or "email" in reason and "outreach" not in reason:
                breakdown["email_verifier"]["credits"] += amt
                breakdown["email_verifier"]["count"] += amt
            elif "outreach" in reason or "pitch" in reason or "send" in reason:
                breakdown["outreach"]["credits"] += amt
                breakdown["outreach"]["count"] += amt
            else:
                breakdown["lead_finder"]["credits"] += amt
                breakdown["lead_finder"]["count"] += amt

    # Fetch extracted leads data from storage
    try:
        from storage import HunterStorageManager
        sm = HunterStorageManager()
        leads = sm.get_history()[:20]
    except Exception:
        leads = []

    usage_percent = 0
    if (current_credits + total_spent) > 0:
        usage_percent = round((total_spent / (current_credits + total_spent)) * 100, 1)

    return {
        "success": True,
        "client": {
            "id": client.get("id"),
            "name": client.get("name"),
            "company": client.get("company"),
            "email": client.get("email"),
            "avatar": client.get("avatar"),
            "api_key": client.get("api_key"),
            "credits": current_credits,
            "total_spent": total_spent,
            "total_added": total_added,
            "usage_percent": usage_percent,
            "status": client.get("status", "active"),
            "is_paid": client.get("is_paid", False),
            "plan": client.get("plan", "free_trial"),
            "auth_provider": client.get("auth_provider", "google"),
            "created_at": client.get("created_at")
        },
        "breakdown": breakdown,
        "recent_transactions": client_txs[:20],
        "extracted_leads": leads
    }

def is_client_paid(client_id):
    if not client_id or client_id in ("admin", "superadmin"):
        return True
    data = load_clients_data()
    for c in data.get("clients", []):
        if c.get("id") == client_id:
            return bool(c.get("is_paid", False) or c.get("plan") in ("premium", "pro", "agency"))
    return False

def activate_paid_status(client_id, plan="premium", add_credits=0):
    data = load_clients_data()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for c in data.get("clients", []):
        if c.get("id") == client_id:
            c["is_paid"] = True
            c["plan"] = plan
            if add_credits > 0:
                c["credits"] = int(c.get("credits", 0)) + int(add_credits)
                # Referral Commission (20% bonus credits to the referrer)
                ref_id = c.get("referred_by")
                if ref_id:
                    ref_client = next((rc for rc in data.get("clients", []) if rc.get("id") == ref_id), None)
                    if ref_client:
                        ref_bonus = max(10, int(add_credits * 0.20))
                        ref_client["credits"] = int(ref_client.get("credits", 0)) + ref_bonus
                        data.setdefault("transactions", []).insert(0, {
                            "id": str(uuid.uuid4())[:8],
                            "client_id": ref_client["id"],
                            "client_name": ref_client.get("company", ref_client.get("name")),
                            "type": "credit_add",
                            "amount": ref_bonus,
                            "balance_after": ref_client["credits"],
                            "reason": f"💰 Referral Commission: 20% bonus ({ref_bonus} cr) from {c.get('name')}'s recharge!",
                            "timestamp": now_str
                        })
                data.setdefault("transactions", []).insert(0, {
                    "id": str(uuid.uuid4())[:8],
                    "client_id": client_id,
                    "client_name": c.get("company", c.get("name")),
                    "type": "credit_add",
                    "amount": int(add_credits),
                    "balance_after": c["credits"],
                    "reason": f"bKash/Nagad Payment Recharge ({plan.upper()})",
                    "timestamp": now_str
                })
            save_clients_data(data)
            return True, c
    return False, None


def get_referral_stats(client_id):
    """Returns referral code, link, invited users count, and earned bonuses."""
    data = load_clients_data()
    clients = data.get("clients", [])
    cl = next((c for c in clients if c.get("id") == client_id), None)
    if not cl:
        return {"success": False, "message": "Client not found"}

    ref_code = cl.get("referral_code") or f"LP-{cl['id'][-6:].upper()}"
    if not cl.get("referral_code"):
        cl["referral_code"] = ref_code
        save_clients_data(data)

    referred = [
        {
            "id": c.get("id"),
            "name": c.get("name", "User"),
            "created_at": c.get("created_at"),
            "is_paid": bool(c.get("is_paid"))
        }
        for c in clients if c.get("referred_by") == client_id
    ]

    # Calculate bonuses from transactions
    all_txs = data.get("transactions", [])
    bonus_earned = sum(
        t.get("amount", 0) for t in all_txs
        if t.get("client_id") == client_id and ("Referral" in t.get("reason", "") or "referral" in t.get("reason", ""))
    )

    return {
        "success": True,
        "referral_code": ref_code,
        "total_referred": len(referred),
        "bonus_credits_earned": bonus_earned,
        "referred_users": referred
    }
