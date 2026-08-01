import sqlite3

CATEGORY_KEYWORDS = {
    'Snacks & Biscuits': ['biscuit', 'cookie', 'chips', 'popcorn', 'namkeen', 'bhujia',
                            'snack', 'wafer', 'banana chips'],
    'Electronics Accessories': ['earphone', 'cable', 'charger', 'case', 'adapter', 'adaptor',
                                  'holder', 'earbud', 'bud', 'headphone', 'cover', 'mount',
                                  'wallet', 'trimmer'],
    'Groceries': ['almond', 'cashew', 'dal', 'oil', 'salt', 'sugar', 'atta', 'rice',
                   'magnesium', 'phosphorus'],
}


def guess_brand(name):
    if not name:
        return None
    return name.split()[0]


def guess_category(name):
    if not name:
        return 'Uncategorized'
    lower = name.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return cat
    return 'Uncategorized'


def main():
    conn = sqlite3.connect('ddd.db')
    rows = conn.execute(
        "SELECT id, name, brand, category FROM products "
        "WHERE brand IS NULL OR category = 'Uncategorized'"
    ).fetchall()

    updated = 0
    for product_id, name, brand, category in rows:
        new_brand = brand or guess_brand(name)
        new_category = guess_category(name) if category in (None, 'Uncategorized') else category
        conn.execute('UPDATE products SET brand=?, category=? WHERE id=?',
                     (new_brand, new_category, product_id))
        updated += 1
        display_name = (name or "")[:45]
        display_brand = str(new_brand)
        print(f"{display_name:45s} -> brand={display_brand:15s} category={new_category}")

    conn.commit()
    print(f"\nUpdated {updated} products.")
    conn.close()


if __name__ == "__main__":
    main()
