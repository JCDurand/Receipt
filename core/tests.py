from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from .models import (
    Account,
    User,
    Transaction,
    Receipt,
    Tag,
    BankStatement,
    Item,
    TransactionTemplate,
    Budget,
    ExchangeRate,
)
from django.db.models import ProtectedError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import IntegrityError, OperationalError
import shutil
import os
from django.conf import settings
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
import subprocess
import uuid
import json
from datetime import date, datetime
from decimal import Decimal
from unittest import mock
from django.urls import reverse
from django.utils import timezone


user = get_user_model()


class HealthCheckTests(APITestCase):
    def test_health_check_ok_without_authentication(self):
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["database"], "ok")

    def test_health_check_returns_503_when_database_unreachable(self):
        with mock.patch("core.views.connection") as connection:
            connection.cursor.side_effect = OperationalError
            response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["database"], "unavailable")


class ItemDetailAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser1",
            password="password1",
            email="test@gmail.com",
            first_name="Test",
            last_name="User",
        )

        self.other_user = User.objects.create_user(
            username="testuser2",
            password="password2",
            email="other@gmail.com",
            first_name="Other",
            last_name="User",
        )

        self.user_receipt = Receipt.objects.create(
            user=self.user, merchant_name="Checkers", total_amount=55.00
        )

        self.user_item = Item.objects.create(
            receipt=self.user_receipt,
            item_name="Bread",
            unit_price=15.00,
            quantity=2,
            item_total=30.00,
        )

        self.other_receipt = Receipt.objects.create(
            user=self.other_user, merchant_name="Pick n Pay", total_amount=25.00
        )

        self.other_item = Item.objects.create(
            receipt=self.other_receipt,
            item_name="Milk",
            unit_price=25.00,
            quantity=1,
            item_total=25.00,
        )

        self.user_item_url = reverse("item_detail", kwargs={"pk": self.user_item.pk})
        self.other_item_url = reverse("item_detail", kwargs={"pk": self.other_item.pk})

    def test_get_item_detail(self):
        """Test if a user can retrieve their own items"""

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.user_item_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_name"], "Bread")
        self.assertEqual(float(response.data["item_total"]), 30.00)

    def test_update_item(self):
        """Test if a user can update their own items"""
        self.client.force_authenticate(user=self.user)

        payload = {"item_name": "Brown Bread"}
        response = self.client.patch(self.user_item_url, payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["item_name"], "Brown Bread")

        self.user_item.refresh_from_db()
        self.assertEqual(self.user_item.item_name, "Brown Bread")

    def test_delete_item(self):
        """Test if a user can delete their own items"""

        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.user_item_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Item.objects.filter(pk=self.user_item.pk).exists())

    def test_user_access(self):
        """Test if user cannot access items from other user receipts"""

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.other_item_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CashEntryCategoryTests(APITestCase):
    """Cash manual entries are their own category and are never receipts/scans."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cashuser",
            password="password1",
            email="cash@gmail.com",
            first_name="Cash",
            last_name="User",
        )
        self.client.force_authenticate(user=self.user)

        self.scan = Receipt.objects.create(user=self.user, display_name="Scan.pdf")
        self.manual_receipt = Receipt.objects.create(
            user=self.user, display_name="Manual receipt", entry_type="receipt"
        )
        self.cash = Receipt.objects.create(
            user=self.user, display_name="Cash lunch", entry_type="cash"
        )

    def _ids(self, category=None):
        params = {"category": category} if category else {}
        response = self.client.get(reverse("document-list"), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {str(d["id"]): d["category"] for d in response.data}

    def test_receipt_category_excludes_cash(self):
        ids = self._ids("receipt")
        self.assertEqual(
            ids, {str(self.scan.id): "receipt", str(self.manual_receipt.id): "receipt"}
        )

    def test_cash_category_only_returns_cash(self):
        self.assertEqual(self._ids("cash"), {str(self.cash.id): "cash"})

    def test_unfiltered_list_labels_cash_as_cash(self):
        self.assertEqual(self._ids()[str(self.cash.id)], "cash")

    def test_manual_cash_entry_is_created_as_cash_category(self):
        response = self.client.post(
            reverse("document-manual-entry"),
            {"display_name": "Taxi", "entry_type": "cash", "items": []},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["category"], "cash")

    def test_cash_cannot_be_deleted_or_renamed_as_receipt(self):
        delete_url = reverse("document-delete", kwargs={"pk": self.cash.id})
        rename_url = reverse("document-rename", kwargs={"pk": self.cash.id})

        self.assertEqual(
            self.client.delete(delete_url + "?category=receipt").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.patch(
                rename_url + "?category=receipt", {"display_name": "x"}, format="json"
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_cash_can_be_renamed_and_deleted_as_cash(self):
        rename_url = reverse("document-rename", kwargs={"pk": self.cash.id})
        response = self.client.patch(
            rename_url + "?category=cash", {"display_name": "Renamed"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["category"], "cash")

        delete_url = reverse("document-delete", kwargs={"pk": self.cash.id})
        response = self.client.delete(delete_url + "?category=cash")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Receipt.objects.filter(pk=self.cash.id).exists())

    def test_cash_cannot_be_linked_to_a_transaction(self):
        response = self.client.patch(
            reverse("document-update", kwargs={"receiptId": self.cash.id}) + "?target=1"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


RECEIPT_CSV = (
    b"Merchant,Date,Item,Quantity,Unit Price,Amount\n"
    b"Checkers,15/08/2026,Milk 2L,2,R28.99,R57.98\n"
    b"Checkers,15/08/2026,Bread,1,R18.50,R18.50\n"
)


class ReceiptParseAPITests(APITestCase):
    """The parse endpoint reads line items from a dropped file without saving it."""

    url = "/api/documents/parse/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="parseuser", password="password1", email="parse@gmail.com"
        )
        self.client.force_authenticate(user=self.user)

    def post_file(self, name, content, content_type):
        return self.client.post(
            self.url,
            {"file": SimpleUploadedFile(name, content, content_type=content_type)},
            format="multipart",
        )

    def test_csv_line_items_are_returned(self):
        response = self.post_file("receipt.csv", RECEIPT_CSV, "text/csv")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["issues"], [])
        self.assertEqual(response.data["merchant_name"], "Checkers")
        self.assertEqual(response.data["transaction_date"], "2026-08-15")
        self.assertEqual(response.data["total_amount"], "76.48")
        self.assertEqual(
            response.data["items"],
            [
                {"name": "Milk 2L", "quantity": "2", "unit_price": "28.99", "total": "57.98"},
                {"name": "Bread", "quantity": "1", "unit_price": "18.50", "total": "18.50"},
            ],
        )

    def test_parsing_does_not_save_anything(self):
        self.post_file("receipt.csv", RECEIPT_CSV, "text/csv")

        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(Item.objects.exists())

    def test_unreadable_row_is_an_issue_and_other_rows_are_kept(self):
        content = RECEIPT_CSV + b"Checkers,NOT A DATE,Butter,1,R44.99,R44.99\n"
        response = self.post_file("receipt.csv", content, "text/csv")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 2)
        self.assertEqual(len(response.data["issues"]), 1)
        self.assertIn("Butter", response.data["issues"][0])

    def test_missing_column_is_an_issue(self):
        response = self.post_file(
            "receipt.csv", b"Merchant,Date,Item\nCheckers,15/08/2026,Milk\n", "text/csv"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertIn("Missing required column", response.data["issues"][0])

    def test_missing_column_is_logged_with_descriptive_message(self):
        with self.assertLogs("core.receipt_parsing", level="WARNING") as logs:
            self.post_file("receipt.csv", b"Date,Description\n12/08/2026,Test\n", "text/csv")

        self.assertTrue(any("Missing required column" in message for message in logs.output))

    def test_csv_without_rows_is_an_issue(self):
        response = self.post_file(
            "receipt.csv", b"Merchant,Date,Item,Quantity,Unit Price,Amount\n", "text/csv"
        )

        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["issues"], ["No line items were found in this file."])

    def test_file_that_is_not_really_a_csv_is_an_issue(self):
        response = self.post_file("receipt.csv", b"\xff\xfe\x00\x81\x82", "text/csv")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(len(response.data["issues"]), 1)

    def test_unsupported_file_types_are_rejected(self):
        for name, content_type in [("notes.txt", "text/plain"), ("photo.png", "image/png")]:
            response = self.post_file(name, b"data", content_type)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, name)
            self.assertIn("not allowed", response.data["error"])

    def test_file_is_required(self):
        response = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)
        response = self.post_file("receipt.csv", RECEIPT_CSV, "text/csv")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @mock.patch("core.receipt_parsing.PdfReceiptParser")
    def test_pdf_line_items_are_returned(self, parser_class):
        parser_class.return_value.parse.return_value = {
            "transactions": [
                {
                    "merchant": "CONVENIENCE CENTRE",
                    "date": date(2026, 5, 9),
                    "item": "TASTE MAGAZINE",
                    "quantity": Decimal(1),
                    "unit_price": Decimal("110.00"),
                    "amount": Decimal("110.00"),
                }
            ],
            "errors": ["The line items add up to 110.00 but the receipt total is 343."],
            "total": Decimal("343"),
        }
        response = self.post_file("receipt.pdf", b"%PDF-1.4", "application/pdf")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["merchant_name"], "CONVENIENCE CENTRE")
        self.assertEqual(response.data["transaction_date"], "2026-05-09")
        self.assertEqual(response.data["total_amount"], "343.00")
        self.assertEqual(response.data["items"][0]["name"], "TASTE MAGAZINE")
        # Whatever the parser could not make sense of is passed on as an issue
        self.assertEqual(len(response.data["issues"]), 1)

    @mock.patch("core.receipt_parsing.PdfReceiptParser")
    def test_unreadable_pdf_is_an_issue(self, parser_class):
        from parser.abstract_parser import ParseException

        parser_class.return_value.parse.side_effect = ParseException("The PDF could not be read.")
        response = self.post_file("receipt.pdf", b"%PDF-1.4", "application/pdf")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertIn("The PDF could not be read.", response.data["issues"][0])

    @mock.patch("core.receipt_parsing.PdfReceiptParser")
    def test_unexpected_parser_failure_is_an_issue(self, parser_class):
        parser_class.return_value.parse.side_effect = RuntimeError("camelot exploded")
        response = self.post_file("receipt.pdf", b"%PDF-1.4", "application/pdf")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["issues"]), 1)
        # Internal details are logged, not shown to the user
        self.assertNotIn("camelot", response.data["issues"][0])


@override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, "test_document_storage"))
class ReceiptUploadItemsTests(APITestCase):
    """Uploading a receipt saves the line items the user was shown."""

    url = "/api/documents/upload/"

    ITEMS = [
        {"name": "Milk 2L", "quantity": "2", "unit_price": "28.99", "total": "57.98"},
        {"name": "Bread", "quantity": "1", "unit_price": "18.50", "total": "18.50"},
    ]

    def setUp(self):
        self.user = User.objects.create_user(
            username="uploaduser", password="password1", email="upload@gmail.com"
        )
        self.client.force_authenticate(user=self.user)

    @classmethod
    def tearDownClass(cls):
        test_storage_path = os.path.join(settings.BASE_DIR, "test_document_storage")
        if os.path.exists(test_storage_path):
            shutil.rmtree(test_storage_path)
        super().tearDownClass()

    def upload(self, name="receipt.csv", content_type="text/csv", **fields):
        data = {
            "file": SimpleUploadedFile(name, RECEIPT_CSV, content_type=content_type),
            "category": "receipt",
            "display_name": "Groceries",
            **fields,
        }
        return self.client.post(self.url, data, format="multipart")

    def test_items_from_the_client_are_saved(self):
        response = self.upload(
            items=json.dumps(self.ITEMS),
            merchant_name="Checkers",
            amount="76.48",
            transaction_date="2026-08-15",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        receipt = Receipt.objects.get(pk=response.data["id"])
        self.assertEqual(receipt.merchant_name, "Checkers")
        self.assertEqual(receipt.total_amount, Decimal("76.48"))
        self.assertEqual(receipt.transaction_date.date(), date(2026, 8, 15))
        self.assertEqual(
            sorted(receipt.items.values_list("item_name", "quantity", "item_total")),
            [("Bread", Decimal("1"), Decimal("18.50")), ("Milk 2L", Decimal("2"), Decimal("57.98"))],
        )
        self.assertEqual(
            sorted(i["item_name"] for i in response.data["meta"]["items"]),
            ["Bread", "Milk 2L"],
        )

    def test_total_defaults_to_the_sum_of_the_items(self):
        response = self.upload(items=json.dumps(self.ITEMS))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["meta"]["amount"], "76.48")

    def test_no_items_is_saved_as_no_items(self):
        with mock.patch("core.views.threading.Thread") as thread:
            response = self.upload(items="[]")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Item.objects.count(), 0)
        # The client already read the file, so the server does not read it again
        thread.assert_not_called()

    def test_without_items_the_server_reads_the_file_itself(self):
        with mock.patch("core.views.threading.Thread") as thread:
            response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        thread.assert_called_once()

    def test_invalid_items_are_rejected(self):
        for bad_items in [
            json.dumps([{"quantity": "1", "unit_price": "1.00", "total": "1.00"}]),
            json.dumps([{"name": "Milk", "unit_price": "abc", "total": "1.00"}]),
            json.dumps({"name": "not a list"}),
            "not json",
        ]:
            response = self.upload(items=bad_items)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad_items)
        self.assertFalse(Receipt.objects.exists())

    # ---- the account a receipt is uploaded to (or "reconcile later") ----

    def test_a_receipt_can_be_uploaded_to_one_of_your_accounts(self):
        account = Account.objects.create(
            user=self.user, account_name="Cheque", account_number="1111"
        )

        response = self.upload(items="[]", account=str(account.id))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Receipt.objects.get(pk=response.data["id"]).account, account)
        self.assertEqual(response.data["meta"]["account"], account.id)

    def test_a_receipt_with_no_account_is_reconciled_later(self):
        response = self.upload(items="[]")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(Receipt.objects.get(pk=response.data["id"]).account)
        self.assertIsNone(response.data["meta"]["account"])

    def test_a_receipt_cannot_be_uploaded_to_another_users_account(self):
        other = User.objects.create_user(
            username="uploadother", password="password1", email="uploadother@gmail.com"
        )
        theirs = Account.objects.create(user=other, account_name="Theirs", account_number="2222")

        response = self.upload(items="[]", account=str(theirs.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Receipt.objects.exists())

    def test_a_manual_receipt_may_leave_its_account_for_later_but_a_statement_may_not(self):
        url = reverse("document-manual-entry")

        receipt = self.client.post(
            url, {"display_name": "Lunch", "entry_type": "receipt", "items": []}, format="json"
        )
        statement = self.client.post(
            url, {"display_name": "Old", "entry_type": "statement", "items": []}, format="json"
        )

        self.assertEqual(receipt.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(receipt.data["meta"]["account"])
        self.assertEqual(statement.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_file_type_is_rejected_not_saved(self):
        for category, extra in [("receipt", {}), ("statement", {"account": str(uuid.uuid4())})]:
            response = self.upload(
                name="notes.txt", content_type="text/plain", category=category, **extra
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, category)
            self.assertIn("not allowed", response.data["error"])
        self.assertFalse(Receipt.objects.exists())


class ItemLinkTests(APITestCase):
    """Matching a line item to a bank statement line, from the Review page."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="linkuser", password="password1", email="link@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="linkother", password="password2", email="linkother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", account_number="1111"
        )
        self.other_account = Account.objects.create(
            user=self.other_user, account_name="Other", account_number="2222"
        )
        self.receipt = Receipt.objects.create(user=self.user, display_name="Groceries")
        self.item = Item.objects.create(
            receipt=self.receipt, item_name="Bread", unit_price=18.50, quantity=1, item_total=18.50
        )
        self.transaction = Transaction.objects.create(
            account=self.account, amount=Decimal("18.50"), transaction_date=date(2026, 8, 15)
        )
        self.client.force_authenticate(user=self.user)

    def link_url(self, item=None, target=None):
        item = item or self.item
        target = target or self.transaction.pk
        return reverse("item-link", kwargs={"item_id": item.pk}) + f"?target={target}"

    def test_item_is_linked_and_transaction_reconciled(self):
        response = self.client.patch(self.link_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.transaction.refresh_from_db()
        self.assertEqual(self.item.transaction, self.transaction)
        self.assertEqual(self.transaction.status, "Reconciled")
        self.assertEqual(response.data["transaction"], self.transaction.pk)

    def test_mismatched_amount_takes_the_bank_amount(self):
        self.transaction.amount = Decimal("20.00")
        self.transaction.save()

        self.client.patch(self.link_url())

        self.item.refresh_from_db()
        self.assertEqual(self.item.item_total, Decimal("20.00"))

    def test_another_users_item_cannot_be_linked(self):
        other_receipt = Receipt.objects.create(user=self.other_user)
        other_item = Item.objects.create(
            receipt=other_receipt, item_name="Milk", unit_price=1, quantity=1, item_total=1
        )

        response = self.client.patch(self.link_url(item=other_item))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_another_users_transaction_cannot_be_linked(self):
        other_transaction = Transaction.objects.create(
            account=self.other_account, amount=Decimal("18.50"), transaction_date=date(2026, 8, 15)
        )

        response = self.client.patch(self.link_url(target=other_transaction.pk))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.transaction)

    def test_target_is_required_and_must_be_valid(self):
        base = reverse("item-link", kwargs={"item_id": self.item.pk})

        for query in ["", "?target=", "?target=not-a-uuid"]:
            response = self.client.patch(base + query)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, query)

    def test_item_api_cannot_set_the_transaction(self):
        self.client.patch(
            reverse("item_detail", kwargs={"pk": self.item.pk}),
            {"transaction": str(self.transaction.pk)},
        )

        self.item.refresh_from_db()
        self.assertIsNone(self.item.transaction)

    def test_document_list_reports_which_items_are_matched(self):
        self.client.patch(self.link_url())
        unmatched = Item.objects.create(
            receipt=self.receipt, item_name="Milk", unit_price=1, quantity=1, item_total=1
        )

        response = self.client.get("/api/documents/", {"category": "receipt"})

        items = {i["item_name"]: i["transaction"] for i in response.data[0]["meta"]["items"]}
        self.assertEqual(items, {"Bread": self.transaction.pk, "Milk": None})


class StatementDetailTests(APITestCase):
    """A statement page lists the transactions read from that statement."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stmtuser", password="password1", email="stmt@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="stmtother", password="password2", email="stmtother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        self.other_account = Account.objects.create(
            user=self.other_user, account_name="Other", account_number="2222"
        )
        self.statement = BankStatement.objects.create(
            account=self.account,
            file_path="statements/2026/08/abc_august.csv",
            display_name="August",
            doc_type="CSV",
        )
        self.later = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("1200.00"),
            transaction_date=date(2026, 8, 20), merchant="Salary",
        )
        self.earlier = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-57.98"),
            transaction_date=date(2026, 8, 15), merchant="CHECKERS", status="Reconciled",
        )
        # Belongs to another statement, so must not be listed
        Transaction.objects.create(
            account=self.account, amount=Decimal("5.00"), transaction_date=date(2026, 8, 1),
            merchant="Unrelated",
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse("statement-detail", kwargs={"pk": self.statement.pk})

    def test_statement_and_its_transactions_are_returned_in_date_order(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["file_name"], "August")
        self.assertEqual(response.data["doc_type"], "CSV")
        self.assertEqual(response.data["account"]["account_name"], "Cheque")
        self.assertEqual(
            [(t["description"], t["amount"], t["status"], t["date"]) for t in response.data["transactions"]],
            [
                ("CHECKERS", "-57.98", "Reconciled", date(2026, 8, 15)),
                ("Salary", "1200.00", "Pending", date(2026, 8, 20)),
            ],
        )

    def test_statement_without_transactions_has_an_empty_list(self):
        empty = BankStatement.objects.create(account=self.account, display_name="Empty")
        response = self.client.get(reverse("statement-detail", kwargs={"pk": empty.pk}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["transactions"], [])

    def test_another_users_statement_is_not_found(self):
        response = self.client.get(self.url)
        self.client.force_authenticate(user=self.other_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_404_NOT_FOUND)

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_document_list_reports_each_statements_transaction_count(self):
        response = self.client.get("/api/documents/", {"category": "statement"})

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["meta"]["transaction_count"], 2)


@override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, "test_document_storage"))
class FileUploadTestCase(APITestCase):
    def setUp(self):
        # Create a test user and log in
        self.user = user.objects.create_user(
            username="testuser", password="password", email="test@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user,
            account_name="Test Account",
            account_number="1234",
            card_type="Visa",
            funds=1000.00,
        )
        self.client.force_authenticate(user=self.user)

    def test_good_csv_upload(self):
        # Test uploading a valid CSV file

        test_file = SimpleUploadedFile(
            "statement1.csv",
            b"date,amount,description\n2026-06-03,1200.00,Groceries",
            content_type="text/csv",
        )
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("file_path", response.data)

    def test_bad_csv_type_upload(self):
        # Test uploading a file with an unsupported file type

        test_file = SimpleUploadedFile(
            "statement2.txt",
            b"date,amount,description\n2026-06-03,1200.00,Groceries",
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_empty_csv_upload(self):
        # Test uploading an empty file

        test_file = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_missing_csv_upload(self):
        # Test uploading without a csv file

        response = self.client.post(
            "/api/upload/", {"account": self.account.id}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_large_csv_upload(self):
        # Test uploading a large CSV file

        large_content = (
            b"date,amount,description\n" + b"2026-06-03,1200.00,Groceries\n" * 3000000
        )
        test_file = SimpleUploadedFile(
            "large_statement.csv", large_content, content_type="text/csv"
        )
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("File exceeds", str(response.data))

    def test_invalid_csv_format_upload(self):
        # Test uploading a CSV file with invalid format

        test_file = SimpleUploadedFile("invalid_format.csv", b"date|amount|description\n2026-06-03|1200.00|Groceries", content_type="text/csv")
        response = self.client.post('/api/upload/', {'file': test_file, 'account': self.account.id}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_csv_upload(self):
        # Test uploading a duplicate CSV file

        test_file = SimpleUploadedFile("statement1.csv", b"date,amount,description\n2026-06-03,1200.00,Groceries", content_type="text/csv")
        self.client.post('/api/upload/', {'file': test_file, 'account': self.account.id}, format='multipart')  # First upload

        response = self.client.post('/api/upload/', {'file': test_file, 'account': self.account.id}, format='multipart')  # Duplicate upload

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_good_pdf_upload(self):
        # Test uploading a valid PDF file

        test_file = SimpleUploadedFile(
            "bank_statement.pdf",
            b"%PDF-1.4\n%Empty PDF for test\n%%EOF",
            content_type="application/pdf",
        )
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("file_path", response.data)

    def test_bad_pdf_type_upload(self):
        # Test uploading a file with an unsupported file type

        test_file = SimpleUploadedFile(
            "bank_statement.txt",
            b"%PDF-1.4\n%Empty PDF for test\n%%EOF",
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_empty_pdf_upload(self):
        # Test uploading an empty PDF file
        test_file = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_missing_pdf_upload(self):
        # Test uploading without a pdf file

        response = self.client.post(
            "/api/upload/", {"account": self.account.id}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_large_pdf_upload(self):
        # Test uploading a large PDF file

        large_content = b"%PDF-1.4\n%Empty PDF for test\n" + b"%%EOF" * 12000000
        test_file = SimpleUploadedFile(
            "large_bank_statement.pdf", large_content, content_type="application/pdf"
        )
        response = self.client.post(
            "/api/upload/",
            {"file": test_file, "account": self.account.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("File exceeds", str(response.data))

    def test_duplicate_pdf_upload(self):
        # Test uploading a duplicate PDF file

        test_file = SimpleUploadedFile("bank_statement.pdf", b"%PDF-1.4\n%Empty PDF for test\n%%EOF", content_type="application/pdf")
        self.client.post('/api/upload/', {'file': test_file, 'account': self.account.id}, format='multipart')  # First upload

        response = self.client.post('/api/upload/', {'file': test_file, 'account': self.account.id}, format='multipart')  # Duplicate upload

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_bad_pdf_format_upload(self):
        # Test uploading a PDF file with invalid format

        test_file = SimpleUploadedFile("invalid_format.pdf", b"%PDF-1.4\n%Invalid PDF for test\n%%EOF", content_type="application/pdf")
        response = self.client.post('/api/upload/', {'file': test_file, 'account': self.account.id}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_manual_entry(self):
        # Ensure manual entry endpoint does not accept incorrect data
        self.client.force_authenticate(user=self.user)

        url = "/api/documents/manual/"
        payload = {
            "entry_type": "cash"
        }

        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("display_name",response.data)
    
    @classmethod
    def tearDownClass(cls):
        # Clean up the test document storage directory after tests
        test_storage_path = os.path.join(settings.BASE_DIR, "test_document_storage")
        if os.path.exists(test_storage_path):
            shutil.rmtree(test_storage_path)
        super().tearDownClass()


class UserRegistrationTestCase(APITestCase):
    def test_user_registration(self):
        # Test user registration
        data = {
            "username": "newuser",
            "email": "newuser@gmail.com",
            "password": "securepassword",
            "first_name": "New",
            "last_name": "User",
            "account_name": "New User Account",
            "account_number": "5678",
            "card_type": "Debit",
            "funds": 1000.00,
        }
        response = self.client.post("/api/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user_id", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_user_registration_missing_fields(self):
        # Test user registration with missing required fields
        data = {
            "username": "newuser",
            "email": "newuser@gmail.com",
            "password": "securepassword",
        }
        response = self.client.post("/api/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)

    def test_user_registration_invalid_email(self):
        # Test user registration with an invalid email format
        data = {
            "username": "newuser",
            "email": "invalid-email-format",
            "password": "securepassword",
            "first_name": "New",
            "last_name": "User",
            "account_name": "New User Account",
            "account_number": "5678",
            "card_type": "Debit",
            "funds": 1000.00,
        }
        response = self.client.post("/api/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Account.objects.count(), 0)

    def test_user_registration_duplicate_username(self):
        # Test user registration with a duplicate username
        user.objects.create_user(
            username="newuser",
            email="existinguser@gmail.com",
            password="securepassword",
        )
        data = {
            "username": "newuser",
            "email": "newuser@gmail.com",
            "password": "securepassword",
            "first_name": "New",
            "last_name": "User",
            "account_name": "New User Account",
            "account_number": "5678",
            "card_type": "Debit",
            "funds": 1000.00,
        }
        response = self.client.post("/api/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Account.objects.count(), 0)


class TransactionTestCase(APITestCase):
    def setUp(self):
        # Create a test user and account
        self.user = user.objects.create_user(
            username="testuser", password="password", email="testuser@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_number="1234", funds=1000.00
        )
        self.client.force_authenticate(user=self.user)

    def test_transaction_creation(self):
        # Test creating a transaction
        data = {
            "account": self.account.id,
            "amount": 100.00,
            "transaction_date": "2026-06-03",
            "merchant": "Checkers",
            "status": "Pending",
        }
        response = self.client.post("/api/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_get_transactions(self):
        # Test retrieving transactions for an account
        Transaction.objects.create(
            account=self.account,
            amount=100.00,
            transaction_date="2026-06-03",
            merchant="Checkers",
            status="Pending",
        )
        response = self.client.get(f"/api/?account={self.account.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


    def test_get_transaction(self):
        # Test retrieving a single transaction

        transaction = Transaction.objects.create(
            account=self.account, amount=75.00, transaction_date="2026-09-17"
        )

        url = f"/api/transaction/{transaction.id}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["amount"], "75.00")

    def test_delete_transaction(self):
        # Test deleting a transaction

        transaction = Transaction.objects.create(
            account=self.account, amount=50.00, transaction_date="2026-09-17"
        )

        url = f"/api/transaction/{transaction.id}/"

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Transaction.objects.filter(id=transaction.id).exists())


class DatabaseTestCase(APITestCase):
    def setUp(self):
        # Set up any necessary data for the database connection test
        self.user = user.objects.create_user(
            username="testuser",
            password="password",
            email="testuser@gmail.com",
            first_name="Test",
            last_name="User",
        )
        self.account = Account.objects.create(
            user=self.user,
            account_number="1234",
            funds=1000.00,
            account_name="Test Account",
            card_type="Cheque",
        )
        self.transaction = Transaction.objects.create(
            account=self.account,
            amount=250.00,
            transaction_date="2026-06-03",
            merchant="Checkers",
            status="Pending",
        )
        self.receipt = Receipt.objects.create(
            user=self.user,
            transaction=self.transaction,
            merchant_name="Checkers",
            total_amount=250.00,
            receipt_path="documents_storage/test_receipt.csv",
        )
        self.bank_statement = BankStatement.objects.create(
            account=self.account,
            file_path="documents_storage/test_statement.csv",
            doc_type="CSV",
            uploaded_at="2026-06-03T12:00:00Z",
        )
        # A predefined tag, created by a migration
        self.tag = Tag.objects.get(name="Groceries", owner=None)
        self.item1 = Item.objects.create(
            receipt=self.receipt,
            item_name="Milk",
            unit_price=50.00,
            quantity=2,
            item_total=100.00,
        )
        self.item2 = Item.objects.create(
            receipt=self.receipt,
            item_name="Bread",
            unit_price=150.00,
            quantity=1,
            item_total=150.00,
        )
        self.item1.tags.add(self.tag)
        self.item2.tags.add(self.tag)
        self.transaction.tags.add(self.tag)

    def test_database_connection(self):
        # Test if the database connection is established
        try:
            user.objects.count()
            self.assertTrue(True)
        except IntegrityError as e:
            self.fail(f"Database connection failed: {e}")

    def test_data_retrieval(self):
        # Test if data can be retrieved from the database
        retrieved_user = user.objects.get(username="testuser")
        self.assertEqual(retrieved_user.email, "testuser@gmail.com")
        self.assertEqual(retrieved_user.first_name, "Test")

    def test_data_creation(self):
        # Test if data can be created in the database
        new_user = user.objects.create_user(
            username="newuser",
            password="password",
            email="newuser@gmail.com",
            first_name="New",
            last_name="User",
        )
        self.assertEqual(new_user.username, "newuser")

    def test_data_update(self):
        # Test if data can be updated in the database
        self.user.first_name = "Updated"
        self.user.save()
        updated_user = user.objects.get(username="testuser")
        self.assertEqual(updated_user.first_name, "Updated")

    def test_data_deletion(self):
        # Test if data can be deleted from the database
        self.user.delete()
        self.assertEqual(Account.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)
        receipt = Receipt.objects.get(id=self.receipt.id)
        self.assertIsNone(receipt.user)
        self.assertIsNone(receipt.transaction)

    def test_item_tag_relationship(self):
        # Test the relationship between Item and Tag
        self.assertIn(self.tag, self.item1.tags.all())
        self.assertIn(self.tag, self.item2.tags.all())

    def test_receipt_transaction_relationship(self):
        # Test the relationship between Receipt and Transaction
        self.assertEqual(self.receipt.transaction, self.transaction)

    def test_bank_statement_account_relationship(self):
        # Test the relationship between BankStatement and Account
        self.assertEqual(self.bank_statement.account, self.account)

    def test_transaction_receipt_relationship(self):
        # Test the relationship between Transaction and Receipt
        self.assertEqual(self.receipt.transaction, self.transaction)

    def test_account_user_relationship(self):
        # Test the relationship between Account and User
        self.assertEqual(self.account.user, self.user)

    def test_predefined_tag_name_is_unique(self):
        with self.assertRaises(IntegrityError):
            Tag.objects.create(name="Groceries")

    def test_tag_name_is_unique_per_owner_only(self):
        other = User.objects.create_user(
            username="tagother", password="password1", email="tagother@gmail.com"
        )
        Tag.objects.create(name="Holiday", owner=self.user)
        Tag.objects.create(name="Holiday", owner=other)

        with self.assertRaises(IntegrityError):
            Tag.objects.create(name="Holiday", owner=self.user)

    def test_transaction_tag_uniqueness(self):
        # Test that the combination of Transaction and Tag is unique in TransactionTag
        self.transaction.tags.add(self.tag)
        self.assertEqual(self.transaction.tags.count(), 1)

    def test_item_receipt_relationship(self):
        # Test the relationship between Item and Receipt
        self.assertEqual(self.item1.receipt, self.receipt)
        self.assertEqual(self.item2.receipt, self.receipt)

    def test_item_total_calculation(self):
        # Test that the item_total is correctly calculated
        self.assertEqual(
            self.item1.item_total, self.item1.unit_price * self.item1.quantity
        )
        self.assertEqual(
            self.item2.item_total, self.item2.unit_price * self.item2.quantity
        )

    def test_transaction_amount_matches_receipt(self):
        # Test that the transaction amount matches the receipt
        self.assertEqual(self.transaction.amount, self.receipt.total_amount)

    def test_receipt_user_relationship(self):
        # Test the relationship between Receipt and User
        self.assertEqual(self.receipt.user, self.user)

    def test_bank_statement_doc_type(self):
        # Test that the BankStatement doc_type is correctly set
        self.assertEqual(self.bank_statement.doc_type, "CSV")

class TaggingTests(APITestCase):
    """Predefined and user-created tags, and applying them to line items."""

    PREDEFINED = {"Groceries", "Fuel", "Salary", "Woolworths", "Checkers", "Pick n Pay", "Spar"}

    def setUp(self):
        self.user = User.objects.create_user(
            username="taguser", password="password1", email="taguser@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="tagother", password="password2", email="tagother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        self.other_account = Account.objects.create(
            user=self.other_user, account_name="Other", account_number="2222"
        )
        self.statement = BankStatement.objects.create(
            account=self.account, file_path="statements/a.csv", display_name="A", doc_type="CSV"
        )
        self.transaction = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-57.98"),
            transaction_date=date(2026, 8, 15), merchant="CHECKERS",
        )
        self.other_transaction = Transaction.objects.create(
            account=self.other_account, amount=Decimal("-5.00"),
            transaction_date=date(2026, 8, 15), merchant="SPAR",
        )
        self.receipt = Receipt.objects.create(user=self.user, merchant_name="Checkers")
        self.item = Item.objects.create(
            receipt=self.receipt, item_name="Milk", unit_price=10, quantity=1, item_total=10
        )
        other_receipt = Receipt.objects.create(user=self.other_user, merchant_name="Spar")
        self.other_item = Item.objects.create(
            receipt=other_receipt, item_name="Eggs", unit_price=5, quantity=1, item_total=5
        )

        self.groceries = Tag.objects.get(name="Groceries", owner=None)
        self.fuel = Tag.objects.get(name="Fuel", owner=None)
        self.mine = Tag.objects.create(name="Holiday", owner=self.user)
        self.theirs = Tag.objects.create(name="Secret", owner=self.other_user)

        self.client.force_authenticate(user=self.user)
        self.list_url = reverse("tag-list")
        self.item_url = reverse("item-tags", kwargs={"pk": self.item.pk})
        self.transaction_url = reverse("transaction-tags", kwargs={"pk": self.transaction.pk})

    def ids(self, *tags):
        return [str(tag.pk) for tag in tags]

    def tag_detail_url(self, tag):
        return reverse("tag-detail", kwargs={"pk": tag.pk})

    def template_detail_url(self, template):
        return reverse("template-delete", kwargs={"pk": template.pk})

    # ---- the tags themselves ----

    def test_predefined_tags_exist_and_have_no_owner(self):
        predefined = Tag.objects.filter(owner=None, is_hidden=False)

        self.assertEqual({tag.name for tag in predefined}, self.PREDEFINED)

    def test_list_returns_predefined_then_own_tags_but_not_other_users(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [tag["name"] for tag in response.data]
        self.assertEqual(set(names), self.PREDEFINED | {"Holiday"})
        self.assertNotIn("Secret", names)
        self.assertEqual(names[-1], "Holiday")
        flags = {tag["name"]: tag["is_predefined"] for tag in response.data}
        self.assertTrue(flags["Fuel"])
        self.assertFalse(flags["Holiday"])

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_create_their_own_tag(self):
        response = self.client.post(self.list_url, {"name": "  Pets  "})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Pets")
        self.assertFalse(response.data["is_predefined"])
        self.assertEqual(Tag.objects.get(pk=response.data["id"]).owner, self.user)

    def test_two_users_can_create_the_same_tag_name_independently(self):
        self.client.post(self.list_url, {"name": "Pets"})
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(self.list_url, {"name": "Pets"})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Tag.objects.filter(name="Pets").count(), 2)

    def test_cannot_create_a_duplicate_of_a_predefined_or_own_tag(self):
        for name in ["Groceries", "groceries", "holiday", "HOLIDAY "]:
            response = self.client.post(self.list_url, {"name": name})

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, name)
        self.assertEqual(Tag.objects.filter(owner=self.user).count(), 1)

    def test_cannot_create_a_blank_tag(self):
        for name in ["", "   "]:
            response = self.client.post(self.list_url, {"name": name})

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, repr(name))

    def test_user_can_create_a_nested_tag(self):
        response = self.client.post(
            self.list_url,
            {"name": "Bakery", "parent": str(self.mine.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        child = Tag.objects.get(pk=response.data["id"])
        self.assertEqual((child.name, child.owner, child.parent), ("Bakery", self.user, self.mine))
        self.assertEqual(str(response.data["parent"]), str(self.mine.pk))

    def test_user_can_edit_a_tag_name_and_parent(self):
        child = Tag.objects.create(name="Bakery", owner=self.user, parent=self.mine)

        response = self.client.patch(
            self.tag_detail_url(child),
            {"name": "Travel", "parent": str(self.groceries.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        child.refresh_from_db()
        self.assertEqual((child.name, child.parent), ("Travel", self.groceries))

    def test_tag_hierarchy_rejects_self_parent_and_descendant_cycles(self):
        child = Tag.objects.create(name="Bakery", owner=self.user, parent=self.mine)

        self_reference = self.client.patch(
            self.tag_detail_url(child), {"parent": str(child.pk)}, format="json"
        )
        cycle = self.client.patch(
            self.tag_detail_url(self.mine), {"parent": str(child.pk)}, format="json"
        )

        self.assertEqual(self_reference.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(cycle.status_code, status.HTTP_400_BAD_REQUEST)
        self.mine.refresh_from_db()
        child.refresh_from_db()
        self.assertIsNone(self.mine.parent)
        self.assertEqual(child.parent, self.mine)

    def test_user_cannot_nest_tags_under_another_users_tag(self):
        created = self.client.post(
            self.list_url,
            {"name": "Private child", "parent": str(self.theirs.pk)},
            format="json",
        )
        edited = self.client.patch(
            self.tag_detail_url(self.mine),
            {"parent": str(self.theirs.pk)},
            format="json",
        )

        self.assertEqual(created.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(edited.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Tag.objects.filter(name="Private child", owner=self.user).exists())

    def test_user_cannot_edit_predefined_or_duplicate_tags(self):
        predefined = self.client.patch(
            self.tag_detail_url(self.groceries), {"name": "Food"}, format="json"
        )
        duplicate = self.client.patch(
            self.tag_detail_url(self.mine), {"name": " groceries "}, format="json"
        )

        self.assertEqual(predefined.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.groceries.refresh_from_db()
        self.mine.refresh_from_db()
        self.assertEqual((self.groceries.name, self.mine.name), ("Groceries", "Holiday"))

    def test_user_can_delete_a_tag_and_remove_it_from_line_items(self):
        self.item.tags.add(self.mine)
        self.transaction.tags.add(self.mine)

        response = self.client.delete(self.tag_detail_url(self.mine))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Tag.objects.filter(pk=self.mine.pk).exists())
        self.assertFalse(self.item.tags.filter(pk=self.mine.pk).exists())
        self.assertFalse(self.transaction.tags.filter(pk=self.mine.pk).exists())

    def test_predefined_tags_cannot_be_deleted(self):
        response = self.client.delete(self.tag_detail_url(self.groceries))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Tag.objects.filter(pk=self.groceries.pk, owner=None).exists())

    def test_tag_with_children_cannot_be_deleted_through_the_api(self):
        child = Tag.objects.create(name="Bakery", owner=self.user, parent=self.mine)

        response = self.client.delete(self.tag_detail_url(self.mine))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Tag.objects.filter(pk=self.mine.pk).exists())
        self.assertEqual(Tag.objects.get(pk=child.pk).parent, self.mine)

    def test_templates_accept_multiple_available_tags_but_not_other_users_tags(self):
        url = reverse("template-list-create")
        template_data = {
            "search_string": "SPAR",
            "merchant_name": "Spar",
            "tags": self.ids(self.groceries, self.mine),
        }

        created = self.client.post(url, template_data, format="json")
        rejected = self.client.post(
            url,
            {**template_data, "search_string": "SECRET", "tags": self.ids(self.theirs)},
            format="json",
        )

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual({str(tag) for tag in created.data["tags"]}, set(template_data["tags"]))
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.user.templates.count(), 1)

    def test_template_reads_hide_legacy_tags_owned_by_another_user(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Spar"
        )
        template.tags.add(self.groceries, self.theirs)

        response = self.client.get(reverse("template-list-create"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data[0]["tags"]), {self.groceries.pk})

        detail = self.client.get(self.template_detail_url(template))

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(set(detail.data["tags"]), {self.groceries.pk})

        updated = self.client.patch(
            self.template_detail_url(template),
            {"merchant_name": "Updated shop"},
            format="json",
        )

        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(set(updated.data["tags"]), {self.groceries.pk})

    def test_user_can_update_template_tags_and_clear_them(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Shop"
        )
        template.tags.add(self.groceries, self.mine)

        updated = self.client.patch(
            self.template_detail_url(template),
            {"merchant_name": "Spar", "tags": self.ids(self.fuel)},
            format="json",
        )
        cleared = self.client.patch(
            self.template_detail_url(template), {"tags": []}, format="json"
        )

        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["merchant_name"], "Spar")
        self.assertEqual(set(updated.data["tags"]), {self.fuel.pk})
        self.assertEqual(cleared.status_code, status.HTTP_200_OK)
        self.assertEqual(cleared.data["tags"], [])
        self.assertFalse(template.tags.exists())

    def test_template_update_rejects_foreign_tags_without_changing_existing_tags(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Shop"
        )
        template.tags.add(self.groceries)

        response = self.client.patch(
            self.template_detail_url(template),
            {"tags": self.ids(self.theirs)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        template.refresh_from_db()
        self.assertEqual(set(template.tags.all()), {self.groceries})

    def test_templates_are_private_and_can_be_deleted_by_their_owner(self):
        own = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Spar"
        )
        theirs = TransactionTemplate.objects.create(
            user=self.other_user, search_string="SECRET", merchant_name="Other"
        )

        for response in (
            self.client.get(self.template_detail_url(theirs)),
            self.client.patch(
                self.template_detail_url(theirs),
                {"merchant_name": "Changed"},
                format="json",
            ),
            self.client.delete(self.template_detail_url(theirs)),
        ):
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        deleted = self.client.delete(self.template_detail_url(own))

        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TransactionTemplate.objects.filter(pk=own.pk).exists())
        self.assertTrue(TransactionTemplate.objects.filter(pk=theirs.pk).exists())

    def test_template_endpoints_require_authentication(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Spar"
        )
        detail_url = self.template_detail_url(template)
        self.client.force_authenticate(user=None)

        responses = (
            self.client.get(reverse("template-list-create")),
            self.client.post(
                reverse("template-list-create"),
                {"search_string": "OTHER", "tags": self.ids(self.groceries)},
                format="json",
            ),
            self.client.get(detail_url),
            self.client.patch(detail_url, {"merchant_name": "x"}, format="json"),
            self.client.delete(detail_url),
        )

        self.assertEqual(
            [response.status_code for response in responses],
            [status.HTTP_401_UNAUTHORIZED] * len(responses),
        )

    def test_user_cannot_read_edit_or_delete_another_users_tag(self):
        for response in (
            self.client.get(self.tag_detail_url(self.theirs)),
            self.client.patch(
                self.tag_detail_url(self.theirs), {"name": "Mine"}, format="json"
            ),
            self.client.delete(self.tag_detail_url(self.theirs)),
        ):
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.name, "Secret")

    def test_tag_with_subtags_cannot_be_deleted(self):
        Tag.objects.create(name="Bakery", owner=self.user, parent=self.mine)

        with self.assertRaises(ProtectedError):
            self.mine.delete()

    # ---- receipt line items ----

    def test_item_can_have_several_tags(self):
        response = self.client.put(self.item_url, {"tags": self.ids(self.groceries, self.mine)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({tag["name"] for tag in response.data["tags"]}, {"Groceries", "Holiday"})
        self.assertEqual(set(self.item.tags.all()), {self.groceries, self.mine})

    def test_putting_tags_replaces_the_previous_ones_and_can_clear_them(self):
        self.item.tags.add(self.groceries, self.fuel)

        self.client.put(self.item_url, {"tags": self.ids(self.fuel)})
        self.assertEqual(set(self.item.tags.all()), {self.fuel})

        response = self.client.put(self.item_url, {"tags": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.item.tags.count(), 0)

    def test_item_cannot_be_given_another_users_tag_or_an_unknown_tag(self):
        for tags in [self.ids(self.theirs), self.ids(self.groceries, self.theirs), [str(uuid.uuid4())]]:
            response = self.client.put(self.item_url, {"tags": tags}, format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, tags)
        self.assertEqual(self.item.tags.count(), 0)

    def test_tags_are_required_and_must_be_uuids(self):
        for body in [{}, {"tags": ["not-a-uuid"]}, {"tags": "abc"}]:
            response = self.client.put(self.item_url, body, format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, body)

    def test_cannot_tag_another_users_item(self):
        url = reverse("item-tags", kwargs={"pk": self.other_item.pk})

        response = self.client.put(url, {"tags": self.ids(self.groceries)})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.other_item.tags.count(), 0)

    def test_item_api_cannot_set_tags(self):
        self.client.patch(
            reverse("item_detail", kwargs={"pk": self.item.pk}),
            {"tags": self.ids(self.theirs)},
            format="json",
        )

        self.assertEqual(self.item.tags.count(), 0)

    def test_document_list_reports_each_items_tags(self):
        self.item.tags.add(self.mine, self.groceries)

        response = self.client.get("/api/documents/", {"category": "receipt"})

        item = response.data[0]["meta"]["items"][0]
        self.assertEqual([tag["name"] for tag in item["tags"]], ["Groceries", "Holiday"])

    # ---- bank statement line items ----

    def test_transaction_can_have_several_tags(self):
        response = self.client.put(
            self.transaction_url, {"tags": self.ids(self.groceries, self.fuel, self.mine)}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [tag["name"] for tag in response.data["tags"]], ["Fuel", "Groceries", "Holiday"]
        )
        self.assertEqual(self.transaction.tags.count(), 3)

    def test_transaction_cannot_be_given_another_users_tag(self):
        response = self.client.put(self.transaction_url, {"tags": self.ids(self.theirs)})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.transaction.tags.count(), 0)

    def test_cannot_tag_another_users_transaction(self):
        url = reverse("transaction-tags", kwargs={"pk": self.other_transaction.pk})

        response = self.client.put(url, {"tags": self.ids(self.groceries)})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.other_transaction.tags.count(), 0)

    def test_transaction_api_cannot_set_tags(self):
        response = self.client.post(
            "/api/",
            {
                "account": str(self.account.pk),
                "amount": "1.00",
                "transaction_date": "2026-08-01",
                "tags": self.ids(self.theirs),
            },
            format="json",
        )

        # The transaction is created, but the tag is ignored
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Transaction.objects.get(pk=response.data["id"]).tags.count(), 0)

    def test_statement_detail_reports_each_transactions_tags(self):
        self.transaction.tags.add(self.mine, self.fuel)

        response = self.client.get(reverse("statement-detail", kwargs={"pk": self.statement.pk}))

        tags = response.data["transactions"][0]["tags"]
        self.assertEqual([tag["name"] for tag in tags], ["Fuel", "Holiday"])


class LineItemListTests(APITestCase):
    """One list of every bank statement line and receipt item, with all their details."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="lineuser", password="password1", email="lineuser@gmail.com"
        )
        other = User.objects.create_user(
            username="lineother", password="password2", email="lineother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        other_account = Account.objects.create(
            user=other, account_name="Other", account_number="2222"
        )

        self.statement = BankStatement.objects.create(
            account=self.account, file_path="statements/march.csv", display_name="March", doc_type="CSV"
        )
        self.spend = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-57.98"),
            transaction_date=date(2026, 3, 10), merchant="SPAR NEWLANDS",
        )
        self.pay = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("1200.00"),
            transaction_date=date(2026, 3, 25), merchant="ACME PTY", description="Salary March",
        )
        self.spend.tags.add(Tag.objects.get(name="Groceries", owner=None))

        self.receipt = Receipt.objects.create(
            user=self.user, merchant_name="Checkers", display_name="Checkers run",
            transaction_date=timezone.make_aware(datetime(2026, 3, 12)),
        )
        self.milk = Item.objects.create(
            receipt=self.receipt, item_name="Milk", unit_price=Decimal("12.50"),
            quantity=Decimal("2"), item_total=Decimal("25.00"),
        )
        self.matched = Item.objects.create(
            receipt=self.receipt, item_name="Bread", unit_price=Decimal("20.00"),
            quantity=Decimal("1"), item_total=Decimal("20.00"), transaction=self.spend,
        )
        cash = Receipt.objects.create(
            user=self.user, entry_type="cash", display_name="Market", transaction_date=timezone.make_aware(datetime(2026, 3, 1)),
        )
        self.cash_item = Item.objects.create(
            receipt=cash, item_name="Apples", unit_price=Decimal("30.00"), quantity=Decimal("1"),
            item_total=Decimal("30.00"),
        )

        # Belongs to someone else, so must never be listed
        Transaction.objects.create(
            account=other_account, amount=Decimal("-9.99"), transaction_date=date(2026, 3, 1), merchant="SECRET"
        )
        other_receipt = Receipt.objects.create(user=other, merchant_name="Secret shop")
        Item.objects.create(
            receipt=other_receipt, item_name="Secret", unit_price=1, quantity=1, item_total=1
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse("line-item-list")

    def lines(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {line["id"]: line for line in response.data}

    def test_lists_statement_lines_and_receipt_items_of_this_user_only(self):
        lines = self.lines()

        self.assertEqual(
            set(lines),
            {self.spend.id, self.pay.id, self.milk.id, self.matched.id, self.cash_item.id},
        )
        kinds = {line["kind"] for line in lines.values()}
        self.assertEqual(kinds, {"statement_line", "receipt_item"})

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_newest_line_first(self):
        response = self.client.get(self.url)

        dates = [line["date"] for line in response.data]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_statement_line_details(self):
        line = self.lines()[self.spend.id]

        self.assertEqual(line["date"], "2026-03-10")
        self.assertEqual(line["description"], "SPAR NEWLANDS")
        self.assertIsNone(line["merchant"])  # the text is not repeated
        self.assertEqual(line["amount"], "-57.98")
        self.assertEqual(line["direction"], "out")
        self.assertEqual(line["status"], "Pending")
        self.assertEqual(line["quantity"], 1)
        self.assertEqual(line["account"]["account_number"], "1111")
        self.assertEqual(
            line["source"], {"id": self.statement.id, "name": "March", "category": "statement", "bank": ""}
        )
        self.assertEqual([tag["name"] for tag in line["tags"]], ["Groceries"])
        self.assertIsNotNone(line["added_at"])

    def test_money_in_is_told_from_money_out_by_the_sign_not_the_stored_type(self):
        line = self.lines()[self.pay.id]

        self.assertEqual(line["direction"], "in")
        self.assertEqual(line["description"], "Salary March")
        self.assertEqual(line["merchant"], "ACME PTY")

    def test_receipt_item_details(self):
        line = self.lines()[self.milk.id]

        self.assertEqual(line["description"], "Milk")
        self.assertEqual(line["merchant"], "Checkers")
        self.assertEqual(line["date"], "2026-03-12")
        self.assertEqual(line["amount"], "25.00")
        self.assertEqual(line["unit_price"], "12.50")
        self.assertEqual(Decimal(line["quantity"]), Decimal("2"))
        self.assertEqual(line["direction"], "out")
        self.assertIsNone(line["status"])
        self.assertFalse(line["is_cash"])
        self.assertEqual(
            line["source"], {"id": self.receipt.id, "name": "Checkers run", "category": "receipt"}
        )

    def test_cash_entries_items_are_marked_cash(self):
        line = self.lines()[self.cash_item.id]

        self.assertTrue(line["is_cash"])
        self.assertEqual(line["source"]["category"], "cash")

    def test_receipt_item_reports_the_statement_line_it_is_matched_to(self):
        lines = self.lines()

        self.assertEqual(lines[self.matched.id]["transaction_id"], self.spend.id)
        self.assertIsNone(lines[self.milk.id]["transaction_id"])

    def test_reports_which_lines_are_matched(self):
        lines = self.lines()

        self.assertTrue(lines[self.matched.id]["matched"])
        self.assertFalse(lines[self.milk.id]["matched"])
        # The statement line has a receipt item matched to it
        self.assertTrue(lines[self.spend.id]["matched"])
        self.assertFalse(lines[self.pay.id]["matched"])


class AccountDetailTests(APITestCase):
    """Viewing a bank account with its statements, and editing its details."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="acctuser", password="password1", email="acctuser@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="acctother", password="password2", email="acctother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Everyday", card_type="Cheque",
            account_number="1111", funds=Decimal("500.00"),
        )
        self.second = Account.objects.create(
            user=self.user, account_name="Rainy day", card_type="Savings", account_number="2222"
        )
        self.other_account = Account.objects.create(
            user=self.other_user, account_name="Theirs", card_type="Cheque", account_number="3333"
        )

        self.march = BankStatement.objects.create(
            account=self.account, file_path="s/march.csv", display_name="March", doc_type="CSV"
        )
        self.april = BankStatement.objects.create(
            account=self.account, file_path="s/april.csv", doc_type="CSV"  # no display name
        )
        self.elsewhere = BankStatement.objects.create(
            account=self.second, file_path="s/savings.csv", display_name="Savings"
        )
        self.line = Transaction.objects.create(
            account=self.account, statement=self.march, amount=Decimal("-10.00"),
            transaction_date=date(2026, 3, 1), merchant="SPAR",
        )
        Transaction.objects.create(
            account=self.account, statement=self.march, amount=Decimal("-5.00"),
            transaction_date=date(2026, 3, 2), merchant="CHECKERS",
        )
        receipt = Receipt.objects.create(user=self.user, account=self.account, merchant_name="Spar")
        self.item = Item.objects.create(
            receipt=receipt, item_name="Milk", unit_price=10, quantity=1, item_total=10
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse("account-detail", kwargs={"pk": self.account.pk})

    def edit(self, **fields):
        return self.client.patch(self.url, fields, format="json")

    # ---- viewing ----

    def test_shows_the_account_and_only_its_own_statements(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["account_name"], "Everyday")
        self.assertEqual(response.data["account_number"], "1111")
        self.assertEqual(response.data["card_type"], "Cheque")
        self.assertEqual(response.data["funds"], "500.00")
        statements = {s["id"]: s for s in response.data["statements"]}
        self.assertEqual(set(statements), {self.march.id, self.april.id})
        self.assertEqual(statements[self.march.id]["file_name"], "March")
        self.assertEqual(statements[self.march.id]["transaction_count"], 2)
        self.assertEqual(statements[self.april.id]["file_name"], "april.csv")  # falls back to the file
        self.assertEqual(statements[self.april.id]["transaction_count"], 0)

    def test_an_account_with_no_statements_lists_none(self):
        url = reverse("account-detail", kwargs={"pk": self.other_account.pk})
        self.client.force_authenticate(user=self.other_user)

        self.assertEqual(self.client.get(url).data["statements"], [])

    def test_cannot_see_or_edit_another_users_account(self):
        url = reverse("account-detail", kwargs={"pk": self.other_account.pk})

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(url, {"account_name": "Mine now"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.other_account.refresh_from_db()
        self.assertEqual(self.other_account.account_name, "Theirs")

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.edit(account_name="x").status_code, status.HTTP_401_UNAUTHORIZED)

    # ---- editing ----

    def test_details_can_be_edited(self):
        response = self.edit(
            account_name="  Main account ", card_type="Credit", account_number="9876", funds="1250.50"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.account.refresh_from_db()
        self.assertEqual(
            (self.account.account_name, self.account.card_type, self.account.account_number, self.account.funds),
            ("Main account", "Credit", "9876", Decimal("1250.50")),
        )
        # the response is the account as it now is, with its statements still
        self.assertEqual(response.data["account_name"], "Main account")
        self.assertEqual(len(response.data["statements"]), 2)

    def test_only_the_details_sent_change(self):
        self.edit(account_name="Renamed")

        self.account.refresh_from_db()
        self.assertEqual(self.account.account_name, "Renamed")
        self.assertEqual(self.account.account_number, "1111")
        self.assertEqual(self.account.funds, Decimal("500.00"))

    def test_edits_show_on_every_statement_and_line_item(self):
        self.edit(account_name="Main account", account_number="9876", card_type="Credit")

        # the statement page
        statement = self.client.get(reverse("statement-detail", kwargs={"pk": self.march.pk}))
        self.assertEqual(statement.data["account"]["account_name"], "Main account")
        self.assertEqual(statement.data["account"]["account_number"], "9876")
        self.assertEqual(statement.data["account"]["card_type"], "Credit")

        # every line item, whether a statement line or a receipt item
        lines = self.client.get(reverse("line-item-list")).data
        for line in (l for l in lines if l["id"] in (self.line.id, self.item.id)):
            self.assertEqual(line["account"]["account_name"], "Main account", line["kind"])
            self.assertEqual(line["account"]["account_number"], "9876", line["kind"])
        self.assertEqual(len([l for l in lines if l["account"]]), 3)  # both statement lines + the item

        # the list of accounts, and the statements' own records still point at it
        names = {a["account_name"] for a in self.client.get(reverse("account-list")).data}
        self.assertEqual(names, {"Main account", "Rainy day"})
        self.march.refresh_from_db()
        self.assertEqual(self.march.account, self.account)

    def test_other_accounts_are_not_touched(self):
        self.edit(account_name="Main account", account_number="9876")

        self.second.refresh_from_db()
        self.assertEqual((self.second.account_name, self.second.account_number), ("Rainy day", "2222"))

    def test_account_number_must_be_four_digits(self):
        for number in ["123", "12345", "12a4", "", "    "]:
            response = self.edit(account_number=number)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, repr(number))
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "1111")

    def test_account_number_cannot_be_another_of_your_accounts(self):
        response = self.edit(account_number="2222")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already have an account", response.data["error"])
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_number, "1111")

    def test_keeping_your_own_number_while_editing_is_fine(self):
        response = self.edit(account_number="1111", account_name="Renamed")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_another_users_account_number_is_not_a_clash(self):
        response = self.edit(account_number="3333")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rejects_invalid_details(self):
        for fields in [
            {"account_name": ""},
            {"account_name": "   "},
            {"account_name": "x" * 101},
            {"card_type": "Platinum"},
            {"funds": "-1"},
            {"funds": "abc"},
        ]:
            response = self.edit(**fields)

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, fields)
        self.account.refresh_from_db()
        self.assertEqual(self.account.account_name, "Everyday")

    def test_owner_and_id_cannot_be_changed(self):
        original_id = self.account.pk
        self.edit(user=str(self.other_user.pk), id=str(uuid.uuid4()), account_name="Renamed")

        self.account.refresh_from_db()
        self.assertEqual((self.account.pk, self.account.user), (original_id, self.user))


class ReceiptMatchingTests(APITestCase):
    """A whole receipt is matched to the bank statement line it was paid with."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="matchuser", password="password1", email="matchuser@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="matchother", password="password2", email="matchother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        self.second = Account.objects.create(
            user=self.user, account_name="Savings", card_type="Savings", account_number="2222"
        )
        self.other_account = Account.objects.create(
            user=self.other_user, account_name="Theirs", account_number="3333"
        )
        self.statement = BankStatement.objects.create(
            account=self.account, file_path="s/a.csv", display_name="A", doc_type="CSV"
        )
        self.line = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-200.00"),
            transaction_date=date(2026, 8, 15), merchant="CHECKERS",
        )
        self.other_line = Transaction.objects.create(
            account=self.other_account, amount=Decimal("-5.00"),
            transaction_date=date(2026, 8, 15), merchant="SECRET",
        )
        self.receipt = Receipt.objects.create(
            user=self.user, display_name="Checkers run", merchant_name="Checkers",
            total_amount=Decimal("209.95"),
        )
        self.item = Item.objects.create(
            receipt=self.receipt, item_name="Milk", unit_price=10, quantity=1, item_total=10
        )
        self.other_receipt = Receipt.objects.create(user=self.other_user, display_name="Theirs")

        self.client.force_authenticate(user=self.user)

    def match(self, receipt=None, line=None, query=None):
        receipt = receipt or self.receipt
        query = query if query is not None else f"?target={(line or self.line).pk}"
        return self.client.patch(
            reverse("document-update", kwargs={"receiptId": receipt.pk}) + query
        )

    def test_matching_links_the_receipt_and_reconciles_the_line(self):
        response = self.match()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.receipt.refresh_from_db()
        self.line.refresh_from_db()
        self.assertEqual(self.receipt.transaction, self.line)
        self.assertEqual(self.line.status, "Reconciled")  # as the other statuses are written
        self.assertEqual(response.data["transaction"], self.line.id)

    def test_the_receipt_takes_the_statements_amount_as_a_positive_total(self):
        response = self.match()

        self.receipt.refresh_from_db()
        # the statement records a debit as negative; the receipt total is what was spent
        self.assertEqual(self.receipt.total_amount, Decimal("200.00"))
        self.assertEqual(response.data["total_amount"], "200.00")

    def test_a_matching_amount_is_left_alone(self):
        self.receipt.total_amount = Decimal("200.00")
        self.receipt.save()

        self.match()

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("200.00"))

    def test_a_receipt_with_no_account_takes_the_lines_account(self):
        self.assertIsNone(self.receipt.account)

        response = self.match()

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.account, self.account)
        self.assertEqual(response.data["account"]["account_number"], "1111")

    def test_a_receipt_cannot_match_a_line_on_a_different_account(self):
        self.receipt.account = self.second
        self.receipt.save()

        response = self.match()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("different bank account", response.data["error"])
        self.receipt.refresh_from_db()
        self.line.refresh_from_db()
        self.assertIsNone(self.receipt.transaction)
        self.assertEqual(self.line.status, "Pending")

    def test_a_receipt_on_the_same_account_matches(self):
        self.receipt.account = self.account
        self.receipt.save()

        self.assertEqual(self.match().status_code, status.HTTP_200_OK)

    def test_a_matched_receipt_shows_as_matched_and_leaves_the_queue(self):
        self.match()

        docs = self.client.get("/api/documents/", {"category": "receipt"}).data
        entry = next(d for d in docs if d["id"] == self.receipt.id)
        self.assertTrue(entry["has_transaction"])
        self.assertEqual(entry["meta"]["account"], self.account.id)

    def test_the_statement_marks_the_line_as_matched(self):
        before = self.client.get(reverse("statement-detail", kwargs={"pk": self.statement.pk}))
        self.match()
        after = self.client.get(reverse("statement-detail", kwargs={"pk": self.statement.pk}))

        self.assertFalse(before.data["transactions"][0]["matched"])
        self.assertTrue(after.data["transactions"][0]["matched"])

    def test_a_receipt_can_only_be_matched_once(self):
        self.match()
        second_line = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-1.00"),
            transaction_date=date(2026, 8, 16), merchant="OTHER",
        )

        response = self.match(line=second_line)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been matched", response.data["error"])

    def test_a_line_can_only_be_matched_once(self):
        self.match()
        another = Receipt.objects.create(user=self.user, display_name="Another")

        response = self.match(receipt=another)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already been matched", response.data["error"])

    def test_a_line_matched_by_one_of_its_items_counts_as_matched(self):
        self.item.transaction = self.line
        self.item.save()

        self.assertEqual(self.match().status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_match_another_users_receipt_or_line(self):
        self.assertEqual(self.match(receipt=self.other_receipt).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.match(line=self.other_line).status_code, status.HTTP_404_NOT_FOUND)
        self.other_receipt.refresh_from_db()
        self.other_line.refresh_from_db()
        self.assertIsNone(self.other_receipt.transaction)
        self.assertEqual(self.other_line.status, "Pending")

    def test_a_bad_target_or_receipt_is_refused_rather_than_failing(self):
        for query in ["", "?target=", "?target=not-a-uuid"]:
            self.assertEqual(
                self.match(query=query).status_code, status.HTTP_400_BAD_REQUEST, query
            )
        url = reverse("document-update", kwargs={"receiptId": "not-a-uuid"})
        self.assertEqual(
            self.client.patch(url + f"?target={self.line.pk}").status_code, status.HTTP_404_NOT_FOUND
        )

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.match().status_code, status.HTTP_401_UNAUTHORIZED)


class ReceiptAccountTests(APITestCase):
    """Linking a receipt which was uploaded as "reconcile later" to a bank account."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="linkuser", password="password1", email="linkuser@gmail.com"
        )
        other = User.objects.create_user(
            username="linkother", password="password2", email="linkother@gmail.com"
        )
        self.account = Account.objects.create(user=self.user, account_name="Cheque", account_number="1111")
        self.second = Account.objects.create(user=self.user, account_name="Savings", account_number="2222")
        self.theirs = Account.objects.create(user=other, account_name="Theirs", account_number="3333")
        self.receipt = Receipt.objects.create(user=self.user, display_name="Receipt")
        self.other_receipt = Receipt.objects.create(user=other, display_name="Theirs")
        self.cash = Receipt.objects.create(user=self.user, display_name="Cash", entry_type="cash")
        self.client.force_authenticate(user=self.user)

    def link(self, receipt=None, account=None):
        url = reverse("receipt-account", kwargs={"pk": (receipt or self.receipt).pk})
        return self.client.patch(url, {"account": str((account or self.account).pk)}, format="json")

    def test_a_receipt_can_be_linked_to_one_of_your_accounts(self):
        response = self.link()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.account, self.account)
        self.assertEqual(response.data["account"]["account_number"], "1111")

    def test_the_link_can_be_changed_while_the_receipt_is_unmatched(self):
        self.link()

        self.assertEqual(self.link(account=self.second).status_code, status.HTTP_200_OK)
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.account, self.second)

    def test_the_account_then_shows_in_the_document_list(self):
        self.link()

        docs = self.client.get("/api/documents/", {"category": "receipt"}).data
        self.assertEqual(next(d for d in docs if d["id"] == self.receipt.id)["meta"]["account"], self.account.id)

    def test_cannot_link_to_another_users_account_or_link_their_receipt(self):
        self.assertEqual(self.link(account=self.theirs).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.link(receipt=self.other_receipt).status_code, status.HTTP_404_NOT_FOUND)
        self.other_receipt.refresh_from_db()
        self.assertIsNone(self.other_receipt.account)

    def test_cash_entries_have_no_account_to_link(self):
        self.assertEqual(self.link(receipt=self.cash).status_code, status.HTTP_404_NOT_FOUND)

    def test_an_account_is_required(self):
        url = reverse("receipt-account", kwargs={"pk": self.receipt.pk})

        for body in [{}, {"account": ""}, {"account": "not-a-uuid"}]:
            response = self.client.patch(url, body, format="json")

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, body)

    def test_a_matched_receipt_cannot_be_moved_to_a_different_account(self):
        statement = BankStatement.objects.create(account=self.account, file_path="s/a.csv")
        line = Transaction.objects.create(
            account=self.account, statement=statement, amount=Decimal("-5.00"),
            transaction_date=date(2026, 8, 1), merchant="X",
        )
        self.receipt.transaction = line
        self.receipt.account = self.account
        self.receipt.save()

        self.assertEqual(self.link(account=self.second).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.link(account=self.account).status_code, status.HTTP_200_OK)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.link().status_code, status.HTTP_401_UNAUTHORIZED)


STATEMENT_CSV = (
    b"Date,Description,Amount\n"
    b"2026-03-01,SPAR NEWLANDS,-50.00\n"
    b"2026-03-02,ACME SALARY,1000.00\n"
)


class LineItemFieldsTests(APITestCase):
    """The merchant, date, debit/credit and tags a user gives a line item before it is saved."""

    upload_url = "/api/documents/upload/"

    @classmethod
    def tearDownClass(cls):
        test_storage_path = os.path.join(settings.BASE_DIR, "test_document_storage")
        if os.path.exists(test_storage_path):
            shutil.rmtree(test_storage_path)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(
            username="fieldsuser", password="password1", email="fieldsuser@gmail.com"
        )
        other = User.objects.create_user(
            username="fieldsother", password="password2", email="fieldsother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        self.groceries = Tag.objects.get(name="Groceries", owner=None)
        self.mine = Tag.objects.create(name="Holiday", owner=self.user)
        self.theirs = Tag.objects.create(name="Secret", owner=other)
        self.client.force_authenticate(user=self.user)
        self.manual_url = reverse("document-manual-entry")

    def manual(self, items, entry_type="receipt", **extra):
        return self.client.post(
            self.manual_url,
            {"display_name": "Shop", "entry_type": entry_type, "items": items, **extra},
            format="json",
        )

    def upload(self, name, content, category, **fields):
        return self.client.post(
            self.upload_url,
            {
                "file": SimpleUploadedFile(name, content, content_type="text/csv"),
                "category": category,
                "display_name": "Doc",
                **fields,
            },
            format="multipart",
        )

    # ---- manual entry ----

    def test_manual_line_items_keep_their_merchant_date_direction_and_tags(self):
        response = self.manual(
            [
                {
                    "name": "Milk", "cost": "12.50", "merchant": "Spar", "date": "2026-03-04",
                    "direction": "debit", "tags": [str(self.groceries.pk), str(self.mine.pk)],
                }
            ]
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = Item.objects.get()
        self.assertEqual(
            (item.merchant, item.date, item.direction, item.item_total),
            ("Spar", date(2026, 3, 4), "debit", Decimal("12.50")),
        )
        self.assertEqual(set(item.tags.all()), {self.groceries, self.mine})
        sent = response.data["meta"]["items"][0]
        self.assertEqual((sent["merchant"], sent["date"], sent["direction"]), ("Spar", "2026-03-04", "debit"))
        self.assertEqual({t["name"] for t in sent["tags"]}, {"Groceries", "Holiday"})

    def test_the_new_fields_are_optional(self):
        response = self.manual([{"name": "Milk", "cost": "12.50"}])

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = Item.objects.get()
        self.assertEqual((item.merchant, item.date, item.direction), ("", None, "debit"))
        self.assertIsNone(response.data["meta"]["items"][0]["merchant"])

    def test_a_credit_pays_back_against_the_total(self):
        response = self.manual(
            [
                {"name": "Shirt", "cost": "100.00", "direction": "debit"},
                {"name": "Refund", "cost": "30.00", "direction": "credit"},
            ]
        )

        self.assertEqual(response.data["meta"]["amount"], "70.00")

    def test_amounts_are_entered_positive_and_dates_in_iso_form(self):
        for bad in [
            {"name": "x", "cost": "-5.00"},
            {"name": "x", "cost": "5.00", "date": "15/08/2026"},
            {"name": "x", "cost": "5.00", "date": "2026-13-45"},
            {"name": "x", "cost": "5.00", "direction": "sideways"},
        ]:
            response = self.manual([bad])

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.assertFalse(Receipt.objects.exists())

    def test_a_line_cannot_carry_another_users_or_an_unknown_tag(self):
        for tag in [str(self.theirs.pk), str(uuid.uuid4())]:
            response = self.manual([{"name": "x", "cost": "5.00", "tags": [tag]}])

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, tag)
        self.assertFalse(Receipt.objects.exists())

    # ---- receipt upload ----

    def test_an_uploaded_receipts_lines_keep_what_the_user_added(self):
        items = [
            {
                "name": "Milk", "quantity": "1", "unit_price": "20.00", "total": "20.00",
                "merchant": "Checkers", "date": "2026-03-01", "direction": "debit",
                "tags": [str(self.groceries.pk)],
            },
            {"name": "Voucher", "quantity": "1", "unit_price": "5.00", "total": "5.00", "direction": "credit"},
        ]

        response = self.upload("r.csv", b"x", "receipt", items=json.dumps(items))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        milk, voucher = Item.objects.get(item_name="Milk"), Item.objects.get(item_name="Voucher")
        self.assertEqual((milk.merchant, milk.date, milk.direction), ("Checkers", date(2026, 3, 1), "debit"))
        self.assertEqual(list(milk.tags.all()), [self.groceries])
        self.assertEqual(voucher.direction, "credit")
        self.assertEqual(response.data["meta"]["amount"], "15.00")  # 20.00 spent, 5.00 back

    def test_a_negative_line_total_is_the_other_direction(self):
        items = [{"name": "Discount", "quantity": "1", "unit_price": "-3.00", "total": "-3.00"}]

        self.upload("r.csv", b"x", "receipt", items=json.dumps(items))

        discount = Item.objects.get()
        self.assertEqual((discount.item_total, discount.direction), (Decimal("3.00"), "credit"))

    def test_a_receipt_line_cannot_carry_another_users_tag_and_nothing_is_saved(self):
        items = [{"name": "Milk", "quantity": "1", "unit_price": "1", "total": "1", "tags": [str(self.theirs.pk)]}]

        response = self.upload("r.csv", b"x", "receipt", items=json.dumps(items))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Receipt.objects.exists())

    # ---- how a saved line is reported ----

    def test_line_items_report_their_own_merchant_date_and_direction(self):
        receipt = Receipt.objects.create(
            user=self.user, merchant_name="Checkers",
            transaction_date=timezone.make_aware(datetime(2026, 3, 1)),
        )
        plain = Item.objects.create(receipt=receipt, item_name="Plain", unit_price=1, quantity=1, item_total=1)
        edited = Item.objects.create(
            receipt=receipt, item_name="Edited", unit_price=1, quantity=1, item_total=1,
            merchant="Woolworths", date=date(2026, 3, 9), direction="credit",
        )

        lines = {l["id"]: l for l in self.client.get(reverse("line-item-list")).data}

        self.assertEqual((lines[plain.id]["merchant"], lines[plain.id]["date"], lines[plain.id]["direction"]), ("Checkers", "2026-03-01", "out"))
        self.assertEqual((lines[edited.id]["merchant"], lines[edited.id]["date"], lines[edited.id]["direction"]), ("Woolworths", "2026-03-09", "in"))

    def test_statement_page_shows_the_text_and_the_merchant_of_an_edited_line(self):
        statement = BankStatement.objects.create(account=self.account, file_path="s/a.csv")
        Transaction.objects.create(
            account=self.account, statement=statement, amount=Decimal("-5.00"),
            transaction_date=date(2026, 3, 1), merchant="SPAR", description="SPAR NEWLANDS ZA",
        )
        Transaction.objects.create(
            account=self.account, statement=statement, amount=Decimal("-6.00"),
            transaction_date=date(2026, 3, 2), merchant="OLD STYLE LINE",
        )

        lines = self.client.get(reverse("statement-detail", kwargs={"pk": statement.pk})).data["transactions"]

        self.assertEqual((lines[0]["description"], lines[0]["merchant"]), ("SPAR NEWLANDS ZA", "SPAR"))
        self.assertEqual((lines[1]["description"], lines[1]["merchant"]), ("OLD STYLE LINE", None))  # as before

    # ---- reading a statement before it is saved ----

    def parse(self, name="s.csv", content=STATEMENT_CSV, **fields):
        return self.client.post(
            reverse("document-parse"),
            {"file": SimpleUploadedFile(name, content, content_type="text/csv"), "category": "statement", **fields},
            format="multipart",
        )

    def test_a_statement_is_read_into_signed_transactions(self):
        response = self.parse()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["transactions"],
            [
                {"amount": "-50.00",
                    "date": "2026-03-01",
                    "direction": "debit",
                    "merchant": "",
                    "name": "SPAR NEWLANDS",
                    "tags": [],},
                {"amount": "1000.00",
                    "date": "2026-03-02",
                    "direction": "credit",
                    "merchant": "",
                    "name": "ACME SALARY",
                    "tags": [],
                },
            ],
        )
        self.assertEqual(response.data["issues"], [])
        self.assertFalse(BankStatement.objects.exists())  # nothing is saved

    def test_statement_templates_apply_their_tags(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Spar"
        )
        template.tags.add(self.groceries, self.mine)

        response = self.parse()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["transactions"][0]["merchant"], "Spar")
        self.assertEqual(
            set(response.data["transactions"][0]["tags"]),
            {str(self.groceries.pk), str(self.mine.pk)},
        )

    def test_statement_preview_and_upload_ignore_legacy_foreign_template_tags(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Spar"
        )
        template.tags.add(self.theirs)

        parsed = self.parse()
        self.assertEqual(parsed.status_code, status.HTTP_200_OK)
        self.assertEqual(parsed.data["transactions"][0]["tags"], [])

        response = self.upload(
            "s.csv",
            STATEMENT_CSV,
            "statement",
            account=str(self.account.pk),
            transactions=self.transactions(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        spar = Transaction.objects.get(statement_id=response.data["id"], description="SPAR NEWLANDS")
        self.assertEqual(list(spar.tags.all()), [])

    def test_statement_upload_applies_all_available_template_tags(self):
        template = TransactionTemplate.objects.create(
            user=self.user, search_string="SPAR", merchant_name="Template Spar"
        )
        template.tags.add(self.groceries, self.mine)

        response = self.upload(
            "s.csv",
            STATEMENT_CSV,
            "statement",
            account=str(self.account.pk),
            transactions=self.transactions(),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        spar = Transaction.objects.get(statement_id=response.data["id"], description="SPAR NEWLANDS")
        self.assertEqual(spar.merchant, "Template Spar")
        self.assertEqual(set(spar.tags.all()), {self.groceries, self.mine})

    def test_debit_and_credit_columns_are_read_too(self):
        csv = b"Date,Description,Debit,Credit\n2026-03-01,SPAR,50.00,\n2026-03-02,SALARY,,1000.00\n"

        response = self.parse(content=csv)

        self.assertEqual([t["amount"] for t in response.data["transactions"]], ["-50.00", "1000.00"])

    def test_an_unreadable_statement_reports_why_rather_than_failing(self):
        response = self.parse(content=b"Foo,Bar\n1,2\n")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["transactions"], [])
        self.assertIn("Missing required column", response.data["issues"][0])

    def test_bad_lines_are_reported_and_the_rest_still_read(self):
        csv = b"Date,Description,Amount\n2026-03-01,GOOD,-5.00\nnot a date,BAD,-6.00\n"

        response = self.parse(content=csv)

        self.assertEqual([t["name"] for t in response.data["transactions"]], ["GOOD"])
        self.assertEqual(len(response.data["issues"]), 1)

    def test_a_pdf_statement_is_read_by_way_of_its_csv(self):
        def fake_pdf_parse(file_path, output_path, **kwargs):
            csv_path = output_path + "-page-1-table-1.csv"
            with open(csv_path, "wb") as out:
                out.write(STATEMENT_CSV)
            return {"filenames": [csv_path], "errors": [], "reports": []}

        with mock.patch("core.statement_parsing.PdfBankParser") as parser:
            parser.return_value.parse.side_effect = fake_pdf_parse
            response = self.client.post(
                reverse("document-parse"),
                {"file": SimpleUploadedFile("s.pdf", b"%PDF-1.4 x", content_type="application/pdf"), "category": "statement"},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["transactions"]), 2)

    def test_a_pdf_statement_passes_bank_type_to_parser(self):
        def fake_pdf_parse(file_path, output_path, **kwargs):
            csv_path = output_path + "-page-1-table-1.csv"
            with open(csv_path, "wb") as out:
                out.write(STATEMENT_CSV)
            return {"filenames": [csv_path], "errors": [], "reports": []}

        with mock.patch("core.statement_parsing.PdfBankParser") as parser:
            parser.return_value.parse.side_effect = fake_pdf_parse
            response = self.client.post(
                reverse("document-parse"),
                {
                    "file": SimpleUploadedFile("s.pdf", b"%PDF-1.4 x", content_type="application/pdf"),
                    "category": "statement",
                    "bank": "fnb",
                },
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        parser.return_value.parse.assert_called_once()
        _, kwargs = parser.return_value.parse.call_args
        self.assertEqual(kwargs.get("bank"), "fnb")

    def test_a_pdf_with_no_table_reports_an_issue(self):
        with mock.patch("core.statement_parsing.PdfBankParser") as parser:
            parser.return_value.parse.return_value = {"filenames": [], "errors": [], "reports": []}
            response = self.client.post(
                reverse("document-parse"),
                {"file": SimpleUploadedFile("s.pdf", b"%PDF-1.4 x", content_type="application/pdf"), "category": "statement"},
                format="multipart",
            )

        self.assertEqual(response.data["transactions"], [])
        self.assertIn("no transactions table", response.data["issues"][0])

    def test_parse_still_reads_receipts_by_default_and_refuses_other_categories(self):
        receipt = self.client.post(
            reverse("document-parse"),
            {"file": SimpleUploadedFile("r.csv", RECEIPT_CSV, content_type="text/csv")},
            format="multipart",
        )
        other = self.parse(category="scan")

        self.assertIn("items", receipt.data)
        self.assertEqual(other.status_code, status.HTTP_400_BAD_REQUEST)

    # ---- uploading a statement as edited ----

    def transactions(self, **overrides):
        base = {"name": "SPAR NEWLANDS", "merchant": "Spar", "date": "2026-03-01", "direction": "debit", "amount": "50.00", "tags": []}
        return json.dumps([{**base, **overrides}, {**base, "name": "ACME SALARY", "merchant": "Acme", "date": "2026-03-02", "direction": "credit", "amount": "1000.00"}])

    def test_a_statements_lines_are_saved_as_the_user_left_them(self):
        with mock.patch("core.views.threading.Thread") as thread:
            response = self.upload(
                "s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk),
                transactions=self.transactions(tags=[str(self.groceries.pk)]),
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        thread.assert_not_called()  # the lines the user saw are the ones saved
        spar, salary = Transaction.objects.order_by("transaction_date")
        self.assertEqual((spar.amount, spar.transaction_type), (Decimal("-50.00"), "Expense"))
        self.assertEqual((salary.amount, salary.transaction_type), (Decimal("1000.00"), "Income"))
        self.assertEqual((spar.merchant, spar.description, spar.transaction_date), ("Spar", "SPAR NEWLANDS", date(2026, 3, 1)))
        self.assertEqual(list(spar.tags.all()), [self.groceries])
        self.assertEqual(spar.account, self.account)
        self.assertEqual(spar.statement_id, response.data["id"])
        self.assertEqual(response.data["meta"]["transaction_count"], 2)

    def test_an_edited_merchant_is_what_is_saved(self):
        response = self.upload(
            "s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk),
            transactions=self.transactions(merchant="Renamed by the user"),
        )

        self.assertEqual(Transaction.objects.get(transaction_date=date(2026, 3, 1)).merchant, "Renamed by the user")

    def test_a_statement_with_no_lines_is_saved_as_such_without_being_read_again(self):
        with mock.patch("core.views.threading.Thread") as thread:
            response = self.upload("s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk), transactions="[]")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Transaction.objects.exists())
        thread.assert_not_called()

    def test_without_lines_the_server_reads_the_statement_itself(self):
        with mock.patch("core.views.threading.Thread") as thread:
            response = self.upload("s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        thread.assert_not_called()

    def test_invalid_statement_lines_are_refused_and_nothing_is_saved(self):
        for bad in [
            {"date": ""}, {"date": "01/03/2026"}, {"direction": "up"}, {"amount": "-5.00"}, {"amount": "abc"},
        ]:
            response = self.upload(
                "s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk),
                transactions=self.transactions(**bad),
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.assertFalse(BankStatement.objects.exists())

    def test_a_statement_line_cannot_carry_another_users_tag(self):
        response = self.upload(
            "s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk),
            transactions=self.transactions(tags=[str(self.theirs.pk)]),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(BankStatement.objects.exists())

    def test_the_saved_lines_show_in_the_line_item_list_with_the_right_direction(self):
        self.upload("s.csv", STATEMENT_CSV, "statement", account=str(self.account.pk), transactions=self.transactions())

        lines = {l["description"]: l for l in self.client.get(reverse("line-item-list")).data}

        self.assertEqual(lines["SPAR NEWLANDS"]["direction"], "out")
        self.assertEqual(lines["ACME SALARY"]["direction"], "in")
        self.assertEqual(lines["SPAR NEWLANDS"]["merchant"], "Spar")

    def test_parsing_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.parse().status_code, status.HTTP_401_UNAUTHORIZED)


class LineItemNameTests(APITestCase):
    """The name a user gives a line item is an alias: the name it was read with is never touched."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="nameuser", password="password1", email="nameuser@gmail.com"
        )
        other = User.objects.create_user(
            username="nameother", password="password2", email="nameother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        other_account = Account.objects.create(
            user=other, account_name="Other", account_number="2222"
        )
        self.statement = BankStatement.objects.create(
            account=self.account, file_path="statements/a.csv", display_name="A", doc_type="CSV"
        )
        # a parsed line has its text as the merchant and no description...
        self.parsed = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-57.98"),
            transaction_date=date(2026, 8, 15), merchant="CHECKERS NEWLANDS ZA",
        )
        # ...and one the user edited before saving has both
        self.edited = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("1000.00"),
            transaction_date=date(2026, 8, 16), merchant="Acme", description="ACME SALARY",
        )
        receipt = Receipt.objects.create(user=self.user, merchant_name="Checkers")
        self.item = Item.objects.create(
            receipt=receipt, item_name="MLK FC 2L", unit_price=10, quantity=1, item_total=10,
            merchant="Checkers", date=date(2026, 8, 15), direction="debit",
        )
        self.other_transaction = Transaction.objects.create(
            account=other_account, amount=Decimal("-5.00"),
            transaction_date=date(2026, 8, 15), merchant="SPAR",
        )
        other_receipt = Receipt.objects.create(user=other, merchant_name="Spar")
        self.other_item = Item.objects.create(
            receipt=other_receipt, item_name="Eggs", unit_price=5, quantity=1, item_total=5
        )

        self.client.force_authenticate(user=self.user)

    def rename(self, name, line, display_name):
        return self.client.patch(
            reverse(name, kwargs={"pk": line.pk}), {"display_name": display_name}, format="json"
        )

    def test_a_receipt_item_can_be_given_an_alias_and_its_own_name_is_kept(self):
        response = self.rename("item-details", self.item, "  Full cream milk  ")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["display_name"], "Full cream milk")
        self.item.refresh_from_db()
        self.assertEqual((self.item.display_name, self.item.item_name), ("Full cream milk", "MLK FC 2L"))

    def test_a_statement_line_can_be_given_an_alias_and_its_own_text_is_kept(self):
        response = self.rename("transaction-details", self.parsed, "Groceries at Checkers")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.parsed.refresh_from_db()
        self.assertEqual(self.parsed.display_name, "Groceries at Checkers")
        self.assertEqual((self.parsed.merchant, self.parsed.description), ("CHECKERS NEWLANDS ZA", None))

    def test_a_blank_name_or_the_lines_own_takes_the_alias_away(self):
        self.rename("item-details", self.item, "Milk")
        self.rename("transaction-details", self.parsed, "Checkers")
        self.rename("transaction-details", self.edited, "Salary")

        self.assertEqual(self.rename("item-details", self.item, "   ").data["display_name"], None)
        self.assertEqual(self.rename("transaction-details", self.parsed, "CHECKERS NEWLANDS ZA").data["display_name"], None)
        # a line the user edited has its description as its own name, not its merchant
        self.assertEqual(self.rename("transaction-details", self.edited, "ACME SALARY").data["display_name"], None)
        for line in (self.item, self.parsed, self.edited):
            line.refresh_from_db()
            self.assertEqual(line.display_name, "")

    def test_a_name_which_is_too_long_is_refused(self):
        response = self.rename("item-details", self.item, "x" * 256)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.display_name, "")

    def test_another_users_line_items_cannot_be_named(self):
        self.assertEqual(self.rename("item-details", self.other_item, "Mine").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.rename("transaction-details", self.other_transaction, "Mine").status_code, status.HTTP_404_NOT_FOUND
        )
        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.display_name, "")

    def test_naming_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.rename("item-details", self.item, "x").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.rename("transaction-details", self.parsed, "x").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_alias_shows_beside_the_original_on_every_page_that_lists_line_items(self):
        self.rename("item-details", self.item, "Milk")
        self.rename("transaction-details", self.parsed, "Checkers")

        lines = {l["id"]: l for l in self.client.get(reverse("line-item-list")).data}
        self.assertEqual((lines[self.item.id]["description"], lines[self.item.id]["display_name"]), ("MLK FC 2L", "Milk"))
        self.assertEqual(
            (lines[self.parsed.id]["description"], lines[self.parsed.id]["display_name"]),
            ("CHECKERS NEWLANDS ZA", "Checkers"),
        )
        self.assertIsNone(lines[self.edited.id]["display_name"])

        statement = self.client.get(reverse("statement-detail", kwargs={"pk": self.statement.pk})).data
        by_id = {t["id"]: t for t in statement["transactions"]}
        self.assertEqual(
            (by_id[self.parsed.id]["description"], by_id[self.parsed.id]["display_name"]),
            ("CHECKERS NEWLANDS ZA", "Checkers"),
        )

        listed = self.client.get(reverse("document-list"), {"category": "receipt"}).data
        item = listed[0]["meta"]["items"][0]
        self.assertEqual((item["item_name"], item["display_name"]), ("MLK FC 2L", "Milk"))

    def test_a_statement_line_reports_which_way_the_money_went(self):
        statement = self.client.get(reverse("statement-detail", kwargs={"pk": self.statement.pk})).data

        by_id = {t["id"]: t for t in statement["transactions"]}
        self.assertEqual(by_id[self.parsed.id]["direction"], "out")
        self.assertEqual(by_id[self.edited.id]["direction"], "in")
        self.assertEqual(by_id[self.edited.id]["merchant"], "Acme")

    def test_a_receipt_item_reports_its_merchant_date_and_direction_to_the_review_page(self):
        listed = self.client.get(reverse("document-list"), {"category": "receipt"}).data

        item = listed[0]["meta"]["items"][0]
        self.assertEqual((item["merchant"], item["date"], item["direction"]), ("Checkers", "2026-08-15", "debit"))


class LineItemEditTests(APITestCase):
    """Changing a saved line item's merchant, date and debit/credit, and what that leaves alone."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="edituser", password="password1", email="edituser@gmail.com"
        )
        other = User.objects.create_user(
            username="editother", password="password2", email="editother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        self.statement = BankStatement.objects.create(
            account=self.account, file_path="statements/a.csv", display_name="A", doc_type="CSV"
        )
        # a line as parsing leaves it: its text is its merchant, and it has no description
        self.parsed = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-57.98"),
            transaction_date=date(2026, 8, 15), merchant="CHECKERS NEWLANDS ZA",
        )
        # and one which was edited before it was saved
        self.edited = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("1000.00"),
            transaction_date=date(2026, 8, 16), merchant="Acme", description="ACME SALARY",
            transaction_type="Income",
        )
        self.receipt = Receipt.objects.create(
            user=self.user, merchant_name="Checkers", total_amount=Decimal("15.00"),
            transaction_date=timezone.make_aware(datetime(2026, 8, 15)),
        )
        self.milk = Item.objects.create(
            receipt=self.receipt, item_name="Milk", unit_price=10, quantity=1, item_total=10
        )
        self.bread = Item.objects.create(
            receipt=self.receipt, item_name="Bread", unit_price=5, quantity=1, item_total=5
        )
        other_account = Account.objects.create(user=other, account_name="Other", account_number="2222")
        self.other_transaction = Transaction.objects.create(
            account=other_account, amount=Decimal("-5.00"),
            transaction_date=date(2026, 8, 15), merchant="SPAR",
        )
        other_receipt = Receipt.objects.create(user=other, merchant_name="Spar")
        self.other_item = Item.objects.create(
            receipt=other_receipt, item_name="Eggs", unit_price=5, quantity=1, item_total=5
        )
        self.client.force_authenticate(user=self.user)

    def edit(self, name, line, **fields):
        return self.client.patch(reverse(name, kwargs={"pk": line.pk}), fields, format="json")

    # ---- a receipt item ----

    def test_a_receipt_item_takes_a_new_merchant_and_date_and_reports_them(self):
        response = self.edit("item-details", self.milk, merchant="Woolworths", date="2026-09-01")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["merchant"], response.data["date"]), ("Woolworths", "2026-09-01"))
        self.assertEqual(response.data["kind"], "receipt_item")
        self.milk.refresh_from_db()
        self.assertEqual((self.milk.merchant, self.milk.date), ("Woolworths", date(2026, 9, 1)))

    def test_only_what_was_sent_changes(self):
        self.edit("item-details", self.milk, merchant="Woolworths", date="2026-09-01")

        response = self.edit("item-details", self.milk, direction="credit")

        self.milk.refresh_from_db()
        self.assertEqual((self.milk.merchant, self.milk.date, self.milk.direction), ("Woolworths", date(2026, 9, 1), "credit"))
        self.assertEqual(response.data["direction"], "in")

    def test_an_item_can_lose_its_own_merchant_and_date_and_have_its_receipts_again(self):
        self.edit("item-details", self.milk, merchant="Woolworths", date="2026-09-01")

        response = self.edit("item-details", self.milk, merchant="", date=None)

        self.assertEqual((response.data["merchant"], response.data["date"]), ("Checkers", "2026-08-15"))
        self.milk.refresh_from_db()
        self.assertEqual((self.milk.merchant, self.milk.date), ("", None))

    def test_flipping_an_item_moves_a_total_which_is_what_its_items_add_up_to(self):
        response = self.edit("item-details", self.bread, direction="credit")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("5.00"))  # 10 - 5

        self.edit("item-details", self.bread, direction="debit")
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("15.00"))

    def test_flipping_an_item_leaves_a_total_which_is_not_the_sum_of_its_items(self):
        self.receipt.total_amount = Decimal("99.99")  # read from the receipt, say
        self.receipt.save()

        self.edit("item-details", self.bread, direction="credit")

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("99.99"))

    def test_an_item_can_still_be_given_an_alias_with_other_changes_in_one_request(self):
        response = self.edit("item-details", self.milk, display_name="Full cream", merchant="Spar")

        self.assertEqual((response.data["display_name"], response.data["description"]), ("Full cream", "Milk"))
        self.milk.refresh_from_db()
        self.assertEqual((self.milk.display_name, self.milk.item_name, self.milk.merchant), ("Full cream", "Milk", "Spar"))

    # ---- a statement line ----

    def test_a_statement_line_takes_a_new_date(self):
        response = self.edit("transaction-details", self.parsed, date="2026-08-20")

        self.assertEqual(response.data["date"], "2026-08-20")
        self.parsed.refresh_from_db()
        self.assertEqual(self.parsed.transaction_date, date(2026, 8, 20))

    def test_a_statement_line_cannot_lose_its_date(self):
        response = self.edit("transaction-details", self.parsed, date=None)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.parsed.refresh_from_db()
        self.assertEqual(self.parsed.transaction_date, date(2026, 8, 15))

    def test_giving_a_parsed_line_a_merchant_keeps_the_text_it_was_read_with_as_its_name(self):
        response = self.edit("transaction-details", self.parsed, merchant="Checkers")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["merchant"], response.data["description"]), ("Checkers", "CHECKERS NEWLANDS ZA"))
        self.parsed.refresh_from_db()
        self.assertEqual((self.parsed.merchant, self.parsed.description), ("Checkers", "CHECKERS NEWLANDS ZA"))

    def test_clearing_the_merchant_of_a_parsed_line_still_keeps_its_text(self):
        response = self.edit("transaction-details", self.parsed, merchant="")

        self.assertEqual((response.data["merchant"], response.data["description"]), (None, "CHECKERS NEWLANDS ZA"))
        self.parsed.refresh_from_db()
        self.assertEqual((self.parsed.merchant, self.parsed.description), (None, "CHECKERS NEWLANDS ZA"))

    def test_changing_the_merchant_of_an_edited_line_leaves_its_description(self):
        self.edit("transaction-details", self.edited, merchant="Acme Ltd")

        self.edited.refresh_from_db()
        self.assertEqual((self.edited.merchant, self.edited.description), ("Acme Ltd", "ACME SALARY"))

    def test_the_alias_of_a_parsed_line_is_still_measured_against_its_text_after_its_merchant_changes(self):
        self.edit("transaction-details", self.parsed, merchant="Checkers", display_name="Groceries")
        response = self.edit("transaction-details", self.parsed, display_name="CHECKERS NEWLANDS ZA")

        self.assertIsNone(response.data["display_name"])

    def test_flipping_a_statement_line_flips_the_sign_of_its_amount(self):
        response = self.edit("transaction-details", self.parsed, direction="credit")

        self.assertEqual((response.data["direction"], response.data["amount"]), ("in", "57.98"))
        self.parsed.refresh_from_db()
        self.assertEqual((self.parsed.amount, self.parsed.transaction_type), (Decimal("57.98"), "Income"))

        response = self.edit("transaction-details", self.parsed, direction="debit")
        self.assertEqual((response.data["direction"], response.data["amount"]), ("out", "-57.98"))
        self.parsed.refresh_from_db()
        self.assertEqual(self.parsed.transaction_type, "Expense")

    def test_saying_a_line_is_the_direction_it_already_is_changes_nothing(self):
        self.edit("transaction-details", self.parsed, direction="debit")
        self.edit("transaction-details", self.edited, direction="credit")

        self.parsed.refresh_from_db()
        self.edited.refresh_from_db()
        self.assertEqual((self.parsed.amount, self.edited.amount), (Decimal("-57.98"), Decimal("1000.00")))

    def test_a_line_of_nothing_cannot_be_made_a_credit(self):
        self.parsed.amount = Decimal("0.00")
        self.parsed.save()

        response = self.edit("transaction-details", self.parsed, direction="credit")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_request_which_is_refused_saves_none_of_its_changes(self):
        response = self.edit("transaction-details", self.parsed, merchant="Checkers", date=None)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.parsed.refresh_from_db()
        self.assertEqual((self.parsed.merchant, self.parsed.description), ("CHECKERS NEWLANDS ZA", None))

    # ---- what is refused ----

    def test_bad_values_are_refused(self):
        for line, name in ((self.milk, "item-details"), (self.parsed, "transaction-details")):
            for bad in ({"direction": "sideways"}, {"date": "01/03/2026"}, {"merchant": "x" * 256}):
                self.assertEqual(
                    self.edit(name, line, **bad).status_code, status.HTTP_400_BAD_REQUEST, (name, bad)
                )

    def test_another_users_line_items_cannot_be_changed(self):
        self.assertEqual(self.edit("item-details", self.other_item, merchant="Mine").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.edit("transaction-details", self.other_transaction, merchant="Mine").status_code, status.HTTP_404_NOT_FOUND
        )
        self.other_item.refresh_from_db()
        self.other_transaction.refresh_from_db()
        self.assertEqual((self.other_item.merchant, self.other_transaction.merchant), ("", "SPAR"))

    def test_changing_a_line_item_requires_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.edit("item-details", self.milk, merchant="x").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.edit("transaction-details", self.parsed, merchant="x").status_code, status.HTTP_401_UNAUTHORIZED)


class LineItemQuantityTests(APITestCase):
    """How many of an item a receipt line is for: 5 red apples for 70.00 is quantity 5."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="qtyuser", password="password1", email="qtyuser@gmail.com"
        )
        other = User.objects.create_user(
            username="qtyother", password="password2", email="qtyother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        statement = BankStatement.objects.create(account=self.account, file_path="s/a.csv")
        self.transaction = Transaction.objects.create(
            account=self.account, statement=statement, amount=Decimal("-70.00"),
            transaction_date=date(2026, 8, 15), merchant="CHECKERS",
        )
        self.receipt = Receipt.objects.create(
            user=self.user, merchant_name="Checkers", total_amount=Decimal("70.00"),
            transaction_date=timezone.make_aware(datetime(2026, 8, 15)),
        )
        self.apples = Item.objects.create(
            receipt=self.receipt, item_name="Red apples", unit_price=70, quantity=1, item_total=70
        )
        other_receipt = Receipt.objects.create(user=other, merchant_name="Spar")
        self.other_item = Item.objects.create(
            receipt=other_receipt, item_name="Eggs", unit_price=5, quantity=1, item_total=5
        )
        self.client.force_authenticate(user=self.user)

    def manual(self, **item):
        return self.client.post(
            reverse("document-manual-entry"),
            {"display_name": "Shop", "entry_type": "cash", "items": [{"name": "Red apples", "cost": "70.00", **item}]},
            format="json",
        )

    def edit(self, line, name="item-details", **fields):
        return self.client.patch(reverse(name, kwargs={"pk": line.pk}), fields, format="json")

    # ---- manual entry ----

    def test_a_manual_line_item_has_a_quantity_of_one_unless_it_says_otherwise(self):
        self.manual()

        item = Item.objects.get(receipt__entry_type="cash")
        self.assertEqual((item.quantity, item.unit_price, item.item_total), (1, Decimal("70.00"), Decimal("70.00")))

    def test_a_manual_line_keeps_its_total_and_shares_it_between_its_quantity(self):
        response = self.manual(quantity="5")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = Item.objects.get(receipt__entry_type="cash")
        self.assertEqual((item.quantity, item.unit_price, item.item_total), (5, Decimal("14.00"), Decimal("70.00")))
        self.assertEqual(Receipt.objects.get(entry_type="cash").total_amount, Decimal("70.00"))
        sent = response.data["meta"]["items"][0]
        self.assertEqual((Decimal(sent["quantity"]), sent["unit_price"], sent["item_total"]), (5, "14.00", "70.00"))

    def test_a_manual_quantity_can_be_fractional_and_the_price_is_rounded_to_the_cent(self):
        self.manual(quantity="3")
        self.manual(quantity="0.75", name="Mince")

        prices = {i.quantity: i.unit_price for i in Item.objects.filter(receipt__entry_type="cash")}
        self.assertEqual(prices[Decimal("3")], Decimal("23.33"))
        self.assertEqual(prices[Decimal("0.75")], Decimal("93.33"))

    def test_a_manual_quantity_which_makes_no_sense_is_refused_and_nothing_is_saved(self):
        for bad in ("0", "-2", "abc", "1.2345", "99999999999"):
            self.assertEqual(self.manual(quantity=bad).status_code, status.HTTP_400_BAD_REQUEST, bad)
        # 99,999,999.99 shared between a thousandth of an item is too much for one item to cost
        self.assertEqual(
            self.manual(cost="99999999.99", quantity="0.001").status_code, status.HTTP_400_BAD_REQUEST
        )
        self.assertFalse(Receipt.objects.filter(entry_type="cash").exists())

    # ---- changing it on a saved item ----

    def test_a_saved_items_quantity_can_be_changed_and_its_price_follows_its_total(self):
        response = self.edit(self.apples, quantity="5")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((Decimal(response.data["quantity"]), response.data["unit_price"], response.data["amount"]), (5, "14.00", "70.00"))
        self.apples.refresh_from_db()
        self.assertEqual((self.apples.quantity, self.apples.unit_price, self.apples.item_total), (5, Decimal("14.00"), Decimal("70.00")))
        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("70.00"))

    def test_the_price_of_an_item_which_was_matched_and_took_a_negative_total_stays_positive(self):
        self.apples.item_total = Decimal("-70.00")
        self.apples.save()

        self.edit(self.apples, quantity="4")

        self.apples.refresh_from_db()
        self.assertEqual((self.apples.unit_price, self.apples.item_total), (Decimal("17.50"), Decimal("-70.00")))

    def test_quantity_changes_alongside_the_other_details_in_one_request(self):
        response = self.edit(self.apples, quantity="2", merchant="Woolworths", direction="credit")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.apples.refresh_from_db()
        self.assertEqual((self.apples.quantity, self.apples.merchant, self.apples.direction), (2, "Woolworths", "credit"))

    def test_a_quantity_which_makes_no_sense_is_refused_and_changes_nothing(self):
        for bad in ("0", "-1", "abc", "1.2345"):
            self.assertEqual(self.edit(self.apples, quantity=bad).status_code, status.HTTP_400_BAD_REQUEST, bad)
        self.apples.item_total = Decimal("99999999.99")
        self.apples.save()
        self.assertEqual(self.edit(self.apples, quantity="0.001", merchant="Spar").status_code, status.HTTP_400_BAD_REQUEST)

        self.apples.refresh_from_db()
        self.assertEqual((self.apples.quantity, self.apples.unit_price, self.apples.merchant), (1, Decimal("70.00"), ""))

    def test_a_statement_line_has_no_quantity(self):
        response = self.edit(self.transaction, name="transaction-details", quantity="2")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)

    def test_another_users_item_quantity_cannot_be_changed(self):
        self.assertEqual(self.edit(self.other_item, quantity="9").status_code, status.HTTP_404_NOT_FOUND)
        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.quantity, 1)

    # ---- how it is reported ----

    def test_the_quantity_shows_wherever_receipt_items_are_listed(self):
        self.edit(self.apples, quantity="5")

        line = {l["id"]: l for l in self.client.get(reverse("line-item-list")).data}[self.apples.id]
        self.assertEqual((Decimal(line["quantity"]), line["unit_price"]), (5, "14.00"))
        listed = self.client.get(reverse("document-list"), {"category": "receipt"}).data
        item = listed[0]["meta"]["items"][0]
        self.assertEqual((Decimal(item["quantity"]), item["unit_price"]), (5, "14.00"))


class DeletionTests(APITestCase):
    """
    What goes, and what stays, when a bank statement or a receipt is deleted. A
    receipt owns its line items; a statement owns the lines nothing was matched
    to; and a receipt outlives its statement.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="deluser", password="password1", email="deluser@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        self.statement = BankStatement.objects.create(account=self.account, file_path=None, display_name="March")
        self.other_statement = BankStatement.objects.create(account=self.account, file_path=None, display_name="April")
        self.groceries = Tag.objects.get(name="Groceries", owner=None)

        def line(statement, text, amount, status="Pending"):
            return Transaction.objects.create(
                account=self.account, statement=statement, amount=Decimal(amount),
                transaction_date=date(2026, 3, 1), merchant=text, status=status,
            )

        # the March statement's lines: two nothing was matched to, and two which receipts were
        self.loose_1 = line(self.statement, "LOOSE ONE", "-10.00")
        self.loose_2 = line(self.statement, "LOOSE TWO", "-20.00")
        self.loose_2.tags.add(self.groceries)
        self.paid_receipt_line = line(self.statement, "CHECKERS", "-70.00", "Reconciled")
        self.paid_item_line = line(self.statement, "SPAR", "-5.00", "Reconciled")
        self.april_line = line(self.other_statement, "APRIL LINE", "-99.00")

        def receipt(name, **fields):
            record = Receipt.objects.create(
                user=self.user, account=self.account, display_name=name,
                merchant_name=name, total_amount=Decimal("70.00"), **fields,
            )
            item = lambda item_name, **extra: Item.objects.create(
                receipt=record, item_name=item_name, unit_price=10, quantity=1, item_total=10, **extra
            )
            return record, item

        # a receipt matched as a whole to a statement line
        self.matched_receipt, make_item = receipt("Matched", transaction=self.paid_receipt_line)
        self.matched_items = [make_item("Apples"), make_item("Pears")]
        # a receipt one of whose items was matched to a statement line
        self.item_matched_receipt, make_item = receipt("Item matched")
        self.linked_item = make_item("Bread", transaction=self.paid_item_line)
        # a receipt which is waiting to be matched
        self.waiting_receipt, make_item = receipt("Waiting")
        self.waiting_items = [make_item("Milk"), make_item("Eggs")]

        self.client.force_authenticate(user=self.user)

    def delete_document(self, document, category):
        return self.client.delete(reverse("document-delete", kwargs={"pk": document.pk}) + f"?category={category}")

    # ---- deleting a bank statement ----

    def test_deleting_a_statement_deletes_the_lines_nothing_was_matched_to(self):
        response = self.delete_document(self.statement, "statement")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BankStatement.objects.filter(pk=self.statement.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk__in=[self.loose_1.pk, self.loose_2.pk]).exists())

    def test_the_lines_a_receipt_is_matched_to_stay_without_a_statement_and_stay_reconciled(self):
        self.delete_document(self.statement, "statement")

        for kept in (self.paid_receipt_line, self.paid_item_line):
            kept.refresh_from_db()
            self.assertIsNone(kept.statement)
            self.assertEqual(kept.status, "Reconciled")

    def test_every_receipt_outlives_its_statement_with_its_line_items_and_its_match(self):
        self.delete_document(self.statement, "statement")

        self.assertEqual(Receipt.objects.count(), 3)
        self.assertEqual(Item.objects.count(), 2 + 1 + 2)
        self.matched_receipt.refresh_from_db()
        self.assertEqual(self.matched_receipt.transaction, self.paid_receipt_line)
        self.linked_item.refresh_from_db()
        self.assertEqual(self.linked_item.transaction, self.paid_item_line)

    def test_a_statement_deletes_only_its_own_lines(self):
        self.delete_document(self.statement, "statement")

        self.assertTrue(Transaction.objects.filter(pk=self.april_line.pk).exists())
        self.assertEqual(self.other_statement.transactions.count(), 1)

    def test_tags_are_not_deleted_with_the_lines_they_were_on(self):
        self.delete_document(self.statement, "statement")

        self.assertTrue(Tag.objects.filter(pk=self.groceries.pk).exists())

    def test_the_kept_lines_are_still_listed_and_still_matched(self):
        self.delete_document(self.statement, "statement")

        lines = {l["id"]: l for l in self.client.get(reverse("line-item-list")).data if l["kind"] == "statement_line"}
        self.assertEqual(set(lines), {self.paid_receipt_line.pk, self.paid_item_line.pk, self.april_line.pk})
        self.assertIsNone(lines[self.paid_receipt_line.pk]["source"])
        self.assertTrue(lines[self.paid_receipt_line.pk]["matched"])

    def test_the_rule_is_the_models_so_a_queryset_delete_follows_it_too(self):
        BankStatement.objects.filter(pk=self.statement.pk).delete()

        self.assertFalse(Transaction.objects.filter(pk__in=[self.loose_1.pk, self.loose_2.pk]).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.paid_receipt_line.pk, statement=None).exists())

    def test_deleting_an_account_leaves_its_receipts(self):
        self.account.delete()

        self.assertEqual(Receipt.objects.count(), 3)
        self.assertEqual(Item.objects.count(), 5)
        self.assertFalse(Transaction.objects.exists())
        self.matched_receipt.refresh_from_db()
        self.assertIsNone(self.matched_receipt.transaction)

    def test_a_statement_with_no_lines_deletes_cleanly(self):
        empty = BankStatement.objects.create(account=self.account, file_path=None)

        self.assertEqual(self.delete_document(empty, "statement").status_code, status.HTTP_204_NO_CONTENT)

    # ---- deleting a receipt ----

    def test_deleting_a_receipt_deletes_all_of_its_line_items_and_no_others(self):
        response = self.delete_document(self.waiting_receipt, "receipt")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Item.objects.filter(pk__in=[i.pk for i in self.waiting_items]).exists())
        self.assertEqual(Item.objects.count(), 2 + 1)
        self.assertEqual(Receipt.objects.count(), 2)

    def test_the_statement_line_a_deleted_receipt_was_matched_to_stays_but_is_no_longer_reconciled(self):
        self.delete_document(self.matched_receipt, "receipt")

        self.paid_receipt_line.refresh_from_db()
        self.assertEqual((self.paid_receipt_line.statement, self.paid_receipt_line.status), (self.statement, "Pending"))
        self.assertFalse(Item.objects.filter(pk__in=[i.pk for i in self.matched_items]).exists())

    def test_a_receipt_whose_item_was_matched_frees_that_line_when_it_is_deleted(self):
        self.delete_document(self.item_matched_receipt, "receipt")

        self.paid_item_line.refresh_from_db()
        self.assertEqual(self.paid_item_line.status, "Pending")
        self.assertFalse(Item.objects.filter(pk=self.linked_item.pk).exists())

    def test_a_line_stays_reconciled_while_another_receipt_is_still_matched_to_it(self):
        self.waiting_receipt.transaction = self.paid_receipt_line
        self.waiting_receipt.save()

        self.delete_document(self.matched_receipt, "receipt")

        self.paid_receipt_line.refresh_from_db()
        self.assertEqual(self.paid_receipt_line.status, "Reconciled")

    def test_deleting_a_cash_entry_deletes_its_line_items(self):
        cash = Receipt.objects.create(user=self.user, entry_type="cash", display_name="Market")
        items = [Item.objects.create(receipt=cash, item_name=n, unit_price=1, quantity=1, item_total=1) for n in "ab"]

        self.assertEqual(self.delete_document(cash, "cash").status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(Item.objects.filter(pk__in=[i.pk for i in items]).exists())

    def test_deleting_an_item_on_its_own_unreconciles_a_line_nothing_else_is_matched_to(self):
        self.linked_item.delete()

        self.paid_item_line.refresh_from_db()
        self.assertEqual(self.paid_item_line.status, "Pending")

    def test_a_line_item_cannot_exist_without_a_receipt(self):
        with self.assertRaises(IntegrityError):
            Item.objects.create(receipt_id=None, item_name="Orphan", unit_price=1, quantity=1, item_total=1)

    # ---- the model's own vocabulary ----

    def test_a_line_knows_whether_it_is_matched(self):
        self.assertTrue(Transaction.objects.get(pk=self.paid_receipt_line.pk).is_matched)
        self.assertTrue(Transaction.objects.get(pk=self.paid_item_line.pk).is_matched)
        self.assertFalse(Transaction.objects.get(pk=self.loose_1.pk).is_matched)
        self.assertEqual(set(Transaction.objects.matched()), {self.paid_receipt_line, self.paid_item_line})
        self.assertEqual(set(Transaction.objects.unmatched()), {self.loose_1, self.loose_2, self.april_line})

    # ---- lines left behind by earlier deletions ----

    def test_the_prune_command_lists_leftover_lines_and_deletes_them_only_when_told_to(self):
        from django.core.management import call_command
        from io import StringIO

        leftover = Transaction.objects.create(
            account=self.account, statement=None, amount=Decimal("-1.00"),
            transaction_date=date(2026, 3, 1), merchant="LEFT BEHIND",
        )
        self.paid_receipt_line.statement = None  # matched, so not a leftover
        self.paid_receipt_line.save()

        listing = StringIO()
        call_command("prune_orphan_transactions", stdout=listing)
        self.assertIn("LEFT BEHIND", listing.getvalue())
        self.assertNotIn("CHECKERS", listing.getvalue())
        self.assertTrue(Transaction.objects.filter(pk=leftover.pk).exists())

        call_command("prune_orphan_transactions", "--delete", stdout=StringIO())
        self.assertFalse(Transaction.objects.filter(pk=leftover.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.paid_receipt_line.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.loose_1.pk).exists())  # still on its statement


class LineItemRemovalTests(APITestCase):
    """Removing a single line item: a receipt item, or a line of a bank statement."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rmuser", password="password1", email="rmuser@gmail.com"
        )
        other = User.objects.create_user(
            username="rmother", password="password2", email="rmother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1111"
        )
        other_account = Account.objects.create(user=other, account_name="Other", account_number="2222")
        self.statement = BankStatement.objects.create(account=self.account, file_path=None)
        self.line = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-15.00"),
            transaction_date=date(2026, 3, 1), merchant="CHECKERS", status="Reconciled",
        )
        self.other_line = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-9.00"),
            transaction_date=date(2026, 3, 2), merchant="SPAR",
        )
        self.groceries = Tag.objects.get(name="Groceries", owner=None)
        # a receipt whose total is what its items add up to, matched to the line
        self.receipt = Receipt.objects.create(
            user=self.user, account=self.account, merchant_name="Checkers", total_amount=Decimal("15.00"),
            transaction=self.line,
        )
        self.milk = Item.objects.create(receipt=self.receipt, item_name="Milk", unit_price=10, quantity=1, item_total=10)
        self.bread = Item.objects.create(receipt=self.receipt, item_name="Bread", unit_price=5, quantity=1, item_total=5)
        self.milk.tags.add(self.groceries)
        other_receipt = Receipt.objects.create(user=other, merchant_name="Spar")
        self.other_item = Item.objects.create(receipt=other_receipt, item_name="Eggs", unit_price=5, quantity=1, item_total=5)
        self.other_line_of_theirs = Transaction.objects.create(
            account=other_account, amount=Decimal("-5.00"), transaction_date=date(2026, 3, 1), merchant="THEIRS",
        )
        self.client.force_authenticate(user=self.user)

    def remove(self, kind, line):
        return self.client.delete(reverse(f"{kind}-remove", kwargs={"pk": line.pk}))

    # ---- a receipt item ----

    def test_a_receipt_item_can_be_removed_and_the_others_stay(self):
        response = self.remove("item", self.bread)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Item.objects.filter(pk=self.bread.pk).exists())
        self.assertTrue(Item.objects.filter(pk=self.milk.pk).exists())
        self.assertTrue(Receipt.objects.filter(pk=self.receipt.pk).exists())

    def test_it_is_gone_from_the_line_item_list(self):
        self.remove("item", self.bread)

        ids = {l["id"] for l in self.client.get(reverse("line-item-list")).data}
        self.assertNotIn(self.bread.id, ids)
        self.assertIn(self.milk.id, ids)

    def test_removing_an_item_takes_it_out_of_a_receipt_total_which_is_made_of_its_items(self):
        self.remove("item", self.bread)

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("10.00"))

    def test_a_credit_item_removed_adds_back_to_the_total(self):
        self.bread.direction = "credit"
        self.bread.save()
        self.receipt.total_amount = Decimal("5.00")  # 10 - 5
        self.receipt.save()

        self.remove("item", self.bread)

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("10.00"))

    def test_removing_an_item_leaves_a_total_which_the_receipt_has_of_its_own(self):
        self.receipt.total_amount = Decimal("99.99")  # read from the receipt, say
        self.receipt.save()

        self.remove("item", self.bread)

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("99.99"))

    def test_removing_a_receipts_last_item_leaves_the_receipt_without_a_total(self):
        self.remove("item", self.bread)
        self.remove("item", self.milk)

        self.receipt.refresh_from_db()
        self.assertIsNone(self.receipt.total_amount)
        self.assertEqual(self.receipt.items.count(), 0)

    def test_removing_an_item_matched_to_a_line_frees_the_line(self):
        item_line = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-3.00"),
            transaction_date=date(2026, 3, 3), merchant="BAKERY", status="Reconciled",
        )
        self.bread.transaction = item_line
        self.bread.save()

        self.remove("item", self.bread)

        item_line.refresh_from_db()
        self.assertEqual(item_line.status, "Pending")

    def test_an_items_tags_go_with_it_but_the_tags_stay(self):
        self.remove("item", self.milk)

        self.assertTrue(Tag.objects.filter(pk=self.groceries.pk).exists())
        self.assertEqual(self.groceries.items.count(), 0)

    def test_another_users_item_cannot_be_removed(self):
        self.assertEqual(self.remove("item", self.other_item).status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Item.objects.filter(pk=self.other_item.pk).exists())

    def test_an_item_which_is_not_there_is_not_found(self):
        self.remove("item", self.bread)

        self.assertEqual(self.remove("item", self.bread).status_code, status.HTTP_404_NOT_FOUND)

    # ---- a statement line ----

    def test_a_statement_line_can_be_removed_and_its_statement_and_other_lines_stay(self):
        response = self.remove("transaction", self.other_line)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Transaction.objects.filter(pk=self.other_line.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.line.pk).exists())
        self.assertTrue(BankStatement.objects.filter(pk=self.statement.pk).exists())

    def test_it_is_gone_from_the_statement_and_the_line_item_list(self):
        self.remove("transaction", self.other_line)

        listed = {l["id"] for l in self.client.get(reverse("line-item-list")).data}
        self.assertNotIn(self.other_line.id, listed)
        on_statement = self.client.get(reverse("statement-detail", kwargs={"pk": self.statement.pk})).data["transactions"]
        self.assertEqual([t["id"] for t in on_statement], [self.line.id])

    def test_removing_a_line_a_receipt_was_matched_to_unmatches_it_but_keeps_the_receipt_and_its_items(self):
        response = self.remove("transaction", self.line)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.receipt.refresh_from_db()
        self.assertIsNone(self.receipt.transaction)
        self.assertEqual(self.receipt.items.count(), 2)
        self.assertEqual(self.receipt.total_amount, Decimal("15.00"))
        listed = self.client.get(reverse("document-list"), {"category": "receipt"}).data
        self.assertFalse(listed[0]["has_transaction"])  # waiting on the Review page again

    def test_removing_a_line_an_item_was_matched_to_unmatches_the_item(self):
        item_line = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-3.00"),
            transaction_date=date(2026, 3, 3), merchant="BAKERY",
        )
        self.bread.transaction = item_line
        self.bread.save()

        self.remove("transaction", item_line)

        self.bread.refresh_from_db()
        self.assertIsNone(self.bread.transaction)

    def test_another_users_statement_line_cannot_be_removed(self):
        self.assertEqual(self.remove("transaction", self.other_line_of_theirs).status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Transaction.objects.filter(pk=self.other_line_of_theirs.pk).exists())

    def test_removing_needs_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.remove("item", self.bread).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.remove("transaction", self.other_line).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Item.objects.filter(pk=self.bread.pk).exists())


class BudgetTests(APITestCase):
    """Monthly budgets on tags: each user has their own, one per tag."""

    def setUp(self):
        self.user = User.objects.create_user(username="budgetuser", password="password1", email="b@gmail.com")
        self.other = User.objects.create_user(username="budgetother", password="password2", email="o@gmail.com")
        self.groceries = Tag.objects.get(name="Groceries", owner=None)
        self.theirs = Tag.objects.create(name="Their own", owner=self.other)
        self.client.force_authenticate(user=self.user)

    def create(self, tag, limit="1500.00"):
        return self.client.post(reverse("budget-list"), {"tag": str(tag.id), "monthly_limit": limit}, format="json")

    def test_a_budget_can_be_set_on_a_tag_and_is_listed(self):
        response = self.create(self.groceries)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        listed = self.client.get(reverse("budget-list")).data
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["tag_name"], "Groceries")
        self.assertEqual(listed[0]["monthly_limit"], "1500.00")

    def test_a_tag_has_only_one_budget(self):
        self.create(self.groceries)

        response = self.create(self.groceries, "200.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Budget.objects.filter(user=self.user).count(), 1)

    def test_a_budget_must_be_more_than_zero(self):
        self.assertEqual(self.create(self.groceries, "0").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.create(self.groceries, "-5").status_code, status.HTTP_400_BAD_REQUEST)

    def test_another_users_tag_cannot_be_budgeted(self):
        self.assertEqual(self.create(self.theirs).status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_budget_can_be_changed_and_removed(self):
        budget_id = self.create(self.groceries).data["id"]
        url = reverse("budget-detail", kwargs={"pk": budget_id})

        self.assertEqual(self.client.patch(url, {"monthly_limit": "900.00"}, format="json").status_code, status.HTTP_200_OK)
        self.assertEqual(Budget.objects.get(pk=budget_id).monthly_limit, Decimal("900.00"))
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Budget.objects.filter(pk=budget_id).exists())

    def test_a_budget_can_cover_all_spending_with_no_tag(self):
        response = self.client.post(reverse("budget-list"), {"monthly_limit": "9000.00"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["tag"])
        self.assertEqual(response.data["tag_name"], "Overall spending")

    def test_there_is_only_one_overall_budget(self):
        self.client.post(reverse("budget-list"), {"monthly_limit": "9000.00"}, format="json")

        response = self.client.post(reverse("budget-list"), {"monthly_limit": "100.00"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_budget_can_be_for_a_number_of_months_from_a_month(self):
        response = self.client.post(
            reverse("budget-list"),
            {"tag": str(self.groceries.id), "monthly_limit": "1500.00", "months": 3, "start_month": "2026-04-17"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["months"], 3)
        self.assertEqual(response.data["start_month"], "2026-04-01")  # a month begins on its first day

    def test_a_budget_with_no_months_goes_on_for_good(self):
        response = self.create(self.groceries)

        self.assertIsNone(response.data["months"])

    def test_the_months_of_a_budget_must_be_at_least_one(self):
        response = self.client.post(
            reverse("budget-list"), {"tag": str(self.groceries.id), "monthly_limit": "10.00", "months": 0}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_changing_a_limit_leaves_its_tag_and_months_as_they_were(self):
        made = self.client.post(
            reverse("budget-list"), {"tag": str(self.groceries.id), "monthly_limit": "10.00", "months": 2}, format="json"
        ).data
        url = reverse("budget-detail", kwargs={"pk": made["id"]})

        changed = self.client.patch(url, {"monthly_limit": "20.00"}, format="json").data

        self.assertEqual((str(changed["tag"]), changed["months"]), (str(self.groceries.id), 2))

    def test_another_users_budgets_are_not_seen_or_changed(self):
        theirs = Budget.objects.create(user=self.other, tag=self.groceries, monthly_limit=Decimal("50.00"))

        self.assertEqual(self.client.get(reverse("budget-list")).data, [])
        url = reverse("budget-detail", kwargs={"pk": theirs.id})
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_budgets_need_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(reverse("budget-list")).status_code, status.HTTP_401_UNAUTHORIZED)


# What the exchange rate service says 1 USD is worth in ZAR, by working day
USD_ZAR = {
    date(2026, 3, 5): Decimal("16.50"),  # a Thursday
    date(2026, 3, 6): Decimal("16.00"),  # a Friday
    date(2026, 3, 9): Decimal("17.00"),  # the Monday after
}


def fake_rates(base, quote, start, end):
    """Stands in for the exchange rate service: ZAR -> USD from the USD -> ZAR table."""
    if (base, quote) == ("ZAR", "USD"):
        return {day: (Decimal(1) / rate).quantize(Decimal("0.00000001")) for day, rate in USD_ZAR.items() if start <= day <= end}
    if (base, quote) == ("USD", "ZAR"):
        return {day: rate for day, rate in USD_ZAR.items() if start <= day <= end}
    return {}


class CurrencyTests(APITestCase):
    """Figures are reported in the user's currency, converted at the rate of each line's own day."""

    def setUp(self):
        self.user = User.objects.create_user(username="fxuser", password="password1", email="fx@gmail.com")
        self.client.force_authenticate(user=self.user)
        self.account = Account.objects.create(user=self.user, account_name="Cheque", account_number="1111")
        self.statement = BankStatement.objects.create(account=self.account, display_name="March", doc_type="CSV")

    def line(self, day, amount, currency="ZAR"):
        return Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal(amount),
            transaction_date=day, merchant="SPAR", currency=currency,
        )

    def lines(self):
        return {line["id"]: line for line in self.client.get("/api/line-items/").data}

    def use(self, currency):
        return self.client.patch("/api/settings/", {"currency": currency}, format="json")

    def test_the_currency_defaults_to_rand_and_lists_what_can_be_chosen(self):
        data = self.client.get("/api/settings/").data

        self.assertEqual(data["currency"], "ZAR")
        self.assertIn({"code": "USD", "name": "United States Dollar"}, data["currencies"])

    def test_the_currency_can_be_changed(self):
        self.assertEqual(self.use("USD").status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.currency, "USD")

    def test_a_currency_there_are_no_rates_for_is_refused(self):
        self.assertEqual(self.use("XYZ").status_code, status.HTTP_400_BAD_REQUEST)

        self.user.refresh_from_db()
        self.assertEqual(self.user.currency, "ZAR")

    @mock.patch("core.currency._fetch", side_effect=AssertionError("no rate is needed"))
    def test_lines_already_in_the_users_currency_are_left_alone(self, fetch):
        line = self.line(date(2026, 3, 5), "-100.00")

        shown = self.lines()[line.id]

        self.assertEqual(shown["amount"], "-100.00")
        self.assertIsNone(shown["conversion"])
        fetch.assert_not_called()

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_line_is_converted_at_the_rate_of_its_own_day(self, fetch):
        thursday = self.line(date(2026, 3, 5), "-165.00", "USD")
        monday = self.line(date(2026, 3, 9), "-170.00", "USD")

        shown = self.lines()

        self.assertEqual(shown[thursday.id]["amount"], "-2722.50")  # 165 x 16.50
        self.assertEqual(shown[monday.id]["amount"], "-2890.00")  # 170 x 17.00
        self.assertEqual(shown[thursday.id]["currency"], "ZAR")

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_the_original_amount_and_the_change_of_currency_are_kept_on_the_line(self, fetch):
        line = self.line(date(2026, 3, 5), "-10.00", "USD")

        shown = self.lines()[line.id]

        self.assertEqual(shown["original_amount"], "-10.00")
        self.assertEqual(shown["original_currency"], "USD")
        self.assertEqual(shown["conversion"], "USD -> ZAR")
        self.assertEqual(Decimal(shown["exchange_rate"]), Decimal("16.50"))

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_the_label_follows_the_currency_chosen(self, fetch):
        line = self.line(date(2026, 3, 5), "-165.00", "ZAR")
        self.use("USD")

        shown = self.lines()[line.id]

        self.assertEqual(shown["conversion"], "ZAR -> USD")
        self.assertEqual(shown["currency"], "USD")
        self.assertEqual(shown["amount"], "-10.00")

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_weekend_uses_the_rate_of_the_working_day_before(self, fetch):
        saturday = self.line(date(2026, 3, 7), "-10.00", "USD")

        self.assertEqual(self.lines()[saturday.id]["amount"], "-160.00")  # Friday's 16.00

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_receipt_items_are_converted_in_the_currency_of_their_receipt(self, fetch):
        receipt = Receipt.objects.create(
            user=self.user, currency="USD", transaction_date=timezone.make_aware(datetime(2026, 3, 5)),
        )
        item = Item.objects.create(
            receipt=receipt, item_name="Coffee", unit_price=Decimal("2.00"), quantity=Decimal("5"), item_total=Decimal("10.00"),
        )

        shown = self.lines()[item.id]

        self.assertEqual(shown["amount"], "165.00")
        self.assertEqual(shown["unit_price"], "33.00")
        self.assertEqual(shown["conversion"], "USD -> ZAR")

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_rates_are_kept_so_that_the_service_is_asked_once(self, fetch):
        self.line(date(2026, 3, 5), "-10.00", "USD")

        self.lines()
        asked = fetch.call_count
        self.lines()

        self.assertGreater(asked, 0)
        self.assertEqual(fetch.call_count, asked)
        self.assertTrue(ExchangeRate.objects.filter(base="USD", quote="ZAR", date=date(2026, 3, 5)).exists())

    @mock.patch("core.currency._fetch", return_value={})
    def test_when_no_rate_can_be_had_the_line_is_not_passed_off_as_converted(self, fetch):
        line = self.line(date(2026, 3, 5), "-10.00", "USD")

        shown = self.lines()[line.id]

        self.assertEqual(shown["amount"], "-10.00")
        self.assertEqual(shown["currency"], "USD")
        self.assertTrue(shown["rate_unavailable"])

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_line_edit_answers_in_the_users_currency_too(self, fetch):
        line = self.line(date(2026, 3, 5), "-10.00", "USD")

        response = self.client.patch(
            f"/api/documents/transactions/{line.id}/details/", {"merchant": "Woolies"}, format="json"
        )

        self.assertEqual(response.data["amount"], "-165.00")
        self.assertEqual(response.data["conversion"], "USD -> ZAR")

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_an_accounts_funds_are_also_given_in_the_users_currency(self, fetch):
        self.account.currency = "USD"
        self.account.funds = Decimal("100.00")
        self.account.save()

        with mock.patch("core.currency.timezone.localdate", return_value=date(2026, 3, 9)):
            account = self.client.get("/api/accounts/").data[0]

        self.assertEqual(account["currency"], "USD")
        self.assertEqual(Decimal(account["funds"]), Decimal("100.00"))
        self.assertEqual(Decimal(account["funds_converted"]), Decimal("1700.00"))

    def test_a_new_account_takes_the_users_currency_unless_told_otherwise(self):
        self.use("USD")

        made = self.client.post(
            "/api/accounts/", {"account_name": "Dollars", "account_number": "2222", "card_type": "Cheque"}, format="json"
        )
        chosen = self.client.post(
            "/api/accounts/",
            {"account_name": "Rands", "account_number": "3333", "card_type": "Cheque", "currency": "ZAR"},
            format="json",
        )

        self.assertEqual(made.data["currency"], "USD")
        self.assertEqual(chosen.data["currency"], "ZAR")

    def test_a_statement_is_uploaded_in_the_currency_chosen_for_it(self):
        response = self.client.post(
            "/api/documents/upload/",
            {
                "file": SimpleUploadedFile("usd.csv", b"Date,Description,Amount\n", content_type="text/csv"),
                "category": "statement",
                "account": str(self.account.id),
                "bank": "fnb",
                "currency": "USD",
                "transactions": json.dumps(
                    [{"name": "Coffee", "merchant": "", "date": "2026-03-05", "direction": "debit", "amount": "4.00"}]
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        statement = BankStatement.objects.get(pk=response.data["id"])
        self.assertEqual((statement.currency, statement.bank), ("USD", "fnb"))
        self.assertEqual(Transaction.objects.get(statement=statement).currency, "USD")

    def test_a_statement_with_no_currency_chosen_takes_its_accounts(self):
        self.account.currency = "EUR"
        self.account.save()

        response = self.client.post(
            "/api/documents/upload/",
            {
                "file": SimpleUploadedFile("eur.csv", b"Date,Description,Amount\n", content_type="text/csv"),
                "category": "statement",
                "account": str(self.account.id),
                "transactions": json.dumps(
                    [{"name": "Coffee", "merchant": "", "date": "2026-03-05", "direction": "debit", "amount": "4.00"}]
                ),
            },
            format="multipart",
        )

        self.assertEqual(Transaction.objects.get(statement_id=response.data["id"]).currency, "EUR")

    def test_a_receipt_is_uploaded_in_the_currency_chosen_for_it(self):
        response = self.client.post(
            "/api/documents/upload/",
            {
                "file": SimpleUploadedFile("r.csv", b"x", content_type="text/csv"),
                "category": "receipt",
                "currency": "GBP",
                "items": json.dumps([{"name": "Tea", "quantity": "1", "unit_price": "3.00", "total": "3.00"}]),
            },
            format="multipart",
        )

        self.assertEqual(Receipt.objects.get(pk=response.data["id"]).currency, "GBP")

    def test_a_currency_there_are_no_rates_for_is_refused_on_upload(self):
        response = self.client.post(
            "/api/documents/upload/",
            {"file": SimpleUploadedFile("r.csv", b"x", content_type="text/csv"), "category": "receipt", "currency": "XYZ", "items": "[]"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_statements_own_page_lists_its_lines_in_the_users_currency(self, fetch):
        line = self.line(date(2026, 3, 5), "-10.00", "USD")

        shown = self.client.get(f"/api/documents/statements/{self.statement.id}/").data["transactions"][0]

        self.assertEqual(shown["id"], line.id)
        self.assertEqual(shown["amount"], "-165.00")
        self.assertEqual(shown["original_amount"], "-10.00")
        self.assertEqual(shown["conversion"], "USD -> ZAR")

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_receipts_items_and_total_are_listed_in_the_users_currency(self, fetch):
        receipt = Receipt.objects.create(
            user=self.user, currency="USD", total_amount=Decimal("10.00"),
            transaction_date=timezone.make_aware(datetime(2026, 3, 5)),
        )
        Item.objects.create(
            receipt=receipt, item_name="Coffee", unit_price=Decimal("2.00"), quantity=Decimal("5"), item_total=Decimal("10.00"),
        )

        meta = next(d for d in self.client.get("/api/documents/", {"category": "receipt"}).data if d["id"] == receipt.id)["meta"]

        self.assertEqual(meta["currency"], "USD")  # what it was recorded in
        self.assertEqual(meta["amount"], "165.00")
        self.assertEqual(meta["amount_conversion"], "USD -> ZAR")
        self.assertEqual(meta["items"][0]["item_total"], "165.00")
        self.assertEqual(meta["items"][0]["unit_price"], "33.00")
        self.assertEqual(meta["items"][0]["original_amount"], "10.00")
        self.assertEqual(meta["items"][0]["conversion"], "USD -> ZAR")

    @mock.patch("core.currency._fetch", side_effect=AssertionError("no rate is needed"))
    def test_a_receipt_in_the_users_currency_is_listed_as_it_is(self, fetch):
        receipt = Receipt.objects.create(user=self.user, total_amount=Decimal("12.50"), transaction_date=timezone.make_aware(datetime(2026, 3, 5)))
        Item.objects.create(receipt=receipt, item_name="Tea", unit_price=Decimal("12.50"), item_total=Decimal("12.50"))

        meta = next(d for d in self.client.get("/api/documents/", {"category": "receipt"}).data if d["id"] == receipt.id)["meta"]

        self.assertEqual(meta["amount"], "12.50")
        self.assertIsNone(meta["amount_conversion"])
        self.assertIsNone(meta["items"][0]["conversion"])

    def test_the_document_list_says_which_statements_a_receipt_is_matched_to(self):
        line = self.line(date(2026, 3, 5), "-10.00")
        receipt = Receipt.objects.create(
            user=self.user, transaction=line, transaction_date=timezone.make_aware(datetime(2026, 3, 5)),
        )
        loose = Receipt.objects.create(user=self.user, transaction_date=timezone.make_aware(datetime(2026, 3, 6)))

        documents = {d["id"]: d for d in self.client.get("/api/documents/", {"category": "receipt"}).data}

        self.assertEqual(documents[receipt.id]["statement_ids"], [str(self.statement.id)])
        self.assertEqual(documents[loose.id]["statement_ids"], [])


class LineItemBulkDeleteTests(APITestCase):
    """Removing several line items at once, and what that does to the documents they are in."""

    url = "/api/line-items/delete/"

    def setUp(self):
        self.user = User.objects.create_user(username="bulkuser", password="password1", email="bulk@gmail.com")
        self.other = User.objects.create_user(username="bulkother", password="password2", email="bulkother@gmail.com")
        self.client.force_authenticate(user=self.user)
        self.account = Account.objects.create(user=self.user, account_name="Cheque", account_number="1111")
        self.statement = BankStatement.objects.create(account=self.account, display_name="March", doc_type="CSV")
        self.a = Transaction.objects.create(account=self.account, statement=self.statement, amount=Decimal("-10.00"), transaction_date=date(2026, 3, 1), merchant="A")
        self.b = Transaction.objects.create(account=self.account, statement=self.statement, amount=Decimal("-20.00"), transaction_date=date(2026, 3, 2), merchant="B")
        self.receipt = Receipt.objects.create(
            user=self.user, display_name="Shop", total_amount=Decimal("30.00"),
            transaction_date=timezone.make_aware(datetime(2026, 3, 3)),
        )
        self.milk = Item.objects.create(receipt=self.receipt, item_name="Milk", unit_price=Decimal("10.00"), item_total=Decimal("10.00"))
        self.bread = Item.objects.create(receipt=self.receipt, item_name="Bread", unit_price=Decimal("20.00"), item_total=Decimal("20.00"))

    def remove(self, *lines):
        return self.client.post(self.url, {"lines": [{"kind": k, "id": str(i)} for k, i in lines]}, format="json")

    def test_several_line_items_are_removed_together(self):
        response = self.remove(("statement_line", self.a.id), ("receipt_item", self.milk.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted"], 2)
        self.assertFalse(Transaction.objects.filter(pk=self.a.id).exists())
        self.assertFalse(Item.objects.filter(pk=self.milk.id).exists())
        self.assertTrue(Transaction.objects.filter(pk=self.b.id).exists())

    def test_a_receipt_total_follows_the_items_removed(self):
        self.remove(("receipt_item", self.milk.id))

        self.receipt.refresh_from_db()
        self.assertEqual(self.receipt.total_amount, Decimal("20.00"))

    def test_a_statement_left_with_no_lines_is_removed_too(self):
        response = self.remove(("statement_line", self.a.id), ("statement_line", self.b.id))

        self.assertEqual(response.data["removed_statements"], [str(self.statement.id)])
        self.assertFalse(BankStatement.objects.filter(pk=self.statement.id).exists())

    def test_a_statement_which_keeps_a_line_is_kept(self):
        response = self.remove(("statement_line", self.a.id))

        self.assertEqual(response.data["removed_statements"], [])
        self.assertTrue(BankStatement.objects.filter(pk=self.statement.id).exists())

    def test_a_receipt_left_with_no_items_is_removed_too(self):
        response = self.remove(("receipt_item", self.milk.id), ("receipt_item", self.bread.id))

        self.assertEqual(response.data["removed_receipts"], [str(self.receipt.id)])
        self.assertFalse(Receipt.objects.filter(pk=self.receipt.id).exists())

    def test_a_receipt_matched_to_a_removed_line_is_unmatched(self):
        self.milk.transaction = self.a
        self.milk.save()
        self.a.status = "Reconciled"
        self.a.save()

        self.remove(("statement_line", self.a.id))

        self.milk.refresh_from_db()
        self.assertIsNone(self.milk.transaction)
        self.assertTrue(Receipt.objects.filter(pk=self.receipt.id).exists())

    def test_the_stored_file_of_a_removed_document_is_deleted(self):
        self.statement.file_path = "statements/march.csv"
        self.statement.save()

        with mock.patch("core.views.delete_stored_file") as delete_file:
            self.remove(("statement_line", self.a.id), ("statement_line", self.b.id))

        delete_file.assert_called_once_with("statements/march.csv")

    def test_nothing_is_removed_if_one_of_them_is_not_the_users(self):
        theirs = Account.objects.create(user=self.other, account_name="Theirs", account_number="9999")
        foreign = Transaction.objects.create(account=theirs, amount=Decimal("-5.00"), transaction_date=date(2026, 3, 1))

        response = self.remove(("statement_line", self.a.id), ("statement_line", foreign.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Transaction.objects.filter(pk=self.a.id).exists())
        self.assertTrue(Transaction.objects.filter(pk=foreign.id).exists())

    def test_a_request_with_no_line_items_or_a_bad_kind_is_refused(self):
        self.assertEqual(self.client.post(self.url, {"lines": []}, format="json").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.remove(("nonsense", self.a.id)).status_code, status.HTTP_400_BAD_REQUEST)

    def test_it_needs_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.remove(("statement_line", self.a.id)).status_code, status.HTTP_401_UNAUTHORIZED)


class AccountBalanceTests(APITestCase):
    """An account's balance follows the lines dated after it was created; earlier history works back from it."""

    def setUp(self):
        self.user = User.objects.create_user(username="baluser", password="password1", email="bal@gmail.com")
        self.client.force_authenticate(user=self.user)
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", account_number="1111", funds=Decimal("1000.00"),
            created_at=timezone.make_aware(datetime(2026, 3, 10, 9, 0)),
        )
        self.statement = BankStatement.objects.create(account=self.account, display_name="March", doc_type="CSV")

    def line(self, day, amount, account=None, currency="ZAR"):
        return Transaction.objects.create(
            account=account or self.account, statement=self.statement, amount=Decimal(amount),
            transaction_date=day, merchant="X", currency=currency,
        )

    def listed(self):
        return {a["id"]: a for a in self.client.get("/api/accounts/").data}[self.account.id]

    def test_with_nothing_uploaded_the_balance_is_the_opening_balance(self):
        self.assertEqual(self.listed()["balance"], "1000.00")

    def test_lines_after_the_account_was_created_move_its_balance(self):
        self.line(date(2026, 3, 12), "-250.00")
        self.line(date(2026, 3, 20), "400.00")

        self.assertEqual(self.listed()["balance"], "1150.00")

    def test_lines_on_or_before_the_day_it_was_created_are_already_in_the_opening_balance(self):
        self.line(date(2026, 3, 1), "-500.00")
        self.line(date(2026, 3, 10), "-50.00")

        self.assertEqual(self.listed()["balance"], "1000.00")

    def test_the_opening_balance_itself_is_left_as_it_was(self):
        self.line(date(2026, 3, 12), "-250.00")
        self.listed()

        self.account.refresh_from_db()
        self.assertEqual(self.account.funds, Decimal("1000.00"))

    def test_an_unmatched_receipt_paid_from_the_account_counts(self):
        receipt = Receipt.objects.create(
            user=self.user, account=self.account, transaction_date=timezone.make_aware(datetime(2026, 3, 15)),
        )
        Item.objects.create(receipt=receipt, item_name="Shoes", unit_price=Decimal("300"), item_total=Decimal("300.00"))

        self.assertEqual(self.listed()["balance"], "700.00")

    def test_a_receipt_matched_to_a_statement_line_counts_once_through_the_line(self):
        spend = self.line(date(2026, 3, 15), "-300.00")
        receipt = Receipt.objects.create(
            user=self.user, account=self.account, transaction=spend, transaction_date=timezone.make_aware(datetime(2026, 3, 15)),
        )
        Item.objects.create(receipt=receipt, item_name="Shoes", unit_price=Decimal("300"), item_total=Decimal("300.00"))

        self.assertEqual(self.listed()["balance"], "700.00")

    def test_another_accounts_lines_do_not_move_it(self):
        other = Account.objects.create(user=self.user, account_name="Other", account_number="2222",
                                       created_at=timezone.make_aware(datetime(2026, 3, 1)))
        self.line(date(2026, 3, 15), "-300.00", account=other)

        self.assertEqual(self.listed()["balance"], "1000.00")

    def test_history_before_creation_works_back_from_the_opening_balance(self):
        self.line(date(2026, 3, 5), "-100.00")   # before: the balance was higher then
        self.line(date(2026, 3, 8), "200.00")
        self.line(date(2026, 3, 12), "-50.00")   # after

        points = {p["date"]: p["balance"] for p in self.history()["points"]}

        self.assertEqual(points["2026-03-10"], "1000.00")  # the opening balance, on the day it was created
        self.assertEqual(points["2026-03-08"], "1000.00")  # nothing moved between the 8th and the 10th
        self.assertEqual(points["2026-03-05"], "800.00")   # before the 200 came in
        self.assertEqual(points["2026-03-12"], "950.00")

    def history(self):
        return next(a for a in self.client.get("/api/accounts/history/").data["accounts"] if a["id"] == self.account.id)

    def test_a_savings_account_which_goes_below_zero_is_flagged(self):
        self.account.card_type = "Savings"
        self.account.save()
        self.line(date(2026, 3, 12), "-1200.00")
        self.line(date(2026, 3, 20), "500.00")

        listed = self.listed()

        self.assertEqual(listed["below_zero"], {"date": "2026-03-12", "balance": "-200.00"})
        self.assertIn("savings account", listed["warning"])

    def test_a_cheque_account_may_go_below_zero(self):
        self.line(date(2026, 3, 12), "-1200.00")

        self.assertIsNone(self.listed()["warning"])

    def test_a_savings_account_below_zero_only_before_it_was_created_is_not_flagged(self):
        self.account.card_type = "Savings"
        self.account.save()
        self.line(date(2026, 3, 9), "5000.00")  # so it was -4000 before; history is not checked

        self.assertIsNone(self.listed()["warning"])

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_line_in_another_currency_moves_the_balance_at_its_days_rate(self, fetch):
        self.line(date(2026, 3, 13), "-10.00", currency="USD")  # the latest rate before it: Monday the 9th's

        self.assertEqual(self.listed()["balance"], "830.00")  # 10 x 17.00

    def test_the_account_detail_has_its_balance_too(self):
        self.line(date(2026, 3, 12), "-250.00")

        detail = self.client.get(f"/api/accounts/{self.account.id}/").data

        self.assertEqual(detail["balance"], "750.00")
        self.assertEqual(detail["opened_on"], "2026-03-10")


class SessionTokenTests(APITestCase):
    """A session's access token lasts 30 minutes and can be renewed with the refresh token."""

    def setUp(self):
        User.objects.create_user(username="sessionuser", password="password1", email="s@gmail.com")

    def login(self):
        return self.client.post("/api/token/", {"username": "sessionuser", "password": "password1"}, format="json").data

    def test_the_access_token_lasts_thirty_minutes(self):
        from rest_framework_simplejwt.tokens import AccessToken

        token = AccessToken(self.login()["access"])

        self.assertEqual(token["exp"] - token["iat"], 30 * 60)

    def test_the_refresh_endpoint_gives_a_new_access_token_and_a_rotated_refresh_token(self):
        tokens = self.login()

        response = self.client.post("/api/token/refresh/", {"refresh": tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertNotEqual(response.data["refresh"], tokens["refresh"])

    def test_a_bad_refresh_token_is_refused(self):
        response = self.client.post("/api/token/refresh/", {"refresh": "not-a-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, "test_document_storage"))
class DocumentFileTests(APITestCase):
    """A document's file is only handed to the user it belongs to."""

    PDF_BYTES = b"%PDF-1.4 statement"
    CSV_BYTES = b"name,total\nMilk,28.99\n"

    def setUp(self):
        self.user = User.objects.create_user(
            username="fileuser", password="password1", email="file@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="fileother", password="password2", email="fileother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", account_number="1111"
        )
        self.statement = BankStatement.objects.create(
            account=self.account,
            file_path=self.store("statements/2026/10/abc_october.pdf", self.PDF_BYTES),
            display_name="October",
            doc_type="PDF",
        )
        self.receipt = Receipt.objects.create(
            user=self.user,
            receipt_path=self.store("receipts/2026/10/abc_slip.csv", self.CSV_BYTES),
        )
        self.client.force_authenticate(user=self.user)

    @classmethod
    def tearDownClass(cls):
        test_storage_path = os.path.join(settings.BASE_DIR, "test_document_storage")
        if os.path.exists(test_storage_path):
            shutil.rmtree(test_storage_path)
        super().tearDownClass()

    def store(self, relative_path, content):
        path = os.path.join(settings.MEDIA_ROOT, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as destination:
            destination.write(content)
        return relative_path

    def file_url(self, document, category=None):
        url = reverse("document-file", kwargs={"pk": document.pk})
        return f"{url}?category={category}" if category else url

    def test_owner_is_sent_the_statement_file(self):
        response = self.client.get(self.file_url(self.statement, "statement"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(response["Content-Disposition"].startswith("inline"))
        self.assertEqual(b"".join(response.streaming_content), self.PDF_BYTES)

    def test_owner_is_sent_the_receipt_file(self):
        response = self.client.get(self.file_url(self.receipt, "receipt"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Plain text, so the browser shows a CSV instead of downloading it
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(b"".join(response.streaming_content), self.CSV_BYTES)

    def test_file_stored_under_an_absolute_path_is_sent(self):
        self.statement.file_path = os.path.join(
            settings.MEDIA_ROOT, self.statement.file_path
        )
        self.statement.save()
        response = self.client.get(self.file_url(self.statement, "statement"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(response.streaming_content), self.PDF_BYTES)

    def test_another_users_files_are_not_found(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.file_url(self.statement, "statement"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.get(self.file_url(self.receipt, "receipt"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_login_is_required(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.file_url(self.statement, "statement"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_category_is_required(self):
        response = self.client.get(self.file_url(self.statement))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.get(self.file_url(self.statement, "other"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_file_missing_from_storage_is_not_found(self):
        os.remove(os.path.join(settings.MEDIA_ROOT, self.statement.file_path))
        response = self.client.get(self.file_url(self.statement, "statement"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_path_outside_the_storage_folder_is_not_found(self):
        self.statement.file_path = "/etc/hostname.pdf"
        self.statement.save()
        response = self.client.get(self.file_url(self.statement, "statement"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_document_without_a_file_is_not_found(self):
        manual = Receipt.objects.create(user=self.user, entry_type="receipt")
        response = self.client.get(self.file_url(manual, "receipt"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_file_of_an_unexpected_type_is_not_served(self):
        self.receipt.receipt_path = self.store(
            "receipts/2026/10/abc_page.html", b"<script>alert(1)</script>"
        )
        self.receipt.save()
        response = self.client.get(self.file_url(self.receipt, "receipt"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TokenRefreshTests(APITestCase):
    """A session is carried on by swapping a refresh token for new tokens."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="refreshuser", password="password1", email="refresh@gmail.com"
        )
        tokens = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "refreshuser", "password": "password1"},
            format="json",
        )
        self.refresh = tokens.data["refresh"]

    def tearDown(self):
        cache.clear()

    def test_refresh_is_served_where_the_website_asks_for_it(self):
        self.assertEqual(reverse("token_refresh"), "/api/token/refresh/")

    def test_refresh_returns_a_new_access_and_refresh_token(self):
        response = self.client.post(
            reverse("token_refresh"), {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotEqual(response.data["refresh"], self.refresh)

    def test_a_refresh_token_cannot_be_used_twice(self):
        self.client.post(reverse("token_refresh"), {"refresh": self.refresh}, format="json")
        response = self.client.post(
            reverse("token_refresh"), {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RateLimitTests(APITestCase):
    """Signing in, registering and uploading are limited to slow down abuse."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="limituser", password="password1", email="limit@gmail.com"
        )

    def tearDown(self):
        cache.clear()

    def post_until_limited(self, url, data, attempts=12, **extra):
        response = None
        for _ in range(attempts):
            response = self.client.post(url, data, **extra)
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break
        return response

    def test_repeated_sign_in_attempts_are_limited(self):
        response = self.post_until_limited(
            reverse("token_obtain_pair"),
            {"username": "limituser", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_sign_in_limit_holds_when_a_login_token_is_sent(self):
        self.client.force_authenticate(user=self.user)
        response = self.post_until_limited(
            reverse("token_obtain_pair"),
            {"username": "limituser", "password": "wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_repeated_registrations_are_limited(self):
        response = self.post_until_limited("/api/register/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_one_client_being_limited_does_not_limit_another(self):
        self.post_until_limited(
            reverse("token_obtain_pair"),
            {"username": "limituser", "password": "wrong"},
            format="json",
        )
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "limituser", "password": "password1"},
            format="json",
            REMOTE_ADDR="10.0.0.2",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_repeated_parsing_is_limited_per_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.post_until_limited(
            reverse("document-parse"), {}, attempts=25, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        other = User.objects.create_user(
            username="limitother", password="password2", email="limitother@gmail.com"
        )
        self.client.force_authenticate(user=other)
        response = self.client.post(reverse("document-parse"), {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_package_sign_in_endpoint_has_a_limit_configured(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "limituser", "password": "password1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, "test_document_storage"))
class StatementUploadAccessTests(APITestCase):
    """A statement can only be uploaded by a signed-in user, to their own account."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="accessuser", password="password1", email="access@gmail.com"
        )
        self.other_user = User.objects.create_user(
            username="accessother", password="password2", email="accessother@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", account_number="1111"
        )

    def upload(self):
        return self.client.post(
            "/api/upload/",
            {
                "file": SimpleUploadedFile(
                    "statement.csv", STATEMENT_CSV, content_type="text/csv"
                ),
                "account": self.account.id,
            },
            format="multipart",
        )

    def test_login_is_required(self):
        self.assertEqual(self.upload().status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(BankStatement.objects.exists())

    def test_statement_cannot_be_uploaded_to_another_users_account(self):
        self.client.force_authenticate(user=self.other_user)
        self.assertEqual(self.upload().status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(BankStatement.objects.exists())


class FailStaleProcessingTests(APITestCase):
    """Documents left unparsed by a server restart are marked as failed."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="staleuser", password="password1", email="stale@gmail.com"
        )
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", account_number="1111"
        )

    def run_command(self):
        from django.core.management import call_command
        from io import StringIO

        output = StringIO()
        call_command("fail_stale_processing", stdout=output)
        return output.getvalue()

    def test_waiting_and_part_parsed_documents_are_marked_failed(self):
        statement = BankStatement.objects.create(
            account=self.account, file_hash="a", processing_status="processing"
        )
        receipt = Receipt.objects.create(user=self.user, processing_status="pending")

        self.assertIn("2 interrupted documents", self.run_command())

        statement.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(statement.processing_status, "failed")
        self.assertEqual(receipt.processing_status, "failed")
        self.assertIn("upload the document again", statement.parser_error)
        self.assertIn("upload the document again", receipt.parser_error)

    def test_finished_documents_are_left_alone(self):
        done = BankStatement.objects.create(
            account=self.account, file_hash="b", processing_status="completed"
        )
        failed = Receipt.objects.create(
            user=self.user, processing_status="failed", parser_error="The receipt could not be parsed."
        )

        self.assertIn("no interrupted documents", self.run_command())

        done.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual(done.processing_status, "completed")
        self.assertIsNone(done.parser_error)
        self.assertEqual(failed.parser_error, "The receipt could not be parsed.")


class ParserTests(APITestCase):
    pass


class TransactionTemplateTagMigrationTests(TransactionTestCase):
    migrate_from = ("core", "0029_transactiontemplate_tag")
    migrate_to = ("core", "0031_sanitize_transactiontemplate_tags")
    # The migrations fork at 0028: the currency and budget changes run alongside
    # these, so the database (and the models the test uses) must have them too
    alongside = ("core", "0030_currency_bank_budget_periods")

    def test_migration_preserves_shared_and_owned_tags_but_drops_foreign_tags(self):
        # Constraint checks deferred by earlier tests in the same transaction
        # would stop Postgres altering the tables the migrations change
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from, self.alongside])
        old_apps = executor.loader.project_state([self.migrate_from, self.alongside]).apps

        User = old_apps.get_model("core", "User")
        Tag = old_apps.get_model("core", "Tag")
        TransactionTemplate = old_apps.get_model("core", "TransactionTemplate")

        user = User.objects.create(
            username="migration-owner", email="migration-owner@example.com", password="!"
        )
        other_user = User.objects.create(
            username="migration-other", email="migration-other@example.com", password="!"
        )
        shared_tag = Tag.objects.get(name="Groceries", owner=None)
        own_tag = Tag.objects.create(name="Migration own", owner=user)
        foreign_tag = Tag.objects.create(name="Migration foreign", owner=other_user)

        shared_template = TransactionTemplate.objects.create(
            user=user, search_string="SHARED", merchant_name="Shared", tag=shared_tag
        )
        own_template = TransactionTemplate.objects.create(
            user=user, search_string="OWN", merchant_name="Own", tag=own_tag
        )
        foreign_template = TransactionTemplate.objects.create(
            user=user, search_string="FOREIGN", merchant_name="Foreign", tag=foreign_tag
        )
        template_ids = (shared_template.pk, own_template.pk, foreign_template.pk)

        try:
            executor = MigrationExecutor(connection)
            migrate_through = ("core", "0030_remove_transactiontemplate_tag_and_more")
            executor.migrate([migrate_through, self.alongside])
            intermediate_apps = executor.loader.project_state([migrate_through, self.alongside]).apps
            IntermediateTemplate = intermediate_apps.get_model(
                "core", "TransactionTemplate"
            )
            IntermediateTemplate.objects.get(pk=template_ids[2]).tags.add(foreign_tag.pk)

            executor = MigrationExecutor(connection)
            executor.migrate([self.migrate_to, self.alongside])
            new_apps = executor.loader.project_state([self.migrate_to, self.alongside]).apps
            MigratedTemplate = new_apps.get_model("core", "TransactionTemplate")

            shared_tags = set(
                MigratedTemplate.objects.get(pk=template_ids[0]).tags.values_list("pk", flat=True)
            )
            own_tags = set(
                MigratedTemplate.objects.get(pk=template_ids[1]).tags.values_list("pk", flat=True)
            )
            foreign_tags = set(
                MigratedTemplate.objects.get(pk=template_ids[2]).tags.values_list("pk", flat=True)
            )

            self.assertEqual(shared_tags, {shared_tag.pk})
            self.assertEqual(own_tags, {own_tag.pk})
            self.assertEqual(foreign_tags, set())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class SubscriptionTests(APITestCase):
    """
    Marking line items as subscriptions with the hidden Subscription tag, and the
    subscriptions they add up to.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="subsuser", password="password1", email="subs@gmail.com")
        self.other = User.objects.create_user(username="subsother", password="password2", email="subso@gmail.com")
        self.account = Account.objects.create(
            user=self.user, account_name="Cheque", card_type="Cheque", account_number="1234"
        )
        self.statement = BankStatement.objects.create(account=self.account, file_path="s/oct.csv")
        self.netflix_sep = self.line("NETFLIX.COM 8473", "-199.00", date(2026, 9, 15), merchant="Netflix")
        self.netflix_oct = self.line("NETFLIX.COM 9921", "-229.00", date(2026, 10, 15), merchant="Netflix")
        self.spotify = self.line("SPOTIFY P1234", "-59.99", date(2026, 10, 31))
        self.groceries = Tag.objects.get(name="Groceries", owner=None)
        self.mark = Tag.objects.subscription()
        self.client.force_authenticate(user=self.user)

    def line(self, text, amount, day, merchant=None):
        return Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal(amount),
            transaction_date=day, description=text if merchant else None, merchant=merchant or text,
        )

    def mark_line(self, line):
        return self.client.put(reverse("transaction-subscription", kwargs={"pk": line.pk}))

    def subscriptions(self):
        return self.client.get(reverse("subscription-list")).data

    # ---- the hidden tag ----

    def test_the_subscription_tag_exists_and_is_hidden(self):
        self.assertTrue(self.mark.is_hidden)
        self.assertTrue(self.mark.is_predefined)

    def test_a_missing_subscription_tag_is_made_again(self):
        Tag.objects.filter(pk=self.mark.pk).delete()

        response = self.mark_line(self.spotify)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_subscription"])
        self.assertTrue(Tag.objects.subscription().is_hidden)

    def test_the_subscription_tag_is_not_listed_or_offered(self):
        names = [tag["name"] for tag in self.client.get("/api/tags/").data]

        self.assertNotIn(Tag.SUBSCRIPTION, names)
        self.assertNotIn(self.mark, Tag.objects.available_to(self.user))

    def test_the_subscription_tag_cannot_be_assigned_edited_or_deleted_as_a_tag(self):
        url = reverse("transaction-tags", kwargs={"pk": self.spotify.pk})
        assigned = self.client.put(url, {"tags": [str(self.mark.id)]}, format="json")
        tag_url = reverse("tag-detail", kwargs={"pk": self.mark.pk})

        self.assertEqual(assigned.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.patch(tag_url, {"name": "Mine"}, format="json").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(tag_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Tag.objects.filter(pk=self.mark.pk, name=Tag.SUBSCRIPTION).exists())

    def test_a_user_may_still_have_a_visible_tag_of_their_own_called_subscription(self):
        response = self.client.post("/api/tags/", {"name": "Subscription"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ---- marking ----

    def test_a_statement_line_can_be_marked_and_unmarked(self):
        marked = self.mark_line(self.spotify)

        self.assertEqual(marked.status_code, status.HTTP_200_OK)
        self.assertTrue(marked.data["is_subscription"])
        self.assertEqual(marked.data["tags"], [])  # the mark is not one of the tags shown
        self.assertIn(self.mark, self.spotify.tags.all())

        unmarked = self.client.delete(reverse("transaction-subscription", kwargs={"pk": self.spotify.pk}))

        self.assertFalse(unmarked.data["is_subscription"])
        self.assertNotIn(self.mark, self.spotify.tags.all())

    def test_marking_twice_is_harmless(self):
        self.mark_line(self.spotify)
        self.mark_line(self.spotify)

        self.assertEqual(self.spotify.tags.filter(pk=self.mark.pk).count(), 1)

    def test_a_receipt_item_can_be_marked(self):
        receipt = Receipt.objects.create(user=self.user, merchant_name="Apple")
        item = Item.objects.create(receipt=receipt, item_name="iCloud 50GB", unit_price=19, quantity=1, item_total=19)

        response = self.client.put(reverse("item-subscription", kwargs={"pk": item.pk}))

        self.assertTrue(response.data["is_subscription"])
        self.assertEqual(self.subscriptions()["subscriptions"][0]["name"], "Apple")

    def test_line_items_say_whether_they_are_subscriptions(self):
        self.mark_line(self.spotify)

        lines = {line["id"]: line for line in self.client.get(reverse("line-item-list")).data}

        self.assertTrue(lines[self.spotify.id]["is_subscription"])
        self.assertFalse(lines[self.netflix_oct.id]["is_subscription"])
        self.assertEqual(lines[self.spotify.id]["tags"], [])

    def test_changing_a_lines_tags_keeps_its_subscription_mark(self):
        self.mark_line(self.spotify)
        url = reverse("transaction-tags", kwargs={"pk": self.spotify.pk})

        self.client.put(url, {"tags": [str(self.groceries.id)]}, format="json")
        response = self.client.put(url, {"tags": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.mark, self.spotify.tags.all())

    def test_another_users_lines_cannot_be_marked(self):
        self.client.force_authenticate(user=self.other)

        self.assertEqual(self.mark_line(self.spotify).status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn(self.mark, self.spotify.tags.all())

    # ---- the subscriptions ----

    def test_each_months_charge_is_the_one_subscription_at_its_latest_price(self):
        for line in [self.netflix_sep, self.netflix_oct, self.spotify]:
            self.mark_line(line)

        data = self.subscriptions()

        netflix, spotify = data["subscriptions"]  # soonest next charge first
        self.assertEqual(
            (netflix["name"], netflix["amount"], netflix["last_charged"], netflix["next_expected"], netflix["charges"]),
            ("Netflix", "229.00", "2026-10-15", "2026-11-15", 2),
        )
        self.assertEqual(spotify["name"], "SPOTIFY P1234")
        self.assertEqual(spotify["next_expected"], "2026-11-30")  # 31 Oct -> 30 Nov
        self.assertEqual(netflix["account"]["account_number"], "1234")
        self.assertEqual(data["monthly_total"], "288.99")

    def test_the_name_the_user_gave_a_line_groups_it(self):
        self.spotify.display_name = "Netflix"
        self.spotify.save()
        for line in [self.netflix_oct, self.spotify]:
            self.mark_line(line)

        self.assertEqual(len(self.subscriptions()["subscriptions"]), 1)

    def test_no_subscriptions(self):
        self.assertEqual(self.subscriptions(), {"subscriptions": [], "monthly_total": "0.00", "currency": "ZAR"})

    @mock.patch("core.currency._fetch", side_effect=fake_rates)
    def test_a_charge_in_another_currency_is_counted_in_the_users(self, fetch):
        usd = Transaction.objects.create(
            account=self.account, statement=self.statement, amount=Decimal("-10.00"), currency="USD",
            transaction_date=date(2026, 3, 5), merchant="ChatGPT Plus",
        )
        self.mark_line(usd)
        self.mark_line(self.spotify)

        data = self.subscriptions()
        chatgpt = next(s for s in data["subscriptions"] if s["name"] == "ChatGPT Plus")

        self.assertEqual((chatgpt["amount"], chatgpt["currency"]), ("165.00", "ZAR"))  # 10 x 16.50
        self.assertEqual(data["monthly_total"], "224.99")  # 165.00 + 59.99

    def test_another_users_subscriptions_are_not_seen(self):
        self.mark_line(self.spotify)
        self.client.force_authenticate(user=self.other)

        self.assertEqual(self.subscriptions()["subscriptions"], [])

    def test_subscriptions_need_authentication(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(reverse("subscription-list")).status_code, status.HTTP_401_UNAUTHORIZED)
