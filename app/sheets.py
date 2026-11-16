
import os
import threading
from functools import wraps

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

TABLE_START_ROW = 2
TABLE_END_ROW = 501

# Ensure only one Google Sheets write runs at a time
# within this Python process.
SHEETS_WRITE_LOCK = threading.Lock()


def serialized_write(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with SHEETS_WRITE_LOCK:
            return function(*args, **kwargs)

    return wrapper


def get_worksheet():
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not credentials_path:
        raise ValueError("Google credentials path is missing.")

    if not spreadsheet_id:
        raise ValueError("GOOGLE_SHEET_ID is missing.")

    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES,
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)

    return spreadsheet.worksheet("Add Transactions")


@serialized_write
def save_transaction(transaction, transaction_id):
    """
    Save a transaction using its stable Telegram transaction ID.

    Column G stores the unique transaction ID.

    The write lock serializes calls within this Python process.
    """

    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    worksheet = get_worksheet()

    # Check whether this transaction was already written.
    existing_ids = worksheet.col_values(7)

    for row_number, existing_id in enumerate(existing_ids, start=1):
        if existing_id.strip() == str(transaction_id):
            return {
                "status": "already_exists",
                "row": row_number,
            }

    row = [
        transaction["date"],
        transaction["type"],
        transaction["category"],
        transaction["amount"],
        transaction["paid_via"],
        transaction["description"],
        str(transaction_id),
    ]

    # Find the first completely empty transaction row.
    for row_number in range(TABLE_START_ROW, TABLE_END_ROW + 1):
        existing_row = worksheet.row_values(row_number)

        if not any(str(cell).strip() for cell in existing_row[:7]):
            worksheet.update(
                range_name=f"A{row_number}:G{row_number}",
                values=[row],
                value_input_option="USER_ENTERED",
            )

            return {
                "status": "saved",
                "row": row_number,
            }

    raise RuntimeError(
        "Transaction table is full. Extend the table before saving."
    )
