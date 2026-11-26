import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import bot, database

USER = 42
TRANSACTION = {
    "date": "2026-11-27", "type": "Expense", "category": "Groceries",
    "amount": 250.0, "paid_via": "UPI", "description": "spent 250",
}


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", USER)
    database.initialize_database()


def make_update(user_id=USER):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message.reply_text = AsyncMock()
    return update


def add(message_id, failed):
    database.save_pending_transaction(USER, message_id, TRANSACTION)
    database.mark_transaction_saving(USER, message_id)
    if failed:
        database.mark_transaction_failed(USER, message_id)


def test_retry_saves_only_failed(monkeypatch):
    add(1, failed=True)
    add(2, failed=False)  # still 'saving'
    save = MagicMock(return_value={"status": "saved", "row": 2})
    monkeypatch.setattr(bot, "save_transaction", save)
    asyncio.run(bot.retry(make_update(), MagicMock()))
    assert save.call_count == 1
    assert [r["status"] for r in database.get_recoverable_transactions()] == ["saving"]


def test_failed_retry_stays_recoverable(monkeypatch):
    add(1, failed=True)
    monkeypatch.setattr(bot, "save_transaction", MagicMock(side_effect=RuntimeError))
    update = make_update()
    asyncio.run(bot.retry(update, MagicMock()))
    assert database.get_recoverable_transactions()[0]["status"] == "failed"
    assert "Not recovered: 1" in update.effective_message.reply_text.call_args.args[0]


def test_retry_rejects_other_users(monkeypatch):
    add(1, failed=True)
    save = MagicMock()
    monkeypatch.setattr(bot, "save_transaction", save)
    asyncio.run(bot.retry(make_update(user_id=7), MagicMock()))
    save.assert_not_called()
