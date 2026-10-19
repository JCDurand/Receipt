import unittest
import logging
import os
import sys
from decimal import Decimal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from parser.csv_receipt_parser import CsvReceiptParser

logging.basicConfig(level=logging.INFO)


class TestCsvReceiptParser(unittest.TestCase):

    def test_checkers_receipt(self):
        parser = CsvReceiptParser()
        result = parser.parse("parser/sample_receipt_checkers.csv")

        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(len(result["transactions"]), 3)

        transaction = result["transactions"][0]
        self.assertEqual(transaction["item"], "Milk 2L")
        self.assertEqual(transaction["quantity"], 2)
        self.assertEqual(transaction["unit_price"], Decimal("28.99"))
        self.assertEqual(transaction["amount"], Decimal("57.98"))

    def test_woolworths_receipt(self):
        parser = CsvReceiptParser()
        result = parser.parse("parser/sample_receipt_woolworths.csv")

        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(len(result["transactions"]), 3)

        transaction = result["transactions"][0]
        self.assertEqual(transaction["item"], "Greek Yoghurt")
        self.assertEqual(transaction["quantity"], 2)
        self.assertEqual(transaction["unit_price"], Decimal("25.00"))
        self.assertEqual(transaction["amount"], Decimal("50.00"))

    def test_picknpay_receipt(self):
        parser = CsvReceiptParser()
        result = parser.parse("parser/sample_receipt_picknpay.csv")

        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(len(result["transactions"]), 3)

        transaction = result["transactions"][0]
        self.assertEqual(transaction["item"], "Eggs 18")
        self.assertEqual(transaction["quantity"], 1)
        self.assertEqual(transaction["unit_price"], Decimal("59.99"))
        self.assertEqual(transaction["amount"], Decimal("59.99"))


if __name__ == "__main__":
    unittest.main()
