import unittest
import sys
import os
import logging
from typing import Any, Dict
from decimal import Decimal
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from csv_bank_parser import CsvBankParser

logging.basicConfig(level=logging.INFO)

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
        result = self.parser.parse("parser/tests/input/csv/date_format.csv");
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
        result = self.parser.parse("parser/tests/input/csv/currency_format.csv");
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
        TEST_DIR = "parser/tests/input/csv"
        input_files = os.listdir(TEST_DIR)
        for input_file in input_files:
            if not "missing" in input_file:
                continue
            with self.assertRaises(ValueError):
                result = self.parser.parse(f"{TEST_DIR}/{input_file}")


if __name__ == "__main__":
    unittest.main()
