#!/usr/bin/env python3
"""Pokémon sealed product scanner.

  python3 scan.py                 scan all shops in config.json, write output/report.html
  python3 scan.py --in-stock      only keep products you can buy right now
  python3 scan.py add <shop-url>  detect a new shop and add it to config.json
"""
import argparse
import csv
import json
import os
import statistics
import urllib.parse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path

from scanner.cardmarket import load_reference
from scanner.classify import Classifier
from scanner.report import write_report
from scanner.sources import detect, fetch_shop, fx_rates_to_eur

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"


def load_sell_prices(path):
    prices = {}
    if not path.exists():
        return prices
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                price = float((row.get("sell_price_eur") or "").replace(",", "."))
            except ValueError:
                continue
            prices[f"{row['set'].strip()}|{row['type'].strip()}|{row['language'].strip().upper()}"] = price
    return prices


def landed_cost(price_eur, shop, cfg):
    units = max(1, int(cfg.get("units_per_order", 1)))
    ship = shop.get("shipping_eur", 0.0) / units
    return price_eur + ship


def scan(cfg, in_stock_only):
    classifier = Classifier(ROOT / "data" / "sets.json")
    fx = fx_rates_to_eur(cfg["fx_fallback_to_eur"])
    print(f"Exchange rates: {fx['_source']}")

    allowed = set(cfg.get("allowed_languages") or [])
    rows, shop_status = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_shop, s, cfg["request_delay_seconds"], cfg["max_pages_per_shop"]): s
                   for s in cfg["shops"] if not s.get("disabled")}
        for fut in as_completed(futures):
            shop = futures[fut]
            try:
                listings = fut.result()
            except Exception as e:
                print(f"  ✗ {shop['name']}: {e}")
                shop_status.append({"shop": shop["name"], "ok": False, "error": str(e)[:120], "listings": 0, "sealed": 0})
                continue
            kept = 0
            for item in listings:
                context = item["context"] + (" pokemon" if shop.get("pokemon_only") else "")
                info = classifier.classify(item["title"], context, shop.get("default_language"))
                if not info:
                    continue
                if allowed and info["language"] not in allowed:
                    continue
                if in_stock_only and not item["in_stock"]:
                    continue
                rate = fx.get(item["currency"])
                if rate is None or item["price"] <= 0:
                    continue
                price_eur = item["price"] * rate
                kept += 1
                rows.append({
                    **info,
                    "title": item["title"],
                    "shop": shop["name"],
                    "country": shop["country"],
                    "in_stock": item["in_stock"],
                    "price": item["price"],
                    "currency": item["currency"],
                    "price_eur": round(price_eur, 2),
                    "landed_eur": round(landed_cost(price_eur, shop, cfg), 2),
                    "url": item["url"],
                })
            print(f"  ✓ {shop['name']}: {len(listings)} listings, {kept} sealed Pokémon")
            shop_status.append({"shop": shop["name"], "ok": True, "listings": len(listings), "sealed": kept})
    try:
        cm = load_reference(classifier, ROOT / "data" / "cache")
        print(f"Cardmarket price guide: {len(cm)} sealed products matched")
    except Exception as e:
        print(f"  ✗ Cardmarket price guide unavailable: {e}")
        cm = {}
    return rows, shop_status, fx["_source"], cm


def add_margins(rows, cfg, sell_prices, cm):
    # Market reference = median of the cheapest in-stock price per shop, per product group.
    by_group = {}
    for r in rows:
        if r["group"] and r["in_stock"]:
            shop_min = by_group.setdefault(r["group"], {})
            shop_min[r["shop"]] = min(shop_min.get(r["shop"], 1e9), r["price_eur"])
    market = {g: (statistics.median(v.values()), len(v)) for g, v in by_group.items()}

    fee = cfg["selling"]["fee_pct"]
    fixed = cfg["selling"]["fixed_cost_eur"]
    use_market = cfg.get("estimate_sell_from_market", True)
    min_shops = cfg.get("min_shops_for_market_estimate", 3)
    for r in rows:
        med, n_shops = market.get(r["group"], (None, 0))
        r["market_median_eur"] = round(med, 2) if med else None
        r["shops_in_stock"] = n_shops
        r["vs_market_pct"] = round((med - r["landed_eur"]) / med, 3) if med and n_shops >= 2 else None
        # Less than half the market price is usually a mis-labelled listing (single pack, wrong language…).
        r["check"] = bool(med and n_shops >= 2 and r["price_eur"] < 0.5 * med)

        ref = cm.get((r["set"], r["type"])) if r["group"] else None
        r["cm_trend_eur"] = ref["trend"] if ref else None
        r["cm_low_eur"] = ref["low"] if ref else None
        r["cm_url"] = ("https://www.cardmarket.com/en/Pokemon/Products/Search?searchString="
                       + urllib.parse.quote_plus(ref["name"])) if ref else ""

        options = {
            "your_price": sell_prices.get(r["group"] or ""),
            "shops_median": med if use_market and med and n_shops >= min_shops else None,
            "cardmarket_trend": r["cm_trend_eur"],
        }
        labels = {"your_price": "your price", "shops_median": "shops median", "cardmarket_trend": "CM trend"}
        sell, source = None, ""
        for key in cfg.get("sell_price_priority", ["your_price", "shops_median", "cardmarket_trend"]):
            if options.get(key):
                sell, source = options[key], labels[key]
                break
        if sell:
            net = sell * (1 - fee) - fixed
            r["sell_eur"] = round(sell, 2)
            r["sell_source"] = source
            r["margin_eur"] = round(net - r["landed_eur"], 2)
            r["margin_pct"] = round((net - r["landed_eur"]) / r["landed_eur"], 3)
        else:
            r["sell_eur"] = r["margin_eur"] = r["margin_pct"] = None
            r["sell_source"] = ""

    # Mark the cheapest in-stock offer per group across Europe.
    best = {}
    for r in rows:
        if r["group"] and r["in_stock"] and (r["group"] not in best or r["landed_eur"] < best[r["group"]]["landed_eur"]):
            best[r["group"]] = r
    for r in rows:
        r["best_in_europe"] = best.get(r["group"]) is r
    return market


def write_csvs(rows, market, sell_prices, stamp):
    OUT.mkdir(exist_ok=True)
    fields = ["set", "type", "language", "title", "shop", "country", "in_stock", "preorder", "price", "currency",
              "price_eur", "landed_eur", "market_median_eur", "shops_in_stock", "vs_market_pct", "sell_eur",
              "sell_source", "margin_eur", "margin_pct", "cm_trend_eur", "cm_low_eur", "best_in_europe", "check", "url"]
    rows_sorted = sorted(rows, key=lambda r: (r["margin_pct"] is None, -(r["margin_pct"] or 0)))
    with (OUT / "deals.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows_sorted)

    # Price history: per scan, the cheapest in-stock offer per product (small enough to keep for years).
    hist = ROOT / "data" / "history.csv"
    new = not hist.exists()
    with hist.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["scanned_at", "set", "type", "language", "best_shop", "best_landed_eur",
                        "shops_median_eur", "shops_in_stock", "cm_trend_eur"])
        for r in sorted((r for r in rows if r["best_in_europe"]), key=lambda r: r["group"]):
            w.writerow([stamp, r["set"], r["type"], r["language"], r["shop"], r["landed_eur"],
                        r["market_median_eur"], r["shops_in_stock"], r["cm_trend_eur"]])

    # Every product found, ready to copy into data/sell_prices.csv with your own sell price.
    with (OUT / "products_to_price.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["set", "type", "language", "sell_price_eur", "market_median_eur", "shops_in_stock"])
        for g, (med, n) in sorted(market.items()):
            s, t, l = g.split("|")
            w.writerow([s, t, l, sell_prices.get(g, ""), round(med, 2), n])


def cmd_add(url):
    cfg_path = ROOT / "config.json"
    shop = detect(url)
    if not shop:
        print("Could not detect a Shopify or WooCommerce catalogue on that site. It needs a custom adapter.")
        return 1
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if any(s["url"].rstrip("/") == shop["url"] for s in cfg["shops"]):
        print("That shop is already in config.json")
        return 0
    cfg["shops"].append(shop)
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added {shop['name']} ({shop['platform']}, {shop['currency']}).")
    print("Open config.json and fill in: country, shipping_eur, default_language.")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", default="scan", choices=["scan", "add"])
    p.add_argument("url", nargs="?")
    p.add_argument("--in-stock", action="store_true", help="only keep products that are in stock")
    args = p.parse_args()

    if args.command == "add":
        if not args.url:
            p.error("add needs a shop url")
        return cmd_add(args.url)

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    sell_prices = load_sell_prices(ROOT / "data" / "sell_prices.csv")
    stamp = time.strftime("%Y-%m-%d %H:%M %Z")  # local time; the GitHub workflow sets TZ=Europe/Amsterdam
    print(f"Scanning {len(cfg['shops'])} shops…")
    rows, status, fx_source, cm = scan(cfg, args.in_stock)
    market = add_margins(rows, cfg, sell_prices, cm)
    write_csvs(rows, market, sell_prices, stamp)
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_url = f"https://github.com/{repo}/actions/workflows/scan.yml" if repo else ""
    write_report(OUT / "report.html", rows, status, cfg, stamp, fx_source, run_url)
    # Tiny file the hosted page checks to see whether a newer scan exists.
    (OUT / "scan.json").write_text(json.dumps({"stamp": stamp}), encoding="utf-8")

    deals = [r for r in rows if r["in_stock"] and (r["margin_pct"] or 0) >= cfg["min_margin_pct_highlight"]]
    print(f"\n{len(rows)} sealed offers · {len(market)} products compared · {len(deals)} in-stock deals ≥ "
          f"{cfg['min_margin_pct_highlight']:.0%} margin")
    print(f"Report: {OUT / 'report.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
