import calendar
import os
import logging
import hashlib
import shutil
import tempfile
import threading

import uuid
from datetime import datetime, time
from decimal import Decimal

from django.db.models import Count, Prefetch
from django.db.models.deletion import ProtectedError
from django.db import DatabaseError, connection
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from rest_framework.response import Response
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError as DRFValidationError, ValidationError as APIValidationError

from django.db import DatabaseError, IntegrityError, connection
from django.db import transaction as db_transaction
from django.http import Http404, FileResponse
from django.core.files.storage import FileSystemStorage, default_storage
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, SuspiciousFileOperation
from django.core.validators import validate_email
from django.shortcuts import render, get_object_or_404

from rest_framework import generics

from .models import Transaction, BankStatement, Account, Receipt, Item, TransactionTemplate, Tag, Budget
from .currency import CURRENCIES, RateBook, conversion_label, is_supported, spot_rate
from .balances import balance_summary, history_payload
from .serializers import (
    BudgetSerializer,
    TransactionSerializer,
    BankstatementSerializer,
    UnifiedDocumentUploadSerializer,
    DocumentRenameSerializer,
    ManualEntrySerializer,
    ItemSerializer,
    TransactionTemplateSerializer,
    TagSerializer,
    TagAssignmentSerializer,
    AccountUpdateSerializer,
    ReceiptAccountSerializer,
    LineItemDetailsSerializer,
)

from .utils import save_uploaded_file, delete_stored_file, validate_document_file
from .throttles import AuthRateThrottle, UploadRateThrottle
from .receipt_parsing import parse_receipt, unit_price_for
from .statement_parsing import parse_statement

from parser.csv_bank_parser import CsvBankParser
from parser.pdf_bank_parser import PdfBankParser
from parser.csv_receipt_parser import CsvReceiptParser
from parser.pdf_receipt_parser import PdfReceiptParser


logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("Health check could not reach the database")
        return Response(
            {"status": "unavailable", "database": "unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "ok", "database": "ok"})


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk, receipt__user=request.user)

    if request.method == "GET":
        serializer = ItemSerializer(item)
        return Response(serializer.data)

    elif request.method in ["PUT", "PATCH"]:
        partial = request.method == "PATCH"
        serializer = ItemSerializer(item, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Only return transactions that belong to the currently logged-in user.
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transaction_list(request):
    if request.method == "GET":
        # prefetch tags to avoid N+1 in transaction serialiser
        transactions = (
            Transaction.objects.filter(account__user=request.user)
            .select_related("account", "statement")
            .prefetch_related("tags")
        )
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)
    elif request.method == "POST":
        serializer = TransactionSerializer(data=request.data)
        if serializer.is_valid():
            transaction = serializer.save()
            return Response(TransactionSerializer(transaction).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def transaction_tags(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, account__user=request.user)

    if request.method == "GET":
        serializer = TransactionSerializer(transaction)
        return Response(serializer.data)

    elif request.method in ["PUT", "PATCH"]:
        partial = request.method == "PATCH"
        serializer = TransactionSerializer(
            transaction, data=request.data, partial=partial
        )
        if serializer.is_valid():
            updated_transaction = serializer.save()
            return Response(TransactionSerializer(updated_transaction).data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == "DELETE":
        transaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET","POST"])
@permission_classes([IsAuthenticated])
def account_list(request):
    if request.method == "GET":
        accounts = Account.objects.filter(user=request.user).order_by("created_at")
        return Response([account_list_payload(a, request.user) for a in accounts], status=status.HTTP_200_OK)

    account_name = request.data.get("account_name")
    account_number = request.data.get("account_number")
    card_type = request.data.get("card_type")
    funds = request.data.get("funds", 0.00)
    currency = request.data.get("currency") or request.user.currency

    if not is_supported(currency):
        return Response(
            {"error": f"'{currency}' is not a currency we have rates for."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not account_name or not account_number or not card_type:
        return Response(
            {"error": "Account name, account number, and card type are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # The account number identifies the account, so the same user creating
    # it twice (even under a different name) is a duplicate, not a new one.
    if Account.objects.filter(
        user=request.user, account_number=account_number
    ).exists():
        return Response(
            {"error": "You already have an account with that account number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        account = Account.objects.create(
            user=request.user,
            account_name=account_name,
            account_number=account_number,
            card_type=card_type,
            funds=funds,
            currency=currency,
        )
    except IntegrityError:
        return Response(
            {"error": "You already have an account with that account number."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(account_list_payload(account, request.user), status=status.HTTP_201_CREATED)


def account_list_payload(account, user):
    """
    A bank account as the account list gives it: its details, its opening
    balance (`funds`, when it was created), and what it holds now (`balance`, in
    its own currency, and `balance_converted`, in the user's), which follows
    every line dated after it was created. A savings account which went below
    zero carries a `warning` saying so.
    """
    return {
        "id": account.id,
        "account_name": account.account_name,
        "account_number": account.account_number,
        "card_type": account.card_type,
        "funds": account.funds,
        "currency": account.currency,
        "funds_converted": converted_funds(account.funds, account.currency, user.currency),
        **balance_summary(account, user.currency),
    }


class AccountHistoryView(APIView):
    """Every account's balance through time, for charting (see core.balances)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        accounts = Account.objects.filter(user=request.user).order_by("created_at")
        return Response(
            {"currency": request.user.currency, "accounts": [history_payload(a, request.user.currency) for a in accounts]},
            status=status.HTTP_200_OK,
        )


def converted_funds(funds, currency, target):
    """An account's funds in the user's currency, at today's rate (unchanged if there is no rate)."""
    if currency == target:
        return funds
    rate = spot_rate(currency, target)
    return (Decimal(funds) * rate).quantize(Decimal("0.01")) if rate else funds


def account_detail_payload(account):
    """A bank account with every statement uploaded to it."""
    statements = (
        BankStatement.objects.filter(account=account)
        .annotate(transaction_count=Count("transactions"))
        .order_by("-uploaded_at")
    )
    return {
        "id": account.id,
        "account_name": account.account_name,
        "account_number": account.account_number,
        "card_type": account.card_type,
        "funds": str(account.funds),
        "currency": account.currency,
        **balance_summary(account, account.user.currency),
        "statements": [
            {
                "id": statement.id,
                "file_name": document_name(statement.display_name, statement.file_path),
                "doc_type": statement.doc_type,
                "uploaded_at": statement.uploaded_at,
                "transaction_count": statement.transaction_count,
            }
            for statement in statements
        ],
    }


class AccountDetailView(APIView):
    """
    One bank account: its details, and the statements uploaded to it. Editing
    the details needs nothing more than saving them: statements, transactions
    and receipts refer to the account rather than holding a copy of its details,
    so every one of them shows the new details from then on.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        account = get_object_or_404(Account, pk=pk, user=request.user)
        return Response(account_detail_payload(account), status=status.HTTP_200_OK)

    def patch(self, request, pk, *args, **kwargs):
        account = get_object_or_404(Account, pk=pk, user=request.user)
        serializer = AccountUpdateSerializer(account, data=request.data, partial=True)

        if not serializer.is_valid():
            message = " ".join(
                str(problem) for problems in serializer.errors.values() for problem in problems
            )
            return Response(
                {"error": message, "fields": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            serializer.save()
        except IntegrityError:
            # Lost a race with another account taking the same number
            return Response(
                {"error": "You already have an account with that account number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(account_detail_payload(account), status=status.HTTP_200_OK)


@api_view(["POST"])
@throttle_classes([AuthRateThrottle])
def register_user(request):
    User = get_user_model()
    username = request.data.get("username")
    password = request.data.get("password")
    email = request.data.get("email")
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    cell_number = request.data.get("cell_number")
    is_admin = request.data.get("is_admin", False)

    if not username or not password or not email or not first_name or not last_name:
        return Response(
            {
                "error": "Username, password, email, first name, and last name are required."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_email(email)
    except ValidationError:
        return Response(
            {"error": "Invalid email format."}, status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists."}, status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {"error": "Email already exists."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )

        return Response(
            {
                "message": "User registered successfully.",
                "user_id": str(user.id),
            },
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([UserRateThrottle, UploadRateThrottle])
def upload_statement(request):
    uploaded_file = request.FILES.get("file")
    account_id = request.data.get("account")
    if not uploaded_file:
        return Response(
            {"error": "No file was uploaded"}, status=status.HTTP_400_BAD_REQUEST
        )

    if uploaded_file.size == 0:
        return Response(
            {"error": "Uploaded file is empty"}, status=status.HTTP_400_BAD_REQUEST
        )

    if uploaded_file.size > settings.MAX_UPLOAD_SIZE:
        return Response(
            {"error": "File exceeds 50MB size limit"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    extension = os.path.splitext(uploaded_file.name)[1].lower()
    if extension not in [".csv", ".pdf"]:
        return Response(
            {"error": "Unsupported file type. Only CSV and PDF files are allowed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not account_id:
        return Response(
            {"error": "Account ID is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        account = Account.objects.get(id=account_id, user=request.user)
    except Account.DoesNotExist:
        return Response(
            {"error": "Account not found"}, status=status.HTTP_404_NOT_FOUND
        )

    doc_type = "CSV" if extension == ".csv" else "PDF"

    # Idempotency check: same account + identical file content, checked before
    # anything is written to disk. (A filename-based check doesn't work here:
    # Django's storage renames a colliding filename before saving it, so a
    # second upload of the same name never collides with the first on disk.)
    file_hash = calculate_file_hash(uploaded_file)
    if BankStatement.objects.filter(account=account, file_hash=file_hash).exists():
        return Response({"error": "Duplicate file upload detected"}, status=status.HTTP_400_BAD_REQUEST)

    f = FileSystemStorage(location="document_storage/")
    filename = f.save(uploaded_file.name, uploaded_file)
    file_path = f.path(filename)

    # Validate parsers
    try:
        if doc_type=="CSV":
            parser = CsvBankParser()
            parser.parse(file_path)
        elif doc_type=="PDF":
            with open(file_path,'rb') as pdf_file:
                if b"Invalid PDF" in pdf_file.read():
                    raise ValueError("Corrupted PDF structure")
    except Exception as e:
        delete_stored_file(file_path)
        return Response({"error":f"Invalid file format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    data = {
        "account": account.id,
        "doc_type": doc_type,
        "file_path": file_path,
        "file_hash": file_hash,
    }

    serializer = BankstatementSerializer(data=data)
    if serializer.is_valid():
        try:
            serializer.save()
        except IntegrityError:
            # Lost a race with another upload of the same file
            delete_stored_file(file_path)
            return Response(
                {"error": "Duplicate file upload detected"}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UnifiedDocumentUpdateView(APIView):
    """
    Match a whole receipt to the bank statement line it was paid with. The
    statement is authoritative: the receipt takes the line's amount, and the
    line's account if the receipt had none yet ("reconcile later").
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, receiptId, *args, **kwargs):
        try:
            receipt_id = uuid.UUID(str(receiptId))
        except ValueError:
            raise Http404
        receipt = get_object_or_404(
            Receipt.objects.filter(user=request.user).exclude(entry_type="cash"),
            pk=receipt_id,
        )

        try:
            target = uuid.UUID(request.query_params.get("target", ""))
        except ValueError:
            return Response(
                {"error": "A valid 'target' transaction ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        line = get_object_or_404(Transaction, pk=target, account__user=request.user)

        if receipt.transaction_id is not None:
            return Response(
                {"error": "This receipt has already been matched to a statement line."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if line.receipts.exists() or line.items.exists():
            return Response(
                {"error": "That statement line has already been matched."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if receipt.account_id is not None and receipt.account_id != line.account_id:
            return Response(
                {
                    "error": "That statement line is on a different bank account to this "
                    "receipt. Change the receipt's account first."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():
            receipt.transaction = line
            receipt.account = line.account
            # a debit is negative on a statement; a receipt's total is not
            receipt.total_amount = abs(line.amount)
            receipt.save()
            line.status = "Reconciled"
            line.save()

        return Response(
            {
                "id": receipt.id,
                "transaction": line.id,
                "account": account_payload(line.account),
                "total_amount": str(receipt.total_amount),
            },
            status=status.HTTP_200_OK,
        )


class ReceiptAccountView(APIView):
    """Link a receipt to the bank account it was paid from, when that was not known at upload."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, *args, **kwargs):
        receipt = get_object_or_404(
            Receipt.objects.filter(user=request.user).exclude(entry_type="cash"), pk=pk
        )
        serializer = ReceiptAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "A valid 'account' ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account = get_object_or_404(
            Account, pk=serializer.validated_data["account"], user=request.user
        )

        # A matched receipt takes its account from its statement line
        if receipt.transaction_id and receipt.transaction.account_id != account.id:
            return Response(
                {
                    "error": "This receipt has been matched to a statement line, so its "
                    "account is that line's account."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        receipt.account = account
        receipt.save()
        return Response(
            {"id": receipt.id, "account": account_payload(account)},
            status=status.HTTP_200_OK,
        )


def tags_payload(line):
    """
    The tags of a line item (receipt item or bank transaction), by name. The
    system's hidden tags are not among them.
    """
    return [
        {"id": tag.id, "name": tag.name}
        for tag in sorted(line.tags.all(), key=lambda tag: tag.name.lower())
        if not tag.is_hidden
    ]


def is_subscription(line):
    """Whether a line item has been marked as a subscription."""
    return any(tag.is_subscription for tag in line.tags.all())


def item_payload(item):
    """A line item as the frontend sees it."""
    return {
        "id": item.id,
        "item_name": item.item_name,
        "display_name": item.display_name or None,
        "item_total": str(item.item_total),
        "quantity": str(item.quantity),
        "unit_price": str(item.unit_price),
        "merchant": item.merchant or None,
        "date": item.date.isoformat() if item.date else None,
        "direction": item.direction,
        "tags": tags_payload(item),
        "transaction": item.transaction_id,
    }


def normalised_line(amount, direction):
    """
    An amount and its direction, with the amount positive. A negative amount
    (a discount on a receipt, say) is the other direction's positive one.
    """
    if amount < 0:
        return -amount, ("credit" if direction == "debit" else "debit")
    return amount, direction


def signed(amount, direction):
    """What a line adds to a total: money out counts for it and money back against it."""
    return -amount if direction == "credit" else amount


def resolve_line_tags(user, rows):
    """
    The tags named by the given lines' `tags` (ids), as {id: Tag}, or an error
    response if any is not one the user can use.
    """
    ids = set()
    try:
        for row in rows:
            row_tags = [str(uuid.UUID(str(tag_id))) for tag_id in row.get("tags", [])]
            row["tags"] = row_tags
            ids.update(row_tags)
    except (TypeError, ValueError, AttributeError):
        return None, Response(
            {"error": "One or more tags do not exist."}, status=status.HTTP_400_BAD_REQUEST
        )
    if not ids:
        return {}, None
    found = {
        str(tag.pk): tag
        for tag in Tag.objects.available_to(user).filter(pk__in=ids)
    }
    if len(found) != len(ids):
        return None, Response(
            {"error": "One or more tags do not exist."}, status=status.HTTP_400_BAD_REQUEST
        )
    return found, None


def add_receipt_in_background(document_record, saved_path, doc_type):
    """
    Read a receipt the client did not read first (an older client, or an API
    call), then fill in its total, merchant, date and line items.
    """
    input_file = f"document_storage/{saved_path}"
    document_record.processing_status = "processing"
    document_record.save(update_fields=["processing_status"])
    logger.info("Starting background receipt parse: receipt=%s type=%s", document_record.id, doc_type)
    try:
        merchant_name = "Unknown"
        transaction_date = None
        total_amount = None
        if doc_type == "PDF":
            total_amount = PdfReceiptParser().minimal_parse(input_file)
        elif doc_type == "CSV":
            result = CsvReceiptParser().parse(input_file)
            transactions = result["transactions"]
            total_amount = CsvReceiptParser.get_total(transactions)
            if transactions:
                merchant_name = transactions[0]["merchant"]
                transaction_date = transactions[0]["date"]
                Item.objects.bulk_create([
                    Item(
                        receipt=document_record,
                        item_name=t["item"],
                        unit_price=t["unit_price"],
                        quantity=t["quantity"],
                        item_total=t["amount"],
                    )
                    for t in transactions
                ])
        else:
            raise ValueError(f"Unsupported receipt type: {doc_type}")

        if total_amount is not None:
            document_record.total_amount = total_amount
            document_record.merchant_name = merchant_name
            document_record.transaction_date = transaction_date
        document_record.processing_status = "completed"
        document_record.parser_error = None
        document_record.save()
        logger.info("Completed background receipt parse: receipt=%s", document_record.id)
    except Exception:
        logger.exception("Background receipt parse failed: receipt=%s", document_record.id)
        document_record.processing_status = "failed"
        document_record.parser_error = "The receipt could not be parsed."
        document_record.save(update_fields=["processing_status", "parser_error"])


class DocumentParseView(APIView):
    """
    Read a receipt's line items, or a bank statement's transactions, without
    saving anything, so the user can see (and correct) what was found, and what
    could not be read, before choosing to upload. `category` says which it is;
    a receipt is assumed.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UserRateThrottle, UploadRateThrottle]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"error": "A file is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        category = request.data.get("category", "receipt")
        bank = request.data.get("bank") or "investec"
        if category not in ("receipt", "statement"):
            return Response(
                {"error": "The category must be 'receipt' or 'statement'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_document_file(uploaded_file)
        except ValidationError as e:
            return Response(
                {"error": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )

        extension = os.path.splitext(uploaded_file.name)[1].lower()
        # The parsers read from a path, so give the upload a private, throwaway one
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, f"{category}{extension}")
            with open(path, "wb") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            if category == "statement":
                result = parse_statement(path, extension, tmp_dir, bank=bank, user=request.user)
            else:
                result = parse_receipt(path, extension)

        return Response(result, status=status.HTTP_200_OK)


class ItemLinkView(APIView):
    """Match a receipt line item to the bank statement line it was paid with."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id, *args, **kwargs):
        try:
            target = uuid.UUID(request.query_params.get("target", ""))
        except ValueError:
            return Response(
                {"error": "A valid 'target' transaction ID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = get_object_or_404(Item, pk=item_id, receipt__user=request.user)
        transaction = get_object_or_404(
            Transaction, pk=target, account__user=request.user
        )

        # The transaction comes from the bank statement, which is authoritative
        if item.item_total != transaction.amount:
            item.item_total = transaction.amount
        item.transaction = transaction
        item.save()

        transaction.status = "Reconciled"
        transaction.save()

        return Response(item_payload(item), status=status.HTTP_200_OK)


def document_name(display_name, path):
    """What a document is called: its display name, else its file's name."""
    return display_name or (os.path.basename(path) if path else "unknown")


def account_payload(account):
    if account is None:
        return None
    return {
        "id": account.id,
        "account_name": account.account_name,
        "card_type": account.card_type,
        "account_number": account.account_number,
        "currency": account.currency,
    }


def statement_line_text(transaction):
    """
    A statement line's own name, as it was read. Statement parsing stores the
    line's text as the merchant and leaves the description empty, so the text is
    the description unless there is one (and is then not repeated as the merchant).
    """
    return transaction.description or transaction.merchant or ""


def statement_line_direction(transaction):
    """
    Parsing never sets a transaction's type, so every line is stored as an
    Expense; the sign of the amount is what tells money in from out.
    """
    return "in" if transaction.amount > 0 else "out"


def statement_line_payload(transaction):
    """A bank statement line, in the shape shared by every line item."""
    statement = transaction.statement
    return {
        "id": transaction.id,
        "kind": "statement_line",
        "date": transaction.transaction_date.isoformat(),
        "added_at": statement.uploaded_at.isoformat() if statement else None,
        "description": statement_line_text(transaction),
        "display_name": transaction.display_name or None,
        "merchant": transaction.merchant if transaction.description else None,
        "amount": str(transaction.amount),
        "currency": transaction.currency,
        "quantity": 1,
        "unit_price": str(transaction.amount),
        "direction": statement_line_direction(transaction),
        "status": transaction.status,
        "is_cash": transaction.is_cash,
        "matched": transaction.is_matched,
        "account": account_payload(transaction.account),
        "source": (
            {
                "id": statement.id,
                "name": document_name(statement.display_name, statement.file_path),
                "category": "statement",
                "bank": statement.bank,
            }
            if statement
            else None
        ),
        "tags": tags_payload(transaction),
        "is_subscription": is_subscription(transaction),
    }


def receipt_item_payload(item):
    """A receipt line item, in the shape shared by every line item."""
    receipt = item.receipt
    return {
        "id": item.id,
        "kind": "receipt_item",
        "date": (item.date or receipt.transaction_date.date()).isoformat(),
        "added_at": receipt.uploaded_at.isoformat(),
        "description": item.item_name,
        "display_name": item.display_name or None,
        "merchant": item.merchant or receipt.merchant_name or None,
        "amount": str(item.item_total),
        "currency": receipt.currency,
        "quantity": str(item.quantity),
        "unit_price": str(item.unit_price),
        "direction": "in" if item.direction == "credit" else "out",
        "status": None,
        "is_cash": receipt.entry_type == "cash",
        "matched": item.transaction_id is not None or receipt.transaction_id is not None,
        # The statement line this item was matched to (its own, else its receipt's)
        "transaction_id": item.transaction_id or receipt.transaction_id,
        "account": account_payload(receipt.account),
        "source": {
            "id": receipt.id,
            "name": document_name(receipt.display_name, receipt.receipt_path),
            "category": "cash" if receipt.entry_type == "cash" else "receipt",
        },
        "tags": tags_payload(item),
        "is_subscription": is_subscription(item),
    }


def convert_payloads(payloads, user):
    """
    Report line item payloads in the user's currency. Each line is converted at
    the exchange rate of its own date, and the amount it was recorded in is kept
    as `original_amount` / `original_currency`. A line which changed currency is
    marked with `conversion` ("ZAR -> USD") and the `exchange_rate` used; one
    which could not be converted (no rate to be had) is left in its own currency,
    with `rate_unavailable` set, rather than passed off as the user's.
    """
    def day_of(payload):
        value = payload["date"]
        return value if hasattr(value, "year") and not isinstance(value, str) else datetime.fromisoformat(str(value)).date()

    book = RateBook(user.currency)
    book.prepare((p["currency"], day_of(p)) for p in payloads)

    for payload in payloads:
        source = payload["currency"]
        payload["original_amount"] = payload["amount"]
        payload["original_currency"] = source
        payload["conversion"] = None
        payload["exchange_rate"] = None
        payload["rate_unavailable"] = False
        if source == user.currency:
            continue

        day = day_of(payload)
        amount, rate = book.convert(Decimal(payload["amount"]), source, day)
        if rate is None:
            payload["rate_unavailable"] = True
            payload["conversion"] = f"{source} (no rate)"
            continue
        payload["amount"] = str(amount)
        if payload.get("unit_price") is not None:
            payload["unit_price"] = str((Decimal(payload["unit_price"]) * rate).quantize(Decimal("0.01")))
        payload["currency"] = user.currency
        payload["conversion"] = conversion_label(source, user.currency)
        payload["exchange_rate"] = str(rate)
    return payloads


CONVERSION_FIELDS = ("original_amount", "original_currency", "conversion", "exchange_rate", "rate_unavailable")


def receipt_amount_proxies(receipt, meta):
    """
    The amounts in a receipt's document entry (each item's total and unit price,
    and the receipt's total) as payloads convert_payloads can convert, each with
    where the converted figures go back to. An item is converted at the rate of
    its own date, or its receipt's when it has none.
    """
    receipt_day = receipt.transaction_date.date().isoformat()
    proxies = []
    for item in meta.get("items") or []:
        proxy = {"currency": receipt.currency, "date": item["date"] or receipt_day,
                 "amount": item["item_total"], "unit_price": item["unit_price"]}
        proxies.append((proxy, item, "item_total"))
    if meta.get("amount") is not None:
        proxy = {"currency": receipt.currency, "date": receipt_day, "amount": str(meta["amount"]), "unit_price": None}
        proxies.append((proxy, meta, "amount"))
    return proxies


def convert_receipt_amounts(proxies, user):
    """Converts what receipt_amount_proxies gathered (from any number of receipts) and puts
    the figures back. The entry's own `currency` stays the one the receipt was recorded in."""
    convert_payloads([proxy for proxy, _, _ in proxies], user)
    for proxy, target, key in proxies:
        target[key] = proxy["amount"]
        if key == "item_total":
            target["unit_price"] = proxy["unit_price"]
            target["currency"] = proxy["currency"]
        for field in CONVERSION_FIELDS:
            target[field if key == "item_total" else f"amount_{field}"] = proxy[field]


class LineItemListView(APIView):
    """
    Every line item a user has, with all of its details: the lines of their
    bank statements and the items on their receipts. Line items have no upload
    time of their own, so `added_at` is when the document they came from was
    uploaded.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        transactions = (
            Transaction.objects.filter(account__user=request.user)
            .select_related("account", "statement")
            .prefetch_related("tags", "items", "receipts")
        )
        items = (
            Item.objects.filter(receipt__user=request.user)
            .select_related("receipt", "receipt__account")
            .prefetch_related("tags")
        )

        results = [statement_line_payload(t) for t in transactions]
        results += [receipt_item_payload(i) for i in items]
        convert_payloads(results, request.user)
        results.sort(key=lambda line: line["date"], reverse=True)
        return Response(results, status=status.HTTP_200_OK)

class TagAssignmentView(APIView):
    """Replace the tags on a line item with the given set."""

    permission_classes = [IsAuthenticated]

    def get_line(self, request, pk):
        raise NotImplementedError

    def payload(self, line):
        raise NotImplementedError

    def put(self, request, pk, *args, **kwargs):
        line = self.get_line(request, pk)
        serializer = TagAssignmentSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        # Only the tags the user can see are theirs to replace; the system's
        # hidden ones (a subscription mark) stay on
        hidden = [tag for tag in line.tags.all() if tag.is_hidden]
        line.tags.set(serializer.validated_data["tags"] + hidden)
        return Response(self.payload(line), status=status.HTTP_200_OK)


class ItemTagsView(TagAssignmentView):
    """Tag a receipt line item."""

    def get_line(self, request, pk):
        return get_object_or_404(Item, pk=pk, receipt__user=request.user)

    def payload(self, item):
        return item_payload(item)


class TransactionTagsView(TagAssignmentView):
    """Tag a bank statement line item."""

    def get_line(self, request, pk):
        return get_object_or_404(Transaction, pk=pk, account__user=request.user)

    def payload(self, transaction):
        return {"id": transaction.id, "tags": tags_payload(transaction)}


class SubscriptionMarkView(APIView):
    """
    Mark a line item as a subscription (PUT), or take the mark off (DELETE). The
    mark is the system's hidden Subscription tag, so it is kept apart from the
    tags the user sees and chooses. Both respond with the line item as the line
    item list shows it.
    """

    permission_classes = [IsAuthenticated]

    def get_line(self, request, pk):
        raise NotImplementedError

    def payload(self, line):
        raise NotImplementedError

    def put(self, request, pk, *args, **kwargs):
        line = self.get_line(request, pk)
        line.tags.add(Tag.objects.subscription())
        return Response(self.payload(line), status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        line = self.get_line(request, pk)
        line.tags.remove(Tag.objects.subscription())
        return Response(self.payload(line), status=status.HTTP_200_OK)


class TransactionSubscriptionView(SubscriptionMarkView):
    """Mark a bank statement line as a subscription."""

    def get_line(self, request, pk):
        return get_object_or_404(
            Transaction.objects.select_related("account", "statement"), pk=pk, account__user=request.user
        )

    def payload(self, transaction):
        return convert_payloads([statement_line_payload(transaction)], transaction.account.user)[0]


class ItemSubscriptionView(SubscriptionMarkView):
    """Mark a receipt line item as a subscription."""

    def get_line(self, request, pk):
        return get_object_or_404(
            Item.objects.select_related("receipt", "receipt__account"), pk=pk, receipt__user=request.user
        )

    def payload(self, item):
        return convert_payloads([receipt_item_payload(item)], item.receipt.user)[0]


def next_month(day):
    """The same day a month later, or the month's last day if it has no such day (31 Jan -> 28 Feb)."""
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


class SubscriptionListView(APIView):
    """
    The user's subscriptions: the line items they marked as one, grouped by what
    they are for (the name the user gave the line, else its merchant, else the
    bank's text), so that each month's Netflix charge is the one subscription.
    Each has its latest charge and when the next is expected, a month after it.
    `monthly_total` is what they all come to in a month, at their latest prices.
    Amounts are in the user's currency, each charge converted at its own date's
    rate (a charge with no rate to be had stays as it was recorded).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        mark = Tag.objects.subscription()
        charges = [
            {
                "name": t.display_name or t.merchant or t.description or "",
                "amount": str(abs(t.amount)),
                "currency": t.currency,
                "date": t.transaction_date,
                "line": {"id": t.id, "kind": "statement_line"},
                "account": t.account,
            }
            for t in Transaction.objects.filter(account__user=request.user, tags=mark).select_related("account")
        ] + [
            {
                "name": i.display_name or i.merchant or i.receipt.merchant_name or i.item_name,
                "amount": str(i.item_total),
                "currency": i.receipt.currency,
                "date": i.date or i.receipt.transaction_date.date(),
                "line": {"id": i.id, "kind": "receipt_item"},
                "account": i.receipt.account,
            }
            for i in Item.objects.filter(receipt__user=request.user, tags=mark).select_related(
                "receipt", "receipt__account"
            )
        ]
        convert_payloads(charges, request.user)

        groups = {}
        for charge in charges:
            groups.setdefault(charge["name"].strip().lower(), []).append(charge)

        subscriptions = []
        for group in groups.values():
            group.sort(key=lambda charge: charge["date"])
            latest = group[-1]
            subscriptions.append(
                {
                    "name": latest["name"].strip(),
                    "amount": str(Decimal(latest["amount"]).quantize(Decimal("0.01"))),
                    "currency": latest["currency"],
                    "last_charged": latest["date"].isoformat(),
                    "next_expected": next_month(latest["date"]).isoformat(),
                    "charges": len(group),
                    "account": account_payload(latest["account"]),
                    "lines": [charge["line"] for charge in group],
                }
            )
        subscriptions.sort(key=lambda subscription: (subscription["next_expected"], subscription["name"].lower()))

        monthly_total = sum((Decimal(s["amount"]) for s in subscriptions), Decimal(0))
        return Response(
            {
                "subscriptions": subscriptions,
                "monthly_total": str(monthly_total.quantize(Decimal("0.01"))),
                "currency": request.user.currency,
            },
            status=status.HTTP_200_OK,
        )

def calculate_file_hash(uploaded_file):
    hasher = hashlib.sha256()

    for chunk in uploaded_file.chunks():
        hasher.update(chunk)

    uploaded_file.seek(0)
    return hasher.hexdigest()

class LineItemDetailsView(APIView):
    """
    Change a saved line item's details: any of its display name, merchant, date,
    direction (debit or credit) and, for a receipt item, quantity, alone or
    together. Responds with the line item as the line item list shows it.

    The display name is an alias: the line's own name is left as it was read, so
    that uploading the same file again still reads (and is recognised) the same.
    A blank name, or the line's own, takes the alias away.
    """

    permission_classes = [IsAuthenticated]

    def get_line(self, request, pk):
        raise NotImplementedError

    def own_name(self, line):
        raise NotImplementedError

    def apply(self, line, data):
        """Set the merchant, date and direction, if they were sent."""
        raise NotImplementedError

    def payload(self, line):
        raise NotImplementedError

    def patch(self, request, pk, *args, **kwargs):
        line = self.get_line(request, pk)
        serializer = LineItemDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with db_transaction.atomic():
            if "display_name" in data:
                line.display_name = "" if data["display_name"] == self.own_name(line) else data["display_name"]
            self.apply(line, data)
            line.save()
        return Response(self.payload(line), status=status.HTTP_200_OK)


class ItemDetailsView(LineItemDetailsView):
    """Change a receipt line item's details."""

    def get_line(self, request, pk):
        return get_object_or_404(
            Item.objects.select_related("receipt", "receipt__account"),
            pk=pk,
            receipt__user=request.user,
        )

    def own_name(self, item):
        return item.item_name

    def apply(self, item, data):
        if "merchant" in data:
            item.merchant = data["merchant"]
        if "date" in data:
            item.date = data["date"]
        if "quantity" in data:
            # The line's total is what the receipt says; the price of each item follows
            try:
                item.unit_price = unit_price_for(item.item_total, data["quantity"])
            except ValueError as error:
                raise APIValidationError({"quantity": [str(error)]})
            item.quantity = data["quantity"]
        if "direction" in data and data["direction"] != item.direction:
            receipt = item.receipt
            items = list(receipt.items.all())

            def total_of(lines):
                return sum((signed(i.item_total, i.direction) for i in lines), Decimal(0))

            # A receipt whose total is what its items add up to stays that way; one
            # with a total of its own (read from the receipt, or set by matching it
            # to a statement line) is left as it is
            follows_items = receipt.total_amount is not None and receipt.total_amount == total_of(items)
            item.direction = data["direction"]
            if follows_items:
                receipt.total_amount = total_of([item if i.pk == item.pk else i for i in items])
                receipt.save(update_fields=["total_amount"])

    def payload(self, item):
        return convert_payloads([receipt_item_payload(item)], item.receipt.user)[0]


class TransactionDetailsView(LineItemDetailsView):
    """Change a bank statement line's details."""

    def get_line(self, request, pk):
        return get_object_or_404(
            Transaction.objects.select_related("account", "statement"),
            pk=pk,
            account__user=request.user,
        )

    def own_name(self, transaction):
        return statement_line_text(transaction)

    def apply(self, transaction, data):
        if "quantity" in data:
            raise APIValidationError({"quantity": ["A statement line has no quantity."]})
        if "merchant" in data:
            # Parsing stores a line's text as its merchant and leaves the
            # description empty, and the text is the line's own name: keep it
            # as the description before the merchant becomes something else
            if not transaction.description:
                transaction.description = transaction.merchant or None
            transaction.merchant = data["merchant"] or None
        if "date" in data:
            if data["date"] is None:
                raise APIValidationError({"date": ["A statement line must have a date."]})
            transaction.transaction_date = data["date"]
        if "direction" in data:
            wanted = data["direction"]
            if wanted != ("credit" if statement_line_direction(transaction) == "in" else "debit"):
                # A statement records a debit as negative and a credit as positive
                size = abs(transaction.amount)
                if wanted == "credit" and size == 0:
                    raise APIValidationError({"direction": ["A line of nothing cannot be a credit."]})
                transaction.amount = size if wanted == "credit" else -size
                transaction.transaction_type = "Income" if wanted == "credit" else "Expense"

    def payload(self, transaction):
        return convert_payloads([statement_line_payload(transaction)], transaction.account.user)[0]


class ItemRemoveView(APIView):
    """
    Remove a receipt line item for good. The receipt keeps its other items, and its
    total follows them if it is made of them.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        get_object_or_404(Item, pk=pk, receipt__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionRemoveView(APIView):
    """
    Remove a bank statement line for good. A receipt which was matched to it is
    left unmatched, and goes back to waiting on the Review page.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        get_object_or_404(Transaction, pk=pk, account__user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LineItemBulkDeleteView(APIView):
    """
    Remove several line items (statement lines and receipt items) at once, for good.

    Each goes as it would one at a time: a receipt's total follows its items, and a
    receipt matched to a removed statement line is left unmatched. The documents
    they belong to recognise the change as well: a bank statement or receipt which
    has no line items left is removed too, with its stored file, as there is
    nothing left of it. Everything is removed or nothing is.

    Responds with how many line items went and which statements and receipts
    went with them.
    """

    permission_classes = [IsAuthenticated]
    MAX_LINES = 500

    def post(self, request, *args, **kwargs):
        wanted = request.data.get("lines")
        if not isinstance(wanted, list) or not wanted:
            return Response({"error": "Choose at least one line item to remove."}, status=status.HTTP_400_BAD_REQUEST)
        if len(wanted) > self.MAX_LINES:
            return Response(
                {"error": f"Remove at most {self.MAX_LINES} line items at a time."}, status=status.HTTP_400_BAD_REQUEST
            )

        line_ids, item_ids = set(), set()
        try:
            for entry in wanted:
                kind, pk = entry["kind"], uuid.UUID(str(entry["id"]))
                if kind == "statement_line":
                    line_ids.add(pk)
                elif kind == "receipt_item":
                    item_ids.add(pk)
                else:
                    raise ValueError(kind)
        except (KeyError, TypeError, ValueError):
            return Response(
                {"error": "Each line item needs an id and a kind (statement_line or receipt_item)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stored_files = []
        with db_transaction.atomic():
            lines = list(Transaction.objects.filter(pk__in=line_ids, account__user=request.user))
            items = list(Item.objects.filter(pk__in=item_ids, receipt__user=request.user).select_related("receipt"))
            if len(lines) != len(line_ids) or len(items) != len(item_ids):
                return Response({"error": "Some of those line items could not be found."}, status=status.HTTP_404_NOT_FOUND)

            statement_ids = {line.statement_id for line in lines if line.statement_id}
            receipt_ids = {item.receipt_id for item in items}

            for item in items:
                item.delete()
            for line in lines:
                line.delete()

            # A document with nothing left in it goes too
            emptied_statements = list(
                BankStatement.objects.filter(pk__in=statement_ids, transactions__isnull=True)
            )
            emptied_receipts = list(Receipt.objects.filter(pk__in=receipt_ids, items__isnull=True))
            removed_statements = [str(s.pk) for s in emptied_statements]
            removed_receipts = [str(r.pk) for r in emptied_receipts]
            for statement in emptied_statements:
                if statement.file_path:
                    stored_files.append(statement.file_path)
                statement.delete()
            for receipt in emptied_receipts:
                if receipt.receipt_path:
                    stored_files.append(receipt.receipt_path)
                receipt.delete()

        for path in stored_files:
            delete_stored_file(path)

        return Response(
            {
                "deleted": len(lines) + len(items),
                "removed_statements": removed_statements,
                "removed_receipts": removed_receipts,
            },
            status=status.HTTP_200_OK,
        )


class UnifiedDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UserRateThrottle, UploadRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = UnifiedDocumentUploadSerializer(data=request.data)
        meta = {}

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        uploaded_file = validated_data["file"]
        category = validated_data["category"]

        try:
            validate_document_file(uploaded_file)
        except ValidationError as e:
            return Response(
                {"error":" ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )

        # The tags the user put on the lines must be theirs to use; check them
        # (before the file is stored, so a bad one leaves nothing behind)
        items_data = validated_data.get("items")
        transactions_data = validated_data.get("transactions")
        line_tags, error = resolve_line_tags(
            request.user, list(items_data or []) + list(transactions_data or [])
        )
        if error:
            return error

        # A receipt's account may be left out ("reconcile later"), but one which is
        # given must be the user's own; check it before the file is stored
        receipt_account = None
        if category == "receipt" and validated_data.get("account"):
            receipt_account = get_object_or_404(
                Account, id=validated_data["account"], user=request.user
            )

        file_hash = calculate_file_hash(uploaded_file)

        if category == "statement":
            account_id = validated_data["account"]
            account = get_object_or_404(Account, id=account_id, user=request.user)

            if BankStatement.objects.filter(
                account=account,
                file_hash=file_hash,
            ).exists():
                return Response(
                    {"message": "This bank statement has already been imported.","duplicate":True},
                    status=status.HTTP_200_OK,
                )
        elif category == "receipt":
            if Receipt.objects.filter(
                user=request.user, 
                file_hash=file_hash).exists():
                return Response(
                    {"message": "This receipt has already been imported.","duplicate":True},
                    status=status.HTTP_200_OK,
                )

        try:
            saved_path = save_uploaded_file(uploaded_file, category)
        except ValidationError as e:
            return Response(
                {"error": " ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        original_file_name = uploaded_file.name
        display_name = validated_data.get("display_name") or original_file_name

        _, ext = os.path.splitext(original_file_name)
        doc_type = ext.upper().replace(".", "")

        if category == "statement":
            statement_currency = validated_data.get("currency") or account.currency
            statement_bank = validated_data.get("bank") or "investec"
            # Resolve the account and ensure it belongs to the current user
            try:
                document_record = BankStatement.objects.create(
                    account=account,
                    file_path=saved_path,
                    doc_type=doc_type,
                    display_name=display_name,
                    bank=statement_bank,
                    currency=statement_currency,
                    processing_status="completed" if transactions_data is not None else "pending",
                    file_hash=file_hash,
                )
            except IntegrityError:
                # Lost a race with another upload of the same file (the earlier
                # .exists() check above only catches non-concurrent duplicates)
                delete_stored_file(saved_path)
                return Response(
                    {"message": "This bank statement has already been imported.", "duplicate": True},
                    status=status.HTTP_200_OK,
                )

            # A statement's lines come from the client, which read the file through
            # the parse endpoint and showed them to the user to check (and edit).
            # One sent without them waits, pending, to be read.
            if transactions_data is not None:
                user_template = list(
                    TransactionTemplate.objects.filter(user=request.user).prefetch_related(
                        Prefetch(
                            "tags",
                            queryset=Tag.objects.available_to(request.user),
                        )
                    )
                )
                transaction_to_create = []

                for row in transactions_data:
                    merchant_name = row.get("merchant") or ""
                    applied_tags = row.get("tags") or []
                    original_name = row["name"].strip()

                    longest_match = None
                    for template in user_template:
                        if template.search_string.lower() in original_name.lower():
                            if not longest_match or len(template.search_string) > len(longest_match.search_string):
                                longest_match = template

                    if longest_match:
                        if longest_match.merchant_name:
                            merchant_name = longest_match.merchant_name
                        if longest_match.tags.exists():
                            for t in longest_match.tags.all():
                                tag_str = str(t.id)
                                if(tag_str not in applied_tags):
                                    applied_tags.append(tag_str)
                                    line_tags[tag_str] = t
                    elif merchant_name == original_name:
                        merchant_name = ""

                    row["tags"] = applied_tags

                    transaction_to_create.append(Transaction(
                        account= account,
                        statement = document_record,
                        amount = -row["amount"] if row["direction"] == "debit" else row["amount"],
                        currency = statement_currency,
                        transaction_type = "Expense" if row["direction"] == "debit" else "Income",
                        transaction_date = row["date"],
                        merchant = merchant_name or None,
                        description = original_name or None,
                        )
                    )
                created = Transaction.objects.bulk_create(transaction_to_create)

                for transaction_record, row in zip(created, transactions_data):
                    if row["tags"]:
                        transaction_record.tags.set([line_tags[t] for t in row["tags"]])

                meta = {
                    "account": account.id,
                    "merchant_name": None,
                    "amount": None,
                    "transaction_date": None,
                    "transaction_count": len(transactions_data)
                }

                document_record.processing_status = "completed"
                document_record.save(update_fields=["processing_status"])

        elif category == "receipt":
            # None when the client did not read the file first; see below
            for item in items_data or []:
                item["total"], item["direction"] = normalised_line(item["total"], item["direction"])
            total_amount = validated_data.get("amount")
            if total_amount is None and items_data:
                total_amount = sum(
                    (signed(item["total"], item["direction"]) for item in items_data), Decimal(0)
                )

            # Create Receipt record linked directly to the user
            document_record = Receipt(
                user=request.user,
                account=receipt_account,
                currency=validated_data.get("currency")
                or (receipt_account.currency if receipt_account else request.user.currency),
                receipt_path=saved_path,
                display_name=display_name,
                merchant_name=validated_data.get("merchant_name", ""),
                total_amount=total_amount,
                processing_status="completed" if items_data is not None else "pending",
                file_hash=file_hash,
            )
            receipt_date = validated_data.get("transaction_date")
            if receipt_date:
                document_record.transaction_date = timezone.make_aware(
                    datetime.combine(receipt_date, time.min)
                )
            try:
                document_record.save()
            except IntegrityError:
                # Lost a race with another upload of the same file (the earlier
                # .exists() check above only catches non-concurrent duplicates)
                delete_stored_file(saved_path)
                return Response(
                    {"message": "This receipt has already been imported.", "duplicate": True},
                    status=status.HTTP_200_OK,
                )

            if items_data is not None:
                # The client read the file through the parse endpoint and the user
                # saw these exact items, so save them rather than parsing again.
                created = Item.objects.bulk_create(
                    [
                        Item(
                            receipt=document_record,
                            item_name=item["name"],
                            unit_price=-abs(item["unit_price"]),
                            quantity=item["quantity"],
                            item_total=item["total"],
                            merchant=item["merchant"],
                            date=item["date"],
                            direction=item["direction"],

                        )
                        for item in items_data
                    ]
                )
                for item_record, item in zip(created, items_data):
                    if item["tags"]:
                        item_record.tags.set([line_tags[t] for t in item["tags"]])
            else:
                threading.Thread(
                    target=add_receipt_in_background,
                    args=(document_record, saved_path, doc_type),
                ).start()

            meta = {
                "account": receipt_account.id if receipt_account else None,
                "merchant_name": document_record.merchant_name,
                "amount": str(document_record.total_amount)
                if document_record.total_amount
                else None,
                "transaction_date": document_record.transaction_date
                if receipt_date
                else None,
                "currency": document_record.currency,
                "items": [item_payload(it) for it in document_record.items.all()],
            }
            convert_receipt_amounts(receipt_amount_proxies(document_record, meta), request.user)

        return Response(
            {
                "id": document_record.id,
                "category": category,
                "file_name": document_record.display_name or original_file_name,
                "file_path": saved_path,
                # Handle potential field naming differences between models
                "uploaded_at": getattr(document_record, "created_at", None)
                or getattr(document_record, "uploaded_at", None),
                "processing_status": document_record.processing_status,
                "parser_error": document_record.parser_error,
                "meta": meta,
            },
            status=status.HTTP_201_CREATED,
        )


def receipt_statement_ids(receipt):
    """The bank statements a receipt is matched to (as a whole, or by any of its items)."""
    lines = [receipt.transaction] + [item.transaction for item in receipt.items.all()]
    return sorted({str(line.statement_id) for line in lines if line is not None and line.statement_id})


def receipts_for_category(user, category):
    """
    Cash manual entries live in the Receipt table but are their own category:
    they are never a receipt/scan, so "receipt" excludes them and "cash"
    selects only them.
    """
    receipts = Receipt.objects.filter(user=user)
    if category == "cash":
        return receipts.filter(entry_type="cash")
    return receipts.exclude(entry_type="cash")


class DocumentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        category_filter = request.query_params.get("category", None)
        results = []

        # 1. Fetch Receipts and cash entries (if requested or no filter applied)
        if category_filter in [None, "receipt", "cash"]:
            # SECURE: Filter directly by the authenticated user
            if category_filter is None:
                receipts = Receipt.objects.filter(user=request.user)
            else:
                receipts = receipts_for_category(request.user, category_filter)
            receipts = (
                receipts.order_by("-id")
                .select_related("transaction")
                .prefetch_related("items__tags", "items__transaction")
            )

            proxies = []
            for r in receipts:
                results.append(
                    {
                        "id": r.id,
                        "category": "cash" if r.entry_type == "cash" else "receipt",
                        "file_name": r.display_name
                        or (
                            os.path.basename(r.receipt_path)
                            if r.receipt_path
                            else "unknown"
                        ),
                        "file_path": r.receipt_path,
                        "uploaded_at": getattr(r, "created_at", None)
                        or getattr(r, "uploaded_at", None),
                        "has_transaction": r.transaction_id is not None,
                        # The bank statements this receipt is matched to, through
                        # the receipt as a whole or through any of its items
                        "statement_ids": receipt_statement_ids(r),
                        "meta": {
                            "currency": r.currency,
                            "account": r.account_id,
                            "merchant_name": r.merchant_name,
                            "amount": str(r.total_amount) if r.total_amount else None,
                            "transaction_date": r.transaction_date,
                            "entry_type": r.entry_type,
                            "items": [item_payload(it) for it in r.items.all()],
                        },
                        "processing_status": r.processing_status,
                        "parser_error": r.parser_error,
                    }
                )
                proxies += receipt_amount_proxies(r, results[-1]["meta"])
            # In the user's currency, as everywhere else; a receipt in another
            # currency says what it was recorded as
            convert_receipt_amounts(proxies, request.user)

        # 2. Fetch Bank Statements (if requested or no filter applied)
        if category_filter in [None, "statement"]:
            # SECURE: Filter spanning the relationship (Statement -> Account -> User)
            statements = (
                BankStatement.objects.filter(account__user=request.user)
                .annotate(transaction_count=Count("transactions"))
                .order_by("-id")
            )

            for s in statements:
                results.append(
                    {
                        "id": s.id,
                        "category": "statement",
                        "file_name": s.display_name
                        or (
                            os.path.basename(s.file_path) if s.file_path else "unknown"
                        ),
                        "file_path": s.file_path,
                        "uploaded_at": getattr(s, "created_at", None)
                        or getattr(s, "uploaded_at", None),
                        "meta": {
                            "account": s.account_id,
                            "merchant_name": None,
                            "amount": None,
                            "transaction_date": None,
                            "transaction_count": s.transaction_count,
                            "bank": s.bank,
                            "currency": s.currency,
                        },
                        "processing_status": s.processing_status,
                        "parser_error": s.parser_error,
                    }
                )

        # 3. If fetching both, sort the combined list by date (newest first)
        if not category_filter:
            # Assumes uploaded_at is a valid datetime object; fallback to string sorting if necessary
            results.sort(key=lambda x: str(x["uploaded_at"]), reverse=True)

        # 4. Fetch transactions if explicitly requested
        if category_filter == "transaction":
            transactions = Transaction.objects.filter(
                account__user=request.user
            ).order_by("-id")

            for t in transactions:
                results.append(
                    {
                        "id": t.id,
                        "category": "transaction",
                        "status": t.status,
                        "meta": {
                            "account": t.account_id,
                            "merchant_name": t.merchant,
                            "amount": t.amount,
                            "transaction_date": t.transaction_date,
                        },
                    }
                )

        return Response(results, status=status.HTTP_200_OK)


class StatementDetailView(APIView):
    """A bank statement together with the transactions read from it."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        # Spans the relationship to ensure the statement's account belongs to the user
        statement = get_object_or_404(
            BankStatement.objects.select_related("account"),
            pk=pk,
            account__user=request.user,
        )
        account = statement.account
        # Statements do not record the order of their lines, so date is the order
        transactions = statement.transactions.order_by(
            "transaction_date", "id"
        ).prefetch_related("tags", "items", "receipts")

        return Response(
            {
                "id": statement.id,
                "category": "statement",
                "file_name": statement.display_name
                or (
                    os.path.basename(statement.file_path)
                    if statement.file_path
                    else "unknown"
                ),
                "file_path": statement.file_path,
                "doc_type": statement.doc_type,
                "uploaded_at": statement.uploaded_at,
                "account": {
                    "id": account.id,
                    "account_name": account.account_name,
                    "card_type": account.card_type,
                    "account_number": account.account_number,
                },
                "currency": statement.currency,
                "transactions": convert_payloads([
                    {
                        "id": t.id,
                        "date": t.transaction_date,
                        "currency": t.currency,
                        # parsing stores a line's text as the merchant, and leaves the
                        # description empty; a line the user edited has both
                        "description": t.description or t.merchant,
                        "display_name": t.display_name or None,
                        "merchant": t.merchant if t.description else None,
                        "amount": str(t.amount),
                        "direction": statement_line_direction(t),
                        "status": t.status,
                        "matched": t.is_matched,
                        "tags": tags_payload(t),
                        "is_subscription": is_subscription(t),
                    }
                    for t in transactions
                ], request.user),
            },
            status=status.HTTP_200_OK,
        )


class UnifiedDocumentDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        category = request.query_params.get("category")

        if category not in ["receipt", "statement", "cash"]:
            return Response(
                {
                    "error": "A valid category ('receipt', 'statement' or 'cash') query parameter is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_path = None
        document = None

        # fetch the document
        if category in ["receipt", "cash"]:
            document = get_object_or_404(
                receipts_for_category(request.user, category), pk=pk
            )
            file_path = document.receipt_path

        elif category == "statement":
            # Spans the relationship to ensure the statement's account belongs to the user
            document = get_object_or_404(
                BankStatement, pk=pk, account__user=request.user
            )
            file_path = document.file_path

        # Clean up the physical file from the Docker volume
        if file_path:
            delete_stored_file(file_path)

        # Delete the database record
        document.delete()

        # Indicates successful delete
        return Response(status=status.HTTP_204_NO_CONTENT)


# Served types are fixed by extension so an upload can never come back as HTML.
# A CSV goes out as plain text: browsers download text/csv instead of showing it.
DOCUMENT_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".csv": "text/plain; charset=utf-8",
}


class UnifiedDocumentFileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        category = request.query_params.get("category")

        if category in ["receipt", "cash"]:
            document = get_object_or_404(
                receipts_for_category(request.user, category), pk=pk
            )
            file_path = document.receipt_path
        elif category == "statement":
            document = get_object_or_404(
                BankStatement, pk=pk, account__user=request.user
            )
            file_path = document.file_path
        else:
            return Response(
                {
                    "error": "A valid category ('receipt', 'statement' or 'cash') query parameter is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        extension = os.path.splitext(file_path or "")[1].lower()
        content_type = DOCUMENT_CONTENT_TYPES.get(extension)
        if not file_path or content_type is None:
            raise Http404("This document has no file.")

        try:
            stored_file = default_storage.open(file_path, "rb")
        except (FileNotFoundError, SuspiciousFileOperation):
            raise Http404("This document's file is missing.")

        response = FileResponse(
            stored_file,
            content_type=content_type,
            filename=document.display_name or os.path.basename(file_path),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class UnifiedDocumentRenameView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, *args, **kwargs):
        category = request.query_params.get("category")

        if category not in ["receipt", "statement", "cash"]:
            return Response(
                {
                    "error": "A valid category ('receipt', 'statement' or 'cash') query parameter is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DocumentRenameSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if category in ["receipt", "cash"]:
            document = get_object_or_404(
                receipts_for_category(request.user, category), pk=pk
            )
        else:
            document = get_object_or_404(
                BankStatement, pk=pk, account__user=request.user
            )

        document.display_name = serializer.validated_data["display_name"]
        document.save(update_fields=["display_name"])

        return Response(
            {
                "id": document.id,
                "category": category,
                "file_name": document.display_name,
            },
            status=status.HTTP_200_OK,
        )


class ManualEntryUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ManualEntrySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        account = None
        if validated_data.get("account"):
            account = get_object_or_404(
                Account, id=validated_data["account"], user=request.user
            )
        items_data = validated_data.get("items", [])
        line_tags, error = resolve_line_tags(request.user, items_data)
        if error:
            return error
        for item in items_data:
            item["cost"], item["direction"] = normalised_line(item["cost"], item["direction"])
        total_amount = (
            sum((signed(item["cost"], item["direction"]) for item in items_data), start=0) or None
        )

        document_record = Receipt.objects.create(
            user=request.user,
            account=account,
            currency=validated_data.get("currency")
            or (account.currency if account else request.user.currency),
            entry_type=validated_data["entry_type"],
            display_name=validated_data["display_name"],
            total_amount=total_amount,
        )

        items = Item.objects.bulk_create(
            [
                Item(
                    receipt=document_record,
                    item_name=item["name"],
                    unit_price=unit_price_for(item["cost"], item["quantity"]),
                    quantity=item["quantity"],
                    item_total=item["cost"],
                    merchant=item["merchant"],
                    date=item["date"],
                    direction=item["direction"],
                )
                for item in items_data
            ]
        )
        for item_record, item in zip(items, items_data):
            if item["tags"]:
                item_record.tags.set([line_tags[t] for t in item["tags"]])

        meta = {
            "account": account.id if account else None,
            "merchant_name": document_record.merchant_name,
            "amount": str(document_record.total_amount) if document_record.total_amount else None,
            "transaction_date": None,
            "entry_type": document_record.entry_type,
            "currency": document_record.currency,
            "items": [item_payload(it) for it in items],
        }
        convert_receipt_amounts(receipt_amount_proxies(document_record, meta), request.user)

        return Response(
            {
                "id": document_record.id,
                "category": "cash" if document_record.entry_type == "cash" else "receipt",
                "file_name": document_record.display_name,
                "file_path": None,
                "uploaded_at": document_record.uploaded_at,
                "meta": meta,
            },
            status=status.HTTP_201_CREATED,
        )


class TransactionTemplateListCreateView(generics.ListCreateAPIView):
    serializer_class = TransactionTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            TransactionTemplate.objects.filter(user=self.request.user)
            .prefetch_related(
                Prefetch(
                    "tags",
                    queryset=Tag.objects.available_to(self.request.user),
                )
            )
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TransactionTemplateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TransactionTemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TransactionTemplate.objects.filter(
            user=self.request.user
        ).prefetch_related(
            Prefetch(
                "tags",
                queryset=Tag.objects.available_to(self.request.user),
            )
        )


class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Tag.objects.available_to(self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        tags = sorted(queryset, key=lambda tag: (not tag.is_predefined, tag.name.lower()))
        serializer = self.get_serializer(tags, many=True)
        return Response(serializer.data)

    def _validate_parent(self, parent, instance=None):
        if parent is None:
            return
        if not Tag.objects.available_to(self.request.user).filter(pk=parent.pk).exists():
            raise DRFValidationError({"parent": "You can only nest tags under tags available to you."})

        ancestor = parent
        while instance is not None and ancestor is not None:
            if ancestor.pk == instance.pk:
                raise DRFValidationError({"parent": "A tag cannot be nested under itself or one of its descendants."})
            ancestor = ancestor.parent

    def perform_create(self, serializer):
        name = serializer.validated_data.get('name')
        self._validate_parent(serializer.validated_data.get("parent"))
        if Tag.objects.available_to(self.request.user).filter(name__iexact=name).exists():
            raise DRFValidationError({"name": "A tag with this name already exists."})
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        if self.get_object().is_predefined:
            raise DRFValidationError({"detail": "Cannot edit predefined default tags."})
        
        name = serializer.validated_data.get('name', self.get_object().name)
        if Tag.objects.available_to(self.request.user).filter(name__iexact=name).exclude(pk=self.get_object().pk).exists():
            raise DRFValidationError({"name": "A tag with this name already exists."})
            
        instance = self.get_object()
        parent = serializer.validated_data.get("parent", instance.parent)
        self._validate_parent(parent, instance)

        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_predefined:
            raise DRFValidationError({"detail": "Cannot delete predefined default tags."})
        try:
            instance.delete()
        except ProtectedError:
            raise DRFValidationError({"detail": "Cannot delete a tag that has child tags."})


class BudgetViewSet(viewsets.ModelViewSet):
    """A user's monthly budgets, one per tag. What has been spent against them
    is worked out on the dashboard from the line items."""

    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user).select_related("tag").order_by("tag__name")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SettingsView(APIView):
    """The user's preferences: for now, the currency every figure is reported in."""

    permission_classes = [IsAuthenticated]

    def payload(self, user):
        return {
            "currency": user.currency,
            "currencies": [{"code": code, "name": name} for code, name in sorted(CURRENCIES.items())],
        }

    def get(self, request, *args, **kwargs):
        return Response(self.payload(request.user), status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        currency = request.data.get("currency")
        if currency is not None:
            if not is_supported(currency):
                return Response(
                    {"error": f"'{currency}' is not a currency we have rates for."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            request.user.currency = currency
            request.user.save(update_fields=["currency"])
        return Response(self.payload(request.user), status=status.HTTP_200_OK)
