"""Cardmarket reference prices from Cardmarket's official public price-guide downloads.

Cardmarket publishes these files daily for everyone. They hold one price per product,
aggregated over ALL languages and ALL sellers. Filtering on language or seller reputation
needs the Cardmarket API (approved professional sellers only), so these are reference
prices, not buyable offers.
"""
import json
import time
import urllib.request
from pathlib import Path

from scanner.sources import USER_AGENT

BASE = "https://downloads.s3.cardmarket.com/productCatalog"
FILES = {
    "products": f"{BASE}/productList/products_nonsingles_6.json",   # 6 = Pokémon
    "prices": f"{BASE}/priceGuide/price_guide_6.json",
}
# Only types where one Cardmarket product = one product (tins, blisters and collections have many variants).
MATCH_TYPES = {"Booster Box", "Elite Trainer Box", "Pokemon Center ETB", "Booster Bundle", "Booster Pack",
               "Build & Battle", "Ultra Premium Collection", "Super Premium Collection"}
SKIP_NAMES = ("18 boosters", "sleeved", "fun pack", "jumbo", "costco", "sam's club", "half", "display set")


def _download(name, url, cache_dir, max_age_h=12):
    path = cache_dir / f"cardmarket_{name}.json"
    if not path.exists() or time.time() - path.stat().st_mtime > max_age_h * 3600:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            path.write_bytes(resp.read())
    return json.loads(path.read_text(encoding="utf-8"))


def load_reference(classifier, cache_dir):
    """Return {(set, type): {"trend", "low", "avg30", "name", "id"}}."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    products = _download("products", FILES["products"], cache_dir)["products"]
    prices = {p["idProduct"]: p for p in _download("prices", FILES["prices"], cache_dir)["priceGuides"]}

    candidates = {}
    for p in products:
        name = p["name"]
        if any(s in name.lower() for s in SKIP_NAMES):
            continue
        info = classifier.classify(name, "pokemon")
        if not info or info["type"] not in MATCH_TYPES or info["set"] == "Unknown set" or info["set"].startswith("JP "):
            continue
        pg = prices.get(p["idProduct"])
        if not pg or not pg.get("trend"):
            continue
        candidates.setdefault((info["set"], info["type"]), []).append((len(name), name, p["idProduct"], pg))

    ref = {}
    for key, items in candidates.items():
        _, name, pid, pg = min(items)  # shortest name = the plain product, e.g. "Perfect Order Booster Box"
        ref[key] = {"trend": pg.get("trend"), "low": pg.get("low"), "avg30": pg.get("avg30"), "name": name, "id": pid}
    return ref
