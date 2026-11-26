import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Kolkata")

CATEGORIES = {
    "groceries": "Groceries",
    "grocery": "Groceries",
    "food": "Food & Dining",
    "restaurant": "Food & Dining",
    "restaurants": "Food & Dining",
    "petrol": "Petrol & Transport",
    "fuel": "Petrol & Transport",
    "transport": "Petrol & Transport",
    "shopping": "Shopping",
    "electricity": "Housing & Bills",
    "rent": "Housing & Bills",
    "bill": "Housing & Bills",
    "bills": "Housing & Bills",
    "medical": "Healthcare",
    "medicine": "Healthcare",
    "medicines": "Healthcare",
    "health": "Healthcare",
    "insurance": "Insurance",
    "movie": "Entertainment",
    "movies": "Entertainment",
    "entertainment": "Entertainment",
    "travel": "Travel",
    "subscription": "Subscriptions",
    "subscriptions": "Subscriptions",
    "salary": "Salary",
    "freelance": "Freelance Income",
    "nps": "NPS",
    "mutual fund": "Mutual Funds",
    "mutual funds": "Mutual Funds",
    "personal loan": "Personal Loan EMI",
    "car loan": "Car Loan EMI",
}

PAYMENT_METHODS = {
    "upi": "UPI",
    "cash": "Cash",
    "credit card": "Credit Card",
    "debit card": "Debit Card",
    "card": "Debit Card",
    "bank transfer": "Bank Transfer",
    "auto debit": "Auto Debit",
}

MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"),
            ("apr", "april"), ("may",), ("jun", "june"),
            ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"),
            ("nov", "november"), ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))

DATE_PATTERN = re.compile(
    r"\b(?:"
    r"(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?P<d>\d{1,2})/(?P<m>\d{1,2})(?:/(?P<y>\d{4}))?"
    rf"|(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH})(?:\s+(?P<year>20\d{{2}}))?"
    r"|(?P<relative>today|yesterday)"
    r")\b"
)

# A number that is not glued to other letters or digits. A currency prefix,
# a minus sign and a "k" suffix are captured so they can be interpreted.
AMOUNT_PATTERN = re.compile(
    r"(?<![\w.,])"
    r"(?P<sign>(?<!\w)-)?"
    r"(?P<currency>₹\s*|(?:rs\.?|inr)\s*)?"
    r"(?P<sign2>-)?"
    r"(?P<number>\d+(?:,\d+)*(?:\.\d+)?)"
    r"(?P<k>k)?"
    r"(?P<suffix>\s*(?:₹|(?:rs|inr|rupees?)\b))?"
    r"(?![\w]|[.,]\d)"
)

# Western (100,000) and Indian (1,00,000) digit grouping.
VALID_NUMBER = re.compile(
    r"(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?"
)

EXAMPLE = "Example: spent 250 on groceries"


def today_in_india():
    return datetime.now(TIMEZONE).date()


def has_word(text, *words):
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def first_match(text, mapping, default):
    for keyword in sorted(mapping, key=len, reverse=True):
        if has_word(text, keyword):
            return mapping[keyword]
    return default


def extract_date(text, today):
    """Return (date, text without the date). Raises ValueError if unusable."""
    matches = list(DATE_PATTERN.finditer(text))

    if not matches:
        return today, text

    if len(matches) > 1:
        raise ValueError("Please mention only one date.")

    match = matches[0]

    try:
        if match["relative"]:
            days = 1 if match["relative"] == "yesterday" else 0
            found = today - timedelta(days=days)
        elif match["iso"]:
            found = date.fromisoformat(match["iso"])
        else:
            day = int(match["d"] or match["day"])
            month = int(match["m"]) if match["m"] else MONTHS[match["month"]]
            year = match["y"] or match["year"]
            found = date(int(year) if year else today.year, month, day)

            # "30 dec" typed in January means last December.
            if not year and found > today:
                found = found.replace(year=today.year - 1)
    except ValueError:
        raise ValueError("That date isn't valid. Example: 5 nov or 05/11/2026")

    if found > today:
        raise ValueError("The date can't be in the future.")

    return found, text[:match.start()] + " " + text[match.end():]


def extract_amount(text):
    """Return the single amount in the text. Raises ValueError if unclear."""
    matches = list(AMOUNT_PATTERN.finditer(text))

    if not matches:
        raise ValueError(f"I couldn't find an amount. {EXAMPLE}")

    # An explicit currency marker settles which number is the amount.
    marked = [m for m in matches if m["currency"] or m["suffix"]]
    candidates = marked or matches

    if len(candidates) > 1:
        raise ValueError(
            "I found more than one number. Send it again with ₹ before "
            "the amount, e.g. bought 2 tickets for ₹600"
        )

    match = candidates[0]

    if match["sign"] or match["sign2"]:
        raise ValueError("Amount must be greater than zero.")

    if not VALID_NUMBER.fullmatch(match["number"]):
        raise ValueError(f"I couldn't read that amount. {EXAMPLE}")

    amount = float(match["number"].replace(",", ""))

    if match["k"]:
        amount *= 1000

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    return round(amount, 2)


def parse_transaction(message: str, today=None):
    text = message.lower().strip()

    try:
        transaction_date, remaining = extract_date(text, today or today_in_india())
        amount = extract_amount(remaining)
    except ValueError as error:
        return {"error": str(error)}

    # Identify transaction type
    if has_word(text, "salary", "received", "income", "earned"):
        transaction_type = "Income"
    elif has_word(text, "invested", "investment", "nps", "mutual fund", "mutual funds"):
        transaction_type = "Investment"
    elif has_word(text, "transfer", "transferred"):
        # "paid by bank transfer" describes the payment method, not the type.
        without_method = text.replace("bank transfer", "")
        if has_word(without_method, "transfer", "transferred") or text.startswith("bank transfer"):
            transaction_type = "Transfer"
        else:
            transaction_type = "Expense"
    else:
        transaction_type = "Expense"

    if transaction_type == "Expense" and has_word(text, "emi", "loan payment"):
        transaction_type = "Debt Payment"

    default_category = "Other Income" if transaction_type == "Income" else "Miscellaneous"

    return {
        "date": transaction_date.isoformat(),
        "type": transaction_type,
        "category": first_match(text, CATEGORIES, default_category),
        "amount": amount,
        "paid_via": first_match(text, PAYMENT_METHODS, "Other"),
        "description": message.strip(),
    }
