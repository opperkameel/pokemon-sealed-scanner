# Sealed Pokémon Scanner (EU)

Scans 34 EU webshops (NL, BE, DE, FR, IT, ES) for **English** sealed Pokémon product (booster boxes, ETBs,
bundles, tins, blisters, collections), finds the cheapest in-stock offer per product across Europe, compares it
with Cardmarket, and calculates your margin.

No installs needed: it only uses Python 3, which is already on your Mac.

## Run it

**Easiest:** double-click `Start Scanner.command` in Finder (or run `python3 app.py`).
The report opens in your browser. Click **Run now** (top right) to start a new scan: you see the progress per shop,
and the page reloads with fresh results when it's done (about 3 minutes). Keep the Terminal window open while you use it.

The app only runs on your own computer (http://127.0.0.1:8765). Close the Terminal window to stop it.

**Without the app:**

```bash
cd pokemon-sealed-scanner
python3 scan.py
```

Then open `output/report.html` in your browser.

Use `python3 scan.py --in-stock` to keep only products you can buy right now.

## Online version (GitHub)

- **Report:** https://opperkameel.github.io/pokemon-sealed-scanner/
- **Automatic scan:** every morning at about 07:00.
- **Scan now:** click **Run now** in the online report. The scan starts on GitHub, the button shows its progress,
  and the page loads the new results by itself (~3 min).
  The first time on each device, the page asks for a GitHub token (one-time setup, the page explains the steps):
  fine-grained, *Only select repositories* → this repo, *Actions: Read and write*. It is stored only in that browser.
  Without a token you can still start a scan on GitHub: repo → *Actions* → *Scan* → **Run workflow**.
- The online report and this code are public (GitHub free plan). Your own sell prices in `data/sell_prices.csv`
  would be public too once you push them. To make everything private, upgrade to GitHub Pro and make the repo private.
- Changed something locally (shops, sets, sell prices)? Push it and the next scan uses it:

```bash
git add -A && git commit -m "Update config" && git push
```

## What you get

| File | What it is |
|---|---|
| `output/report.html` | Filterable report. Tab **All offers** shows every listing, tab **Best price per product** shows the cheapest in-stock shop per product |
| `output/deals.csv` | Same data for Excel / Google Sheets, sorted by margin |
| `output/products_to_price.csv` | Every product found, with its market price. Use it to fill in your sell prices |
| `data/history.csv` | Grows with every scan: the cheapest in-stock offer per product, so you can track price trends over time |

## How the numbers work

- **Landed cost** = shop price + shipping to you (`shipping_eur` per shop in `config.json`, divided by `units_per_order`).
- **Market** = median price across the shops that have that exact product (same set, type and language) in stock.
- **CM trend / CM low**: from Cardmarket's official daily price guide (downloaded automatically, cached 12 h).
  These prices mix **all languages and all sellers**, so treat them as a reference. Click them to open Cardmarket
  and check the English offers from sellers with a good rating yourself.
- **Sell price**: picked in the order of `sell_price_priority` in `config.json`. Default:
  your own price (`data/sell_prices.csv`), then the median of the shops (only when 3+ shops stock it), then the Cardmarket trend.
- **Margin** = sell price − selling fees (`selling.fee_pct` + `fixed_cost_eur`) − landed cost.
- **verify listing** = the price is under half of the market price. This is usually a labelling issue (single pack, other language, damaged box), so check it before you buy.

## Set your own sell prices (recommended)

1. Run a scan.
2. Open `output/products_to_price.csv`, copy the rows you care about into `data/sell_prices.csv` and fill in `sell_price_eur`.
   Use what you actually sell for (your shop, or the Cardmarket trend price).
3. Scan again. Those products now show *your price* and a real margin.

## Add more shops

Any EU shop on **Shopify** or **WooCommerce** can be added in one command:

```bash
python3 scan.py add https://some-shop.de
```

Then open `config.json` and fill in `country`, `shipping_eur` and `default_language` for that shop.
If the shop only sells Pokémon and doesn't put "Pokémon" in its product titles, add `"pokemon_only": true`.
To pause a shop, add `"disabled": true`.

Shops on other platforms (Shopware, Magento, custom sites) need their own adapter in `scanner/sources.py`.

## English only

`allowed_languages` in `config.json` is set to `["EN"]`. The language comes from the product title, or from the
shop's categories/tags when they name exactly one language. In shops that sell several languages, a product with
no language label is skipped, so nothing in another language slips through. To also scan e.g. Japanese, use `["EN", "JP"]`.

## Cardmarket: what is and isn't possible

- Included: Cardmarket's public price guide (trend, lowest price) for ~280 sealed products.
- Not included: live English offers filtered on seller reputation. Cardmarket blocks automated visitors to its site,
  and that data is only available through the Cardmarket API, which they grant to approved professional sellers.
  If you get API access, it can be added to `scanner/cardmarket.py`.

## Recognising products

`data/sets.json` maps set names in English, German, French and Japanese (plus set codes like `sv8.5` / `EB07`) to one set name.
When a new set is released, add it there; otherwise its listings show as *Unknown set* and are not compared across shops.

## Things to check yourself

- `shipping_eur` values are estimates. Check each shop's real shipping cost to your address.
- Be a polite visitor: keep `request_delay_seconds` at 1 or more. Scanning a few times a day is plenty.
