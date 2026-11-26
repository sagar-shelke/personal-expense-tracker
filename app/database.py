import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")

        connection.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                telegram_message_id INTEGER NOT NULL,
                transaction_date TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                paid_via TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (telegram_user_id, telegram_message_id)
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_status
            ON transactions(status)
        """)


def save_pending_transaction(user_id, message_id, transaction):
    with get_connection() as connection:
        cursor = connection.execute("""
            INSERT OR IGNORE INTO transactions (
                telegram_user_id,
                telegram_message_id,
                transaction_date,
                transaction_type,
                category,
                amount,
                paid_via,
                description,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            user_id,
            message_id,
            transaction["date"],
            transaction["type"],
            transaction["category"],
            transaction["amount"],
            transaction["paid_via"],
            transaction["description"],
        ))

        return cursor.rowcount == 1


def get_pending_transaction(user_id):
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM transactions
            WHERE telegram_user_id = ?
              AND status = 'pending'
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,)).fetchone()


def mark_transaction_saving(user_id, message_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE transactions
            SET status = 'saving'
            WHERE telegram_user_id = ?
              AND telegram_message_id = ?
              AND status IN ('pending', 'failed')
        """, (user_id, message_id))

        return cursor.rowcount == 1


def mark_transaction_saved(user_id, message_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE transactions
            SET status = 'saved'
            WHERE telegram_user_id = ?
              AND telegram_message_id = ?
              AND status IN ('pending', 'saving', 'failed')
        """, (user_id, message_id))

        return cursor.rowcount == 1


def mark_transaction_failed(user_id, message_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE transactions
            SET status = 'failed'
            WHERE telegram_user_id = ?
              AND telegram_message_id = ?
              AND status = 'saving'
        """, (user_id, message_id))

        return cursor.rowcount == 1


def get_recoverable_transactions():
    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM transactions
            WHERE status IN ('saving', 'failed')
            ORDER BY id ASC
        """).fetchall()


def cancel_pending_transaction(user_id, message_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE transactions
            SET status = 'cancelled'
            WHERE telegram_user_id = ?
              AND telegram_message_id = ?
              AND status = 'pending'
        """, (user_id, message_id))

        return cursor.rowcount == 1
