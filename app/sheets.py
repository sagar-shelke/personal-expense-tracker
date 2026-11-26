
import logging
import os
import threading
import time
from functools import wraps

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

TABLE_START_ROW = 2
TABLE_END_ROW = 501

# Waits, in seconds, before retrying a rate-limited (HTTP 429) save.
RETRY_DELAYS = (5, 20, 45)

# Text starting with these could be read as a formula by Google Sheets.
FORMULA_PREFIXES = ("=", "+", "-", "@")

logger = logging.getLogger(__name__)

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


def as_plain_text(value):
    """Stop user-typed text from being evaluated as a formula."""
    if value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def retry_on_rate_limit(function):
    """Retry the whole save, so the duplicate ID check runs every time."""

    @wraps(function)
    def wrapper(*args, **kwargs):
        for delay in RETRY_DELAYS:
            try:
                return function(*args, **kwargs)
            except APIError as error:
                if error.response.status_code != 429:
                    raise
                logger.warning("Sheets rate limit hit; retrying in %ss.", delay)
                time.sleep(delay)

        return function(*args, **kwargs)

    return wrapper


@retry_on_rate_limit
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

    row = [
        transaction["date"],
        transaction["type"],
        transaction["category"],
        transaction["amount"],
        transaction["paid_via"],
        as_plain_text(transaction["description"]),
        str(transaction_id),
    ]

    # Read all IDs and rows in one request to stay within the read quota.
    # The range has no end row so IDs below the table are checked too.
    rows = worksheet.get("A1:G")
    empty_row = None

    for row_number, cells in enumerate(rows, start=1):
        if len(cells) >= 7 and str(cells[6]).strip() == str(transaction_id):
            return {"status": "already_exists", "row": row_number}

        if (
            empty_row is None
            and TABLE_START_ROW <= row_number <= TABLE_END_ROW
            and not any(str(cell).strip() for cell in cells[:7])
        ):
            empty_row = row_number

    # The API omits trailing empty rows.
    if empty_row is None:
        next_row = max(len(rows) + 1, TABLE_START_ROW)
        if next_row <= TABLE_END_ROW:
            empty_row = next_row

    if empty_row is not None:
        worksheet.update(
            range_name=f"A{empty_row}:G{empty_row}",
            values=[row],
            value_input_option="USER_ENTERED",
        )
        return {"status": "saved", "row": empty_row}

    raise RuntimeError(
        "Transaction table is full. Extend the table before saving."
    )
