from unittest.mock import MagicMock

import pytest
from gspread.exceptions import APIError

from app import sheets

TRANSACTION = {
    "date": "2026-11-27", "type": "Expense", "category": "Groceries",
    "amount": 250.0, "paid_via": "UPI", "description": "spent 250",
}
HEADER = ["Date", "Type", "Category", "Amount", "Paid Via", "Description", "ID"]
FILLED = ["x"] * 6


@pytest.fixture
def worksheet(monkeypatch):
    fake = MagicMock()
    fake.get.return_value = [HEADER]
    monkeypatch.setattr(sheets, "get_worksheet", lambda: fake)
    monkeypatch.setattr(sheets.time, "sleep", lambda seconds: None)
    return fake


def api_error(code):
    response = MagicMock(status_code=code)
    response.json.return_value = {
        "error": {"code": code, "message": "x", "status": "x"}
    }
    return APIError(response)


@pytest.mark.parametrize("rows, expected", [
    ([], 2),
    ([HEADER], 2),
    ([HEADER, FILLED, [], FILLED], 3),
    ([HEADER] + [FILLED] * 200, 202),
])
def test_uses_first_empty_row_with_one_read(worksheet, rows, expected):
    worksheet.get.return_value = rows
    assert sheets.save_transaction(TRANSACTION, "1-1") == {
        "status": "saved", "row": expected,
    }
    assert worksheet.get.call_count == 1
    worksheet.row_values.assert_not_called()


@pytest.mark.parametrize("rows, expected", [
    ([HEADER, [], FILLED + ["1-1"]], 3),
    ([HEADER] + [[]] * 600 + [FILLED + ["1-1"]], 602),
])
def test_does_not_write_duplicates(worksheet, rows, expected):
    worksheet.get.return_value = rows
    assert sheets.save_transaction(TRANSACTION, "1-1") == {
        "status": "already_exists", "row": expected,
    }
    worksheet.update.assert_not_called()


def test_full_table(worksheet):
    worksheet.get.return_value = [HEADER] + [FILLED] * 500
    with pytest.raises(RuntimeError):
        sheets.save_transaction(TRANSACTION, "1-1")


@pytest.mark.parametrize("text", ["=1+1 spent", "+250 food", "-x 250", "@a 250"])
def test_formulas_are_escaped(worksheet, text):
    sheets.save_transaction({**TRANSACTION, "description": text}, "1-1")
    assert worksheet.update.call_args.kwargs["values"][0][5] == "'" + text


def test_retries_rate_limit(worksheet):
    worksheet.get.side_effect = [api_error(429), [HEADER]]
    assert sheets.save_transaction(TRANSACTION, "1-1")["status"] == "saved"


def test_retry_after_uncertain_write_finds_existing_row(worksheet):
    worksheet.get.side_effect = [[HEADER], [HEADER, FILLED + ["1-1"]]]
    worksheet.update.side_effect = api_error(429)
    assert sheets.save_transaction(TRANSACTION, "1-1")["status"] == "already_exists"
    assert worksheet.update.call_count == 1


@pytest.mark.parametrize("code, attempts", [(429, 4), (403, 1)])
def test_gives_up(worksheet, code, attempts):
    worksheet.get.side_effect = api_error(code)
    with pytest.raises(APIError):
        sheets.save_transaction(TRANSACTION, "1-1")
    assert worksheet.get.call_count == attempts
