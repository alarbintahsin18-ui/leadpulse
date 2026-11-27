import os
import json
import uuid
import time
import urllib.request
from datetime import datetime

PAYMENTS_FILE = "/tmp/clienthunt_data/payments.json" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "payments.json")
_BUNDLED_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
_CONFIG_FILE = "/tmp/config.json" if os.environ.get("VERCEL") else _BUNDLED_CONFIG_FILE

# Optional permanent cloud persistence for Vercel serverless (Firebase Realtime Database REST URL)
# e.g. FIREBASE_DB_URL=https://leadzio-default-rtdb.firebaseio.com
_CLOUD_CACHE = {"data": None, "ts": 0.0}

def get_firebase_db_url():
    return (os.environ.get("FIREBASE_DB_URL") or "").strip().rstrip("/")

def has_cloud_db():
    return bool(get_firebase_db_url())

def _read_local_config():
    for path in ([_CONFIG_FILE, _BUNDLED_CONFIG_FILE] if _CONFIG_FILE != _BUNDLED_CONFIG_FILE else [_CONFIG_FILE]):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    return {}

def _load_site_settings(force_refresh=False):
    db_url = get_firebase_db_url()
    if db_url:
        now = time.time()
        if not force_refresh and _CLOUD_CACHE["data"] is not None and (now - _CLOUD_CACHE["ts"] < 5.0):
            return dict(_CLOUD_CACHE["data"])
        try:
            req = urllib.request.Request(f"{db_url}/leadzio_site_settings.json", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw else None
                if isinstance(parsed, dict):
                    _CLOUD_CACHE["data"] = parsed
                    _CLOUD_CACHE["ts"] = now
                    return dict(parsed)
        except Exception:
            pass
    return _read_local_config().get("site_settings", {})

def _save_site_settings(site_settings_dict):
    # 1. Always write to local / /tmp config.json
    cfg = _read_local_config()
    cfg["site_settings"] = site_settings_dict
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

    # 2. If Firebase Realtime Database URL is configured, sync permanently to cloud
    db_url = get_firebase_db_url()
    if db_url:
        try:
            payload = json.dumps(site_settings_dict).encode("utf-8")
            req = urllib.request.Request(
                f"{db_url}/leadzio_site_settings.json",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    _CLOUD_CACHE["data"] = dict(site_settings_dict)
                    _CLOUD_CACHE["ts"] = time.time()
                    return True
        except Exception as e:
            print("[!] Firebase RTDB save error:", e)
            return False
    return True

def get_live_packages():
    """Returns packages merged with live Admin Panel overrides from config.json."""
    settings = _load_site_settings()
    overrides = settings.get("packages", {})
    merged = {}
    for pid, base in PACKAGES.items():
        p = dict(base)
        ov = overrides.get(pid, {})
        if ov.get("name"):
            p["name"] = str(ov["name"]).strip()
        if ov.get("credits") is not None:
            p["credits"] = int(ov["credits"])
        if ov.get("price_bdt") is not None:
            p["price_bdt"] = int(ov["price_bdt"])
        if ov.get("price_usd") is not None:
            p["price_usd"] = int(ov["price_usd"])
        merged[pid] = p
    return merged

def get_live_offer():
    """Returns live Promotional / First-Time Offer configuration from config.json."""
    settings = _load_site_settings()
    raw = settings.get("promo_offer", {}) if isinstance(settings.get("promo_offer"), dict) else {}
    enabled = bool(raw.get("enabled", False))
    expires_at = str(raw.get("expires_at", "")).strip()
    expired = False
    if enabled and expires_at:
        try:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00").split("+")[0])
            if datetime.now() > exp_dt:
                expired = True
        except Exception:
            pass
    return {
        "enabled": enabled,
        "is_active": bool(enabled and not expired),
        "expired": expired,
        "title": str(raw.get("title", "First-Time Launch Offer")).strip() or "Special Offer",
        "target_pkg": str(raw.get("target_pkg", "starter_500")).strip() or "starter_500",
        "discount_type": str(raw.get("discount_type", "custom_price")).strip() or "custom_price",
        "discount_value": max(0, int(raw.get("discount_value", 250) or 0)),
        "first_time_only": bool(raw.get("first_time_only", True)),
        "promo_code": str(raw.get("promo_code", "")).strip().upper(),
        "expires_at": expires_at
    }

def calculate_package_price(package_id, is_first_time_buyer=True, promo_code=""):
    """Computes final BDT price for a package considering any active Admin promotional offer."""
    live_pkgs = get_live_packages()
    pkg = live_pkgs.get(package_id) or live_pkgs["starter_500"]
    orig_price = max(1, int(pkg.get("price_bdt", 500)))
    offer = get_live_offer()

    result = {
        "package_id": pkg["id"],
        "original_price": orig_price,
        "final_price": orig_price,
        "discount_amount": 0,
        "discount_pct": 0,
        "offer_applied": False,
        "offer_title": "",
        "promo_code_used": ""
    }

    if not offer.get("is_active"):
        return result

    target = offer.get("target_pkg", "all")
    if target != "all" and target != pkg["id"]:
        return result

    if offer.get("first_time_only") and not is_first_time_buyer:
        return result

    req_code = offer.get("promo_code", "")
    entered_code = (promo_code or "").strip().upper()
    if req_code and entered_code != req_code:
        return result

    dtype = offer.get("discount_type", "custom_price")
    dval = offer.get("discount_value", 0)
    if dtype == "custom_price":
        final_price = max(1, min(orig_price, dval)) if dval > 0 else orig_price
    elif dtype == "percent":
        pct = max(0, min(95, dval))
        final_price = max(1, int(round(orig_price * (100 - pct) / 100.0)))
    elif dtype == "fixed":
        final_price = max(1, orig_price - dval)
    else:
        final_price = orig_price

    if final_price < orig_price:
        disc_amt = orig_price - final_price
        disc_pct = int(round((disc_amt / orig_price) * 100))
        result.update({
            "final_price": final_price,
            "discount_amount": disc_amt,
            "discount_pct": disc_pct,
            "offer_applied": True,
            "offer_title": offer.get("title", "Special Offer"),
            "promo_code_used": req_code if req_code else ""
        })
    return result

def get_live_payment_methods():
    """Returns payment methods merged with live Admin Panel numbers."""
    settings = _load_site_settings()
    methods = {k: dict(v) for k, v in PAYMENT_METHODS.items()}
    if settings.get("bkash_number"):
        methods["bkash"]["number"] = str(settings["bkash_number"]).strip()
    if settings.get("nagad_number"):
        methods["nagad"]["number"] = str(settings["nagad_number"]).strip()
    methods["bkash"]["enabled"] = bool(settings.get("bkash_enabled", True))
    methods["nagad"]["enabled"] = bool(settings.get("nagad_enabled", True))
    return methods

PACKAGES = {
    "starter_500": {
        "id": "starter_500",
        "name": "Starter Plan",
        "credits": 500,
        "price_bdt": 500,
        "price_usd": 5,
        "features": ["500 Verified Leads", "Email Verifier Unlocked", "Cold Outreach Unlocked", "Up to 50 Leads / Batch"]
    },
    "growth_2000": {
        "id": "growth_2000",
        "name": "Growth Pro (Best Value)",
        "credits": 2000,
        "price_bdt": 1800,
        "price_usd": 18,
        "features": ["2,000 Verified Leads", "Email Verifier Unlocked", "Cold Outreach Unlocked", "Up to 100 Leads / Batch", "Priority Tech Detector"]
    },
    "agency_5000": {
        "id": "agency_5000",
        "name": "Agency Unlimited",
        "credits": 5000,
        "price_bdt": 4000,
        "price_usd": 40,
        "features": ["5,000 Verified Leads", "All Features Unlocked", "Unlimited Batch Scrapes", "10 SMTP Mailbox Sender", "Lifetime Priority Support"]
    }
}

PAYMENT_METHODS = {
    "bkash": {
        "name": "bKash (Send Money)",
        "number": "01820575753",
        "type": "Personal (Send Money)",
        "logo_color": "#E2136E",
        "instructions": "Open bKash App or dial *247# and choose 'Send Money' to the number above."
    },
    "nagad": {
        "name": "Nagad (Send Money)",
        "number": "01820575753",
        "type": "Personal (Send Money)",
        "logo_color": "#F7931E",
        "instructions": "Open Nagad App or dial *167# and choose 'Send Money' to the number above."
    }
}

def ensure_payments_file():
    os.makedirs(os.path.dirname(PAYMENTS_FILE), exist_ok=True)
    if not os.path.exists(PAYMENTS_FILE):
        with open(PAYMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

def load_payments():
    ensure_payments_file()
    try:
        with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_payments(payments):
    ensure_payments_file()
    with open(PAYMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payments, f, indent=2, ensure_ascii=False)

def submit_payment(client_id, client_name, client_email, gateway, sender_number, trx_id, package_id, is_first_time_buyer=True, promo_code=""):
    """
    Submits a payment and verifies it in real time against live incoming bKash/Nagad SMS
    synced from the owner's Android phone via Leadzio PaySync.
    """
    import sms_payment_sync

    payments = load_payments()
    live_pkgs = get_live_packages()
    pkg = live_pkgs.get(package_id) or live_pkgs["starter_500"]
    pricing = calculate_package_price(pkg["id"], is_first_time_buyer=is_first_time_buyer, promo_code=promo_code)
    expected_bdt = pricing["final_price"]

    trx_clean = trx_id.strip().upper()
    sender_clean = sender_number.strip()
    
    # Prevent duplicate TrxID reuse
    for p in payments:
        if p.get("trx_id") == trx_clean and p.get("status") == "approved":
            return False, "This Transaction ID has already been used and approved.", None

    # Live Mobile SMS Verification via Leadzio PaySync
    matched, code, sync_msg, sms_rec = sms_payment_sync.verify_and_claim_sms(
        trx_id=trx_clean,
        expected_amount=expected_bdt,
        sender_number=sender_clean,
        gateway=gateway
    )

    if code in ("already_used", "amount_mismatch", "sender_mismatch"):
        return False, sync_msg, None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payment_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
    status = "approved" if matched else "pending"

    record = {
        "id": payment_id,
        "client_id": client_id,
        "client_name": client_name,
        "client_email": client_email,
        "gateway": gateway,
        "sender_number": sender_clean,
        "trx_id": trx_clean,
        "package_id": pkg["id"],
        "package_name": pkg["name"],
        "amount_bdt": expected_bdt,
        "original_amount_bdt": pricing["original_price"],
        "discount_amount_bdt": pricing["discount_amount"],
        "offer_applied": pricing["offer_title"] if pricing["offer_applied"] else "",
        "credits": pkg["credits"],
        "status": status,
        "verification_method": "Auto SMS Sync" if matched else "Waiting for SMS / Admin",
        "created_at": now_str,
        "verified_at": now_str if matched else None
    }
    payments.insert(0, record)
    save_payments(payments)

    if matched:
        return True, f"🎉 {sync_msg} {pkg['credits']} Credits added & PRO features unlocked!", record
    return True, sync_msg, record

def get_payment_stats():
    payments = load_payments()
    approved = [p for p in payments if p.get("status") == "approved"]
    pending = [p for p in payments if p.get("status") == "pending"]
    rejected = [p for p in payments if p.get("status") == "rejected"]
    
    total_rev = sum(p.get("amount_bdt", 0) for p in approved)
    bkash_rev = sum(p.get("amount_bdt", 0) for p in approved if p.get("gateway") == "bkash")
    nagad_rev = sum(p.get("amount_bdt", 0) for p in approved if p.get("gateway") == "nagad")
    total_credits = sum(p.get("credits", 0) for p in approved)

    return {
        "total_revenue_bdt": total_rev,
        "bkash_revenue_bdt": bkash_rev,
        "nagad_revenue_bdt": nagad_rev,
        "total_credits_sold": total_credits,
        "total_orders": len(payments),
        "approved_count": len(approved),
        "pending_count": len(pending),
        "rejected_count": len(rejected)
    }

def approve_payment(payment_id):
    payments = load_payments()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for p in payments:
        if p.get("id") == payment_id:
            p["status"] = "approved"
            p["verified_at"] = now_str
            save_payments(payments)
            return True, p
    return False, None

def reject_payment(payment_id, reason="Invalid Transaction"):
    payments = load_payments()
    for p in payments:
        if p.get("id") == payment_id:
            p["status"] = "rejected"
            p["rejection_reason"] = reason
            save_payments(payments)
            return True, p
    return False, None

def delete_payment(payment_id):
    payments = load_payments()
    new_payments = [p for p in payments if p.get("id") != payment_id]
    if len(new_payments) != len(payments):
        save_payments(new_payments)
        return True
    return False
