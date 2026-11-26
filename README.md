# Personal Expense Tracker

A private Telegram bot that turns short messages into rows in Google Sheets.

## Features

- Preview each transaction, then reply `YES` to save or `NO` to cancel
- Only one allowed Telegram user can use the bot
- Reads amounts such as `250`, `1,00,000`, `1.5k` and `₹600`
- Reads `today`, `yesterday`, `5 nov`, `05/11/2026` (day first) and `2026-11-05`; dates use India time
- Avoids duplicate rows by storing a transaction ID in the sheet
- Retries rate-limited saves; failed saves can be retried with `/retry` and are rechecked on restart

## Message examples

| Message | Note |
|---|---|
| `Spent 250 on groceries using UPI` | Dated today |
| `Spent 1.5k on shopping yesterday` | `k` means thousand |
| `Paid 1,00,000 rent on 5 nov by bank transfer` | Past date |
| `Bought 2 movie tickets for ₹600` | With several numbers, mark the amount with `₹`, `Rs` or `INR` |

Categories and payment methods are matched by keyword (see `app/parser.py`). Check the preview before saving.

## Setup

You need Python 3.10 or later.

1. **Install**

   ```bash
   git clone https://github.com/sagar-shelke/personal-expense-tracker.git
   cd personal-expense-tracker
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Telegram:** create a bot with [@BotFather](https://t.me/BotFather) and copy its token. Find your numeric user ID.
3. **Google:** enable the Google Sheets API, create a service account, and download its JSON key into `credentials/` (ignored by Git).
4. **Sheet:** create a tab named `Add Transactions` and share the spreadsheet with the service account's email as an Editor. Row 1 is for headers. Rows 2–501 hold transactions:

   | A | B | C | D | E | F | G |
   |---|---|---|---|---|---|---|
   | Date | Type | Category | Amount | Paid Via | Description | Transaction ID |

   A row counts as empty only if A–G are all blank, so don't prefill formulas or defaults in these columns.

5. **Configure:** copy `.env.example` to `.env` and fill it in.
6. **Run** from the project folder:

   ```bash
   python -m app.bot
   ```

## Commands

| Command | Action |
|---|---|
| `/start` | Welcome message |
| `/help` | Help and examples |
| `/status` | Bot status and count of unfinished saves |
| `/cancel` | Cancel the pending transaction |
| `/retry` | Retry failed saves |

`/status` confirms that the bot is running; it does not test the Google Sheets connection.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a fake worksheet and a temporary database, so they need no credentials.

## Limitations

- Run only one copy of the bot; the write lock works within one process.
- The table is limited to 500 transactions unless you change `TABLE_END_ROW` in `app/sheets.py`.
- While a rate-limited save is waiting to retry, other messages wait too.

## License

[MIT](LICENSE)
