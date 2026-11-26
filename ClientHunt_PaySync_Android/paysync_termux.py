#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClientHunt PaySync — Instant Zero-Build Android Termux SMS Sync App
Works in 2 minutes on ANY Android phone using Termux + Termux:API (no Android Studio needed!)

Setup on Android Phone:
1. Install Termux & Termux:API from F-Droid.
2. Open Termux and run:
   pkg install python termux-api -y
   python paysync_termux.py
"""

import json
import time
import subprocess
import urllib.request

# === PASTE YOUR DETAILS FROM /admin -> PaySync ===
WEBHOOK_URL = "http://YOUR_DOMAIN_OR_IP:5055/api/sms-sync/receive"
SYNC_KEY = "PASTE_YOUR_CHSYNC_KEY_HERE"
POLL_INTERVAL_SEC = 5
# =================================================

SEEN_IDS = set()

def push_sms(sender, body):
    payload = json.dumps({
        "sender": sender,
        "message": body,
        "device": "Android Termux PaySync"
    }).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-PaySync-Key": SYNC_KEY
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))

def main():
    print("⚡ ClientHunt PaySync Live Android Listener Started...")
    print(f"   Target: {WEBHOOK_URL}")
    while True:
        try:
            raw = subprocess.check_output(["termux-sms-list", "-l", "15", "-t", "inbox"], text=True)
            messages = json.loads(raw)
            for m in messages:
                mid = m.get("_id") or f"{m.get('received')}_{m.get('number')}"
                if mid in SEEN_IDS:
                    continue
                sender = str(m.get("number") or "")
                body = str(m.get("body") or "")
                low = (sender + " " + body).lower()
                if any(k in low for k in ["bkash", "nagad", "trxid", "txnid", "received tk"]):
                    resp = push_sms(sender, body)
                    print(f"[✓] Synced {sender}: {resp.get('message')}")
                SEEN_IDS.add(mid)
        except Exception as e:
            print(f"[!] Sync notice: {e}")
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
