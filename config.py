"""
config.py
Curated list of tracked products. These are real, live Amazon.in URLs,
verified to work with scraper.py as of this writing. Flipkart is left out
of v1 — it blocks non-browser requests far more aggressively than Amazon,
and getting past that reliably needs a browser-based fetch (Playwright),
which is a good v2 upgrade rather than a v1 blocker.

Add more products the same way: find a real Amazon.in product URL and
add an entry below with the same shape.
"""

TRACKED_PRODUCTS = [
    # -------- Groceries / FMCG --------
    {"url": "https://www.amazon.in/Fortune-Sunlite-Refined-Sunflower-Oil/dp/B0140PWG0M",
     "platform": "amazon", "category": "Groceries", "brand": "Fortune"},
    {"url": "https://www.amazon.in/Tata-Sampann-Pulses-Toor-Dal/dp/B074N7VHV4",
     "platform": "amazon", "category": "Groceries", "brand": "Tata Sampann"},
    {"url": "https://www.amazon.in/Amul-Butter-Pasteurised-500g-Pack/dp/B018E0G4MU",
     "platform": "amazon", "category": "Groceries", "brand": "Amul"},

    # -------- Personal care --------
    {"url": "https://www.amazon.in/Dove-Intense-Repair-Shampoo-650ml/dp/B07H9STZWF",
     "platform": "amazon", "category": "Personal Care", "brand": "Dove"},
    {"url": "https://www.amazon.in/Head-Shoulders-Anti-Shampoo-360ml/dp/B0769LRX82",
     "platform": "amazon", "category": "Personal Care", "brand": "Head & Shoulders"},
    {"url": "https://www.amazon.in/Colgate-Toothpaste-Strong-Teeth-Dental/dp/B00DRDZLJW",
     "platform": "amazon", "category": "Personal Care", "brand": "Colgate"},
    {"url": "https://www.amazon.in/Parachute-Coconut-Pure-Hair-500ml/dp/B012WIQLNM",
     "platform": "amazon", "category": "Personal Care", "brand": "Parachute"},
    {"url": "https://www.amazon.in/Himalaya-Purifying-Neem-150ml/dp/B010Z0LH8I",
     "platform": "amazon", "category": "Personal Care", "brand": "Himalaya"},

    # Add more here, following the same shape, once you're ready to expand.
]

# Weight/volume unit normalization -> grams or millilitres
UNIT_TO_GRAMS_OR_ML = {
    "kg": 1000, "g": 1, "gm": 1, "gms": 1,
    "l": 1000, "ltr": 1000, "litre": 1000,
    "ml": 1,
}

REQUEST_HEADERS_POOL = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"},
]

REQUEST_DELAY_SECONDS = (2, 5)  # randomized delay range between requests

