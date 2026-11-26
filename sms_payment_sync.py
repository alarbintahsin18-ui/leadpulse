# -*- coding: utf-8 -*-
"""
ClientHunt PaySync — Self-Hosted Mobile SMS Payment Automation Engine
Replaces third-party gateways (like UddoktaPay) with 0% fee direct Android SMS sync.
Receives real bKash & Nagad SMS from the owner's Android phone and auto-verifies
customer Transaction IDs (TrxID) + Sender Numbers in real time.
"""

import os
import re
import json
import uuid
import secrets
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL"):
    import shutil as _shutil
    CONFIG_FILE = "/tmp/config.json"
    _seed_cfg = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(CONFIG_FILE) and os.path.exists(_seed_cfg):
        try:
            _shutil.copy2(_seed_cfg, CONFIG_FILE)
        except Exception:
            pass
    SMS_INBOX_FILE = "/tmp/clienthunt_data/sms_inbox.json"
else:
    CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
    SMS_INBOX_FILE = os.path.join(BASE_DIR, "data", "sms_inbox.json")


def _load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_paysync_config():
    cfg = _load_config()
    ps = cfg.get("paysync") or {}
    if not ps.get("sync_key"):
        ps["sync_key"] = "CHSYNC-" + secrets.token_hex(12).upper()
        ps["enabled"] = True
        ps["last_sync_at"] = None
        ps["device_name"] = "Not Connected Yet"
        cfg["paysync"] = ps
        _save_config(cfg)
    return ps


def save_paysync_config(sync_key=None, enabled=True, regenerate=False):
    cfg = _load_config()
    ps = cfg.get("paysync") or {}
    if regenerate:
        ps["sync_key"] = "CHSYNC-" + secrets.token_hex(12).upper()
    elif sync_key:
        ps["sync_key"] = sync_key.strip()
    elif not ps.get("sync_key"):
        ps["sync_key"] = "CHSYNC-" + secrets.token_hex(12).upper()
    ps["enabled"] = bool(enabled)
    cfg["paysync"] = ps
    _save_config(cfg)
    return ps


def verify_sync_key(provided_key):
    cfg = get_paysync_config()
    if not provided_key:
        return False
    return provided_key.strip() == cfg.get("sync_key", "").strip()


def _ensure_inbox():
    os.makedirs(os.path.dirname(SMS_INBOX_FILE), exist_ok=True)
    if not os.path.exists(SMS_INBOX_FILE):
        with open(SMS_INBOX_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def load_sms_inbox():
    _ensure_inbox()
    try:
        with open(SMS_INBOX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_sms_inbox(records):
    _ensure_inbox()
    with open(SMS_INBOX_FILE, "w", encoding="utf-8") as f:
        json.dump(records[:500], f, indent=2, ensure_ascii=False)


def parse_bd_payment_sms(sender_title="", message_text=""):
    """
    Parses real Bangladeshi bKash & Nagad Send Money / Cash In SMS messages.
    Examples:
    - bKash: "You have received Tk 500.00 from 01712345678. Fee Tk 0.00. Balance Tk 2,500.00. TrxID BKA7629810 at 26/11/2026 22:15"
    - Nagad: "Money Received. Amount: Tk 500.00 Sender: 01812345678 Ref: N/A TxnID: 72AB91CD Balance: Tk 1500.00"
    """
    msg = (message_text or "").strip()
    snd_low = (sender_title or "").lower()
    msg_low = msg.lower()

    # Detect Gateway
    gateway = "unknown"
    if "bkash" in snd_low or "trxid" in msg_low or "bkash" in msg_low:
        gateway = "bkash"
    elif "nagad" in snd_low or "txnid" in msg_low or "nagad" in msg_low:
        gateway = "nagad"

    # Must be an incoming money received SMS (ignore outgoing Send Money / Cash Out)
    is_incoming = any(k in msg_low for k in [
        "have received", "money received", "cash in", "received tk", "received bdt", "payment received"
    ])
    if not is_incoming:
        return None

    # Extract Amount (Tk 500.00 / BDT 1,800.00)
    amt_match = re.search(r'(?:tk|bdt)\.?\s*([0-9,]+(?:\.[0-9]{1,2})?)', msg, re.I)
    if not amt_match:
        return None
    try:
        amount = float(amt_match.group(1).replace(",", ""))
    except Exception:
        return None

    # Extract TrxID / TxnID
    trx_match = re.search(r'(?:trxid|txnid|trx\s*id|txn\s*id|transaction\s*id)[\s:.-]*([A-Z0-9]{6,20})', msg, re.I)
    if not trx_match:
        return None
    trx_id = trx_match.group(1).strip().upper()

    # Extract Sender Phone Number (11-digit BD number 013-019)
    phone_match = re.search(r'(?:from|sender)[\s:.-]*(?:\+?88)?(01[3-9]\d{8})', msg, re.I)
    if not phone_match:
        phone_match = re.search(r'(?:\+?88)?(01[3-9]\d{8})', msg)
    sender_number = phone_match.group(1) if phone_match else ""

    return {
        "gateway": gateway if gateway != "unknown" else "bkash",
        "amount": amount,
        "trx_id": trx_id,
        "sender_number": sender_number,
        "raw_sms": msg[:300]
    }


def record_incoming_sms(sender_title="", message_text="", device_name="Android Phone", explicit_data=None):
    """
    Saves a verified incoming bKash/Nagad SMS from the owner's phone and
    auto-approves any waiting pending payment order that matches this TrxID!
    """
    # Update device last heartbeat
    cfg = _load_config()
    ps = cfg.get("paysync") or get_paysync_config()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ps["last_sync_at"] = now_str
    if device_name:
        ps["device_name"] = device_name
    cfg["paysync"] = ps
    _save_config(cfg)

    parsed = explicit_data if explicit_data else parse_bd_payment_sms(sender_title, message_text)
    if not parsed:
        return False, "Ignored non-payment SMS.", None, False

    inbox = load_sms_inbox()
    trx_id = parsed["trx_id"].strip().upper()

    # Deduplicate by TrxID
    for existing in inbox:
        if existing.get("trx_id") == trx_id:
            return True, f"SMS TrxID {trx_id} already synced.", existing, False

    sms_rec = {
        "id": f"SMS-{uuid.uuid4().hex[:8].upper()}",
        "gateway": parsed["gateway"],
        "amount": float(parsed["amount"]),
        "trx_id": trx_id,
        "sender_number": parsed.get("sender_number", ""),
        "raw_sms": parsed.get("raw_sms", message_text[:300]),
        "device_name": device_name,
        "received_at": now_str,
        "claimed": False,
        "claimed_by": None,
        "claimed_at": None
    }
    inbox.insert(0, sms_rec)

    # Auto-match against any already-submitted PENDING payment order!
    auto_approved_order = False
    try:
        import payment_manager
        import client_manager

        payments = payment_manager.load_payments()
        for p in payments:
            if p.get("status") == "pending" and p.get("trx_id", "").upper() == trx_id:
                req_amt = float(p.get("amount_bdt", 0))
                if sms_rec["amount"] >= req_amt:
                    p["status"] = "approved"
                    p["verified_at"] = now_str
                    p["verification_method"] = "Auto SMS Sync"
                    payment_manager.save_payments(payments)

                    sms_rec["claimed"] = True
                    sms_rec["claimed_by"] = p.get("client_id")
                    sms_rec["claimed_at"] = now_str

                    client_manager.activate_paid_status(
                        p.get("client_id"),
                        plan="premium",
                        add_credits=int(p.get("credits", 0))
                    )
                    auto_approved_order = True
                    break
    except Exception as e:
        print(f"[PaySync Auto-Match Error] {e}", flush=True)

    save_sms_inbox(inbox)
    return True, f"Synced {sms_rec['gateway'].upper()} Tk {sms_rec['amount']} (TrxID: {trx_id})", sms_rec, auto_approved_order


def verify_and_claim_sms(trx_id, expected_amount, sender_number="", gateway=""):
    """
    Checks if a customer-submitted TrxID matches an unclaimed incoming SMS
    from the owner's Android phone. Marks as claimed immediately to prevent reuse.
    Returns: (matched: bool, code: str, message: str, sms_record: dict | None)
    """
    trx_clean = (trx_id or "").strip().upper()
    sender_digits = re.sub(r'\D', '', sender_number or "")[-11:]
    inbox = load_sms_inbox()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for rec in inbox:
        if rec.get("trx_id", "").upper() == trx_clean:
            if rec.get("claimed"):
                return False, "already_used", "This Transaction ID has already been claimed.", rec

            sms_amt = float(rec.get("amount", 0))
            if sms_amt < float(expected_amount):
                return False, "amount_mismatch", f"Received Tk {int(sms_amt)} for TrxID {trx_clean}, but selected package requires Tk {int(expected_amount)}.", rec

            # Optional sender number cross-check (if SMS contained sender number)
            sms_sender = re.sub(r'\D', '', rec.get("sender_number", ""))[-11:]
            if sms_sender and sender_digits and sms_sender != sender_digits:
                return False, "sender_mismatch", f"Sender number mismatch for TrxID {trx_clean}. Please enter the exact number you sent money from.", rec

            # Exact Match! Claim it immediately.
            rec["claimed"] = True
            rec["claimed_at"] = now_str
            save_sms_inbox(inbox)
            return True, "verified", f"Instant SMS Verified! Tk {int(sms_amt)} received via {rec.get('gateway', 'bKash/Nagad').upper()}.", rec

    return False, "not_found", "Payment submitted! Waiting for live SMS confirmation from mobile (auto-activates within seconds once received).", None
