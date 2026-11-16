
import re
from datetime import date

CATEGORIES = {
    "groceries": "Groceries",
    "grocery": "Groceries",
    "food": "Food & Dining",
    "restaurant": "Food & Dining",
    "petrol": "Petrol & Transport",
    "fuel": "Petrol & Transport",
    "transport": "Petrol & Transport",
    "shopping": "Shopping",
    "electricity": "Housing & Bills",
    "rent": "Housing & Bills",
    "bill": "Housing & Bills",
    "medical": "Healthcare",
    "medicine": "Healthcare",
    "health": "Healthcare",
    "insurance": "Insurance",
    "movie": "Entertainment",
    "entertainment": "Entertainment",
    "travel": "Travel",
    "subscription": "Subscriptions",
    "salary": "Salary",
    "freelance": "Freelance Income",
    "nps": "NPS",
    "mutual fund": "Mutual Funds",
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


def parse_transaction(message: str):
    text = message.lower().strip()

    # Extract amount
    amount_match = re.search(
        r"(?:₹|rs\.?\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)",
        text,
    )

    if not amount_match:
        return {"error": "I couldn't find an amount. Example: spent 250 on groceries"}

    amount = float(amount_match.group(1).replace(",", ""))

    if amount <= 0:
        return {"error": "Amount must be greater than zero."}

    # Identify transaction type
    if any(word in text for word in ["salary", "received", "income", "earned"]):
        transaction_type = "Income"
    elif any(word in text for word in ["invested", "investment", "nps", "mutual fund"]):
        transaction_type = "Investment"
    elif "transfer" in text:
        transaction_type = "Transfer"
    elif "emi" in text or "loan payment" in text:
        transaction_type = "Debt Payment"
    else:
        transaction_type = "Expense"

    # Identify category
    category = None
    for keyword in sorted(CATEGORIES, key=len, reverse=True):
        if keyword in text:
            category = CATEGORIES[keyword]
            break

    if category is None:
        category = "Other Income" if transaction_type == "Income" else "Miscellaneous"

    # Identify payment method
    payment_method = "Other"
    for keyword in sorted(PAYMENT_METHODS, key=len, reverse=True):
        if keyword in text:
            payment_method = PAYMENT_METHODS[keyword]
            break

    return {
        "date": date.today().isoformat(),
        "type": transaction_type,
        "category": category,
        "amount": amount,
        "paid_via": payment_method,
        "description": message.strip(),
    }

