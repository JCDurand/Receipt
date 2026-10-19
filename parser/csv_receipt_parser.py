import csv
from typing import Any, Dict, List
from decimal import Decimal

from .abstract_parser import Parser


class CsvReceiptParser(Parser):
    """
    Parser for CSV receipt files.

    Expected columns can include:
    - Merchant
    - Date
    - Item
    - Quantity
    - Unit Price
    - Amount
    """

    HEADER_OPTIONS = {
        "merchant": ["Merchant", "merchant", "Store", "store"],
        "date": ["Date", "date"],
        "item": ["Item", "item", "Description", "description"],
        "quantity": ["Quantity", "quantity", "Qty", "qty"],
        "unit_price": ["Unit Price", "unit_price", "UnitPrice", "unit price"],
        "amount": ["Amount", "amount", "Total", "total"],
    }

    def _find_header(self, headers: List[str], options: List[str]) -> str | None:
        for option in options:
            if option in headers:
                return option
        return None

    def get_total(self, transactions: List[Dict[str, Any]]) -> Decimal:
        total = Decimal("0")
        for transaction in transactions:
            total += transaction["amount"]
        return total

    def parse(self, file_path: str) -> Dict[str, Any]:
        self.logger.info(
            "Received CSV receipt file for parsing: %s",
            file_path
        )

        transactions: List[Dict[str, Any]] = []
        errors: List[str] = []

        try:
            with open(file_path, "r", newline="", encoding="utf-8-sig") as file:
                reader = csv.DictReader(file)

                if not reader.fieldnames:
                    error = "CSV receipt file has no headers."
                    self.logger.error(error)
                    return {
                        "transactions": [],
                        "errors": [error],
                        "total": Decimal("0"),
                    }

                headers = reader.fieldnames

                merchant_header = self._find_header(
                    headers,
                    self.HEADER_OPTIONS["merchant"]
                )
                date_header = self._find_header(
                    headers,
                    self.HEADER_OPTIONS["date"]
                )
                item_header = self._find_header(
                    headers,
                    self.HEADER_OPTIONS["item"]
                )
                quantity_header = self._find_header(
                    headers,
                    self.HEADER_OPTIONS["quantity"]
                )
                unit_price_header = self._find_header(
                    headers,
                    self.HEADER_OPTIONS["unit_price"]
                )
                amount_header = self._find_header(
                    headers,
                    self.HEADER_OPTIONS["amount"]
                )

                if not date_header:
                    raise ValueError("Missing required column: date")
                
                if not item_header:
                    raise ValueError("Missing required column: item")

                if not amount_header and not (unit_price_header and quantity_header):
                    raise ValueError("Missing required column: amount")

                for row_number, row in enumerate(reader, start=2):
                    try:

                        date_value = row.get(date_header)
                        item_value = row.get(item_header)

                        if not date_value:
                            raise ValueError("Missing date.")

                        if not item_value:
                            raise ValueError("Missing item.")

                        parsed_date = Parser.parse_date(date_value)

                        if amount_header and row.get(amount_header):
                            amount = Parser.parse_amount(row[amount_header])

                        elif unit_price_header and quantity_header:
                            quantity = float(row[quantity_header])
                            unit_price = Parser.parse_amount(
                                row[unit_price_header]
                            )
                            amount = unit_price * quantity

                        else:
                            raise ValueError(
                                "Missing amount or unit price/quantity."
                            )

                        merchant = (
                            row.get(merchant_header, "")
                            if merchant_header
                            else ""
                        )

                        transaction = {
                            "date": parsed_date,
                            "description": item_value.strip(),
                            "amount": amount,
                            "merchant": merchant.strip(),
                        }

                        if quantity_header and row.get(quantity_header):
                            transaction["quantity"] = float(
                                row[quantity_header]
                            )

                        if unit_price_header and row.get(unit_price_header):
                            transaction["unit_price"] = Parser.parse_amount(
                                row[unit_price_header]
                            )

                        transactions.append(transaction)

                    except Exception as exc:
                        item_display = row.get(item_header) or "Unknown"
                        error = f"Row {row_number} ({item_display}): {exc}"
                        errors.append(error)
                        self.logger.error(
                            "Error parsing CSV receipt row %s (%s): %s",
                            row_number,
                            item_display,
                            exc
                            )

            total = self.get_total(transactions)

            self.logger.info(
                "Successfully parsed CSV receipt file: %s",
                file_path
            )

            self.logger.info(
                "Receipt parsing complete: %d transactions, %d errors",
                len(transactions),
                len(errors)
            )

            return {
                "transactions": transactions,
                "errors": errors,
                "total": total,
            }

        except Exception as exc:
            self.logger.error(
                "Error parsing CSV receipt file %s: %s",
                file_path,
                exc
            )
            raise


if __name__ == "__main__":
    import sys

    parser = CsvReceiptParser()

    if len(sys.argv) < 2:
        print("Usage: python csv_receipt_parser.py <csv_file>")
        sys.exit(1)

    result = parser.parse(sys.argv[1])

    print(result)
