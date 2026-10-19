import camelot
import numpy as np
import pandas as pd

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
import shutil
import os
import re
import subprocess
import sys
import tempfile

from .abstract_parser import Parser, ParseException

# regex for (possibly negative) decimal numbers
NUMBER_PATTERN = r"[-+]?\d*\.?\d+"

LAYERED_FOLDER = "text_layered"

# A price at the end of a line of OCR text, e.g. "23.05", "209,95" or "343  00":
# OCR often turns the decimal point into a comma or drops it for a space.
PRICE_PATTERN = re.compile(r"^R?\s*(-?\d[\d ]*?)\s*[.,\s]\s*(\d{2})$")
# A plain quantity cell, e.g. "2" or "0.5"
QUANTITY_PATTERN = re.compile(r"^\d+(?:[.,]\d{1,3})?$")
# Dates as they appear on receipts, e.g. 09/05/2026 or 2026-05-09
DATE_PATTERN = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b")
# Rows from here on (e.g. "TOTAL", "SUBTOTAL") are no longer line items
TOTAL_PATTERN = re.compile(r"total", re.IGNORECASE)
# Only tables the extractor is at least this sure about are trusted
MIN_TABLE_CONFIDENCE = 0.7

class PdfReceiptParser(Parser):
    """Read a receipt PDF, add a text layer to it, then extract required information."""

    def __init__(self):
        """
        Ensure on parser creation that the temporary folder exists.
        """
        super().__init__()
        if not os.path.exists(LAYERED_FOLDER):
            os.mkdir(LAYERED_FOLDER)

    def __del__(self):
        """
        Ensure on parser destruction that the temporary folder no longer exists.
        """
        if os.path.exists(LAYERED_FOLDER):
            shutil.rmtree(LAYERED_FOLDER, ignore_errors=True)

    @staticmethod
    def find_total(table: camelot.core.Table) -> Decimal:
        """
        Extract a total value from a table from a receipt.

        Parameters
        ----------
        table : camelot.table
            The camelot table to try extract from.

        Returns
        -------
        Decimal or None
            The total extracted, or None if nothing could be found.
        """
        df = table.df
        # find all occurrences of the string "total" with any case, including string with newlines
        mask = df.map(lambda x : bool(re.search("Total", str(x), re.DOTALL | re.IGNORECASE)))
        rows, _ = np.where(mask)
        rows = list(rows)
        rows_dupe = rows[:]
        # some total amounts only appear a row after the word "Total"
        for row in rows_dupe:
            if row + 1 < df.shape[0]:
                rows.append(row+1)
        numbers = []
        for cell in df.iloc[rows].to_numpy().ravel():
            # numbers may be comma separated or spread across lines
            contents = str(cell).replace("\n", "").replace(",", "")
            for number in re.findall(NUMBER_PATTERN, contents):
                numbers.append(number)
        return max(map(Decimal, numbers)) if len(numbers) > 0 else None

    def run_ocr(self, filepath: str) -> bool:
        """
        Add a text layer to the given PDF using ocrmypdf.

        Parameters
        ----------
        filepath : str
            path to PDF

        Returns
        -------
        bool
            True if ocrmypdf exited with zero, False otherwise
        """
        file = filepath.split("/")[-1]
        self.logger.debug("Running ocrmypdf:")
        # ocrmypdf adds a text layer to image-only pdfs
        try:
            process = subprocess.run(["ocrmypdf", "--force-ocr", filepath, f"{LAYERED_FOLDER}/{file}"],
                                     check=True, capture_output=True, text=True)
            # ocrmypdf writes some useful information, but it does it to stderr
            self.logger.debug(process.stderr)
            self.logger.debug("-------------------\nEnd ocrmypdf output")
            self.logger.debug(f"Generated file {LAYERED_FOLDER}/{file}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"ocrmypdf exited with code {e.returncode}:\n{e.stderr}")
            return False
        return True

    def minimal_parse(self, filepath: str, skip_ocr: bool = False) -> Decimal:
        """
        Read a given receipt pdf and attempt to extract only the total.

        Parameters
        ----------
        filepath : str
            The location of the receipt pdf.
        skip_ocr : bool
            Whether the given pdf already has a text-layer and OCR is not required.

        Returns
        -------
        Decimal | None
            The total found, or None if no total could be found.
        """
        self.logger.info(f"Running minimal parse on {filepath}")
        file = filepath.split("/")[-1]
        # on ocr failure, simply give up
        if not skip_ocr:
            if not self.run_ocr(filepath): return None
        found_total = False
        total = None
        for flavor in ["lattice", "stream"]:
            self.logger.debug(f"Trying flavour {flavor}")
            tables = camelot.read_pdf(f"{LAYERED_FOLDER}/{file}", flavor=flavor)
            for table in tables:
                if table.confidence >= 0.7:
                    total = self.find_total(table)
                    if total != None:
                        self.logger.info(f"Found total {total}")
                        found_total = True
                        break
                else:
                    self.logger.debug(f"Ignoring table with confidence {table.confidence}")
            if found_total: break
        else:
            self.logger.warning("Failed to find total in any sufficiently confident table")
        return total

    @staticmethod
    def _clean(text: Any) -> str:
        """Collapse the runs of whitespace that OCR leaves in table cells."""
        return re.sub(r"\s+", " ", str(text)).strip()

    @staticmethod
    def _to_price(text: str) -> Optional[Decimal]:
        """Read a price such as "23.05", "209,95" or "343 00", or None if it isn't one."""
        match = PRICE_PATTERN.match(PdfReceiptParser._clean(text))
        if not match:
            return None
        whole, cents = match.groups()
        try:
            return Decimal(f"{whole.replace(' ', '')}.{cents}")
        except InvalidOperation:
            return None

    @staticmethod
    def extract_items(table: camelot.core.Table) -> List[Dict[str, Any]]:
        """
        Read line items from a receipt table.

        A row is a line item when it has some text followed by a price. Reading
        stops at the first row that mentions a total, so totals, tender and VAT
        breakdowns further down are not mistaken for items.

        Parameters
        ----------
        table : camelot.table
            The camelot table to try extract from.

        Returns
        -------
        list of dict
            The items, each with "item", "quantity", "unit_price" and "amount".
        """
        items = []
        for _, row in table.df.iterrows():
            cells = [c for c in (PdfReceiptParser._clean(v) for v in row) if c]
            if not cells:
                continue
            if TOTAL_PATTERN.search(" ".join(cells)):
                break

            quantity = Decimal(1)
            if len(cells) == 1:
                # Everything in one cell: the name, then the price on the last line
                lines = [ln for ln in (PdfReceiptParser._clean(v)
                                       for v in str(row.iloc[0]).split("\n")) if ln]
                if len(lines) < 2:
                    continue
                name = " ".join(lines[:-1])
                amount = PdfReceiptParser._to_price(lines[-1])
            else:
                # One cell per column: name first, price last, and possibly a
                # quantity in between
                name = cells[0]
                amount = PdfReceiptParser._to_price(cells[-1])
                for cell in cells[1:-1]:
                    if QUANTITY_PATTERN.match(cell):
                        quantity = Decimal(cell.replace(",", "."))
                        break

            if amount is None or not name:
                continue
            unit_price = amount / quantity if quantity > 0 else amount
            items.append({
                "item": name,
                "quantity": quantity,
                "unit_price": unit_price.quantize(Decimal("0.01")),
                "amount": amount,
            })
        return items

    @staticmethod
    def find_merchant(table: camelot.core.Table) -> Optional[str]:
        """The merchant is taken to be the first line of text on the receipt."""
        for _, row in table.df.iterrows():
            for value in row:
                for line in str(value).split("\n"):
                    line = PdfReceiptParser._clean(line)
                    if re.search(r"[A-Za-z]{3}", line):
                        return line
        return None

    @staticmethod
    def find_date(tables: List[camelot.core.Table]):
        """Find the first date printed anywhere on the receipt, or None."""
        for table in tables:
            for value in table.df.to_numpy().ravel():
                for candidate in DATE_PATTERN.findall(str(value)):
                    try:
                        return Parser.parse_date(candidate)
                    except ValueError:
                        continue
        return None

    def parse(self, filepath: str) -> Dict[str, Any]:
        """
        Read a receipt pdf and attempt to extract its line items.

        Returns the same shape as CsvReceiptParser.parse, plus the receipt total.
        Nothing here is guaranteed: receipts are photographed or printed in every
        layout imaginable, so what could not be read is described in "errors"
        rather than guessed at.

        Parameters
        ----------
        filepath : str
            The location of the receipt pdf.

        Returns
        -------
        dict
            "transactions": the line items found, like the CSV receipt parser's
            "errors": a description of everything that went wrong
            "total": the receipt total as a Decimal, or None if not found

        Raises
        ------
        ParseException
            If the pdf could not be read at all.
        """
        self.logger.info(f"Running full parse on {filepath}")
        errors = []

        with tempfile.TemporaryDirectory() as layered_dir:
            layered_file = os.path.join(layered_dir, "receipt.pdf")
            try:
                # ocrmypdf adds a text layer to image-only pdfs
                subprocess.run(["ocrmypdf", "--force-ocr", filepath, layered_file],
                               check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"ocrmypdf exited with code {e.returncode}:\n{e.stderr}")
                raise ParseException("The PDF could not be read.") from e

            tables = []
            items = []
            for flavor in ["lattice", "stream"]:
                self.logger.debug(f"Trying flavour {flavor}")
                found = [t for t in camelot.read_pdf(layered_file, flavor=flavor)
                         if t.confidence >= MIN_TABLE_CONFIDENCE]
                tables.extend(found)
                for table in found:
                    items = self.extract_items(table)
                    if items:
                        break
                if items:
                    break

            total = None
            for table in tables:
                total = self.find_total(table)
                if total is not None:
                    break

            merchant = self.find_merchant(tables[0]) if tables else None
            receipt_date = self.find_date(tables)

        if not tables:
            errors.append("No receipt text could be recognised in this PDF.")
        elif not items:
            errors.append("No line items could be recognised in this PDF.")
        if total is None:
            errors.append("The receipt total could not be found.")
        elif items:
            items_total = sum((i["amount"] for i in items), Decimal(0))
            if items_total != total:
                errors.append(
                    f"The line items add up to {items_total} but the receipt total is {total}."
                )

        return {
            "transactions": [
                {"merchant": merchant, "date": receipt_date, **item} for item in items
            ],
            "errors": errors,
            "total": total,
        }


if __name__ == "__main__":
    parser = PdfReceiptParser()
    print(parser.parse(sys.argv[1]))
