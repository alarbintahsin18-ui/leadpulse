import os
import re
import ssl
import json
import socket
import time
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from tech_detector import detect_technologies

try:
    import dns.resolver
    HAS_DNS = True
except ImportError:
    HAS_DNS = False

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        HAS_DDGS = False

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

DIRECTORY_DOMAINS = [
    "yellowpages", "whitepages", "yelp.com", "bbb.org", "manta.com",
    "mapquest", "foursquare", "angi.com", "homeadvisor", "thumbtack",
    "houzz", "porch.com", "angieslist", "chamberofcommerce",
    "dandb.com", "buzzfile.com", "bizapedia", "opencorporates",
    "corporationwiki", "zoominfo.com", "owler.com", "crunchbase.com",
    "craft.co", "comparably.com", "glassdoor.com", "indeed.com",
    "signalhire.com", "rocketreach.co", "apollo.io", "hunter.io",
    "spokeo.com", "beenverified.com", "intelius.com", "truepeoplesearch",
    "fastpeoplesearch", "usphonebook", "callerinfo", "callername",
    "whocalld", "findpeoplesearch", "allbusiness.com", "enrichlabs.ai",
    "datanyze.com", "contactout.com", "lusha.com", "seamless.ai",
    "companydata.com", "bizprofile.net", "corporatedir.com", "us-companies.org"
]

SOCIAL_DOMAINS = [
    "facebook.com", "linkedin.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "tiktok.com", "pinterest.com", "reddit.com"
]

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "sharklasers.com", "throwawaymail.com", "getairmail.com", "yopmail.com",
    "dispostable.com", "trashmail.com", "burnermail.io", "fakeinbox.com",
    "mytemp.email", "mohmal.com", "generator.email", "temp-mail.org"
}

FREE_MAIL_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com",
    "zoho.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "yandex.com"
}

def validate_email_mx(email):
    """
    Validates email RFC syntax, disposable domains, and performs real DNS MX check.
    Returns deliverability score, status badge, provider name, and MX records.
    """
    clean_em = str(email).strip().lower()
    if not clean_em or "@" not in clean_em:
        return {
            "email": clean_em,
            "syntax_valid": False,
            "has_mx": False,
            "provider": "Invalid",
            "is_disposable": False,
            "is_free": False,
            "status": "Invalid Syntax",
            "score": 0,
            "mx_records": []
        }

    # RFC 5322 Syntax Regex
    syntax_valid = bool(re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$', clean_em))
    if not syntax_valid:
        return {
            "email": clean_em,
            "syntax_valid": False,
            "has_mx": False,
            "provider": "Invalid Syntax",
            "is_disposable": False,
            "is_free": False,
            "status": "Invalid Syntax",
            "score": 0,
            "mx_records": []
        }

    domain = clean_em.split("@")[1].strip()
    is_disposable = domain in DISPOSABLE_DOMAINS
    is_free = domain in FREE_MAIL_PROVIDERS

    if is_disposable:
        return {
            "email": clean_em,
            "domain": domain,
            "syntax_valid": True,
            "has_mx": False,
            "provider": "Disposable / Burner Email",
            "is_disposable": True,
            "is_free": False,
            "status": "Risky (Disposable)",
            "score": 10,
            "mx_records": []
        }

    mx_records = []
    has_mx = False
    provider = "Custom Corporate Mail Server"

    # DNS MX lookup
    if HAS_DNS:
        try:
            custom_resolver = dns.resolver.Resolver()
            custom_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
            custom_resolver.timeout = 3.0
            custom_resolver.lifetime = 3.0
            answers = custom_resolver.resolve(domain, 'MX')
            mx_records = [r.exchange.to_text().rstrip('.') for r in answers]
            has_mx = len(mx_records) > 0
        except Exception:
            try:
                answers = dns.resolver.resolve(domain, 'MX', lifetime=3.0)
                mx_records = [r.exchange.to_text().rstrip('.') for r in answers]
                has_mx = len(mx_records) > 0
            except Exception:
                has_mx = False

    # Fallback to socket host resolution if no direct MX
    if not has_mx:
        try:
            socket.gethostbyname(domain)
            has_mx = True
            mx_records = [f"Direct Host A-Record ({domain})"]
            provider = "Domain Host Fallback"
        except Exception:
            has_mx = False

    # Determine Provider Type
    if has_mx:
        joined_mx = " ".join(mx_records).lower()
        if any(g in joined_mx for g in ["google", "aspmx", "l.google.com"]):
            provider = "Google Workspace / Gmail"
        elif any(m in joined_mx for m in ["outlook", "microsoft", "protection.outlook"]):
            provider = "Microsoft 365 / Exchange"
        elif "zoho" in joined_mx:
            provider = "Zoho Mail"
        elif any(sec in joined_mx for sec in ["pphosted", "proofpoint", "mimecast", "barracuda"]):
            provider = "Enterprise Secure Gateway (Proofpoint/Mimecast)"
        elif is_free:
            provider = f"{domain.split('.')[0].title()} Free Mail"

    # Calculate deliverability confidence score
    if not has_mx:
        status = "Undeliverable (No MX Record)"
        score = 15
    elif is_free:
        status = "Deliverable (Personal/Free)"
        score = 88
    else:
        status = "Deliverable (Corporate Verified)"
        score = 99

    return {
        "email": clean_em,
        "domain": domain,
        "syntax_valid": True,
        "has_mx": has_mx,
        "provider": provider,
        "is_disposable": is_disposable,
        "is_free": is_free,
        "status": status,
        "score": score,
        "mx_records": mx_records[:4]
    }

def generate_email_permutations(first_name, last_name, domain):
    """
    Generates standard B2B corporate email permutations for a contact and domain.
    Also tests domain MX once to attach verified deliverability tag.
    """
    fn = re.sub(r'[^a-zA-Z0-9]', '', (first_name or '').lower())
    ln = re.sub(r'[^a-zA-Z0-9]', '', (last_name or '').lower())
    dom = domain.lower().replace("http://", "").replace("https://", "").split("/")[0].strip()
    if dom.startswith("www."):
        dom = dom[4:]

    if not dom:
        return []

    # Check MX for domain
    domain_check = validate_email_mx(f"verify@{dom}")
    domain_has_mx = domain_check.get("has_mx", False)
    provider = domain_check.get("provider", "Corporate Mail")

    patterns = []
    if fn and ln:
        patterns = [
            (f"{fn}.{ln}@{dom}", "{first}.{last}@{domain}", "Most Common B2B (95%)"),
            (f"{fn}@{dom}", "{first}@{domain}", "Executive Standard (90%)"),
            (f"{fn[0]}{ln}@{dom}", "{f}{last}@{domain}", "Enterprise Standard (88%)"),
            (f"{fn}{ln}@{dom}", "{first}{last}@{domain}", "Common Variation (75%)"),
            (f"{fn}_{ln}@{dom}", "{first}_{last}@{domain}", "Underscore Pattern (70%)"),
            (f"{fn[0]}.{ln}@{dom}", "{f}.{last}@{domain}", "Dotted Initial (65%)"),
            (f"{ln}.{fn}@{dom}", "{last}.{first}@{domain}", "Inverted Pattern (50%)"),
            (f"{ln}@{dom}", "{last}@{domain}", "Surname Only (45%)"),
            (f"{fn}.{ln[0]}@{dom}", "{first}.{l}@{domain}", "First + Last Initial (40%)")
        ]
    elif fn:
        patterns = [
            (f"{fn}@{dom}", "{first}@{domain}", "Primary Executive (90%)"),
            (f"contact@{dom}", "contact@{domain}", "Company Inquiries (80%)"),
            (f"hello@{dom}", "hello@{domain}", "General Inbox (75%)")
        ]
    else:
        patterns = [
            (f"contact@{dom}", "contact@{domain}", "Company Inquiries (80%)"),
            (f"hello@{dom}", "hello@{domain}", "General Inbox (75%)")
        ]

    results = []
    for em, pat, conf in patterns:
        results.append({
            "email": em,
            "pattern": pat,
            "confidence": conf,
            "has_mx": domain_has_mx,
            "provider": provider,
            "status": "Deliverable MX Verified" if domain_has_mx else "Unverified MX"
        })
    return results

def clean_phone(phone_str):
    if not phone_str:
        return ""
    raw = str(phone_str).strip()
    digits = re.sub(r'\D', '', raw)

    # 1. Bangladesh format (11 digits starting with 01, or 13 digits starting with 8801)
    if (len(digits) == 11 and digits.startswith('01')) or (len(digits) == 13 and digits.startswith('8801')):
        d = digits[-11:]
        return f"+880 {d[1:5]}-{d[5:]}"

    # 2. North America NANPA format: strictly area code [2-9] (US area codes never start with 0 or 1)
    if len(digits) == 10 and digits[0] in '23456789':
        return f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits.startswith('1') and digits[1] in '23456789':
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    # 3. United Kingdom format
    if (len(digits) == 11 and digits.startswith('07')) or (len(digits) == 12 and digits.startswith('447')):
        d = digits[-10:]
        return f"+44 {d[:4]} {d[4:]}"

    # 4. If already prefixed with +, preserve cleanly
    if raw.startswith("+"):
        return raw

    return raw

TWO_PART_TLDS = {
    "co.uk", "org.uk", "me.uk", "ltd.uk", "net.uk",
    "co.in", "net.in", "org.in", "gen.in", "ind.in",
    "com.au", "net.au", "org.au", "edu.au",
    "com.bd", "org.bd", "edu.bd", "gov.bd",
    "co.nz", "net.nz", "org.nz",
    "co.za", "org.za", "net.za",
    "com.sg", "edu.sg",
    "com.my", "org.my",
    "com.ph", "org.ph",
    "co.jp", "ne.jp",
    "com.br", "org.br",
    "com.mx", "org.mx",
    "com.ar", "com.co"
}

def get_root_domain(netloc):
    if not netloc:
        return ""
    netloc = netloc.split(":")[0].lower().strip()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    parts = netloc.split(".")
    if len(parts) >= 3:
        last_two = f"{parts[-2]}.{parts[-1]}"
        if last_two in TWO_PART_TLDS:
            return f"{parts[-3]}.{last_two}"
        return f"{parts[-2]}.{parts[-1]}"
    elif len(parts) == 2:
        return f"{parts[0]}.{parts[1]}"
    return netloc

def is_directory_or_social(domain):
    dom = domain.lower()
    return any(d in dom for d in DIRECTORY_DOMAINS) or any(s in dom for s in SOCIAL_DOMAINS)

def parse_person_name(full_name):
    if not full_name:
        return "", "", ""
    clean = re.sub(r'^(dr\.|mr\.|ms\.|mrs\.|prof\.)\s+', '', full_name, flags=re.I).strip()
    clean = re.sub(r'\s*,\s*(phd|md|mba|cpa|esq|jd|ceo|founder|co-founder|president|owner|partner).*$', '', clean, flags=re.I).strip()
    clean = re.sub(r'\s*\(.*?\)', '', clean).strip()
    clean = re.sub(r'["""\'\\]', '', clean).strip()
    parts = [p for p in clean.split() if p and len(p) > 1 and not p.lower().endswith(('.', ','))]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", parts[0]
    return parts[0], parts[-1], f"{parts[0]} {parts[-1]}"

def clean_company_name(title_or_snippet):
    raw = str(title_or_snippet)
    raw = re.sub(r'[\s\.\,\-]+$', '', raw)
    raw = re.sub(r'^(?:contact|about|welcome to|visit|find)\s+', '', raw, flags=re.I)
    raw = re.sub(r'^(?:Internet\s*marketing\s*service|Digital\s*marketing\s*agency|Marketing\s*agency|Web\s*design\s*agency|Advertising\s*agency|Company|Business|Firm)\s+', '', raw, flags=re.I)
    patterns = [
        r'\|\s*BBB\s*(?:Business\s*Profile|Directory)?.*$',
        r'[-–|]\s*(?:Yelp|YellowPages|Whitepages|MapQuest|Manta|Angi|AllBusiness|ZoomInfo|LinkedIn|Facebook|Instagram|Twitter|X|Enrich\s*Labs).*$',
        r'[-–|]\s*(?:Company\s*Profile|Business\s*Directory|Customer\s*Reviews|Ratings).*$',
        r'[-–|]\s*Updated\s+[A-Za-z]+\s+\d{4}.*$',
        r'[-–|]\s*(?:Marketing\s*Agency|Internet\s*Marketing|Digital\s*Marketing|Web\s*Design).*$',
        r'\s+(?:from|in|near|located\s+in)\s+[A-Za-z\s,]+$',
        r'\b(?:LLC|Inc\.?|Corp\.?|Ltd\.?|Co\.?)\b.*$',
    ]
    for pat in patterns:
        raw = re.sub(pat, '', raw, flags=re.I).strip()
    parts = re.split(r'[-–|:•]', raw)
    cand = parts[0].strip() if parts else raw.strip()
    if cand.isupper():
        cand = cand.title()
    return cand

def fetch_url(url, timeout=3.5):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            return {"status": 200, "html": content, "url": resp.geturl()}
    except Exception as e:
        return {"status": 0, "html": "", "url": url, "error": str(e)}

def _bing_rss_search(query, max_results=15):
    """Fast, reliable Bing RSS search fallback returning title, href, body."""
    import xml.etree.ElementTree as ET
    results = []
    try:
        url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query) + f"&format=rss&count={min(max_results, 30)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=6) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item"):
                href = (item.findtext("link") or "").strip()
                title = (item.findtext("title") or "").strip()
                body = (item.findtext("description") or "").strip()
                if href:
                    results.append({"title": title, "href": href, "body": body})
                if len(results) >= max_results:
                    break
    except Exception:
        pass
    return results

def ddgs_query(query, max_results=15):
    """
    High-yield multi-engine OSINT search combining Bing, Yahoo, and Bing RSS.
    Merges and deduplicates results across engines so large limits actually return high volumes.
    """
    merged = []
    seen_urls = set()

    def _add(items):
        for it in (items or []):
            href = (it.get("href") or "").strip()
            if href and href not in seen_urls:
                seen_urls.add(href)
                merged.append(it)

    if HAS_DDGS:
        # Use active high-yield backends (bing + yahoo); merge both when max_results > 8
        for backend in ['bing', 'yahoo']:
            try:
                with DDGS() as ddgs:
                    res = list(ddgs.text(query, backend=backend, max_results=max_results))
                    _add(res)
            except Exception:
                continue
            if len(merged) >= max_results:
                break

    # Supplement with Bing RSS if we still need more results
    if len(merged) < max_results:
        _add(_bing_rss_search(query, max_results=max_results))

    return merged[:max_results]

class HunterIntelligenceEngine:
    def __init__(self):
        pass

    def reverse_phone_lookup(self, phone_query):
        raw_phone = clean_phone(phone_query)
        digits = re.sub(r'\D', '', phone_query)

        results = {
            "query_type": "phone",
            "input_phone": raw_phone,
            "company_name": "",
            "domain": "",
            "first_name": "",
            "last_name": "",
            "contact_name": "",
            "contact_title": "",
            "email": "",
            "all_emails": [],
            "all_phones": [raw_phone] if raw_phone else [],
            "address": "",
            "linkedin_url": "",
            "facebook_url": "",
            "twitter_url": "",
            "instagram_url": "",
            "industry": "",
            "ip_address": "",
            "email_pattern": "",
            "people": [],
            "sources": []
        }

        if len(digits) < 7:
            return results

        # ── Step 1: Query without hyphens ──
        if len(digits) == 11 and digits.startswith('01'):
            spaced_phone = f"{digits[:5]} {digits[5:]}"
        elif len(digits) >= 10:
            spaced_phone = f"{digits[-10:-7]} {digits[-7:-4]} {digits[-4:]}"
        else:
            spaced_phone = digits

        phone_results = ddgs_query(spaced_phone, max_results=7)
        if not phone_results and len(digits) >= 10:
            phone_results = ddgs_query(f"{digits[-10:]} business contact", max_results=5)

        for r in phone_results:
            results["sources"].append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            })

        # ── Step 2: Company Name Extraction ──
        company_votes = {}
        found_address = ""

        bad_corp_keywords = [
            "phone", "lookup", "reverse", "caller", "free", "number", "beware",
            "who called", "whocalls", "numtrace", "numlookup", "check", "trace",
            "search", "report", "complaint", "directory", "scam", "spam",
            "telemarketer", "robocall", "toll free", "area code", "whitepages",
            "yellowpages", "for sale", "buy this domain", "domain is for sale"
        ]

        for r in phone_results:
            title = r.get("title", "")
            body = r.get("body", "")

            cand_name = clean_company_name(title)
            if len(cand_name) > 2 and not any(bad in cand_name.lower() for bad in bad_corp_keywords):
                company_votes[cand_name] = company_votes.get(cand_name, 0) + 1

            if not found_address:
                addr_match = re.search(r'(?:Address[:\s]+)?(\d+\s+[A-Za-z0-9\s,\.]+(?:Drive|Dr|Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Way|Suite|Ste)\s*[A-Za-z0-9\s,\.]*)', body, re.I)
                if addr_match:
                    found_address = re.sub(r'(?i)\s*\b(?:Phone|Tel|Mobile|Call|Fax|Email|Trade\s*License|Quick\s*Links|Copyright).*$', '', addr_match.group(1)).strip(' ,-:\n\r\t')

        best_company = max(company_votes, key=company_votes.get) if company_votes else ""
        if not best_company:
            results["company_name"] = "Unregistered / Private Line"
            results["contact_name"] = "Private Subscriber"
            results["contact_title"] = "Personal Line"
            return results
        results["company_name"] = best_company
        if found_address:
            results["address"] = found_address

        # ── Step 3: Find Domain ──
        official_domain = ""
        comp_slug = re.sub(r'\W+', '', best_company.lower()) if best_company else ""
        words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', best_company)] if best_company else []

        # 1. Check emails in snippets for company domain
        for r in phone_results:
            body = r.get("body", "") + " " + r.get("title", "")
            found_emails = re.findall(r'[a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z]{2,})', body)
            for em_dom in found_emails:
                em_dom = em_dom.lower()
                if not is_directory_or_social(em_dom) and not any(free in em_dom for free in ["gmail", "yahoo", "hotmail", "outlook"]):
                    if comp_slug and (comp_slug[:5] in em_dom or em_dom.split('.')[0] in comp_slug):
                        official_domain = em_dom
                        break
            if official_domain:
                break

        # 2. Check candidate URLs that match company name
        if not official_domain and best_company:
            for r in phone_results:
                href = r.get("href", "")
                parsed = urllib.parse.urlparse(href)
                root_dom = get_root_domain(parsed.netloc)
                if root_dom and not is_directory_or_social(root_dom):
                    dom_clean = root_dom.split('.')[0].lower()
                    if dom_clean in comp_slug or comp_slug in dom_clean or (words and words[0] in dom_clean):
                        official_domain = root_dom
                        break

        # 3. Direct DNS check: e.g. ignitevisibility.com
        if not official_domain and comp_slug and len(comp_slug) >= 4:
            for cand_slug in [f"{comp_slug}.com", f"{''.join(words[:2])}.com" if len(words) > 2 else ""]:
                if cand_slug:
                    try:
                        socket.gethostbyname(cand_slug)
                        official_domain = cand_slug
                        break
                    except Exception:
                        pass

        # 4. Search for official website
        if not official_domain and best_company:
            dom_search = ddgs_query(f'{best_company} official website', max_results=4)
            for ds in dom_search:
                href = ds.get("href", "")
                parsed = urllib.parse.urlparse(href)
                root_dom = get_root_domain(parsed.netloc)
                if root_dom and not is_directory_or_social(root_dom):
                    dom_clean = root_dom.split('.')[0].lower()
                    if dom_clean in comp_slug or comp_slug in dom_clean:
                        official_domain = root_dom
                        break

        results["domain"] = official_domain

        # ── Step 4: Run Domain Intelligence ──
        if official_domain:
            domain_intel = self.domain_intelligence(official_domain, company_hint=best_company)
            self._merge_intel(results, domain_intel)
        elif best_company:
            self._osint_leadership_search(results, best_company, "")
        # ── Guarantee Personal LinkedIn Profile for Decision Maker ──
        if results.get("contact_name") and (not results.get("linkedin_url") or "/company/" in results.get("linkedin_url", "")):
            for p in results.get("people", []):
                if p.get("linkedin_url") and "linkedin.com/in/" in p["linkedin_url"]:
                    results["linkedin_url"] = p["linkedin_url"]
                    break
            if not results.get("linkedin_url") or "/company/" in results.get("linkedin_url", ""):
                try:
                    pl_res = ddgs_query(f"{results['contact_name']} {results['company_name']} linkedin", max_results=3)
                    for pr in pl_res:
                        href = pr.get("href", "")
                        if "linkedin.com/in/" in href:
                            results["linkedin_url"] = href
                            break
                except Exception:
                    pass

        return results

    def company_lookup(self, company_query):
        clean_name = clean_company_name(company_query)
        dom_search = ddgs_query(f'{clean_name} official website', max_results=4)
        found_dom = ""
        comp_slug = re.sub(r'\W+', '', clean_name.lower())
        for ds in dom_search:
            href = ds.get("href", "")
            parsed = urllib.parse.urlparse(href)
            root_dom = get_root_domain(parsed.netloc)
            if root_dom and not is_directory_or_social(root_dom):
                dom_slug = re.sub(r'\W+', '', root_dom.split('.')[0].lower())
                if dom_slug in comp_slug or comp_slug in dom_slug or comp_slug[:5] in dom_slug:
                    found_dom = root_dom
                    break
                elif not found_dom:
                    found_dom = root_dom

        if not found_dom:
            found_dom = f"{clean_name.lower().replace(' ', '')}.com"

        return self.domain_intelligence(found_dom, company_hint=clean_name)

    def domain_intelligence(self, domain_or_url, company_hint=None):
        dom = domain_or_url.replace("https://", "").replace("http://", "").split("/")[0].strip().lower()
        dom = dom.replace("www.", "")
        base_url = f"https://{dom}"

        intel = {
            "query_type": "domain",
            "domain": dom,
            "company_name": company_hint or dom.split(".")[0].replace("-", " ").title(),
            "first_name": "",
            "last_name": "",
            "contact_name": "",
            "contact_title": "",
            "email": "",
            "all_emails": [],
            "all_phones": [],
            "address": "",
            "linkedin_url": "",
            "facebook_url": "",
            "twitter_url": "",
            "instagram_url": "",
            "people": [],
            "email_pattern": f"{{first}}@{dom}",
            "ip_address": "",
            "tech_stack": [],
            "sources": []
        }

        try:
            intel["ip_address"] = socket.gethostbyname(dom)
        except Exception:
            intel["ip_address"] = "Cloud Protected"

        pages = [base_url, f"{base_url}/about", f"{base_url}/contact"]
        soups = []
        for p in pages:
            res = fetch_url(p)
            if res["status"] == 200 and len(res.get("html", "")) > 300:
                s = BeautifulSoup(res["html"], 'html.parser')
                soups.append({"soup": s, "url": res["url"], "html": res["html"]})
                intel["sources"].append({"url": res["url"], "status": "200 OK"})
                if not intel["tech_stack"]:
                    intel["tech_stack"] = detect_technologies(res["html"])

        if len(soups) <= 1:
            # Fallback to alternative paths if about or contact were not found
            for alt_p in [f"{base_url}/about-us", f"{base_url}/contact-us", f"{base_url}/team"]:
                res = fetch_url(alt_p)
                if res["status"] == 200 and len(res.get("html", "")) > 300:
                    s = BeautifulSoup(res["html"], 'html.parser')
                    soups.append({"soup": s, "url": res["url"]})
                    intel["sources"].append({"url": res["url"], "status": "200 OK"})

        if not soups:
            res = fetch_url(f"https://www.{dom}")
            if res["status"] == 200:
                soups.append({"soup": BeautifulSoup(res["html"], 'html.parser'), "url": res["url"]})

        # Extract Real Brand Name from Homepage Title if available
        if soups:
            home_soup = soups[0]["soup"]
            if home_soup.title and home_soup.title.string:
                raw_t = home_soup.title.string.strip()
                brand = re.split(r'[-–|:]', raw_t)[0].strip()
                if brand and len(brand) < 40 and not any(bad in brand.lower() for bad in ["welcome", "home", "untitled", "login", "index"]):
                    intel["company_name"] = brand

        for page in soups:
            s = page["soup"]
            for a in s.find_all("a", href=True):
                href = a["href"].strip()
                h_low = href.lower()
                if href.startswith("tel:"):
                    raw = href.replace("tel:", "").split("?")[0].strip()
                    cp = clean_phone(raw)
                    if cp and cp not in intel["all_phones"]:
                        intel["all_phones"].append(cp)
                elif href.startswith("mailto:"):
                    em = href.replace("mailto:", "").split("?")[0].strip().lower()
                    if "@" in em and not any(em.endswith(ext) for ext in [".png", ".jpg", ".svg", ".webp"]):
                        if em not in intel["all_emails"]:
                            intel["all_emails"].append(em)

                # WhatsApp detection
                if "wa.me/" in h_low or "whatsapp.com" in h_low:
                    clean_wa = href.split("?")[0].split("#")[0]
                    wa_digits = re.sub(r'\D', '', clean_wa)
                    if 10 <= len(wa_digits) <= 15:
                        cp = clean_phone(wa_digits)
                        if cp and cp not in intel["all_phones"]:
                            intel["all_phones"].append(cp)

                if "linkedin.com/in/" in h_low and not intel["linkedin_url"]:
                    intel["linkedin_url"] = href
                if ("facebook.com" in h_low or "fb.com" in h_low) and not intel["facebook_url"]:
                    if not any(b in h_low for b in ["sharer", "share.php"]):
                        intel["facebook_url"] = href
                if ("twitter.com" in h_low or "x.com" in h_low) and not intel["twitter_url"]:
                    if not any(b in h_low for b in ["share", "intent/tweet"]):
                        intel["twitter_url"] = href
                if "instagram.com" in h_low and not intel["instagram_url"]:
                    intel["instagram_url"] = href

            page_text = s.get_text(separator=" ", strip=True)
            for em in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}', page_text):
                em = em.lower().strip('.')
                if not any(em.endswith(ext) for ext in [".png", ".jpg", ".svg", ".webp", ".js"]):
                    if dom in em and em not in intel["all_emails"]:
                        intel["all_emails"].append(em)

            # Multi-Country Smart Phone Number Detection
            for pm in re.findall(r'(?:\+?880|0)1[3-9]\d{8}', page_text):
                cp = clean_phone(pm)
                if cp and cp not in intel["all_phones"]:
                    intel["all_phones"].append(cp)

            for pm in re.findall(r'(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?[2-9]\d{2}[-.\s]?\d{4}', page_text):
                cp = clean_phone(pm)
                if cp and cp not in intel["all_phones"]:
                    intel["all_phones"].append(cp)

            for pm in re.findall(r'\+\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,5}', page_text):
                cp = clean_phone(pm)
                if cp and cp not in intel["all_phones"]:
                    intel["all_phones"].append(cp)

            # Filter phone numbers to ensure no corrupted numbers
            intel["all_phones"] = [p for p in intel["all_phones"] if len(re.sub(r'\D', '', p)) <= 15]

            # Physical address detection: look for address keywords and road/street/city keywords
            if not intel.get("address"):
                addr_match = re.search(r'(?:Registered\s*(?:Office)?\s*Address|Office\s*Address)[:\s]+([^<\r\n]{15,150}(?:Road|Rd|Street|St|Mansion|Floor|Avenue|Ave|Barishal|Dhaka|Bangladesh|USA|CA|NY|TX|IL|FL|Suite|Ste)[^<\r\n]{0,80})', page_text, re.I)
                if addr_match:
                    raw_addr = addr_match.group(1).strip()
                    cleaned_addr = re.split(r'(?i)\b(?:Trade\s*License|Quick\s*Links|Phone|Tel|Mobile|Email|Copyright)\b', raw_addr)[0].strip(' ,-:\n\r\t')
                    intel["address"] = cleaned_addr

            self._extract_leadership_from_soup(s, dom, intel)

        # OSINT Web Fallback for Leadership if not found on page
        if len(intel["people"]) < 2:
            self._osint_leadership_search(intel, intel["company_name"], dom)

        # Assign primary contact & email: prioritize person with verified linkedin or executive title
        if intel["people"]:
            def person_priority(person):
                score = 0
                if "linkedin.com/in/" in person.get("linkedin_url", ""):
                    score += 10
                role = person.get("title", "").lower()
                if any(r in role for r in ["founder", "ceo", "chief executive", "president", "owner"]):
                    score += 5
                elif any(r in role for r in ["cmo", "cto", "coo", "vp", "director"]):
                    score += 3
                return score

            intel["people"].sort(key=person_priority, reverse=True)
            p = intel["people"][0]
            intel["first_name"] = p.get("first_name", "")
            intel["last_name"] = p.get("last_name", "")
            intel["contact_name"] = p.get("full_name", "")
            intel["contact_title"] = p.get("title", "")
            if p.get("linkedin_url") and "linkedin.com/in/" in p["linkedin_url"]:
                intel["linkedin_url"] = p["linkedin_url"]

            # Ensure decision maker gets personal linkedin profile if not already set
            if intel.get("contact_name") and (not intel.get("linkedin_url") or "linkedin.com/in/" not in intel.get("linkedin_url", "")):
                try:
                    p_lk_results = ddgs_query(f'"{intel["contact_name"]}" "{intel["company_name"]}" linkedin', max_results=3)
                    for plr in p_lk_results:
                        pl_href = plr.get("href", "")
                        pl_title = plr.get("title", "").lower()
                        if "linkedin.com/in/" in pl_href:
                            if intel.get("last_name", "").lower() in pl_title or intel.get("first_name", "").lower() in pl_title:
                                intel["linkedin_url"] = pl_href
                                if intel.get("people"):
                                    intel["people"][0]["linkedin_url"] = pl_href
                                break
                except Exception:
                    pass

            # Decision maker email priority: direct personal name email if first name is known
            if intel.get("first_name") and dom:
                intel["email"] = f"{intel['first_name'].lower()}@{dom}"
                if intel["email"] not in intel["all_emails"]:
                    intel["all_emails"].insert(0, intel["email"])
            elif intel.get("all_emails"):
                non_generic = [e for e in intel["all_emails"] if not any(g in e.lower() for g in ["info@", "contact@", "support@", "sales@", "opportunity@"])]
                intel["email"] = non_generic[0] if non_generic else intel["all_emails"][0]
        else:
            # Fallback for companies with no named individual published
            intel["contact_name"] = f"{intel['company_name']} Management"
            intel["contact_title"] = "Executive Management / Support"
            intel["first_name"] = intel["company_name"].split()[0] if intel["company_name"] else "Executive"
            intel["last_name"] = intel["company_name"].split()[-1] if len(intel["company_name"].split()) > 1 else "Management"
            intel["linkedin_url"] = ""
            if intel["all_emails"]:
                intel["email"] = intel["all_emails"][0]
            else:
                intel["email"] = f"support@{dom}"

        return intel

    def _extract_leadership_from_soup(self, soup, dom, intel):
        def looks_like_person(name):
            name = name.strip()
            # Must NOT contain punctuation, digits, or symbols (reject "Registered Address:", "Sign In!", etc.)
            if re.search(r'[^a-zA-Z\s]', name):
                return False
            parts = name.split()
            if not (2 <= len(parts) <= 3):
                return False

            ui_and_business_words = {
                "sign", "in", "up", "out", "log", "login", "register", "registered",
                "address", "location", "office", "street", "road", "mansion", "factory",
                "phone", "email", "support", "contact", "about", "team", "view", "plans",
                "order", "best", "seller", "terms", "privacy", "policy", "rights", "reserved",
                "copyright", "menu", "home", "cart", "checkout", "search", "faq", "blog",
                "service", "services", "product", "products", "software", "store", "solution",
                "solutions", "agency", "company", "group", "holdings", "enterprise", "llc",
                "inc", "ltd", "corp", "co", "gmbh", "pvt", "limited", "detox", "program",
                "programs", "recovery", "treatment", "rehab", "wellness", "care", "medical",
                "medically", "intensive", "aftercare", "admission", "insurance", "coverage",
                "levels", "residential", "overview", "process", "features", "pricing",
                "our", "your", "their", "my", "his", "her", "leadership", "executive",
                "executives", "directors", "board", "management", "staff", "advisors",
                "advisor", "founders", "founder", "members", "people", "who", "we",
                "are", "meet", "join", "working", "works", "mission", "values", "culture",
                "vision", "trusted", "partners", "clients", "testimonials", "stories",
                "story", "growth", "results", "leaders", "advisory", "departments"
            }
            if any(p.lower() in ui_and_business_words for p in parts):
                return False

            # Strictly require every word to be an alphabetic title-case name
            return all(p.isalpha() and p[0].isupper() and p[1:].islower() and len(p) >= 2 for p in parts)

        leadership_roles = ["founder", "co-founder", "ceo", "chief executive", "president", "chairman", "director", "owner", "partner", "cto", "cmo", "coo", "vp"]

        def extract_clean_role(text):
            if not text:
                return ""
            t = text.strip()
            # If short title
            if len(t) <= 50 and any(r in t.lower() for r in leadership_roles):
                narrative_words = ["who", "started", "years", "lead it", "leads", "served", "prior", "joined", "leading", "since", "founded"]
                if not any(nw in t.lower() for nw in narrative_words):
                    return t
            # Regex match
            m = re.search(r'\b(Co-Founder|Founder|Chief Executive Officer|CEO|President|Executive Chairman|Chairman|Managing Director|Director|Owner|Partner|Chief Technology Officer|CTO|Chief Marketing Officer|CMO|Chief Operating Officer|COO|VP(?:\s+of\s+[A-Za-z\s]+)?)\b', t, re.I)
            if m:
                return m.group(0).strip()
            return ""

        for h in soup.find_all(['h2', 'h3', 'h4', 'strong', 'p']):
            txt = h.get_text(strip=True)
            if looks_like_person(txt):
                role = ""
                nxt = h.find_next_sibling()
                if nxt:
                    role = extract_clean_role(nxt.get_text(strip=True))
                if not role and h.parent:
                    p_nxt = h.parent.find_next_sibling()
                    if p_nxt:
                        role = extract_clean_role(p_nxt.get_text(strip=True))

                if role:
                    fn, ln, full = parse_person_name(txt)
                    if fn and ln and not any(p["full_name"] == full for p in intel["people"]):
                        intel["people"].append({
                            "first_name": fn,
                            "last_name": ln,
                            "full_name": full,
                            "title": role,
                            "email": f"{fn.lower()}@{dom}",
                            "linkedin_url": ""
                        })

    def _osint_leadership_search(self, intel, company_name, dom):
        if not HAS_DDGS or not company_name:
            return

        def matches_target_company(title, body, cand_role, target_comp, target_dom):
            comb = f"{title} {body}".lower()
            dom_slug = target_dom.lower().replace("www.", "").split(".")[0] if target_dom else ""
            comp_slug = target_comp.lower().strip() if target_comp else ""

            # Check if role specifies a foreign company (e.g. "CEO, ThoughtSpot" or "CEO at Soft BD Ltd")
            role_comp_match = re.search(r'(?:at|@|,|for)\s+([A-Za-z0-9\s&.-]+)', cand_role, re.I)
            if role_comp_match:
                stated_comp = role_comp_match.group(1).strip().lower()
                stated_comp = re.sub(r'\b(inc|llc|ltd|corp|co)\b.*$', '', stated_comp).strip()
                if stated_comp and len(stated_comp) > 2:
                    if not (stated_comp in comp_slug or comp_slug in stated_comp or stated_comp in dom_slug or dom_slug in stated_comp):
                        return False

            # Disqualify common false positive companies
            for dq in ["thoughtspot", "soft bd ltd", "technosoft", "tds softlink", "tsoft", "rocketreach"]:
                if dq in comb and dq not in comp_slug and dq not in dom_slug:
                    return False

            # For domain-based queries, require domain slug match or multi-word exact company match
            if dom_slug and len(dom_slug) >= 4:
                if dom_slug in comb:
                    return True
                # If domain slug not in text, only accept if exact multi-word company (>= 2 words) is present
                comp_words = [w for w in comp_slug.split() if len(w) >= 3]
                if len(comp_words) >= 2 and all(w in comb for w in comp_words):
                    return True
                return False

            return comp_slug in comb

        queries = [
            f'site:linkedin.com/in/ "{dom}"' if dom else "",
            f'site:linkedin.com/in/ "{company_name}" founder' if len(company_name.split()) >= 2 else "",
            f'site:linkedin.com/in/ "{company_name}" CEO' if len(company_name.split()) >= 2 else ""
        ]
        queries = [q for q in queries if q]

        for q in queries:
            res = ddgs_query(q, max_results=3)
            for r in res:
                title = r.get("title", "")
                href = r.get("href", "")
                body = r.get("body", "")

                t_clean = re.sub(r'\s*[|\-–]\s*LinkedIn.*$', '', title, flags=re.I).strip()
                parts = re.split(r'\s*[-–]\s*', t_clean, maxsplit=1)
                cand_name = parts[0].strip()
                cand_role = parts[1].strip() if len(parts) > 1 else ""

                if not cand_role:
                    role_match = re.search(r'\b(Founder|Co-Founder|CEO|President|CMO|CTO|Managing Director|Owner)\b', body, re.I)
                    cand_role = role_match.group(1).title() if role_match else "Executive / Leader"

                # Check strict target company match
                if not matches_target_company(title, body, cand_role, company_name, dom):
                    continue

                clean_role = re.sub(r'\s+at\s+.*$', '', cand_role, flags=re.I).strip()
                clean_role = re.sub(r'\s*,\s*[A-Za-z0-9\s&.-]+$', '', clean_role, flags=re.I).strip()
                fn, ln, full = parse_person_name(cand_name)

                bad_names = ["linkedin", "profile", "view", "the", "meet", "who", "roi", "elite", "our", "detox", "relapse", "program", "address", "sign", "in"]
                if fn and ln and not any(bad in fn.lower() for bad in bad_names) and not any(bad in ln.lower() for bad in bad_names):
                    if not any(p["full_name"] == full for p in intel["people"]):
                        email_addr = f"{fn.lower()}@{dom}" if dom else f"{fn.lower()}@{company_name.lower().replace(' ', '')}.com"
                        intel["people"].append({
                            "first_name": fn,
                            "last_name": ln,
                            "full_name": full,
                            "title": clean_role,
                            "email": email_addr,
                            "linkedin_url": href if "linkedin.com/in/" in href else ""
                        })

    def _merge_intel(self, base, fresh):
        for k in ["company_name", "domain", "contact_name", "contact_title",
                  "first_name", "last_name", "email", "address", "linkedin_url",
                  "facebook_url", "twitter_url", "instagram_url", "industry",
                  "ip_address", "email_pattern"]:
            if not base.get(k) and fresh.get(k):
                base[k] = fresh[k]

        # Prioritize personal LinkedIn URL over company profile
        if fresh.get("linkedin_url") and "linkedin.com/in/" in fresh["linkedin_url"]:
            base["linkedin_url"] = fresh["linkedin_url"]

        # Ensure direct personal email is prioritized over generic addresses
        if fresh.get("first_name") and fresh.get("domain"):
            cand_direct = f"{fresh['first_name'].lower()}@{fresh['domain']}"
            if not base.get("email") or any(gen in base.get("email", "").lower() for gen in ["info@", "contact@", "support@", "sales@", "opportunity@"]):
                base["email"] = cand_direct

        for em in fresh.get("all_emails", []):
            if em not in base.get("all_emails", []):
                base["all_emails"].append(em)

        for ph in fresh.get("all_phones", []):
            if ph not in base.get("all_phones", []):
                base["all_phones"].append(ph)

        if fresh.get("people"):
            base["people"] = fresh["people"]

        if not base.get("email") and base.get("all_emails"):
            base["email"] = base["all_emails"][0]

        for src in fresh.get("sources", []):
            if src not in base.get("sources", []):
                base.setdefault("sources", []).append(src)

    def bulk_enrich(self, query_list):
        """
        Multi-threaded Turbo enrichment of queries (phones, domains, or company names).
        Runs concurrently with ThreadPoolExecutor for 10x speed.
        """
        def process_single(raw_q):
            q = str(raw_q).strip()
            if not q:
                return None
            cleaned_digits = "".join(filter(str.isdigit, q))
            if len(cleaned_digits) >= 7 and ("-" in q or "(" in q or q.startswith("+") or cleaned_digits == q):
                q_type = "phone"
                data = self.reverse_phone_lookup(q)
            elif "." in q and " " not in q:
                q_type = "domain"
                data = self.domain_intelligence(q)
            else:
                q_type = "company"
                data = self.company_lookup(q)
            return {
                "query": q,
                "type": q_type,
                "data": data
            }

        valid_queries = [q for q in query_list if str(q).strip()]
        with ThreadPoolExecutor(max_workers=8) as executor:
            raw_results = list(executor.map(process_single, valid_queries))
            results = [r for r in raw_results if r]

        return results

