import os
import json
import uuid
import urllib.parse
from datetime import datetime
from database import get_db_connection

# 1x1 Transparent Pixel GIF
PIXEL_GIF = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

def generate_tracking_id():
    return f"trk_{uuid.uuid4().hex[:12]}"

def insert_tracking_pixel(html_body, tracking_id, host_url="http://localhost:5055"):
    """
    Appends a lightweight 1x1 tracking pixel at the end of the HTML email body.
    """
    if not tracking_id:
        return html_body
    
    pixel_tag = f'<img src="{host_url}/api/track/open/{tracking_id}.png" width="1" height="1" style="display:none;opacity:0;" alt="" />'
    if "</body>" in html_body:
        return html_body.replace("</body>", f"{pixel_tag}</body>")
    return f"{html_body}\n{pixel_tag}"

def wrap_links_for_tracking(html_body, tracking_id, host_url="http://localhost:5055"):
    """
    Replaces outbound <a href="..."> links with a click-tracking redirector.
    """
    import re
    if not tracking_id:
        return html_body

    def replacer(match):
        orig_url = match.group(1)
        # Don't wrap mailto or internal anchors
        if orig_url.startswith("mailto:") or orig_url.startswith("#") or "api/track" in orig_url:
            return match.group(0)
        encoded = urllib.parse.quote_plus(orig_url)
        tracked_url = f"{host_url}/api/track/click/{tracking_id}?url={encoded}"
        return f'href="{tracked_url}"'

    return re.sub(r'href=["\'](https?://[^"\']+)["\']', replacer, html_body)

def record_email_open(tracking_id, ip="", user_agent=""):
    """
    Records an open event in SQLite database and outreach logs.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE outreach_tracking
            SET opened = 1,
                opened_at = COALESCE(opened_at, ?),
                open_count = open_count + 1
            WHERE tracking_id = ?
        """, (now_str, tracking_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[Tracking] DB update error:", e)

    # Also update outreach_logs.json for backwards compatibility
    logs_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outreach_logs.json")
    if os.path.exists(logs_file):
        try:
            with open(logs_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
            updated = False
            for entry in logs:
                if entry.get("tracking_id") == tracking_id:
                    entry["opened"] = True
                    entry["opened_at"] = entry.get("opened_at") or now_str
                    entry["open_count"] = entry.get("open_count", 0) + 1
                    updated = True
                    break
            if updated:
                with open(logs_file, "w", encoding="utf-8") as f:
                    json.dump(logs, f, indent=2)
        except Exception as e:
            print("[Tracking] JSON update error:", e)

def record_email_click(tracking_id, target_url=""):
    """
    Records a click event and returns the target URL to redirect to.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE outreach_tracking
            SET clicked = 1,
                clicked_at = COALESCE(clicked_at, ?),
                click_count = click_count + 1
            WHERE tracking_id = ?
        """, (now_str, tracking_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[Tracking] Click DB error:", e)

    return target_url or "https://google.com"
