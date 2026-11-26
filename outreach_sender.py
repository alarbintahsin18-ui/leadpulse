import os
import re
import json
import smtplib
import uuid
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email_tracker import generate_tracking_id, insert_tracking_pixel, wrap_links_for_tracking
from database import get_db_connection

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "outreach_accounts.json")
LOGS_FILE = os.path.join(BASE_DIR, "outreach_logs.json")

# ═════════════════════════════════════════════════
# PRE-BUILT AI-OPTIMIZED COLD EMAIL COPY TEMPLATES
# ═════════════════════════════════════════════════
# ═════════════════════════════════════════════════
# PRE-BUILT SERVICE PRESETS & DYNAMIC COPY GENERATION
# ═════════════════════════════════════════════════
DEFAULT_SERVICE_PRESETS = {
    "meta_ads": {
        "service_name": "Meta & Facebook Ads Acquisition Funnels",
        "agency_name": "Vanguard Paid Media",
        "sender_name": "Marcus Sterling",
        "sender_title": "Performance Marketing Director",
        "value_prop": "we build high-ROI Meta ad funnels that retarget lost website visitors and turn existing brand authority into predictable private appointments.",
        "cta": "Would you be open to a quick 2-minute breakdown showing how many potential clients your website is currently losing without retargeting?"
    },
    "web_design": {
        "service_name": "Modern Website Redesign & Mobile Speed Optimization",
        "agency_name": "Nexus Web Studio",
        "sender_name": "Alex Vance",
        "sender_title": "Product & Design Lead",
        "value_prop": "we revamp outdated or slow websites into lightning-fast, high-converting digital storefronts that turn casual visitors into paying customers.",
        "cta": "Would you be open to a quick 2-minute video audit showing high-impact improvements for your site?"
    },
    "local_seo": {
        "service_name": "Google Top-3 Organic Search & Maps Ranking",
        "agency_name": "Apex Search Partners",
        "sender_name": "Jordan Blake",
        "sender_title": "Search Growth Strategist",
        "value_prop": "we help local market leaders capture top-3 rankings on Google search and Maps for high-intent keywords that competitors are winning.",
        "cta": "Could I send over a 1-page keyword blueprint showing the exact search terms you can rank for this month?"
    },
    "seo_growth": {
        "service_name": "Google Top-3 Organic Search & Maps Ranking",
        "agency_name": "Apex Search Partners",
        "sender_name": "Jordan Blake",
        "sender_title": "Search Growth Strategist",
        "value_prop": "we help local market leaders capture top-3 rankings on Google search and Maps for high-intent keywords that competitors are winning.",
        "cta": "Could I send over a 1-page keyword blueprint showing the exact search terms you can rank for this month?"
    },
    "ai_booking": {
        "service_name": "24/7 AI Receptionist & Appointment Scheduling Automation",
        "agency_name": "PulseBot AI Solutions",
        "sender_name": "Sarah Jenkins",
        "sender_title": "AI Systems Architect",
        "value_prop": "we deploy intelligent 24/7 conversational booking bots that qualify new inquiries instantly and schedule client consultations directly into your calendar without staff overhead.",
        "cta": "Could I share a 60-second interactive preview of an AI appointment bot customized for your practice?"
    },
    "reputation": {
        "service_name": "Automated 5-Star Google Reviews & Reputation Scaling",
        "agency_name": "ReviewTrust Media",
        "sender_name": "Elena Rostova",
        "sender_title": "Reputation Growth Director",
        "value_prop": "we implement seamless automated review collection workflows that capture steady 5-star Google ratings from satisfied clients to dominate local authority.",
        "cta": "Would you like to see how we helped a similar practice gain 40+ new verified 5-star reviews in 30 days?"
    },
    "b2b_outreach": {
        "service_name": "B2B Outbound Lead Generation & Sales Appointments",
        "agency_name": "Pipeline Pro Intelligence",
        "sender_name": "Marcus Reed",
        "sender_title": "Client Acquisition Director",
        "value_prop": "we build targeted outbound email campaigns to pre-qualified decision-makers, booking predictable sales meetings directly into your calendar.",
        "cta": "If you have capacity for new high-ticket clients, could I share 5 free sample verified decision-maker leads tailored to your ICP?"
    },
    "lead_generation": {
        "service_name": "B2B Outbound Lead Generation & Sales Appointments",
        "agency_name": "Pipeline Pro Intelligence",
        "sender_name": "Marcus Reed",
        "sender_title": "Client Acquisition Director",
        "value_prop": "we build targeted outbound email campaigns to pre-qualified decision-makers, booking predictable sales meetings directly into your calendar.",
        "cta": "If you have capacity for new high-ticket clients, could I share 5 free sample verified decision-maker leads tailored to your ICP?"
    },
    "software_b2b": {
        "service_name": "Enterprise Business Automation & Software Solutions",
        "agency_name": "AutomateX Solutions",
        "sender_name": "Sarah Jenkins",
        "sender_title": "Operations & Tech Director",
        "value_prop": "we implement streamlined workflow automation software that cuts manual admin tasks and customer onboarding friction by up to 35%.",
        "cta": "Would you have 5 minutes for an introductory exploratory chat this Thursday?"
    },
    "partnership": {
        "service_name": "Strategic Client Referral & Mutual Growth Partnership",
        "agency_name": "Alliance Growth Network",
        "sender_name": "David Cross",
        "sender_title": "Head of Strategic Partnerships",
        "value_prop": "we connect complementary service providers to exchange high-value client referrals and expand market reach without extra advertising cost.",
        "cta": "Would you be open for a 10-minute introductory phone call next week to see if a partnership makes sense?"
    }
}

AI_PITCH_TEMPLATES = DEFAULT_SERVICE_PRESETS

def extract_clean_city(raw_location="", raw_address=""):
    """
    Extracts a clean, short municipal city name (e.g. 'Barishal', 'Austin', 'London')
    from potentially messy location or full street address strings.
    Never returns street names, building names, floor numbers, or postal codes.
    """
    candidates = [raw_location or "", raw_address or ""]
    street_tokens = [
        "floor", "mansion", "road", "rd", "street", "st", "lane", "ave", "avenue", 
        "blvd", "boulevard", "suite", "ste", "building", "bldg", "plaza", "sector", 
        "flat", "apt", "house", "plot", "shop"
    ]
    countries = ["bangladesh", "united states", "usa", "uk", "united kingdom", "india", "canada", "australia", "germany"]

    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate.strip()
        parts = [p.strip() for p in candidate.split(",") if p.strip()]
        for part in reversed(parts):
            p_clean = re.sub(r'[\d\-–#]', '', part).strip()
            if not p_clean or p_clean.lower() in countries:
                continue
            words = [w.lower() for w in re.findall(r'[a-zA-Z]+', p_clean)]
            if any(w in street_tokens for w in words):
                continue
            if 3 <= len(p_clean) <= 25 and re.search(r'[A-Za-z]', p_clean):
                return p_clean
                
    return ""

def generate_personalized_copy(lead, service_info=None, goal="meta_ads"):
    """
    Generates a unique, high-converting international cold email copy
    customized specifically for this lead's details (company, domain, location, category, rating)
    and the user's specific offered service, agency name, value proposition, and CTA.
    """
    service_info = service_info or {}
    preset_key = goal if goal in DEFAULT_SERVICE_PRESETS else ("meta_ads" if "meta" in str(goal).lower() else "web_design")
    preset = DEFAULT_SERVICE_PRESETS.get(preset_key, DEFAULT_SERVICE_PRESETS["meta_ads"])
    
    service_name = service_info.get("service_name", "").strip() or preset["service_name"]
    agency_name = service_info.get("agency_name", "").strip() or preset.get("agency_name", "Your Agency")
    sender_name = service_info.get("sender_name", "").strip() or preset.get("sender_name", "Your Name")
    sender_title = service_info.get("sender_title", "").strip() or preset.get("sender_title", "Founder / Director")
    value_prop = service_info.get("value_prop", "").strip() or preset["value_prop"]
    cta = service_info.get("cta", "").strip() or preset["cta"]

    company = (lead.get("company") or lead.get("name") or "your company").strip()
    dm = lead.get("contact_name") or lead.get("first_name") or ""
    first_name = dm.split()[0] if dm else "there"
    if dm.startswith("Dr."):
        parts = dm.split()
        first_name = f"{parts[0]} {parts[1]}" if len(parts) > 1 else dm
    if not first_name or first_name.lower() in ["mr.", "ms.", "mrs.", "lead", "contact"]:
        first_name = "there"

    domain = lead.get("domain") or (lead.get("website", "").replace("https://", "").replace("http://", "").split("/")[0].split("?")[0] if lead.get("website") else "")
    city = extract_clean_city(lead.get("location") or lead.get("city"), lead.get("address"))
    category = (lead.get("sub_specialty") or lead.get("category") or "").strip()

    city_phrase = f" in {city}" if city else ""
    website_phrase = f" on {domain}" if domain and "." in domain else ""

    # Subject line aligned strictly with chosen offer
    if "meta" in preset_key or "ads" in preset_key:
        subject = f"Question regarding {company}'s Meta Pixel & paid client funnels"
    elif "web" in preset_key:
        subject = f"Quick question regarding {domain or company}'s site & conversion"
    elif "seo" in preset_key:
        subject = f"Google Maps top-3 ranking opportunity for {company}{city_phrase}"
    elif "booking" in preset_key or "ai" in preset_key:
        subject = f"Automating after-hours appointments for {company}"
    elif "reputation" in preset_key:
        subject = f"Strengthening {company}'s Google review authority"
    else:
        subject = f"Qualified client pipeline for {company}"

    # Specific pain-point observation if detected
    pain_point_text = ""
    if lead.get("buying_reason"):
        pain_point_text = f"<br><br><em>Specifically noticed: {lead['buying_reason']}</em>"

    # Generate high-converting individualized email body
    body = f"""Hi {first_name},<br><br>
I noticed the impressive work you and the team are doing at <strong>{company}</strong>{city_phrase}.<br><br>
At <strong>{agency_name}</strong>, we specialize in <strong>{service_name}</strong>. Specifically, {value_prop}{pain_point_text}<br><br>
Looking at your current setup{website_phrase}, I identified a few direct opportunities that could help {company} attract more high-ticket clients and save valuable team hours.<br><br>
{cta}<br><br>
Best regards,<br>
<strong>{sender_name}</strong><br>
{sender_title} &bull; {agency_name}"""

    return {
        "subject": subject,
        "body": body
    }

def generate_all_personalized_emails(leads, service_info=None, goal="software_b2b"):
    """
    Loops through every lead in the list and attaches individual, custom personalized subject and body.
    """
    updated_leads = []
    for lead in leads:
        lead_copy = dict(lead)
        copy = generate_personalized_copy(lead_copy, service_info=service_info, goal=goal)
        lead_copy["personalized_subject"] = copy["subject"]
        lead_copy["personalized_body"] = copy["body"]
        updated_leads.append(lead_copy)
    return updated_leads

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts[:10], f, indent=2)

def load_logs():
    if not os.path.exists(LOGS_FILE):
        return []
    try:
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_log_entry(entry):
    logs = load_logs()
    logs.insert(0, entry)
    logs = logs[:500]
    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

def test_smtp_account(acc):
    host = acc.get("host", "").strip()
    port = int(acc.get("port", 587))
    user = acc.get("user", "").strip()
    password = acc.get("password", "").strip()
    security = acc.get("security", "STARTTLS").upper()

    if not host or not user:
        return False, "Host and Username are required."

    try:
        if security == "SSL" or port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if security == "STARTTLS" or port == 587:
                server.starttls()
        
        if password:
            server.login(user, password)
        server.quit()
        return True, "SMTP Connection & Authentication Succeeded!"
    except Exception as e:
        return False, f"SMTP Error: {str(e)}"

def format_lead_copy(template_text, lead_info):
    lead_info = lead_info or {}
    contact = lead_info.get("contact_name") or lead_info.get("name", "there")
    first_name = lead_info.get("first_name") or contact.split()[0] if contact else "there"
    replacements = {
        "{{FirstName}}": first_name,
        "{{LastName}}": lead_info.get("last_name", ""),
        "{{FullName}}": contact,
        "{{Company}}": lead_info.get("company_name") or lead_info.get("name", "your company"),
        "{{Title}}": lead_info.get("contact_title") or lead_info.get("category", "Leadership"),
        "{{Domain}}": lead_info.get("domain", ""),
        "{{Phone}}": lead_info.get("phone", ""),
        "{{City}}": lead_info.get("location") or lead_info.get("address", "")
    }
    result = template_text
    for key, val in replacements.items():
        result = result.replace(key, str(val))
    return result

def send_cold_email(to_email, subject, body_html, account_id="auto", lead_info=None, track_opens=False, track_clicks=False, host_url="http://localhost:5055", client_id=None):
    to_email_clean = (to_email or "").strip().lower()
    if not to_email_clean or "@" not in to_email_clean:
        return False, "Recipient email is empty or invalid."

    # Pre-flight MX record check to protect sender reputation
    domain_part = to_email_clean.split("@")[-1]
    try:
        import dns.resolver
        r = dns.resolver.Resolver()
        r.nameservers = ['8.8.8.8', '1.1.1.1']
        r.timeout = 2.0
        r.lifetime = 3.0
        mx_ans = r.resolve(domain_part, 'MX')
        if not mx_ans:
            return False, f"Domain @{domain_part} has no active MX mail records. Delivery aborted to protect sender reputation."
    except Exception:
        return False, f"Domain @{domain_part} does not have valid MX mail exchanger records. Delivery aborted."

    accounts = load_accounts()
    active_accounts = [a for a in accounts if a.get("active", True)]
    if not active_accounts:
        return False, "No active domain mail accounts configured. Please add an SMTP account first."

    selected_acc = None
    if account_id and account_id != "auto":
        for a in active_accounts:
            if a.get("id") == account_id:
                selected_acc = a
                break
    if not selected_acc:
        selected_acc = min(active_accounts, key=lambda x: x.get("today_sent", 0))

    final_subject = format_lead_copy(subject, lead_info)
    final_body = format_lead_copy(body_html, lead_info)

    # Inject Email Open & Click Tracking (Optional - User Toggleable)
    tracking_id = None
    if track_opens:
        tracking_id = generate_tracking_id()
        final_body = insert_tracking_pixel(final_body, tracking_id, host_url=host_url)
        if track_clicks:
            final_body = wrap_links_for_tracking(final_body, tracking_id, host_url=host_url)

    host = selected_acc.get("host", "").strip()
    port = int(selected_acc.get("port", 587))
    user = selected_acc.get("user", "").strip()
    password = selected_acc.get("password", "").strip()
    from_name = selected_acc.get("from_name", "").strip()
    from_email = selected_acc.get("from_email", user).strip()
    security = selected_acc.get("security", "STARTTLS").upper()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = final_subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg["Date"] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")

    part1 = MIMEText(final_body, "html")
    msg.attach(part1)

    try:
        if security == "SSL" or port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=12)
        else:
            server = smtplib.SMTP(host, port, timeout=12)
            if security == "STARTTLS" or port == 587:
                server.starttls()

        if password:
            server.login(user, password)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()

        selected_acc["today_sent"] = selected_acc.get("today_sent", 0) + 1
        save_accounts(accounts)

        log_id = str(uuid.uuid4())[:8]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "id": log_id,
            "tracking_id": tracking_id or "",
            "timestamp": now_str,
            "sender_account": selected_acc.get("name", from_email),
            "from_email": from_email,
            "to_email": to_email,
            "subject": final_subject,
            "status": "Delivered",
            "opened": False,
            "open_count": 0,
            "clicked": False,
            "error": ""
        }
        save_log_entry(log_entry)

        # Store in SQLite tracking ledger
        if tracking_id:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                INSERT OR REPLACE INTO outreach_tracking (id, tracking_id, client_id, recipient_email, recipient_name, subject, status, sender_account, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (log_id, tracking_id, client_id, to_email, (lead_info or {}).get("contact_name", ""), final_subject, "sent", selected_acc.get("name", from_email), now_str))
                conn.commit()
                conn.close()
            except Exception as e:
                print("[Tracking] DB save error:", e)

        return True, f"Sent via {from_email}"
    except Exception as e:
        err_msg = str(e)
        log_entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sender_account": selected_acc.get("name", from_email),
            "from_email": from_email,
            "to_email": to_email,
            "subject": final_subject,
            "status": "Failed",
            "error": err_msg
        }
        save_log_entry(log_entry)
        return False, f"Failed: {err_msg}"

def send_bulk_cold_emails(leads, subject, body_html, account_id="auto", delay_seconds=2, track_opens=False, track_clicks=False, host_url="http://localhost:5055", client_id=None):
    """
    Sends bulk cold emails to a list of leads rotating across configured inboxes.
    Includes delay to protect sender reputation.
    """
    results = {
        "total": len(leads),
        "delivered": 0,
        "failed": 0,
        "details": []
    }

    accounts = load_accounts()
    active_accounts = [a for a in accounts if a.get("active", True)]
    if not active_accounts:
        return False, "No active domain mail accounts configured."

    for idx, lead in enumerate(leads):
        email = lead.get("email") or (lead.get("all_emails", [""])[0] if lead.get("all_emails") else "")
        if not email or "@" not in email:
            results["failed"] += 1
            results["details"].append({"email": email, "status": "Skipped (No Email)"})
            continue

        lead_subject = lead.get("personalized_subject") or subject
        lead_body = lead.get("personalized_body") or body_html
        ok, msg = send_cold_email(
            email, 
            lead_subject, 
            lead_body, 
            account_id=account_id, 
            lead_info=lead,
            track_opens=track_opens,
            track_clicks=track_clicks,
            host_url=host_url,
            client_id=client_id
        )
        if ok:
            results["delivered"] += 1
            results["details"].append({"email": email, "status": "Delivered", "msg": msg})
        else:
            results["failed"] += 1
            results["details"].append({"email": email, "status": "Failed", "msg": msg})

        # Polite delay between sends to avoid rate limiting
        if idx < len(leads) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

    return True, results


def generate_multi_step_sequence(lead, service_info=None, goal="meta_ads"):
    """
    Generates a high-converting 3-step automated drip cold outreach sequence:
    - Step 1: Initial Hook & Value Proposition (Day 1)
    - Step 2: Day 3 Follow-Up (Case Study & Concrete Proof)
    - Step 3: Day 7 Final Nudge (Polite Break-up & Permission to close file)
    Also generates 1-click WhatsApp pitch hook.
    """
    import urllib.parse
    
    step1 = generate_personalized_copy(lead, service_info=service_info, goal=goal)
    
    service_info = service_info or {}
    preset_key = goal if goal in DEFAULT_SERVICE_PRESETS else ("meta_ads" if "meta" in str(goal).lower() else "web_design")
    preset = DEFAULT_SERVICE_PRESETS.get(preset_key, DEFAULT_SERVICE_PRESETS["meta_ads"])
    
    service_name = service_info.get("service_name", "").strip() or preset["service_name"]
    agency_name = service_info.get("agency_name", "").strip() or preset.get("agency_name", "Your Agency")
    sender_name = service_info.get("sender_name", "").strip() or preset.get("sender_name", "Your Name")
    sender_title = service_info.get("sender_title", "").strip() or preset.get("sender_title", "Founder / Director")
    
    company = (lead.get("company") or lead.get("name") or "your company").strip()
    dm = lead.get("contact_name") or lead.get("first_name") or ""
    first_name = dm.split()[0] if dm else "there"
    if dm.startswith("Dr."):
        parts = dm.split()
        first_name = f"{parts[0]} {parts[1]}" if len(parts) > 1 else dm
    if not first_name or first_name.lower() in ["mr.", "ms.", "mrs.", "lead", "contact"]:
        first_name = "there"

    city = extract_clean_city(lead.get("location") or lead.get("city"), lead.get("address"))
    city_phrase = f" in {city}" if city else ""

    # Step 2: Day 3 Follow-up (Case study / Proof)
    step2_subject = f"Re: {step1['subject']}"
    step2_body = f"""Hi {first_name},<br><br>
Following up on my note earlier this week regarding <strong>{company}</strong>.<br><br>
We recently helped a similar business{city_phrase} increase their qualified client inquiries by 40%+ in under 60 days using our streamlined <strong>{service_name}</strong> system.<br><br>
I put together a brief 3-point checklist of the exact levers we adjusted that would directly apply to {company}.<br><br>
Would it make sense to send those 3 bullet points over to you or the appropriate person on your team?<br><br>
Best regards,<br>
<strong>{sender_name}</strong><br>
{sender_title} &bull; {agency_name}"""

    # Step 3: Day 7 Final Breakup
    step3_subject = f"Permission to close file? ({company})"
    step3_body = f"""Hi {first_name},<br><br>
I haven't heard back, so I assume optimizing your <strong>{service_name}</strong> pipeline isn't a priority for <strong>{company}</strong> right now — which is completely understandable.<br><br>
I don't want to clutter your inbox. Should I close your file for now, or is this something you'd like to revisit next quarter?<br><br>
Either way, wishing you and {company} continued growth and success.<br><br>
Best regards,<br>
<strong>{sender_name}</strong><br>
{sender_title} &bull; {agency_name}"""

    # WhatsApp Quick Outreach Hook
    raw_phone = lead.get("phone") or lead.get("phone_number") or ""
    clean_phone = re.sub(r'[^0-9+]', '', str(raw_phone)).strip()
    if clean_phone.startswith("0") and len(clean_phone) == 11:
        # Bangladesh local standard
        clean_phone = "88" + clean_phone
    elif clean_phone.startswith("+"):
        clean_phone = clean_phone[1:]

    wa_text = f"Hi {first_name}, noticed {company}{city_phrase}. We help businesses with {service_name}. Would you be open to a quick 2-min breakdown for {company}? - {sender_name} ({agency_name})"
    wa_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(wa_text)}" if clean_phone else ""

    return {
        "step1": {
            "title": "Step 1 &bull; Day 1 (Initial Hook)",
            "delay_days": 0,
            "subject": step1["subject"],
            "body": step1["body"]
        },
        "step2": {
            "title": "Step 2 &bull; Day 3 (Case Study Follow-up)",
            "delay_days": 3,
            "subject": step2_subject,
            "body": step2_body
        },
        "step3": {
            "title": "Step 3 &bull; Day 7 (Break-up / Low Friction)",
            "delay_days": 7,
            "subject": step3_subject,
            "body": step3_body
        },
        "whatsapp": {
            "phone": clean_phone,
            "text": wa_text,
            "url": wa_url
        }
    }
