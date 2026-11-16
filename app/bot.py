
import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.parser import parse_transaction
from app.sheets import save_transaction
from app.database import (
    initialize_database,
    save_pending_transaction,
    get_pending_transaction,
    mark_transaction_saving,
    mark_transaction_saved,
    mark_transaction_failed,
    get_recoverable_transactions,
    cancel_pending_transaction,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_transaction(row):
    return {
        "date": row["transaction_date"],
        "type": row["transaction_type"],
        "category": row["category"],
        "amount": row["amount"],
        "paid_via": row["paid_via"],
        "description": row["description"],
    }


def build_transaction_id(user_id, message_id):
    return f"{user_id}-{message_id}"


async def recover_transactions(application):
    """Recover transactions interrupted during Google Sheets synchronization."""

    recoverable = get_recoverable_transactions()

    if not recoverable:
        logger.info("No interrupted transactions found.")
        return

    logger.info(
        "Found %s transaction(s) requiring recovery.",
        len(recoverable),
    )

    for row in recoverable:
        user_id = row["telegram_user_id"]
        message_id = row["telegram_message_id"]

        transaction_id = build_transaction_id(user_id, message_id)
        transaction = build_transaction(row)

        try:
            # A failed transaction must return to saving before retry.
            if row["status"] == "failed":
                marked = mark_transaction_saving(user_id, message_id)

                if not marked:
                    logger.warning(
                        "Could not claim failed transaction %s.",
                        transaction_id,
                    )
                    continue

            # The same transaction ID prevents another row being created
            # if Google Sheets already received the original write.
            result = await asyncio.to_thread(
                save_transaction,
                transaction,
                transaction_id,
            )

            marked = mark_transaction_saved(user_id, message_id)

            if not marked:
                logger.error(
                    "Could not update SQLite after recovery: %s",
                    transaction_id,
                )
                continue

            logger.info(
                "Recovered transaction %s. Sheets status: %s, row: %s",
                transaction_id,
                result["status"],
                result["row"],
            )

        except Exception:
            mark_transaction_failed(user_id, message_id)

            logger.exception(
                "Recovery failed for transaction %s.",
                transaction_id,
            )


async def authorize(update: Update) -> bool:
    user = update.effective_user

    if not user or user.id != ALLOWED_USER_ID:
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ You are not authorized to use this expense tracker."
            )
        return False

    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorize(update):
        return

    await update.effective_message.reply_text(
        "👋 Welcome to your 2027 Personal Expense Tracker!\n\n"
        "Send a transaction like:\n"
        "Spent 250 on groceries using UPI\n\n"
        "I'll show you a preview before saving."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorize(update):
        return

    await update.effective_message.reply_text(
        "📖 Available commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show help\n"
        "/status - Check bot status\n"
        "/cancel - Cancel pending transaction\n\n"
        "Example:\n"
        "Spent 250 on groceries using UPI"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorize(update):
        return

    recoverable = get_recoverable_transactions()

    await update.effective_message.reply_text(
        "✅ Telegram bot is running!\n"
        "✅ Google Sheets integration configured!\n"
        "✅ SQLite database initialized!\n"
        f"🔄 Transactions requiring recovery: {len(recoverable)}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorize(update):
        return

    user_id = update.effective_user.id
    pending = get_pending_transaction(user_id)

    if not pending:
        await update.effective_message.reply_text(
            "There is no pending transaction to cancel."
        )
        return

    cancelled = cancel_pending_transaction(
        user_id,
        pending["telegram_message_id"],
    )

    if not cancelled:
        await update.effective_message.reply_text(
            "This transaction is already being processed."
        )
        return

    await update.effective_message.reply_text(
        "❌ Pending transaction cancelled."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorize(update):
        return

    user_id = update.effective_user.id
    message = update.effective_message.text.strip()

    existing = get_pending_transaction(user_id)

    if existing:
        await update.effective_message.reply_text(
            "You already have a pending transaction.\n"
            "Reply YES to save it or NO to cancel it."
        )
        return

    transaction = parse_transaction(message)

    if "error" in transaction:
        await update.effective_message.reply_text(transaction["error"])
        return

    message_id = update.effective_message.message_id

    inserted = save_pending_transaction(
        user_id,
        message_id,
        transaction,
    )

    if not inserted:
        await update.effective_message.reply_text(
            "This transaction message has already been processed."
        )
        return

    preview = (
        "🧾 Transaction Preview\n\n"
        f"📅 Date: {transaction['date']}\n"
        f"📌 Type: {transaction['type']}\n"
        f"📂 Category: {transaction['category']}\n"
        f"💰 Amount: ₹{transaction['amount']:,.2f}\n"
        f"💳 Paid Via: {transaction['paid_via']}\n"
        f"📝 Description: {transaction['description']}\n\n"
        "Reply YES to save or NO to cancel."
    )

    await update.effective_message.reply_text(preview)


async def handle_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await authorize(update):
        return

    user_id = update.effective_user.id
    message = update.effective_message.text.strip().lower()

    pending = get_pending_transaction(user_id)

    if not pending:
        await update.effective_message.reply_text(
            "No pending transaction found. Send a new transaction first."
        )
        return

    if message in ["yes", "confirm", "save"]:

        message_id = pending["telegram_message_id"]

        # Claim the transaction before making the external API call.
        marked = mark_transaction_saving(user_id, message_id)

        if not marked:
            await update.effective_message.reply_text(
                "⚠️ This transaction is already being processed. "
                "Please wait."
            )
            return

        transaction = build_transaction(pending)
        transaction_id = build_transaction_id(user_id, message_id)

        try:
            result = await asyncio.to_thread(
                save_transaction,
                transaction,
                transaction_id,
            )

            saved = mark_transaction_saved(user_id, message_id)

            if not saved:
                await update.effective_message.reply_text(
                    "⚠️ Google Sheets contains the transaction, "
                    "but SQLite could not confirm the save. "
                    "It will be checked during recovery."
                )
                return

            if result["status"] == "already_exists":
                message_text = (
                    "✅ Transaction was already present in Google Sheets."
                )
            else:
                message_text = (
                    "✅ Transaction saved successfully to Google Sheets!"
                )

            await update.effective_message.reply_text(
                f"{message_text}\n"
                f"📊 Google Sheets row: {result['row']}\n"
                f"🆔 Transaction ID: {transaction_id}"
            )

        except Exception:
            mark_transaction_failed(user_id, message_id)

            logger.exception(
                "Failed to save transaction %s",
                transaction_id,
            )

            await update.effective_message.reply_text(
                "⚠️ Could not confirm the Google Sheets write.\n"
                "Your transaction has been marked for recovery.\n"
                "It will be checked automatically when the bot restarts."
            )

    elif message in ["no", "cancel"]:
        cancelled = cancel_pending_transaction(user_id, pending["telegram_message_id"])

        if cancelled:
            await update.effective_message.reply_text(
                "❌ Transaction cancelled."
            )
        else:
            await update.effective_message.reply_text(
                "This transaction is already being processed."
            )

    else:
        await update.effective_message.reply_text(
            "Please reply YES to save or NO to cancel."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorize(update):
        return

    message = update.effective_message.text.strip().lower()

    if message in ["yes", "confirm", "save", "no", "cancel"]:
        await handle_confirmation(update, context)
    else:
        await handle_message(update, context)


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is missing from .env")

    if ALLOWED_USER_ID == 0:
        raise ValueError("TELEGRAM_ALLOWED_USER_ID is missing from .env")

    initialize_database()

    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(recover_transactions)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("cancel", cancel))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    logger.info("Starting 2027 Expense Tracker Bot...")

    application.run_polling()


if __name__ == "__main__":
    main()
