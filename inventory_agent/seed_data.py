"""
Seed script: populate supplier_docs content from JSON files and add sample
historical sales/purchase data for testing.
"""
import os
import json
import sys
from datetime import datetime, date, timedelta
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def seed_supplier_docs():
    """Read JSON files from data/ and upsert content into supplier_docs."""
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    conn = db.get_connection()
    cursor = conn.cursor()

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(data_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = json.load(f)

        supplier_id = content["supplier_id"]
        doc_type = content.get("doc_type", fname.replace(".json", ""))
        title = content.get("supplier_name", "") + " - " + doc_type

        # Check if row exists
        cursor.execute(
            "SELECT id FROM supplier_docs WHERE supplier_id = ? AND filename = ?",
            (supplier_id, fname),
        )
        row = cursor.fetchone()
        content_json = json.dumps(content)
        if row:
            cursor.execute(
                "UPDATE supplier_docs SET content_json = ?, title = ? WHERE id = ?",
                (content_json, title, row["id"]),
            )
        else:
            cursor.execute(
                """INSERT INTO supplier_docs (supplier_id, doc_type, title, filename, content_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (supplier_id, doc_type, title, fname, content_json),
            )

    conn.commit()
    conn.close()
    print("Supplier docs seeded from JSON files")


def seed_sample_history():
    """Add sample sales, purchases, waste events for the last 30 days."""
    conn = db.get_connection()
    cursor = conn.cursor()

    # Only seed if tables are empty
    cursor.execute("SELECT COUNT(*) FROM sales")
    if cursor.fetchone()[0] > 0:
        conn.close()
        print("Sample history already exists, skipping")
        return

    skus = ["SKU-001", "SKU-002", "SKU-003", "SKU-004", "SKU-005"]
    base_prices = {"SKU-001": 16.0, "SKU-002": 24.0, "SKU-003": 29.0, "SKU-004": 14.0, "SKU-005": 19.0}

    # Generate 30 days of sales
    today = date.today()
    for i in range(30, 0, -1):
        sale_date = today - timedelta(days=i)
        for sku in skus:
            # Random daily sales: 0-8 bottles
            qty = random.randint(0, 8)
            if qty == 0:
                continue
            sold_at = f"{sale_date.isoformat()}T{random.randint(10,22):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
            price = base_prices[sku] + random.uniform(-1, 1)
            cursor.execute(
                """INSERT INTO sales (sold_at, sku, quantity, selling_price, source)
                   VALUES (?, ?, ?, ?, 'pos')""",
                (sold_at, sku, qty, round(price, 2)),
            )

    # Add some waste events
    for _ in range(5):
        sku = random.choice(skus)
        qty = random.randint(1, 4)
        occurred_at = f"{today.isoformat()}T{random.randint(8,17):02d}:{random.randint(0,59):02d}:00"
        cursor.execute(
            """INSERT INTO waste_events (occurred_at, sku, quantity, reason, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (occurred_at, sku, qty, "spoilage", "seed data"),
        )

    # Add some open purchase orders
    cursor.execute(
        """INSERT INTO purchases (ordered_at, sku, quantity, supplier, expected_delivery, unit_cost, status)
           VALUES (?, ?, ?, ?, ?, ?, 'ordered')""",
        (today.isoformat(), "SKU-004", 24, "SUP-001", (today + timedelta(days=3)).isoformat(), 9.50),
    )
    cursor.execute(
        """INSERT INTO purchases (ordered_at, sku, quantity, supplier, expected_delivery, unit_cost, status)
           VALUES (?, ?, ?, ?, ?, ?, 'ordered')""",
        (today.isoformat(), "SKU-002", 12, "SUP-002", (today + timedelta(days=5)).isoformat(), 18.00),
    )

    conn.commit()
    conn.close()
    print("Sample sales, waste, and purchase history seeded")


if __name__ == "__main__":
    db.init_db()
    seed_supplier_docs()
    seed_sample_history()
    print("Seeding complete")
