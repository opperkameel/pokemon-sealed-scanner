"""Live Cardmarket offers through the official Cardmarket API (v2.0).

For every product: English offers only, from sellers in the configured countries (default BE + NL)
with at least the configured reputation (default "very good"). The lowest price becomes the benchmark.

Needs Cardmarket API keys ("Dedicated App"), read from environment variables:
  CARDMARKET_APP_TOKEN, CARDMARKET_APP_SECRET, CARDMARKET_ACCESS_TOKEN, CARDMARKET_ACCESS_SECRET
Locally: put them in a file called .env next to scan.py (never commit it).
On GitHub: add them as repository secrets (Settings → Secrets and variables → Actions).
Without keys this module does nothing and the scanner falls back to the public price guide.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.cardmarket.com/ws/v2.0/output.json"
ENV_KEYS = ("CARDMARKET_APP_TOKEN", "CARDMARKET_APP_SECRET", "CARDMARKET_ACCESS_TOKEN", "CARDMARKET_ACCESS_SECRET")
LANGUAGE_IDS = {"EN": 1, "FR": 2, "DE": 3, "ES": 4, "IT": 5, "CN": 6, "JP": 7, "PT": 8, "KR": 10}
# Cardmarket reputation codes: 1 outstanding, 2 very good, 3 good, 4 average, 5 bad, 0 not enough sales yet.
REPUTATION = {"outstanding": 1, "very good": 2, "good": 3, "average": 4}
COUNTRY_ALIASES = {"D": "DE"}


def _quote(s):
    return urllib.parse.quote(str(s), safe="~-._")


def oauth_header(method, url, app_token, app_secret, access_token, access_secret, nonce=None, timestamp=None):
    """OAuth 1.0a HMAC-SHA1 header, as Cardmarket requires (realm = URL without query string)."""
    base_url, _, query = url.partition("?")
    oauth = {
        "oauth_consumer_key": app_token,
        "oauth_token": access_token,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_version": "1.0",
    }
    params = list(oauth.items()) + urllib.parse.parse_qsl(query, keep_blank_values=True)
    param_str = "&".join(f"{k}={v}" for k, v in sorted((_quote(k), _quote(v)) for k, v in params))
    base = "&".join([method.upper(), _quote(base_url), _quote(param_str)])
    key = f"{_quote(app_secret)}&{_quote(access_secret)}".encode()
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join([f'realm="{base_url}"'] + [f'{k}="{_quote(v)}"' for k, v in oauth.items()])


def _load_env_file(root):
    path = Path(root) / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def credentials(root):
    _load_env_file(root)
    creds = [os.environ.get(k, "").strip() for k in ENV_KEYS]
    return creds if all(creds) else None


def _get(path, creds, params):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": oauth_header("GET", url, *creds),
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        if e.code == 204:          # no articles at all
            return {}
        if e.code == 206:          # partial content: more results than requested, still usable
            return json.loads(e.read().decode("utf-8") or "{}")
        raise


def _seller_country(seller):
    country = (seller.get("address") or {}).get("country") or seller.get("country") or ""
    country = str(country).upper()
    return COUNTRY_ALIASES.get(country, country)


def benelux_minimum(product_ids, settings, root):
    """Return ({idProduct: {"price", "seller", "country", "offers"}}, status message)."""
    creds = credentials(root)
    if not creds:
        return {}, "off (no Cardmarket API keys)"
    countries = {c.upper() for c in settings.get("seller_countries", ["BE", "NL"])}
    lang_id = LANGUAGE_IDS[settings.get("language", "EN").upper()]
    max_rep = REPUTATION[settings.get("min_seller_reputation", "very good").lower()]
    delay = float(settings.get("request_delay_seconds", 0.3))

    result, errors = {}, 0
    for pid in sorted(set(product_ids)):
        try:
            data = _get(f"/articles/{pid}", creds, {"idLanguage": lang_id, "start": 0, "maxResults": 1000})
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {}, f"failed: Cardmarket refused the API keys (HTTP {e.code})"
            if e.code == 429:
                return result, f"stopped early: Cardmarket API request limit reached ({len(result)} products done)"
            errors += 1
            continue
        except Exception:
            errors += 1
            continue
        offers = []
        for a in data.get("article", []) or []:
            seller = a.get("seller") or {}
            rep = seller.get("reputation")
            if (a.get("language") or {}).get("idLanguage", lang_id) != lang_id:
                continue
            if _seller_country(seller) not in countries:
                continue
            if not isinstance(rep, int) or not (1 <= rep <= max_rep):
                continue
            if seller.get("onVacation"):
                continue
            offers.append((float(a.get("price", 0) or 0), seller.get("username", ""), _seller_country(seller)))
        offers = [o for o in offers if o[0] > 0]
        if offers:
            price, user, country = min(offers)
            result[pid] = {"price": round(price, 2), "seller": user, "country": country, "offers": len(offers)}
        time.sleep(delay)
    msg = f"{len(result)} of {len(set(product_ids))} products have English offers from {'/'.join(sorted(countries))} sellers"
    return result, msg + (f" ({errors} lookups failed)" if errors else "")
