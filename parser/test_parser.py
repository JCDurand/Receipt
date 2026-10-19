import unittest

import os
from typing import Any, Dict
from decimal import Decimal
from datetime import date
from types import SimpleNamespace

import pandas as pd

from csv_bank_parser import CsvBankParser
from csv_receipt_parser import CsvReceiptParser
from pdf_bank_parser import PdfBankParser
from pdf_receipt_parser import PdfReceiptParser


INPUT_DIR     = "parser/tests/input/csv"
INPUT_DIR_PDF = "parser/tests/input/pdf"
OUTPUT_DIR    = "parser/tests/output"


class TestCSVParser(unittest.TestCase):

    def transaction_equals(self, trans: Dict[str, Any], expected_date: date,
                           description: str, amount: Decimal):
        """
        Test if the given transaction has the given data.
        """
        self.assertEqual(trans["date"], expected_date)
        self.assertEqual(trans["description"], description)
        self.assertEqual(trans["amount"], amount)

    def setUp(self):
        """
        Initialise CSV bank parser.
        """
        self.parser = CsvBankParser()

    def test_date_formats(self):
        """
        Test that all date formats are correctly read and saved.
        """
        result = self.parser.parse(f"{INPUT_DIR}/date_format.csv");
        transactions, errors = result["transactions"], result["errors"]
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transactions), 7)
        expected_date = date.fromisoformat("2026-08-12")
        for transaction in transactions:
            self.transaction_equals(transaction, expected_date,
                                    "Test", Decimal(1))

    def test_currency_formats(self):
        """
        Test that all amount fields are correctly read and saved.
        """
        result = self.parser.parse(f"{INPUT_DIR}/currency_format.csv");
        transactions, errors = result["transactions"], result["errors"]
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transactions), 9)
        expected_date = date.fromisoformat("2026-08-12")
        for transaction in transactions:
            self.transaction_equals(transaction, expected_date,
                                    "Test", Decimal(1000))

    def test_missing_data(self):
        """
        Test that the parser fails correctly when fields are missing.
        """
        self.assertTrue(True)
        input_files = os.listdir(INPUT_DIR)
        for input_file in input_files:
            if not "missing" in input_file:
                continue
            with self.assertRaises(ValueError):
                result = self.parser.parse(f"{INPUT_DIR}/{input_file}")


class TestCSVReceiptParser(unittest.TestCase):

    def setUp(self):
        """
        Initialise CSV receipt parser before each test.
        """
        self.parser = CsvReceiptParser()

    def transaction_equals(
        self,
        transaction: Dict[str, Any],
        expected_merchant: str,
        expected_date: date,
        item: str,
        quantity: int,
        unit_price: Decimal,
        amount: Decimal
    ):
        """
        Verify a parsed receipt transaction matches expected values.
        """
        self.assertEqual(transaction["merchant"], expected_merchant)
        self.assertEqual(transaction["date"], expected_date)
        self.assertEqual(transaction["item"], item)
        self.assertEqual(transaction["quantity"], quantity)
        self.assertEqual(transaction["unit_price"], unit_price)
        self.assertEqual(transaction["amount"], amount)

    def test_valid_receipt(self):
        """
        Test that a valid receipt CSV is parsed correctly.
        """
        result = self.parser.parse(
            f"{INPUT_DIR}/receipt_valid.csv"
        )

        transactions = result["transactions"]
        errors = result["errors"]

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transactions), 1)

        self.transaction_equals(
            transactions[0],
            "Test Merchant",
            date.fromisoformat("2026-08-12"),
            "Test Item",
            2,
            Decimal("100"),
            Decimal("200")
            )

    def test_missing_date_column(self):
        """
        Test that the parser raises ValueError when the date column
        is missing.
        """
        with self.assertRaises(ValueError):
            self.parser.parse(
                f"{INPUT_DIR}/receipt_missing_date.csv"
            )

    def test_missing_item_column(self):
        """
        Test that the parser raises ValueError when the item/description
        column is missing.
        """
        with self.assertRaises(ValueError):
            self.parser.parse(
                f"{INPUT_DIR}/receipt_missing_item.csv"
            )

    def test_missing_quantity_column(self):
        """
        Test that the parser raises ValueError when the quantity
        column is missing.
        """
        with self.assertRaises(ValueError):
            self.parser.parse(
                f"{INPUT_DIR}/receipt_missing_quantity.csv"
            )

    def test_missing_unit_price_column(self):
        """
        Test that the parser raises ValueError when the unit price
        column is missing.
        """
        with self.assertRaises(ValueError):
            self.parser.parse(
                f"{INPUT_DIR}/receipt_missing_unit_price.csv"
            )

    def test_missing_amount_column(self):
        """
        Test that the parser raises ValueError when the amount
        column is missing.
        """
        with self.assertRaises(ValueError):
            self.parser.parse(
                f"{INPUT_DIR}/receipt_missing_amount.csv"
            )

    def test_date_formats(self):
        """
        Test that all supported date formats are correctly parsed.
        """
        result = self.parser.parse(
            f"{INPUT_DIR}/receipt_date_formats.csv"
        )

        transactions = result["transactions"]
        errors = result["errors"]

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transactions), 6)

        expected_date = date.fromisoformat("2026-08-12")

        for transaction in transactions:
            self.transaction_equals(
                transaction,
                "Test Merchant",
                expected_date,
                "Test Item",
                1,
                Decimal("100"),
                Decimal("100")
            )

    def test_currency_formats(self):
        """
        Test that supported currency formats are correctly parsed.
        """
        result = self.parser.parse(
            f"{INPUT_DIR}/receipt_currency_formats.csv"
        )

        transactions = result["transactions"]
        errors = result["errors"]

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transactions), 3)

        expected_date = date.fromisoformat("2026-08-12")

        for transaction in transactions:
            self.transaction_equals(
                transaction,
                "Test Merchant",
                expected_date,
                "Test Item",
                1,
                Decimal("1000.00"),
                Decimal("1000.00")
            )

    def test_header_alternatives(self):
        """
        Test that alternative supported column names are accepted.
        """
        result = self.parser.parse(
            f"{INPUT_DIR}/receipt_header_alternatives.csv"
        )

        transactions = result["transactions"]
        errors = result["errors"]

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transactions), 1)

        self.transaction_equals(
            transactions[0],
            "Test Merchant",
            date.fromisoformat("2026-08-12"),
            "Alternative Item",
            3,
            Decimal("50"),
            Decimal("150")
        )

    def test_invalid_row_data(self):
        """
        Test that invalid row data is reported as an error and
        valid rows are still parsed.
        """
        result = self.parser.parse(
            f"{INPUT_DIR}/receipt_invalid_row.csv"
        )

        transactions = result["transactions"]
        errors = result["errors"]

        self.assertEqual(len(transactions), 1)
        self.assertEqual(len(errors), 1)

        self.assertEqual(
            transactions[0]["item"],
            "Valid Item"
        )

        self.assertIn("Invalid Item", errors[0])


class TestPdfBankParser(unittest.TestCase):

    def test_investec_input(self):
        csv_parser = CsvBankParser()
        pdf_parser = PdfBankParser()

        csv_result = csv_parser.parse(f"{INPUT_DIR}/manual_testable.csv")
        if not os.path.isdir(OUTPUT_DIR):
            os.mkdir(OUTPUT_DIR)
        _ = pdf_parser.parse(f"{INPUT_DIR_PDF}/Testable.pdf", f"{OUTPUT_DIR}/Testable", "Investec", 2)
        pdf_result = csv_parser.parse(f"{OUTPUT_DIR}/Testable-page-2-table-1.csv")

        self.assertEqual(csv_result, pdf_result)


class TestPDFReceiptParser(unittest.TestCase):

    @staticmethod
    def table(rows):
        """A stand-in for a camelot table: only its dataframe is read."""
        return SimpleNamespace(df=pd.DataFrame(rows))

    def test_minimal_parse(self):
        pdf_parser = PdfReceiptParser()
        result = pdf_parser.minimal_parse(f"{INPUT_DIR_PDF}/Testable_receipt.pdf")
        self.assertEqual(result, 343)

    def test_full_parse(self):
        """
        Test that line items, merchant, date and total are all read from a
        real (photographed) receipt.
        """
        result = PdfReceiptParser().parse(f"{INPUT_DIR_PDF}/Testable_receipt.pdf")
        transactions = result["transactions"]

        self.assertEqual(result["errors"], [])
        self.assertEqual(result["total"], 343)
        self.assertEqual(
            [t["amount"] for t in transactions],
            [Decimal("209.95"), Decimal("23.05"), Decimal("110.00")],
        )
        for transaction in transactions:
            self.assertEqual(transaction["merchant"], "CONVIENIENCE CENTRE")
            self.assertEqual(transaction["date"], date(2026, 5, 9))
            self.assertEqual(transaction["quantity"], 1)

    def test_unreadable_pdf(self):
        """
        Test that a file which is not really a pdf is reported rather than
        crashing or returning nothing.
        """
        from abstract_parser import ParseException
        with self.assertRaises(ParseException):
            PdfReceiptParser().parse(f"{INPUT_DIR}/sample_receipt_checkers.csv")

    def test_extract_items_single_cell_rows(self):
        """
        Test items are read when a row is one cell of "name, newline, price",
        with OCR's comma and dropped decimal points, and reading stops at the total.
        """
        table = self.table({0: [
            "SHOP NAME",
            "Milk \n1 209,95",
            "Bread \n18.50",
            "Discount \n-5 00",
            "ITEMS 3 \nTOTAL \n223 45",
            "Card \n223.45",
        ]})
        items = PdfReceiptParser.extract_items(table)

        self.assertEqual([i["item"] for i in items], ["Milk", "Bread", "Discount"])
        self.assertEqual(
            [i["amount"] for i in items],
            [Decimal("1209.95"), Decimal("18.50"), Decimal("-5.00")],
        )

    def test_extract_items_multiple_columns(self):
        """
        Test items are read when each column of the receipt is its own cell,
        including a quantity between the name and price.
        """
        table = self.table({
            0: ["Item", "Milk 2L", "Bread", "Total"],
            1: ["Qty", "2", "", ""],
            2: ["Price", "57.98", "18.50", "76.48"],
        })
        items = PdfReceiptParser.extract_items(table)

        self.assertEqual([i["item"] for i in items], ["Milk 2L", "Bread"])
        self.assertEqual(items[0]["quantity"], 2)
        self.assertEqual(items[0]["unit_price"], Decimal("28.99"))
        self.assertEqual(items[0]["amount"], Decimal("57.98"))
        self.assertEqual(items[1]["quantity"], 1)

    def test_extract_items_none_found(self):
        """
        Test that a table with no priced rows gives no items.
        """
        table = self.table({0: ["SHOP NAME", "VAT REG. NO.4580164244", "Thank you"]})
        self.assertEqual(PdfReceiptParser.extract_items(table), [])

if __name__ == "__main__":
    unittest.main()
