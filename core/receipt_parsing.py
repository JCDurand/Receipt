"""
Turns the output of the receipt parsers into the JSON shape the frontend shows
in the upload dialog: line items, receipt details and a list of issues.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from parser.abstract_parser import ParseException
from parser.csv_receipt_parser import CsvReceiptParser
from parser.pdf_receipt_parser import PdfReceiptParser

logger = logging.getLogger(__name__)

# The largest amount an Item can store (max_digits=10, decimal_places=2)
MAX_AMOUNT = Decimal("99999999.99")

CENT = Decimal("0.01")
MILLI = Decimal("0.001")


def _quantity(value):
    """A quantity as plain text: "2", "0.5" - never "1E+1" or "2.000"."""
    text = format(Decimal(value).quantize(MILLI, ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def unit_price_for(total, quantity):
    """
    What one of a receipt line's items costs: the line's total shared between
    them, so a line of 5 red apples for 70.00 is 14.00 each. The total is what the
    receipt says and does not change with the quantity. Raises ValueError if the
    price is more than an Item can store.
    """
    price = (abs(total) / quantity).quantize(CENT, ROUND_HALF_UP)
    if price > MAX_AMOUNT:
        raise ValueError("That quantity makes the price of each item too large to store.")
    return price


def _fail(message):
    return {
        "merchant_name": None,
        "transaction_date": None,
        "total_amount": None,
        "items": [],
        "issues": [message],
    }


def parse_receipt(path, extension):
    """
    Read line items from a receipt file without saving anything.

    Never raises for a bad file: anything that goes wrong is reported in the
    returned "issues" so the user can see it, and whatever could be read is
    still returned.

    Parameters
    ----------
    path : str
        Where the file is on disk.
    extension : str
        ".pdf" or ".csv"

    Returns
    -------
    dict
        merchant_name, transaction_date (ISO string), total_amount (string),
        items (name, quantity, unit_price, total - all strings) and issues
        (a list of messages).
    """
    extension = extension.lower()
    try:
        if extension == ".csv":
            parsed = CsvReceiptParser().parse(path)
            total = (
                CsvReceiptParser().get_total(parsed["transactions"])
                if parsed["transactions"]
                else None
            )
        elif extension == ".pdf":
            parsed = PdfReceiptParser().parse(path)
            total = parsed["total"]
        else:
            return _fail(f"'{extension}' files cannot be read for line items.")
    except (ValueError, ParseException) as e:
        # The parsers' own messages, e.g. "Missing required column: item"
        logger.warning("Receipt parser rejected file %s: %s", path, e)
        return _fail(f"Line items could not be read: {e}")
    except Exception:
        logger.exception("Unexpected error while parsing %s", path)
        return _fail("Line items could not be read: this file is not in a supported format.")

    transactions = parsed["transactions"]
    issues = list(parsed["errors"])

    items = []
    for transaction in transactions:
        name = transaction.get("description") or transaction.get("item") or ""
        quantity = transaction.get("quantity", 1)
        quantity = Decimal(str(quantity))

        amount = transaction["amount"].quantize(CENT, ROUND_HALF_UP)
        if "unit_price" in transaction:
            unit_price = transaction["unit_price"].quantize(CENT, ROUND_HALF_UP)
        else:
            try:
                unit_price = unit_price_for(amount, quantity)
            except ValueError as e:
                issues.append(f"'{name}': {e}")
                continue

        if abs(amount) > MAX_AMOUNT or abs(unit_price) > MAX_AMOUNT:
            issues.append(f"'{name}' has an amount that is too large to store.")
            continue

        items.append({
            "name": name,
            "quantity": _quantity(quantity),
            "unit_price": str(unit_price),
            "total": str(amount),
        })

    if not items and not issues:
        issues.append("No line items were found in this file.")

    first = transactions[0] if transactions else {}
    receipt_date = first.get("date")
    if total is not None:
        total = total.quantize(CENT, ROUND_HALF_UP)

    return {
        "merchant_name": first.get("merchant") or None,
        "transaction_date": receipt_date.isoformat() if receipt_date else None,
        "total_amount": str(total) if total is not None else None,
        "items": items,
        "issues": issues,
    }
