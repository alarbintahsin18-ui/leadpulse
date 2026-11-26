import os
import json
import uuid
from datetime import datetime

PAYMENTS_FILE = "/tmp/clienthunt_data/payments.json" if os.environ.get("VERCEL") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "payments.json")

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

def submit_payment(client_id, client_name, client_email, gateway, sender_number, trx_id, package_id):
    """
    Submits a payment and verifies it in real time against live incoming bKash/Nagad SMS
    synced from the owner's Android phone via ClientHunt PaySync.
    """
    import sms_payment_sync

    payments = load_payments()
    pkg = PACKAGES.get(package_id) or PACKAGES["starter_500"]
    trx_clean = trx_id.strip().upper()
    sender_clean = sender_number.strip()
    
    # Prevent duplicate TrxID reuse
    for p in payments:
        if p.get("trx_id") == trx_clean and p.get("status") == "approved":
            return False, "This Transaction ID has already been used and approved.", None

    # Live Mobile SMS Verification via ClientHunt PaySync
    matched, code, sync_msg, sms_rec = sms_payment_sync.verify_and_claim_sms(
        trx_id=trx_clean,
        expected_amount=pkg["price_bdt"],
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
        "amount_bdt": pkg["price_bdt"],
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
