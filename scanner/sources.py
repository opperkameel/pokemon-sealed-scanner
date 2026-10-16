"""Fetch product listings from shops. One adapter per shop platform.

Every adapter yields plain dicts:
  {title, price, currency, in_stock, url, context}
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = "Mozilla/5.0 (compatible; PokemonSealedScanner/1.0; price comparison)"


def get_json(url, timeout=25, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or attempt == retries:
                raise
            wait = e.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.isdigit() else 5 * (attempt + 1))
        except (TimeoutError, urllib.error.URLError, ConnectionError):
            if attempt == retries:
                raise
            time.sleep(5 * (attempt + 1))


# ---------- Shopify: public /products.json ----------

def fetch_shopify(shop, delay, max_pages):
    base = shop["url"].rstrip("/")
    path = f"/collections/{shop['collection']}/products.json" if shop.get("collection") else "/products.json"
    for page in range(1, max_pages + 1):
        data = get_json(f"{base}{path}?limit=250&page={page}")
        products = data.get("products", [])
        if not products:
            return
        for p in products:
            context = " ".join([p.get("product_type") or "", p.get("vendor") or "", " ".join(p.get("tags") or [])])
            for v in p.get("variants", []):
                vtitle = v.get("title") or ""
                title = p["title"] if vtitle in ("Default Title", "") else f"{p['title']} - {vtitle}"
                yield {
                    "title": title,
                    "price": float(v["price"]),
                    "currency": shop["currency"],
                    "in_stock": bool(v.get("available")),
                    "url": f"{base}/products/{p['handle']}" + (f"?variant={v['id']}" if len(p["variants"]) > 1 else ""),
                    "context": context,
                }
        time.sleep(delay)


# ---------- WooCommerce: public Store API ----------

def fetch_woocommerce(shop, delay, max_pages):
    base = shop["url"].rstrip("/")
    search = shop.get("search", "pokemon")
    for page in range(1, max_pages + 1):
        params = {"per_page": 100, "page": page}
        if search:
            params["search"] = search
        q = urllib.parse.urlencode(params)
        try:
            products = get_json(f"{base}/wp-json/wc/store/v1/products?{q}")
        except urllib.error.HTTPError as e:
            if e.code == 400:  # page past the end
                return
            raise
        if not products:
            return
        for p in products:
            prices = p.get("prices") or {}
            minor = int(prices.get("currency_minor_unit", 2))
            raw = prices.get("price")
            if raw in (None, ""):
                continue
            cats = " ".join(c.get("name", "") for c in p.get("categories", []))
            yield {
                "title": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(p.get("name", "")))).strip(),
                "price": int(raw) / (10 ** minor),
                "currency": prices.get("currency_code") or shop["currency"],
                "in_stock": bool(p.get("is_in_stock")) and bool(p.get("is_purchasable", True)),
                "url": p.get("permalink", base),
                "context": cats,
            }
        time.sleep(delay)


ADAPTERS = {"shopify": fetch_shopify, "woocommerce": fetch_woocommerce}


def fetch_shop(shop, delay, max_pages):
    return list(ADAPTERS[shop["platform"]](shop, delay, max_pages))


# ---------- Currency ----------

def fx_rates_to_eur(fallback):
    """Daily ECB reference rates, as 'multiply by this to get EUR'. Falls back to config."""
    rates = dict(fallback)
    try:
        req = urllib.request.Request("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
        for cube in root.iter():
            if cube.get("currency") and cube.get("rate"):
                rates[cube.get("currency")] = 1.0 / float(cube.get("rate"))
        rates["EUR"] = 1.0
        rates["_source"] = "ECB"
    except Exception:
        rates["_source"] = "config fallback"
    return rates


# ---------- Detect a new shop's platform ----------

def detect(url):
    base = url.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    try:
        meta = get_json(f"{base}/meta.json")
        get_json(f"{base}/products.json?limit=1")
        host = urllib.parse.urlparse(base).hostname
        return {
            "name": meta.get("name") or host, "url": base, "platform": "shopify",
            "country": "??", "currency": meta.get("currency", "EUR"), "shipping_eur": 6.95,
            "default_language": None,
        }
    except Exception:
        pass
    try:
        products = get_json(f"{base}/wp-json/wc/store/v1/products?per_page=1")
        if isinstance(products, list):
            cur = products[0]["prices"]["currency_code"] if products else "EUR"
            host = urllib.parse.urlparse(base).hostname
            return {
                "name": re.sub(r"^www\.", "", host), "url": base, "platform": "woocommerce",
                "country": "??", "currency": cur, "shipping_eur": 6.95, "default_language": None,
            }
    except Exception:
        pass
    return None
