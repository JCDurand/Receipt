import csv
from typing import Any, Dict, List

from .abstract_parser import Parser


class CsvBankParser(Parser):
    """Read a bank statement CSV and return a list of transactions."""

    def parse(self, file_path: str) -> Dict[str, List[Any]]:
        self.logger.info("Received CSV bank file for parsing: %s", file_path)

        transactions = []
        errors = []

        try:
            with open(
                file_path,
                mode="r",
                newline="",
                encoding="utf-8-sig"
            ) as csv_file:
                reader = csv.DictReader(csv_file)

                header_options = {
                    "date": ["Date", "Posted Date"],
                    "description": ["Description", "Transaction Description"],
                    "amount": ["Amount"],
                    "debit": ["Debit"],
                    "credit": ["Credit"],
                }

                headers = reader.fieldnames or []

                header_lookup = {
                    header.lower(): header
                    for header in headers
                }

                header_map = {}

                # Required fields
                for field in ["date", "description"]:
                    for option in header_options[field]:
                        if option.lower() in header_lookup:
                            header_map[field] = header_lookup[option.lower()]
                            break
                    else:
                        raise ValueError(
                            f"Missing required column: {field}"
                        )

                # Amount OR Debit/Credit
                amount_header = next(
                    (
                        header_lookup[h.lower()]
                        for h in header_options["amount"]
                        if h.lower() in header_lookup
                    ),
                    None,
                )

                debit_header = next(
                    (
                        header_lookup[h.lower()]
                        for h in header_options["debit"]
                        if h.lower() in header_lookup
                    ),
                    None,
                )

                credit_header = next(
                    (
                        header_lookup[h.lower()]
                        for h in header_options["credit"]
                        if h.lower() in header_lookup
                    ),
                    None,
                )

                if amount_header:
                    header_map["amount"] = amount_header
                elif debit_header and credit_header:
                    header_map["debit"] = debit_header
                    header_map["credit"] = credit_header
                else:
                    raise ValueError(
                        "CSV must contain either an Amount or both Debit and Credit columns."
                    )

                for line_number, row in enumerate(reader, start=2):

                    # Skip completely empty rows
                    if not any(
                        value.strip()
                        for value in row.values()
                        if value
                    ):
                        continue

                    try:
                        if "amount" in header_map:
                            amount = Parser.parse_amount(
                                row[header_map["amount"]]
                            )
                        else:
                            debit = row[header_map["debit"]].strip()
                            credit = row[header_map["credit"]].strip()

                            if credit:
                                amount = Parser.parse_amount(credit)
                            elif debit:
                                amount = -Parser.parse_amount(debit)
                            else:
                                raise ValueError(
                                    "Both Debit and Credit are empty"
                                )

                        transaction = {
                            "date": Parser.parse_date(
                                row[header_map["date"]]
                            ),
                            "description": row[
                                header_map["description"]
                            ].strip(),
                            "amount": amount
                        }

                        transactions.append(transaction)

                    except Exception as e:
                        description = row.get(
                            header_map.get("description", ""),
                            "Unknown"
                        )

                        error = (
                            f"Line {line_number} "
                            f"({description}): {e}"
                        )

                        errors.append(error)

                        self.logger.error(
                            "Error parsing CSV bank line %d (%s): %s",
                            line_number,
                            description,
                            e
                        )

        except Exception as e:
            self.logger.error(
                "Error parsing CSV bank file %s: %s",
                file_path,
                e
            )
            raise

        self.logger.info(
            "Successfully parsed CSV bank file: %s",
            file_path
        )

        self.logger.info(
            "Parsing complete: %d transactions, %d errors",
            len(transactions),
            len(errors)
        )

        return {
            "transactions": transactions,
            "errors": errors
        }


if __name__ == "__main__":
    import sys
    csv_parser = CsvBankParser()
    print(csv_parser.parse(sys.argv[1]))
