# Discount Deception Detector

Catches fake "70% OFF" claims and shrinkflation on Amazon.in / Flipkart by
tracking a curated set of products daily and running statistical anomaly
detection on price, MRP, pack size, and review-count history.

## How it works

| Signal | Method |
|---|---|
| **MRP inflation** | Z-score + IQR outlier test on a product's own historical MRP. Flags when today's "before" price is a statistical outlier — the classic move of inflating MRP right before a "sale". |
| **Shrinkflation** | Tracks price-per-gram/ml over time. Flags when it rises >8% even if the sticker price looks flat. |
| **Review spikes** | Rolling z-score on day-over-day review count changes. Flags sudden bursts that look like review manipulation. |
| **Discount mismatch** | Compares the *advertised* discount (vs current MRP) to the product's *real* long-run discount (vs its own historical median). Flags a >15 point gap. |

These four combine into a single **0–100 Trust Score** (see `analysis.py`).

## Setup

```bash
pip install -r requirements.txt

# Option A — instant demo, no internet required:
python generate_demo_data.py

# Option B — real data (edit config.py with real product URLs first):
python scraper.py

streamlit run app.py
```

## Project structure

```
db.py                  SQLite schema + helpers
config.py               Tracked product list (edit this with real URLs)
scraper.py              Amazon/Flipkart scraper (requests + BeautifulSoup)
analysis.py             Anomaly detection + Trust Score engine
generate_demo_data.py   Seeds realistic demo history (no scraping needed)
app.py                  Streamlit dashboard
.github/workflows/      Daily cron scrape via GitHub Actions
```

## Important honesty notes (read before you demo this)

- **Scraping selectors will break.** Amazon and Flipkart change their HTML
  regularly and actively block bots. The CSS selectors in `scraper.py` are
  a reasonable starting point, not a guarantee — expect to inspect the
  live page and adjust them. If `requests` gets consistently blocked,
  switch `fetch_html()` to a Playwright/Selenium-based fetch.
- **This project scrapes public product pages for personal/educational
  analysis.** It does not bypass logins, paywalls, or CAPTCHAs, and it
  respects a randomized delay between requests. Still, both platforms'
  terms of service technically disallow automated scraping — treat this
  as a portfolio/learning project, not a commercial scraper, and keep
  request volume low (the 50–100 product scope in `config.py` is
  intentional).
- **For a live demo, seed with `generate_demo_data.py` first.** It gives
  you a populated dashboard with real flagged anomalies (some products
  deliberately have MRP inflation, some shrinkflation, some review
  spikes) so the report cards and leaderboard aren't empty or flat —
  independent of whether a live scrape succeeds that day.

## Next steps to extend

- Add more categories once weight/unit parsing is solid for groceries + personal care.
- Swap SQLite for Postgres if you want to deploy with concurrent writers.
- Add a "notify me" feature (email/Telegram) when a tracked product's
  Trust Score drops below a threshold.
