import re
from urllib.parse import urlparse

TECH_RULES = {
    "CMS & Platforms": [
        {"name": "Shopify", "pattern": r'(?:cdn\.shopify\.com|window\.Shopify|Shopify\.theme|myshopify\.com)', "icon": "fa-brands fa-shopify", "category": "E-Commerce"},
        {"name": "WordPress", "pattern": r'(?:wp-content|wp-includes|generator=["\']WordPress)', "icon": "fa-brands fa-wordpress", "category": "CMS"},
        {"name": "WooCommerce", "pattern": r'(?:woocommerce|wc-cart|wc-api)', "icon": "fa-solid fa-cart-shopping", "category": "E-Commerce"},
        {"name": "Webflow", "pattern": r'(?:website-files\.com|data-wf-site|webflow\.js)', "icon": "fa-solid fa-water", "category": "CMS"},
        {"name": "Wix", "pattern": r'(?:wixstatic\.com|wix\.com|_wix_)', "icon": "fa-brands fa-wix", "category": "Website Builder"},
        {"name": "Squarespace", "pattern": r'(?:squarespace\.com|static1\.squarespace\.com)', "icon": "fa-brands fa-squarespace", "category": "Website Builder"},
        {"name": "Magento", "pattern": r'(?:/static/frontend/|Mage\.Cookies|mage/cookies)', "icon": "fa-brands fa-magento", "category": "E-Commerce"},
        {"name": "Ghost", "pattern": r'(?:ghost-root|generator=["\']Ghost)', "icon": "fa-solid fa-ghost", "category": "CMS"},
        {"name": "PrestaShop", "pattern": r'(?:prestashop|presta)', "icon": "fa-solid fa-bag-shopping", "category": "E-Commerce"},
    ],
    "Frontend Frameworks": [
        {"name": "React", "pattern": r'(?:data-reactroot|react\.development|react\.production|__NEXT_DATA__|_next/)', "icon": "fa-brands fa-react", "category": "Framework"},
        {"name": "Next.js", "pattern": r'(?:_next/static|__NEXT_DATA__)', "icon": "fa-solid fa-n", "category": "Framework"},
        {"name": "Vue.js", "pattern": r'(?:vue\.js|data-v-[a-f0-9]|_nuxt/)', "icon": "fa-brands fa-vuejs", "category": "Framework"},
        {"name": "Nuxt.js", "pattern": r'(?:_nuxt/|window\.__NUXT__)', "icon": "fa-solid fa-mountain", "category": "Framework"},
        {"name": "Angular", "pattern": r'(?:ng-version|ng-app|angular\.js)', "icon": "fa-brands fa-angular", "category": "Framework"},
        {"name": "Tailwind CSS", "pattern": r'(?:tailwindcss|tailwind)', "icon": "fa-solid fa-wind", "category": "CSS"},
        {"name": "Bootstrap", "pattern": r'(?:bootstrap\.min\.css|bootstrap\.bundle)', "icon": "fa-brands fa-bootstrap", "category": "CSS"},
        {"name": "jQuery", "pattern": r'(?:jquery\.min\.js|jquery-[0-9\.]+\.js)', "icon": "fa-solid fa-code", "category": "Library"}
    ],
    "Analytics & Tracking": [
        {"name": "Google Analytics", "pattern": r'(?:googletagmanager\.com|analytics\.js|gtag\(|UA-[0-9]+|G-[A-Z0-9]+)', "icon": "fa-brands fa-google", "category": "Analytics"},
        {"name": "Meta / FB Pixel", "pattern": r'(?:connect\.facebook\.net/en_US/fbevents\.js|fbq\([\'"]init[\'"])', "icon": "fa-brands fa-facebook", "category": "Marketing"},
        {"name": "TikTok Pixel", "pattern": r'(?:analytics\.tiktok\.com|ttq\.load)', "icon": "fa-brands fa-tiktok", "category": "Marketing"},
        {"name": "Hotjar", "pattern": r'(?:static\.hotjar\.com|hotjar-)', "icon": "fa-solid fa-fire", "category": "Heatmaps"},
        {"name": "Klaviyo", "pattern": r'(?:static\.klaviyo\.com|klaviyo\.js)', "icon": "fa-solid fa-envelope-open-text", "category": "Email Marketing"}
    ],
    "Payments & Checkout": [
        {"name": "Stripe", "pattern": r'(?:js\.stripe\.com|stripe\.com)', "icon": "fa-brands fa-stripe", "category": "Payment"},
        {"name": "PayPal", "pattern": r'(?:paypal\.com/sdk|paypalobjects\.com)', "icon": "fa-brands fa-paypal", "category": "Payment"},
        {"name": "bKash / Nagad", "pattern": r'(?:bkash|nagad|sslcommerz)', "icon": "fa-solid fa-wallet", "category": "Payment"}
    ],
    "CDN & Infrastructure": [
        {"name": "Cloudflare", "pattern": r'(?:__cfduid|cf-ray|cloudflare)', "icon": "fa-brands fa-cloudflare", "category": "CDN"},
        {"name": "AWS CloudFront", "pattern": r'(?:cloudfront\.net)', "icon": "fa-brands fa-aws", "category": "CDN"},
        {"name": "Vercel", "pattern": r'(?:x-vercel-id|vercel)', "icon": "fa-solid fa-triangle-exclamation", "category": "Hosting"}
    ]
}

def detect_technologies(html_content, headers=None):
    """
    Detects CMS, Frameworks, Analytics, Payments, and CDN used by a website.
    Returns list of dicts: [{"name": "Shopify", "category": "E-Commerce", "icon": "..."}]
    """
    if not html_content:
        return []

    combined_text = html_content
    if headers and isinstance(headers, dict):
        header_str = " ".join(f"{k}:{v}" for k, v in headers.items())
        combined_text = header_str + " " + combined_text

    detected = []
    seen = set()

    for group, items in TECH_RULES.items():
        for item in items:
            name = item["name"]
            if name in seen:
                continue
            if re.search(item["pattern"], combined_text, re.IGNORECASE):
                detected.append({
                    "name": name,
                    "category": item["category"],
                    "icon": item["icon"],
                    "group": group
                })
                seen.add(name)

    return detected
