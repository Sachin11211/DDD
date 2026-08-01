"""
scraper.py
Daily scraper for tracked Amazon.in / Flipkart product pages.

IMPORTANT — read before running:
  Amazon and Flipkart both actively block automated requests and change
  their page markup often. This scraper is built to fail LOUD and SAFE:
  if a field can't be parsed, it's stored as None rather than guessed,
  and the run continues to the next product. Expect to update the CSS
  selectors in `_extract_amazon` / `_extract_flipkart` every so often —
  that maintenance is normal, not a bug in this script.

  If requests-based scraping starts getting consistently blocked
  (CAPTCHA pages, empty responses), swap the `fetch_html` function for
  a Playwright/Selenium-based fetch — the parsing functions below don't
  need to change, only how the HTML is obtained.
"""

import random
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

import db

# Prefer lxml (faster, more lenient), but fall back to Python's built-in
# parser if lxml isn't installed, so a missing optional dependency never
# hard-fails the whole scrape.
try:
    import lxml  # noqa: F401
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"
from config import (TRACKED_PRODUCTS, UNIT_TO_GRAMS_OR_ML,
                     REQUEST_HEADERS_POOL, REQUEST_DELAY_SECONDS)

WEIGHT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|g|gm|gms|l|ltr|litre|ml)\b", re.IGNORECASE
)


def fetch_html(url: str) -> str | None:
    headers = random.choice(REQUEST_HEADERS_POOL)
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[warn] {url} returned status {resp.status_code}")
            return None
        return resp.text
    except requests.RequestException as e:
        print(f"[error] fetch failed for {url}: {e}")
        return None


def parse_weight(text: str):
    """Extract a normalized (value_in_g_or_ml, unit) from free text like
    a product title, e.g. '1 kg' -> (1000, 'g'), '500 ml' -> (500, 'ml')."""
    if not text:
        return None, None
    match = WEIGHT_PATTERN.search(text)
    if not match:
        return None, None
    value, unit = float(match.group(1)), match.group(2).lower()
    multiplier = UNIT_TO_GRAMS_OR_ML.get(unit, 1)
    normalized_unit = "ml" if unit in ("l", "ltr", "litre", "ml") else "g"
    return value * multiplier, normalized_unit


def _clean_price(text: str):
    if not text:
        return None
    digits = re.sub(r"[^\d.]", "", text)
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _sanity_check_mrp(price, mrp):
    """MRP can never legitimately be lower than the selling price. If it is,
    the scraper almost certainly grabbed the wrong element (e.g. Amazon's
    '₹X/100g' per-unit price annotation instead of the actual strikethrough
    MRP) — discard it rather than silently store an impossible value that
    would corrupt the discount-mismatch and MRP-inflation detectors."""
    if price is None or mrp is None:
        return mrp
    if mrp < price:
        print(f"[warn] discarding implausible MRP {mrp} (< price {price}) — "
              f"likely a mis-parsed page element, not the real MRP")
        return None
    return mrp


def _parse_bought_past_month(soup) -> int | None:
    """Amazon shows a real popularity badge like '400+ bought in past month'
    or, for very popular items, '70K+ bought in past month'. This is genuine
    Amazon data (not estimated or fabricated by us) — when present, it's the
    closest thing to a real 'trending / selling well' signal on the page."""
    el = soup.find(string=re.compile(r"bought in past month", re.IGNORECASE))
    if not el:
        return None
    m = re.search(r"([\d,.]+)\s*(K)?\+?\s*bought", el, re.IGNORECASE)
    if not m:
        return None
    number = float(m.group(1).replace(",", ""))
    if m.group(2):  # 'K' suffix present
        number *= 1000
    return int(number)


def _extract_amazon(html: str) -> dict:
    soup = BeautifulSoup(html, PARSER)

    title_el = soup.select_one("#productTitle")
    name = title_el.get_text(strip=True) if title_el else None

    price_el = soup.select_one(".a-price .a-offscreen") or soup.select_one("#priceblock_ourprice")
    price = _clean_price(price_el.get_text()) if price_el else None

    # Amazon's real MRP lives inside .apex-basisprice-value on current page
    # templates. The old generic ".a-text-price .a-offscreen" selector also
    # matches per-unit price annotations elsewhere on the page (e.g. a
    # "₹X/100g" callout), which also carry the a-text-price class — so it's
    # tried second, only as a fallback.
    mrp_el = (soup.select_one(".apex-basisprice-value .a-offscreen")
              or soup.select_one(".a-text-price .a-offscreen"))
    mrp = _clean_price(mrp_el.get_text()) if mrp_el else None
    mrp = _sanity_check_mrp(price, mrp)

    rating_el = soup.select_one("span.a-icon-alt")
    rating = None
    if rating_el:
        m = re.search(r"([\d.]+)", rating_el.get_text())
        rating = float(m.group(1)) if m else None

    review_el = soup.select_one("#acrCustomerReviewText")
    review_count = None
    if review_el:
        m = re.search(r"([\d,]+)", review_el.get_text())
        review_count = int(m.group(1).replace(",", "")) if m else None

    seller_el = soup.select_one("#sellerProfileTriggerId")
    seller = seller_el.get_text(strip=True) if seller_el else "Amazon"

    weight_value, weight_unit = parse_weight(name)
    bought_past_month = _parse_bought_past_month(soup)

    return dict(name=name, price=price, mrp=mrp, rating=rating,
                review_count=review_count, seller=seller,
                weight_value=weight_value, weight_unit=weight_unit,
                bought_past_month=bought_past_month)


def _extract_flipkart(html: str) -> dict:
    soup = BeautifulSoup(html, PARSER)

    title_el = soup.select_one("span.B_NuCI, span.VU-ZEz")
    name = title_el.get_text(strip=True) if title_el else None

    price_el = soup.select_one("div._30jeq3._16Jk6d, div.Nx9bqj.CxhGGd")
    price = _clean_price(price_el.get_text()) if price_el else None

    mrp_el = soup.select_one("div._3I9_wc._2p6lqe, div.yRaY8j.A6\\+E6v")
    mrp = _clean_price(mrp_el.get_text()) if mrp_el else None
    mrp = _sanity_check_mrp(price, mrp)

    rating_el = soup.select_one("div._3LWZlK, div.XQDdHH")
    rating = float(rating_el.get_text(strip=True)) if rating_el else None

    review_el = soup.select_one("span._2_R_DZ, span.Wphh3N")
    review_count = None
    if review_el:
        m = re.search(r"([\d,]+)\s*Reviews", review_el.get_text())
        review_count = int(m.group(1).replace(",", "")) if m else None

    seller_el = soup.select_one("#sellerName span, div.yeLR25")
    seller = seller_el.get_text(strip=True) if seller_el else "Flipkart"

    weight_value, weight_unit = parse_weight(name)

    return dict(name=name, price=price, mrp=mrp, rating=rating,
                review_count=review_count, seller=seller,
                weight_value=weight_value, weight_unit=weight_unit)


def scrape_product(url: str, platform: str) -> dict | None:
    html = fetch_html(url)
    if html is None:
        return None
    try:
        if platform == "amazon":
            data = _extract_amazon(html)
        elif platform == "flipkart":
            data = _extract_flipkart(html)
        else:
            return None
    except Exception as e:
        print(f"[error] parse failed for {url}: {e}")
        return None

    # Guard against fake/expired ASINs or dead links: Amazon and Flipkart
    # don't cleanly 404 these, they redirect to a generic page (homepage,
    # search, deals carousel) that still returns HTTP 200 and may still
    # contain SOME price-shaped element on it. Without this check, a typo'd
    # or placeholder URL would silently produce fabricated-looking data
    # instead of failing. A missing product title means we're not actually
    # looking at a real product page, so reject the whole result.
    if not data.get("name"):
        print(f"[warn] {url} did not resolve to a real product page (no title found) — skipping")
        return None

    return data


def run_daily_scrape(db_path: str = db.DB_PATH):
    db.init_db(db_path)
    today = date.today().isoformat()

    with db.get_conn(db_path) as conn:
        # Build the full list of things to scrape today: everything in
        # config.py, PLUS anything already sitting in the database (which
        # includes products someone pasted into the app and that got
        # tracked on the spot) that isn't already in config.py. This way,
        # pasting a link once means it keeps getting updated every day
        # going forward, without needing to hand-edit config.py.
        seen_urls = set()
        to_scrape = []

        for entry in TRACKED_PRODUCTS:
            if entry["url"] not in seen_urls:
                to_scrape.append(entry)
                seen_urls.add(entry["url"])

        for row in db.get_all_products(conn):
            row = dict(row)
            if row["url"] not in seen_urls:
                to_scrape.append({"url": row["url"], "platform": row["platform"],
                                   "category": row.get("category"), "brand": row.get("brand")})
                seen_urls.add(row["url"])

        for entry in to_scrape:
            url, platform = entry["url"], entry["platform"]
            data = scrape_product(url, platform)
            if data is None or data.get("price") is None:
                print(f"[skip] could not extract data for {url}")
                continue

            product_id = db.upsert_product(
                conn, url=url, platform=platform, name=data["name"],
                category=entry.get("category"), brand=entry.get("brand"),
                seller=data.get("seller"), weight_value=data.get("weight_value"),
                weight_unit=data.get("weight_unit"),
            )
            db.insert_snapshot(
                conn, product_id=product_id, snapshot_date=today,
                price=data.get("price"), mrp=data.get("mrp"),
                weight_value=data.get("weight_value"),
                weight_unit=data.get("weight_unit"),
                rating=data.get("rating"), review_count=data.get("review_count"),
                bought_past_month=data.get("bought_past_month"),
            )
            print(f"[ok] {entry.get('brand') or platform} -> price={data.get('price')} "
                  f"mrp={data.get('mrp')}")

            time.sleep(random.uniform(*REQUEST_DELAY_SECONDS))


if __name__ == "__main__":
    run_daily_scrape()
