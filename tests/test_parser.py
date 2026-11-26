from datetime import date

import pytest

from app.parser import parse_transaction

TODAY = date(2026, 11, 27)


def parse(message):
    return parse_transaction(message, today=TODAY)


@pytest.mark.parametrize("message, amount", [
    ("spent 250 on groceries using UPI", 250),
    ("spent 1,00,000 on rent", 100000),
    ("spent 100,000 on rent", 100000),
    ("spent 1.5k on shopping", 1500),
    ("spent rs.250 on food", 250),
    ("spent INR 250.50 on food", 250.5),
    ("spent 250 on food.", 250),
    ("250rs on food", 250),
    ("spent 250/- on food", 250),
    ("300 rupees petrol", 300),
    ("groceries - 250", 250),
    ("bought 2 tickets for 600 rs", 600),
    ("spent 25000 on travel", 25000),
    ("bought 2 movie tickets for ₹600", 600),
    ("on 5 nov spent 300 on food", 300),
    ("spent 300 on food on 05/11/2026", 300),
])
def test_amounts(message, amount):
    assert parse(message)["amount"] == amount


@pytest.mark.parametrize("message", [
    "bought 2 movie tickets for 600",
    "spent -50 on food",
    "spent ₹-50 on food",
    "spent -₹50 on food",
    "spent 0 on food",
    "spent 1,0,0 on food",
    "spent 12.345 on food",
    "spent 5lakh on a car",
    "spent money on food",
    "spent 50 on 31/02/2026",
    "spent 50 on 2026-12-05",
])
def test_rejects_unclear_input(message):
    assert "error" in parse(message)


@pytest.mark.parametrize("message, expected", [
    ("spent 50 on food", "2026-11-27"),
    ("spent 50 on food yesterday", "2026-11-26"),
    ("spent 50 on 5th november", "2026-11-05"),
    ("spent 50 on 30 dec", "2025-12-30"),
    ("spent 50 on 2026-11-01", "2026-11-01"),
])
def test_dates(message, expected):
    assert parse(message)["date"] == expected


def test_keywords_match_whole_words():
    assert parse("paid 899 premium subscription")["type"] == "Expense"
    assert parse("paid 1200 to parents")["category"] == "Miscellaneous"
    assert parse("spent 100 at cardamom cafe")["paid_via"] == "Other"


@pytest.mark.parametrize("message, kind", [
    ("salary 50000 received by bank transfer", "Income"),
    ("invested 5000 in mutual funds", "Investment"),
    ("transferred 2000 to savings", "Transfer"),
    ("transfer 2000 to savings", "Transfer"),
    ("paid 15000 rent by bank transfer", "Expense"),
    ("paid 15000 car loan emi", "Debt Payment"),
    ("paid 15000 car loan emi by bank transfer", "Debt Payment"),
])
def test_types(message, kind):
    assert parse(message)["type"] == kind
