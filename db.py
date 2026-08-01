"""
db.py
SQLite layer for the Discount Deception Detector.

Two tables:
  products       -> one row per tracked product (latest known state)
  price_history  -> one row per (product, day) snapshot, used for all
                     time-series / anomaly detection logic.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "ddd.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    platform        TEXT NOT NULL,          -- 'amazon' | 'flipkart'
    name            TEXT,
    category        TEXT,
    brand           TEXT,
    seller          TEXT,
    weight_value    REAL,                   -- normalized numeric quantity
    weight_unit     TEXT,                   -- 'g' | 'ml' (normalized)
    created_at      TEXT,
    last_updated    TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL,
    snapshot_date   TEXT NOT NULL,          -- YYYY-MM-DD
    price           REAL,
    mrp             REAL,
    weight_value    REAL,
    weight_unit     TEXT,
    rating          REAL,
    review_count    INTEGER,
    bought_past_month INTEGER,              -- real Amazon popularity badge, when shown
    FOREIGN KEY (product_id) REFERENCES products(id),
    UNIQUE(product_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_history_product_date
    ON price_history(product_id, snapshot_date);
"""


@contextmanager
def get_conn(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH):
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn):
    """Adds columns to existing databases that were created before a schema
    change, without touching any existing rows. Safe to call every time —
    it checks first and does nothing if the column already exists."""
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(price_history)")]
    if "bought_past_month" not in cols:
        conn.execute("ALTER TABLE price_history ADD COLUMN bought_past_month INTEGER")


def upsert_product(conn, url, platform, name, category, brand, seller,
                    weight_value, weight_unit):
    now = datetime.utcnow().isoformat()
    cur = conn.execute("SELECT id FROM products WHERE url = ?", (url,))
    row = cur.fetchone()
    if row:
        product_id = row["id"]
        conn.execute(
            """UPDATE products
               SET name=?, category=?, brand=?, seller=?, weight_value=?,
                   weight_unit=?, last_updated=?
               WHERE id=?""",
            (name, category, brand, seller, weight_value, weight_unit, now, product_id),
        )
    else:
        cur = conn.execute(
            """INSERT INTO products
               (url, platform, name, category, brand, seller, weight_value,
                weight_unit, created_at, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (url, platform, name, category, brand, seller, weight_value,
             weight_unit, now, now),
        )
        product_id = cur.lastrowid
    return product_id


def insert_snapshot(conn, product_id, snapshot_date, price, mrp,
                     weight_value, weight_unit, rating, review_count,
                     bought_past_month=None):
    conn.execute(
        """INSERT OR REPLACE INTO price_history
           (product_id, snapshot_date, price, mrp, weight_value, weight_unit,
            rating, review_count, bought_past_month)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (product_id, snapshot_date, price, mrp, weight_value, weight_unit,
         rating, review_count, bought_past_month),
    )


def get_product_by_url(conn, url):
    cur = conn.execute("SELECT * FROM products WHERE url = ?", (url,))
    return cur.fetchone()


def get_all_products(conn):
    cur = conn.execute("SELECT * FROM products ORDER BY category, name")
    return cur.fetchall()


def get_history(conn, product_id):
    cur = conn.execute(
        """SELECT * FROM price_history
           WHERE product_id = ?
           ORDER BY snapshot_date ASC""",
        (product_id,),
    )
    return cur.fetchall()
