import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def get_uddoktapay_config():
    """Reads UddoktaPay credentials from config.json or environment variables."""
    api_key = os.environ.get("UDDOKTAPAY_API_KEY", "").strip()
    env = os.environ.get("UDDOKTAPAY_ENV", "live").strip()

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                up_cfg = cfg.get("uddoktapay", {})
                if up_cfg.get("api_key"):
                    api_key = up_cfg.get("api_key").strip()
                if up_cfg.get("env"):
                    env = up_cfg.get("env").strip()
        except Exception:
            pass

    base_url = "https://pay.uddoktapay.com/api/checkout-v2" if env == "live" else "https://sandbox.uddoktapay.com/api/checkout-v2"
    verify_url = "https://pay.uddoktapay.com/api/verify-payment" if env == "live" else "https://sandbox.uddoktapay.com/api/verify-payment"
    is_conf = bool(api_key and not api_key.startswith("sandbox_test"))

    return {
        "api_key": api_key,
        "env": env,
        "base_url": base_url,
        "verify_url": verify_url,
        "is_configured": is_conf
    }

def save_uddoktapay_config(api_key: str, env: str = "live"):
    """Saves UddoktaPay configuration to config.json."""
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["uddoktapay"] = {
        "api_key": api_key.strip(),
        "env": env.strip() if env in ("live", "sandbox") else "live"
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return True

def is_uddoktapay_configured():
    cfg = get_uddoktapay_config()
    return cfg["is_configured"]

def create_uddoktapay_charge(client, package, redirect_url=None, cancel_url=None, webhook_url=None):
    """
    Creates an automated checkout session with UddoktaPay v2 API.
    Redirects customer to UddoktaPay's official hosted payment page.
    No simulation, no fake credits.
    Returns: (success: bool, payment_url: str or error_message: str)
    """
    cfg = get_uddoktapay_config()
    if not cfg["api_key"]:
        return False, "UddoktaPay API key is not configured. Please enter your UddoktaPay API key in the Admin Panel or config.json."

    full_name = client.get("name") or client.get("company") or "LeadPulse User"
    email = client.get("email") or "client@leadpulse.ai"
    amount = package.get("price_bdt", 500)

    payload = {
        "full_name": full_name,
        "email": email,
        "amount": amount,
        "metadata": {
            "client_id": client.get("id"),
            "package_id": package.get("id"),
            "credits": package.get("credits"),
            "timestamp": datetime.now().isoformat()
        },
        "redirect_url": redirect_url or "http://localhost:5055/?payment=success",
        "cancel_url": cancel_url or "http://localhost:5055/?payment=cancelled",
        "webhook_url": webhook_url or "http://localhost:5055/api/payment/uddoktapay/webhook"
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            cfg["base_url"],
            data=data,
            headers={
                "RT-UDDOKTAPAY-API-KEY": cfg["api_key"],
                "Content-Type": "application/json",
                "User-Agent": "LeadPulse-AI/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            if res_data.get("status") and res_data.get("payment_url"):
                return True, res_data["payment_url"]
            return False, res_data.get("message", "Failed to initialize UddoktaPay payment session.")
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return False, err_body.get("message", str(e))
        except Exception:
            return False, f"UddoktaPay API Error: HTTP {e.code}"
    except Exception as e:
        return False, f"Connection error to UddoktaPay: {str(e)}"

def verify_uddoktapay_invoice(invoice_id: str):
    """
    Verifies payment directly with UddoktaPay v2 verify API.
    Returns: (success: bool, message: str, payment_info: dict)
    """
    cfg = get_uddoktapay_config()
    if not cfg["api_key"]:
        return False, "UddoktaPay API key is not configured.", {}

    if not invoice_id:
        return False, "Missing invoice_id.", {}

    try:
        payload = json.dumps({"invoice_id": invoice_id}).encode("utf-8")
        req = urllib.request.Request(
            cfg["verify_url"],
            data=payload,
            headers={
                "RT-UDDOKTAPAY-API-KEY": cfg["api_key"],
                "Content-Type": "application/json",
                "User-Agent": "LeadPulse-AI/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            status = (res_data.get("status") or "").upper()
            if status == "COMPLETED":
                metadata = res_data.get("metadata", {})
                client_id = metadata.get("client_id")
                package_id = metadata.get("package_id")
                trx_id = res_data.get("transaction_id", invoice_id)
                amount = float(res_data.get("amount", 0))

                return True, "Payment verified successfully via UddoktaPay", {
                    "client_id": client_id,
                    "package_id": package_id,
                    "trx_id": trx_id,
                    "amount": amount,
                    "gateway": "uddoktapay",
                    "sender_number": res_data.get("sender_number", "Automated Checkout")
                }
            return False, f"Payment status is {status}, not COMPLETED", res_data
    except Exception as e:
        return False, str(e), {}

def verify_uddoktapay_webhook(data, header_key=""):
    """
    Verifies IPN webhook response from UddoktaPay.
    """
    cfg = get_uddoktapay_config()
    if cfg["is_configured"]:
        if header_key != cfg["api_key"]:
            return False, "Invalid Webhook Signature API Key", {}

    status = (data.get("status") or "").upper()
    if status == "COMPLETED":
        metadata = data.get("metadata", {})
        client_id = metadata.get("client_id")
        package_id = metadata.get("package_id")
        trx_id = data.get("transaction_id", f"UDD_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        amount = float(data.get("amount", 0))

        return True, "Payment verified successfully via UddoktaPay", {
            "client_id": client_id,
            "package_id": package_id,
            "trx_id": trx_id,
            "amount": amount,
            "gateway": "uddoktapay",
            "sender_number": data.get("sender_number", "Automated Gateway")
        }
    return False, f"Payment status is {status}, not COMPLETED", {}
