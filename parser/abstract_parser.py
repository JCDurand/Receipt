import logging

from datetime import datetime, date
from decimal import Decimal

class ParseException(Exception):
    pass

class Parser():
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def parse_date(date_string: str) -> date:
        """Convert different date formats into a consistent date object."""

        formats = [
            "%d/%m/%Y",  # 12/08/2026
            "%d-%m-%Y",  # 12-08-2026
            "%Y/%m/%d",  # 2026/08/12
            "%Y-%m-%d",  # 2026-08-12
            "%d/%m/%y",  # 12/08/26
            "%d-%m-%y",  # 12-08-26
            "%d %b %Y",  # 12 Aug 2026
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_string.strip(), fmt).date()
            except ValueError:
                continue

        raise ValueError(f"Unsupported date format: {date_string}")

    @staticmethod
    def parse_amount(amount_string: str) -> Decimal:
        """Convert different currency formats into a Decimal."""

        cleaned = (
            amount_string.strip()
            .replace("R", "").replace("r", "")
            .replace(",", "")
            .replace(" ", "")
        )

        return Decimal(cleaned)
