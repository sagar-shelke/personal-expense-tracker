
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS processed_updates (
                update_id INTEGER PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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


def mark_transaction_saved(user_id, message_id):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE transactions
            SET status = 'saved'
            WHERE telegram_user_id = ?
              AND telegram_message_id = ?
              AND status = 'pending'
        """, (user_id, message_id))

        return cursor.rowcount == 1


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


def is_update_processed(update_id):
    with get_connection() as connection:
        result = connection.execute("""
            SELECT 1
            FROM processed_updates
            WHERE update_id = ?
        """, (update_id,)).fetchone()

        return result is not None


def mark_update_processed(update_id, user_id):
    with get_connection() as connection:
        connection.execute("""
            INSERT OR IGNORE INTO processed_updates (
                update_id,
                telegram_user_id
            )
            VALUES (?, ?)
        """, (update_id, user_id))
