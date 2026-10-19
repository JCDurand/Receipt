"""
Turns the output of the bank statement parsers into the JSON the frontend shows
in the upload dialog: the transactions found, and a list of issues.
"""
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Prefetch

from parser.abstract_parser import ParseException
from parser.csv_bank_parser import CsvBankParser
from parser.pdf_bank_parser import PdfBankParser
from .models import Tag, TransactionTemplate

logger = logging.getLogger(__name__)

# The largest amount a Transaction can store (max_digits=10, decimal_places=2)
MAX_AMOUNT = Decimal("99999999.99")

CENT = Decimal("0.01")


def _fail(message):
    return {"transactions": [], "issues": [message]}


def parse_statement(path, extension, work_dir, bank="investec", user=None):
    """
    Read the transactions of a bank statement without saving anything.

    Never raises for a bad file: anything that goes wrong is reported in the
    returned "issues" so the user can see it, and whatever could be read is
    still returned.

    Parameters
    ----------
    path : str
        Where the file is on disk.
    extension : str
        ".pdf" or ".csv"
    work_dir : str
        A scratch directory, for the CSV a PDF is first turned into.
    bank : str
        The bank type to use for parsing.

    Returns
    -------
    dict
        transactions (name, date as an ISO string, amount as a signed string:
        a debit is negative and a credit positive) and issues (a list of
        messages).
    """
    extension = extension.lower()
    issues = []
    try:
        if extension == ".pdf":
            pdf_result = PdfBankParser().parse(
                path, os.path.join(work_dir, "statement"), bank=bank
            )
            if not pdf_result["filenames"]:
                return _fail("Transactions could not be read: no transactions table was found in this file.")
            path = pdf_result["filenames"][0]
            parsed = CsvBankParser().parse(path)
            for path in pdf_result["filenames"][1:]:
                add_result = CsvBankParser().parse(path)
                for key, value in add_result.items():
                    field_type = type(value)
                    target = parsed[key]
                    if field_type != list or type(target) != field_type: continue
                    target.extend(value)
        elif extension != ".csv":
            return _fail(f"'{extension}' files cannot be read for transactions.")
        else:
            parsed = CsvBankParser().parse(path)
    except (ValueError, ParseException) as e:
        # The parsers' own messages, e.g. "Missing required column: date"
        return _fail(f"Transactions could not be read: {e}")
    except Exception:
        logger.exception("Unexpected error while parsing %s", path)
        return _fail("Transactions could not be read: this file is not in a supported format.")

    issues.extend(parsed["errors"])

    templates = (
        list(
            TransactionTemplate.objects.filter(user=user).prefetch_related(
                Prefetch("tags", queryset=Tag.objects.available_to(user))
            )
        )
        if user
        else []
    )

    transactions = []
    for row in parsed["transactions"]:
        amount = row["amount"].quantize(CENT, ROUND_HALF_UP)
        if abs(amount) > MAX_AMOUNT:
            issues.append(f"'{row['description']}' has an amount that is too large to store.")
            continue

        original_name = row["description"]
        merchant_name = original_name
        applied_tags = []

        longest_match = None
        for template in templates:
            if template.search_string.lower() in original_name.lower():
                if not longest_match or len(template.search_string) > len(longest_match.search_string):
                    longest_match = template

        if longest_match:
            if longest_match.merchant_name:
                merchant_name = longest_match.merchant_name
            applied_tags.extend(str(tag.id) for tag in longest_match.tags.all())


        transactions.append(
            {
                "name": original_name,
                "merchant": merchant_name if merchant_name != original_name else "",
                "date": row["date"].isoformat(),
                "amount": str(amount),
                "tags": applied_tags,
                "direction": "debit" if amount < 0 else "credit"
            }
        )

    if not transactions and not issues:
        issues.append("No transactions were found in this file.")

    return {"transactions": transactions, "issues": issues}
