"""
generate_demo_data.py
Populates ddd.db with ~90 days of realistic-looking history for a set of
demo products, deliberately injecting some MRP inflation, shrinkflation,
and review-spike patterns into a subset of them.

Why this exists: live scraping of Amazon/Flipkart can get blocked at any
moment (CAPTCHA, IP throttling, layout changes). Interview demos should
not depend on that working live. Run this once to seed a convincing,
reproducible dataset, then layer real daily scrapes on top with
scraper.py once you're ready.

Run: python generate_demo_data.py
"""

import random
from datetime import date, timedelta

import db

random.seed(42)

DAYS_OF_HISTORY = 90
TODAY = date.today()

DEMO_PRODUCTS = [
    # -------- Groceries / FMCG --------
    dict(name="Fortune Sunflower Oil 1L", platform="amazon", category="Groceries",
         brand="Fortune", base_price=145, base_mrp=180, weight=1000, unit="ml",
         seller="Fortune Retail", pattern="clean"),
    dict(name="Tata Sampann Toor Dal 1kg", platform="amazon", category="Groceries",
         brand="Tata Sampann", base_price=165, base_mrp=190, weight=1000, unit="g",
         seller="Tata Consumer", pattern="mrp_inflation"),
    dict(name="Aashirvaad Atta 5kg", platform="flipkart", category="Groceries",
         brand="Aashirvaad", base_price=255, base_mrp=280, weight=5000, unit="g",
         seller="ITC Retail", pattern="shrinkflation"),
    dict(name="MDH Deggi Mirch 100g", platform="amazon", category="Groceries",
         brand="MDH", base_price=68, base_mrp=75, weight=100, unit="g",
         seller="MDH Foods", pattern="clean"),
    dict(name="Britannia Good Day Biscuits 600g", platform="flipkart", category="Groceries",
         brand="Britannia", base_price=90, base_mrp=110, weight=600, unit="g",
         seller="Britannia Direct", pattern="shrinkflation"),
    dict(name="Saffola Gold Oil 1L", platform="amazon", category="Groceries",
         brand="Saffola", base_price=175, base_mrp=210, weight=1000, unit="ml",
         seller="Marico Retail", pattern="review_spike"),
    dict(name="Amul Butter 500g", platform="amazon", category="Groceries",
         brand="Amul", base_price=260, base_mrp=275, weight=500, unit="g",
         seller="Amul Direct", pattern="clean"),
    dict(name="Haldiram Namkeen 400g", platform="flipkart", category="Groceries",
         brand="Haldiram", base_price=95, base_mrp=130, weight=400, unit="g",
         seller="Haldiram Retail", pattern="mrp_inflation"),

    # -------- Personal care --------
    dict(name="Dove Shampoo 650ml", platform="amazon", category="Personal Care",
         brand="Dove", base_price=520, base_mrp=650, weight=650, unit="ml",
         seller="HUL Retail", pattern="mrp_inflation"),
    dict(name="Head & Shoulders Anti-Dandruff 340ml", platform="amazon",
         category="Personal Care", brand="Head & Shoulders", base_price=310,
         base_mrp=375, weight=340, unit="ml", seller="P&G Retail", pattern="clean"),
    dict(name="Nivea Body Lotion 400ml", platform="flipkart", category="Personal Care",
         brand="Nivea", base_price=340, base_mrp=399, weight=400, unit="ml",
         seller="Nivea Official", pattern="shrinkflation"),
    dict(name="Colgate Strong Teeth 200g", platform="amazon", category="Personal Care",
         brand="Colgate", base_price=95, base_mrp=115, weight=200, unit="g",
         seller="Colgate Retail", pattern="clean"),
    dict(name="Patanjali Aloe Vera Gel 150ml", platform="flipkart",
         category="Personal Care", brand="Patanjali", base_price=80, base_mrp=140,
         weight=150, unit="ml", seller="Patanjali Store", pattern="mrp_inflation"),
    dict(name="Lakme Sunscreen SPF 50 100g", platform="amazon", category="Personal Care",
         brand="Lakme", base_price=380, base_mrp=475, weight=100, unit="g",
         seller="Lakme Direct", pattern="review_spike"),
    dict(name="Himalaya Face Wash 150ml", platform="amazon", category="Personal Care",
         brand="Himalaya", base_price=150, base_mrp=175, weight=150, unit="ml",
         seller="Himalaya Retail", pattern="shrinkflation"),
    dict(name="Parachute Coconut Oil 500ml", platform="flipkart",
         category="Personal Care", brand="Parachute", base_price=210, base_mrp=240,
         weight=500, unit="ml", seller="Marico Retail", pattern="clean"),
]


def simulate_history(product: dict):
    """Returns a list of daily snapshot dicts for one product across
    DAYS_OF_HISTORY days, applying the product's deception `pattern`."""
    rows = []
    price = product["base_price"]
    mrp = product["base_mrp"]
    weight = product["weight"]
    rating = round(random.uniform(3.8, 4.6), 1)
    reviews = random.randint(200, 4000)

    for day_offset in range(DAYS_OF_HISTORY, 0, -1):
        d = TODAY - timedelta(days=day_offset)

        # normal daily noise
        price_noise = random.uniform(-0.01, 0.01)
        price = max(1, price * (1 + price_noise))
        reviews += random.randint(0, 12)

        if product["pattern"] == "mrp_inflation" and day_offset <= 10:
            # sharply inflate MRP right before "today" to fake a big discount
            mrp = product["base_mrp"] * random.uniform(1.35, 1.6)

        elif product["pattern"] == "shrinkflation" and day_offset <= 45:
            # weight quietly shrinks over the last ~45 days, price holds steady
            progress = (45 - day_offset) / 45
            weight = product["weight"] * (1 - 0.18 * progress)

        elif product["pattern"] == "review_spike" and day_offset == 3:
            # sudden burst of reviews 3 days ago (classic review-bombing/buying signal)
            reviews += random.randint(300, 600)

        rows.append(dict(
            snapshot_date=d.isoformat(),
            price=round(price, 2),
            mrp=round(mrp, 2),
            weight_value=round(weight, 1),
            weight_unit=product["unit"],
            rating=rating,
            review_count=int(reviews),
            bought_past_month=random.choice([None, None, random.randint(50, 5000)]),
        ))

    return rows


def main():
    db.init_db()
    with db.get_conn() as conn:
        for i, product in enumerate(DEMO_PRODUCTS):
            url = f"https://www.{'amazon.in/dp' if product['platform']=='amazon' else 'flipkart.com/p'}/DEMO{i:03d}"
            product_id = db.upsert_product(
                conn, url=url, platform=product["platform"], name=product["name"],
                category=product["category"], brand=product["brand"],
                seller=product["seller"], weight_value=product["weight"],
                weight_unit=product["unit"],
            )
            for row in simulate_history(product):
                db.insert_snapshot(conn, product_id=product_id, **row)

            print(f"[seeded] {product['name']} ({product['pattern']})")

    print(f"\nDone. Seeded {len(DEMO_PRODUCTS)} products with {DAYS_OF_HISTORY} days of history each.")
    print("Run: streamlit run app.py")


if __name__ == "__main__":
    main()
