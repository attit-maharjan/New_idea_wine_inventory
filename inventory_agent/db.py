"""
Database initialization and helpers for the Autonomous Inventory Agent.
Uses SQLite with file: inventory.db
"""

import sqlite3
import os
from typing import List, Dict, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

SEED_DATA = [
    ("SKU-001", "Chardonnay", 15, 10, 12.0, 5, 4),
    ("SKU-002", "Pinot Noir", 8, 10, 18.0, 7, 3),
    ("SKU-003", "Cabernet", 20, 12, 22.0, 6, 5),
    ("SKU-004", "Sauvignon Blanc", 5, 8, 10.0, 4, 2),
    ("SKU-005", "Prosecco", 12, 10, 14.0, 5, 4),
]


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema and seed data."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wines (
            sku TEXT PRIMARY KEY,
            name TEXT,
            current_stock INTEGER,
            reorder_point INTEGER,
            unit_cost REAL,
            lead_time_days INTEGER,
            supplier_reliability INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            sku TEXT,
            trigger_reason TEXT,
            llm_diagnosis TEXT,
            chosen_policy TEXT,
            service_level REAL,
            calculated_quantity INTEGER,
            tokens_used INTEGER,
            status TEXT
        )
    """)

    # Seed wines if table is empty
    cursor.execute("SELECT COUNT(*) FROM wines")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            """INSERT INTO wines (sku, name, current_stock, reorder_point, 
               unit_cost, lead_time_days, supplier_reliability)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            SEED_DATA,
        )

    conn.commit()
    conn.close()


def reset_db() -> None:
    """Reset the database to seed values."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM wines")
    cursor.executemany(
        """INSERT INTO wines (sku, name, current_stock, reorder_point, 
           unit_cost, lead_time_days, supplier_reliability)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        SEED_DATA,
    )

    cursor.execute("DELETE FROM agent_logs")
    conn.commit()
    conn.close()


def get_all_wines() -> List[Dict]:
    """Return all wines as a list of dicts."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wines ORDER BY sku")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_wine_by_sku(sku: str) -> Optional[Dict]:
    """Return a single wine by SKU."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wines WHERE sku = ?", (sku,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_stock(sku: str, delta: int) -> None:
    """Update current_stock by delta (can be negative)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE wines SET current_stock = MAX(0, current_stock + ?) WHERE sku = ?",
        (delta, sku),
    )
    conn.commit()
    conn.close()


def update_lead_time(sku: str, delta: int) -> None:
    """Update lead_time_days by delta."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE wines SET lead_time_days = MAX(1, lead_time_days + ?) WHERE sku = ?",
        (delta, sku),
    )
    conn.commit()
    conn.close()


def get_recent_logs(limit: int = 20) -> List[Dict]:
    """Return the most recent agent logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM agent_logs ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_approvals() -> List[Dict]:
    """Return all logs with status='pending_human'."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM agent_logs WHERE status = 'pending_human' ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def insert_log(
    timestamp: str,
    sku: str,
    trigger_reason: str,
    llm_diagnosis: str,
    chosen_policy: str,
    service_level: float,
    calculated_quantity: int,
    tokens_used: int,
    status: str,
) -> int:
    """Insert a new agent log entry and return its id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO agent_logs 
           (timestamp, sku, trigger_reason, llm_diagnosis, chosen_policy, 
            service_level, calculated_quantity, tokens_used, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp,
            sku,
            trigger_reason,
            llm_diagnosis,
            chosen_policy,
            service_level,
            calculated_quantity,
            tokens_used,
            status,
        ),
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def update_log_status(log_id: int, new_status: str) -> None:
    """Update the status of a log entry."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE agent_logs SET status = ? WHERE id = ?", (new_status, log_id)
    )
    conn.commit()
    conn.close()


def get_total_tokens() -> int:
    """Return the sum of all tokens_used from agent_logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COALESCE(SUM(tokens_used), 0) FROM agent_logs")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def get_wine_skus() -> List[Tuple[str, str]]:
    """Return list of (sku, name) tuples for dropdown selection."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sku, name FROM wines ORDER BY sku")
    rows = cursor.fetchall()
    conn.close()
    return [(row["sku"], row["name"]) for row in rows]
