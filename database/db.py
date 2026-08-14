import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def seed_db():
    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if existing > 0:
            return

        password_hash = generate_password_hash("demo123")
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", password_hash),
        )
        user_id = cursor.lastrowid

        first_of_month = date.today().replace(day=1)

        sample_expenses = [
            (12.50, "Food", 2, "Groceries at local market"),
            (45.00, "Transport", 4, "Monthly bus pass top-up"),
            (89.99, "Bills", 6, "Electricity bill"),
            (25.00, "Health", 9, "Pharmacy - over-the-counter meds"),
            (60.00, "Entertainment", 11, "Movie night with friends"),
            (150.00, "Shopping", 14, "New running shoes"),
            (8.75, "Other", 17, "Miscellaneous stationery"),
            (32.40, "Food", 20, "Dinner at a restaurant"),
        ]

        for amount, category, day_of_month, description in sample_expenses:
            expense_date = first_of_month + timedelta(days=day_of_month - 1)
            conn.execute(
                """
                INSERT INTO expenses (user_id, amount, category, date, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, amount, category, expense_date.isoformat(), description),
            )

        conn.commit()
    finally:
        conn.close()


def email_exists(email):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM users WHERE email = ? LIMIT 1", (email,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def create_user(name, email, password):
    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()
