import camelot

import pandas as pd
from typing import Any, Dict, List, Tuple
import re
from functools import lru_cache

from .abstract_parser import Parser, ParseException

class PdfBankParser(Parser):
    """Read a bank statement PDF and produce an estimate CSV."""

    """
    Different banks format their bank statements differently, and this format
    impacts the ideal choice for camelot parser.  Banks which have explicit
    grids in their tables should try `lattice`, banks with no gridlines but
    consistent whitespace should try `stream` or `network`.  Default behaviour
    is currently `auto` which tries to choose per page, but this behaviour
    should not be relied upon.
    """
    BANK_PARSE_METHODS = {
            "investec": "stream",
            "fnb": "stream", # weird extra spacing in the description makes this more consistent
            "absa": "stream",
    }

    @staticmethod
    def _clean_investec(tables: List[camelot.core.Table]) -> Tuple[List[pd.DataFrame], List[int]]:
        """
        Further process tables from an Investec bank statement.

        Parameters
        ----------
        tables : List[Table]
            A list of tables returned by camelot parser.

        Returns
        -------
        (List[DataFrame], List[int])
            A pair of Pandas data frames representing further processed data,
            and indices of tables which have been processed.
        """
        updated_tables = []
        kept_indices = []
        DEBIT_COL = 3
        CREDIT_COL = 4
        for i, table in enumerate(tables):
            if table.confidence < 0.7: continue
            kept_indices.append(i)
            dataframe = table.df
            # remove rows which do not have either debit or credit (balance rows)
            no_debits = (dataframe[DEBIT_COL] == "")
            no_credits = (dataframe[CREDIT_COL] == "")
            dataframe.drop(dataframe[no_debits & no_credits].index, inplace=True)
            # collapse multiple whitespaces to one
            dataframe = dataframe.map(lambda entry : " ".join(entry.split()))
            updated_tables.append(dataframe)

        return (updated_tables, kept_indices)

    MONTH_OF_YEAR = {
        "Jan": 0,
        "Feb": 1,
        "Mar": 2,
        "Apr": 3,
        "May": 4,
        "Jun": 5,
        "Jul": 6,
        "Aug": 7,
        "Sep": 8,
        "Oct": 9,
        "Nov": 10,
        "Dec": 11
    }

    @staticmethod
    def _clean_fnb(tables: List[camelot.core.Table]) -> Tuple[List[pd.DataFrame], List[int]]:
        """
        Further process tables from an FNB bank statement.

        Parameters
        ----------
        tables : List[Table]
            A list of tables returned by camelot parser.

        Returns
        -------
        (List[DataFrame], List[int])
            A pair of Pandas data frames representing further processed data,
            and indices of tables which have been processed (i.e. not dropped).
        """
        updated_tables = []
        kept_indices = []

        df = tables[1].df
        # year appears in here somewhere, and this will hopefully extract it
        date_pattern = r"Statement\s*date\s*:\s*\d{1,2}\s+([A-Za-z]+)\s+(\d{4})"
        matches = df.stack().str.extract(date_pattern, flags=re.IGNORECASE).dropna()
        end_month = PdfBankParser.MONTH_OF_YEAR.get(matches.iloc[0, 0][:3])
        statement_year = int(matches.iloc[0, 1]) if not matches.empty else None

        for n, table in enumerate(tables[2:]):
            kept_indices.append(n+2)
            df = table.df
            df.iloc[1, 1] = "Description"
            df.drop(df.index[0], inplace=True)
            df.drop(df.index[1], inplace=True)

            df.columns = ["Date", "Description", "Dead Description", "Extended Description",
                          "Amount", "Balance", "Bank Charges"]

            if df.iloc[-1, 1] == "Closing Balance":
                df.drop(df.index[-1], inplace=True)

            # rarely, the description gets sucked into the date column
            for i, (date, description, extended_description) in enumerate(
                    zip(df["Date"], df["Description"], df["Extended Description"])):
                if i == 0: continue

                if len(date) != 6:
                    new_date = date[:6]
                    new_description = date[6:].strip() + description
                else:
                    new_date = date
                    new_description = description

                year = statement_year
                month = PdfBankParser.MONTH_OF_YEAR.get(date[3:])
                # for example: Dec > Mar => Dec of previous year
                if year and month and end_month and month > end_month:
                    year -= 1
                df.iloc[i, 0] = new_date + (f" {year}" if year else "")

                if extended_description != "":
                    new_description += f": {extended_description}"
                df.iloc[i, 1] = new_description

            parse_credit = lambda cell : cell[:-2] if cell.endswith("Cr") else f"-{cell}"
            df.loc[2:, "Amount"] = df.loc[2:, "Amount"].apply(parse_credit)
            df.loc[2:, "Balance"] = df.loc[2:, "Balance"].apply(parse_credit)

            df.drop(columns=["Dead Description", "Extended Description", "Bank Charges"], inplace=True)
            updated_tables.append(df)

        return (updated_tables, kept_indices)

    @staticmethod
    def _clean_absa(tables: List[camelot.core.Table]) -> Tuple[List[pd.DataFrame], List[int]]:
        """
        Further process tables from an ABSA bank statement.

        Parameters
        ----------
        tables : List[Table]
            A list of tables returned by camelot parser.

        Returns
        -------
        (List[DataFrame], List[int])
            A pair of Pandas data frames representing further processed data,
            and indices of tables which have been processed (i.e. not dropped).
        """
        updated_tables = []
        kept_indices = []
        for n, table in enumerate(tables):
            if n == 0: continue
            kept_indices.append(n)
            df = table.df

            # sometimes the statement period makes it into the table
            first_row = df.iloc[0]
            cell = first_row.iloc[0]
            if cell.strip() != "" and (first_row.iloc[1:] == "").all():
                df = df.iloc[1:].reset_index(drop=True)
            df.iloc[0] = df.iloc[0].apply(lambda cell : cell.replace("\n", ""))

            # sometimes the page number is included in the table, creating 2 more columns
            if len(df.columns) == 6:
                df = df.iloc[:-1]
                empty_cols = [col for col in df.columns if (df[col] == "").all()]
                df = df.drop(columns=empty_cols).reset_index(drop=True)

            df.columns = ["Date", "Description", "Amount", "Balance"]

            collapsing_rows = []
            # apparently no nice way to iterate while mutating
            for i in range(1, len(df)):
                date = df.loc[i, "Date"]
                description = df.loc[i, "Description"]

                if date == "" and description != "":
                    prev = df.loc[i-1, "Description"]
                    space = " " if not prev.endswith(" ") else ""
                    df.loc[i-1, "Description"] = prev + space + description
                    collapsing_rows.append(i)

            df = df.drop(index=collapsing_rows)
            updated_tables.append(df)

        return (updated_tables, kept_indices)

    """
    We can optionally define further functions to operate on individual bank
    statement formats.
    Such a function is assumed to be static with signature
    `foo(tables: List[camelot.core.Table]) -> Tuple[List[pd.DataFrame], List[int]]`
    The first return must contain all dataframes to be saved to CSVs, and the
    second must contain all indices of tables (in the original tables argument)
    which have corresponding dataframes being saved.
    """
    BANK_CLEAN_FUNCTIONS = {
            "investec": _clean_investec,
            "fnb": _clean_fnb,
            "absa": _clean_absa,
    }

    @lru_cache(len(BANK_CLEAN_FUNCTIONS))
    def parse(self, file_path: str, output_path: str, bank: str = "",
              num_pages: int = -1, password: str = None) -> Dict[str, List[Any]]:
        """
        Read a bank statement and produce an equivalent CSV of transactions.

        Parameters
        ----------
        file_path : str
            The location of the bank statement PDF.

        output_path : sstr
            The directory and prefix for output CSVs.  For example,
            `outputs/output` yields typical file
            `outputs/output-page-{i}-table-{i}.csv`.

        bank : str
            The common name of the bank whose statement is being parsed.  This
            allows for special handling of individual formats.

        num_pages : int
            Unused argument.  The parser will now use the entire input file
            by default.

        password : str
            Possible password required to unlock the PDF.

        Returns
        -------
        Dict[String, List[ParseException] | List[camelot.Table.parsing_report]
            A dictionary containing a list of errors which occurred during
            parsing (failure is quiet), and a list of reports on each table's
            parse.
        """
        self.logger.info(f"Parsing file {file_path}")
        if num_pages != -1:
            self.logger.warning(f"The 'num_pages' argument of {self.parse.__name__} is no longer used.")
        errors = []
        reports = []
        filenames = []
        result = {
                "errors": errors,
                "reports": reports,
                "filenames": filenames,
        }
        if bank.lower() not in self.BANK_PARSE_METHODS:
            self.logger.warning(f"Unsupported bank {bank}. Using default parser.")
            errors.append(ParseException((f"Unsupported bank {bank}. Using default parser.")))
            parse_method = "auto"
        else:
            self.logger.debug(f"Parsing with bank {bank}")
            parse_method = self.BANK_PARSE_METHODS[bank.lower()]

        tables = camelot.read_pdf(file_path, flavor=parse_method, pages="all",
                                  password=password, parallel=True)
        self.logger.info(f"Found {len(tables)} tables")
        if len(tables) == 0:
            self.logger.warning("Failed to parse any tables")
            errors.append(ParseException("Failed to parse any tables."))
            return result

        # TODO we should check for confirmation on tables below a certain confidence

        if bank.lower() in self.BANK_CLEAN_FUNCTIONS:
            # This is a (String -> function) hashmap
            updated_tables, kept_indices = \
                    self.BANK_CLEAN_FUNCTIONS[bank.lower()](tables)
            if len(updated_tables) == 0:
                self.logger.warning(f"No acceptable-quality tables remain after bank-specific filtering for {bank}." + \
                                    " Is this the correct bank?")
                errors.append(ParseException("No acceptable table parses."))
                return result
            new_tables = []
            for kept_index in kept_indices:
                new_tables.append(tables[kept_index])
            tables = new_tables
        else:
            updated_tables = None

        reports += [table.parsing_report for table in tables]
        self.logger.debug(f"Found {len(reports)} acceptable tables:")
        for report in reports:
            self.logger.debug(str(report))

        if updated_tables:
            for df, table in zip(updated_tables, tables):
                filename = f"{output_path}-page-{table.page}-table-{table.order}.csv"
                self.logger.debug(f"Output file {filename}")
                filenames.append(filename)
                df.to_csv(filename, header=False, index=False)
        else:
            for table in tables:
                filename = f"{output_path}-page-{table.page}-table-{table.order}.csv"
                self.logger.debug(f"Output file {filename}")
                filenames.append(filename)
            tables.export(output_path, f="csv")

        return result

def main():
    pdf_parser = PdfBankParser()
    result = pdf_parser.parse(
            "tests/input/pdf/Testable.pdf", "output-Testable", "Investec", 2
    )

    print("Parsing errors:")
    for error in result["errors"]:
        print(error)
    print("Accuracy reports:")
    for report in result["reports"]:
        print(report)


if __name__ == "__main__":
    main()
