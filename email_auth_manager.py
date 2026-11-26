import os
import re
import json
import time
import random
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import client_manager

# ═══════════════════════════════════════════════════════════
# ALLOWED PERSONAL EMAIL PROVIDERS (Anti-Fake / Anti-Spam)
# ═══════════════════════════════════════════════════════════
ALLOWED_PERSONAL_DOMAINS = {
    # Google
    "gmail.com", "googlemail.com",
    # Microsoft
    "outlook.com", "hotmail.com", "live.com", "msn.com", "passport.com",
    # Yahoo
    "yahoo.com", "ymail.com", "rocketmail.com", "yahoo.co.uk", "yahoo.ca", "yahoo.com.au", "yahoo.in",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # Proton & Privacy
    "proton.me", "protonmail.com", "pm.me",
    # Other respected personal webmail
    "zoho.com", "mail.com", "aol.com", "gmx.com", "gmx.net", "fastmail.com", "tutanota.com", "tuta.io"
}

DISPOSABLE_BLACKLIST_KEYWORDS = [
    "temp", "dispos", "throwaway", "fake", "mailinator", "10minute", "guerrilla", 
    "sharklasers", "yopmail", "getairmail", "trashmail", "burner", "mytemp", "generator"
]

# In-memory storage for 6-digit verification codes
# { email: { "code": "123456", "expires_at": timestamp, "password_hash": "..." } }
PENDING_EMAIL_CODES = {}

def is_allowed_personal_email(email_str):
    """
    Validates if the email belongs to an accepted personal webmail provider.
    Rejects disposable, burner, or non-personal email addresses.
    """
    if not email_str or "@" not in email_str:
        return False, "Please enter a valid email address."
    
    email_clean = email_str.strip().lower()
    parts = email_clean.split("@")
    if len(parts) != 2:
        return False, "Invalid email structure."
        
    username, domain = parts[0], parts[1]
    
    # 1. Check length
    if len(username) < 2 or len(domain) < 4:
        return False, "Email address is too short."
        
    # 2. Check for disposable keywords
    for kw in DISPOSABLE_BLACKLIST_KEYWORDS:
        if kw in domain:
            return False, f"Disposable or temporary email (@{domain}) is not allowed to prevent free-credit abuse. Please use your personal Gmail, Yahoo, Outlook, or iCloud."
            
    # 3. Check personal domain whitelist
    if domain not in ALLOWED_PERSONAL_DOMAINS:
        return False, f"Only trusted personal email addresses (Gmail, Yahoo, Outlook, Hotmail, iCloud, Proton) are accepted. Domain '@{domain}' is not permitted."
        
    return True, "Valid personal email address."

def generate_and_send_code(email_str, password=None):
    """
    Generates a secure 6-digit verification code and sends it to the user's personal email.
    """
    is_valid, msg = is_allowed_personal_email(email_str)
    if not is_valid:
        return False, msg, None

    email_clean = email_str.strip().lower()
    code = f"{random.randint(100000, 999999)}"
    now = time.time()
    expires_at = now + 600  # 10 minutes expiry

    PENDING_EMAIL_CODES[email_clean] = {
        "code": code,
        "expires_at": expires_at,
        "password": password or "",
        "attempts": 0
    }

    # Attempt sending via configured SMTP in outreach_sender
    email_sent = False
    send_err = None

    try:
        from outreach_sender import load_accounts
        accounts = load_accounts()
        active_accs = [a for a in accounts if a.get("active", True)]
        if active_accs:
            acc = active_accs[0]
            host = acc.get("host", "").strip()
            port = int(acc.get("port", 587))
            user = acc.get("user", "").strip()
            pw = acc.get("password", "").strip()
            security = acc.get("security", "STARTTLS").upper()
            from_email = acc.get("from_email", user).strip()
            from_name = acc.get("from_name", "LeadPulse AI Security").strip()

            msg_obj = MIMEMultipart("alternative")
            msg_obj["Subject"] = f"Your LeadPulse AI Verification Code: {code}"
            msg_obj["From"] = f"{from_name} <{from_email}>"
            msg_obj["To"] = email_clean

            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; background: #0f172a; border-radius: 16px; padding: 24px; color: #f8fafc; border: 1px solid #334155;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #38bdf8; margin: 0;">⚡ LeadPulse AI</h2>
                    <p style="color: #94a3b8; font-size: 13px; margin: 4px 0 0 0;">B2B Lead Intelligence & Outreach Engine</p>
                </div>
                <div style="background: #1e293b; border-radius: 12px; padding: 20px; text-align: center; border: 1px solid #475569;">
                    <p style="margin: 0 0 12px 0; font-size: 14px; color: #cbd5e1;">Your One-Time Login & Verification Code is:</p>
                    <div style="font-size: 32px; font-weight: 900; letter-spacing: 6px; color: #38bdf8; font-family: monospace; background: #090d16; padding: 14px; border-radius: 8px; display: inline-block; border: 1px dashed #0284c7;">
                        {code}
                    </div>
                    <p style="font-size: 12px; color: #94a3b8; margin: 14px 0 0 0;">Valid for 10 minutes. Do not share this code with anyone.</p>
                </div>
                <div style="margin-top: 20px; text-align: center; font-size: 11px; color: #64748b;">
                    <p style="margin: 0;">🎁 New accounts receive 250 Free Bonus Credits upon verification.</p>
                </div>
            </div>
            """
            msg_obj.attach(MIMEText(html_body, "html"))

            if security == "SSL" or port == 465:
                srv = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                srv = smtplib.SMTP(host, port, timeout=10)
                if security == "STARTTLS" or port == 587:
                    srv.starttls()
            if pw:
                srv.login(user, pw)
            srv.sendmail(from_email, [email_clean], msg_obj.as_string())
            srv.quit()
            email_sent = True
    except Exception as e:
        send_err = str(e)
        print(f"[!] Email sending note: {send_err}")

    if email_sent:
        return True, f"A 6-digit verification code has been sent to {email_clean}. Please check your inbox or spam folder.", None
    else:
        # SMTP not configured or failed - allow dev/testing fallback with code displayed in UI
        return True, f"Verification code generated for {email_clean}!", code

def verify_code_and_login(email_str, input_code, device_id=None, ip_address=None):
    """
    Verifies the submitted 6-digit code and creates/fetches the client with anti-abuse 250 bonus credit protection.
    """
    email_clean = (email_str or "").strip().lower()
    code_clean = (input_code or "").strip()

    if not email_clean or email_clean not in PENDING_EMAIL_CODES:
        return False, "No verification code requested for this email. Please request a new code.", None

    entry = PENDING_EMAIL_CODES[email_clean]
    now = time.time()

    if now > entry["expires_at"]:
        del PENDING_EMAIL_CODES[email_clean]
        return False, "The verification code has expired. Please request a new one.", None

    entry["attempts"] += 1
    if entry["attempts"] > 5:
        del PENDING_EMAIL_CODES[email_clean]
        return False, "Too many incorrect attempts. Please request a fresh code.", None

    if entry["code"] != code_clean:
        return False, "Invalid verification code. Please check and try again.", None

    # Code verified! Clear from pending
    del PENDING_EMAIL_CODES[email_clean]

    display_name = email_clean.split("@")[0].capitalize()
    dev_id = device_id or f"dev_{int(time.time())}"
    ip_addr = ip_address or "127.0.0.1"
    uid = f"email_{int(time.time())}"

    client, is_new, is_admin, trial_abused = client_manager.get_or_create_google_client(
        email_clean,
        name=display_name,
        picture="",
        device_id=dev_id,
        ip_address=ip_addr,
        google_uid=uid,
        email_verified=True
    )
    client["auth_provider"] = "email_code"
    return True, f"Welcome back, {client.get('name')}! Verification successful.", client
