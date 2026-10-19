import calendar
import hashlib
import os
import random
import re
import sys
from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction as db_transaction
from django.utils import timezone

from core.models import Account, BankStatement, Item, Receipt, Tag, Transaction


ACCOUNT_NUMBER = "2048"
ACCOUNT_NAME = "Everyday Account"
ACCOUNT_CARD_TYPE = "Cheque"
DEFAULT_OPENING_BALANCE = Decimal("5000.00")
DEMO_STATEMENT_PREFIX = "Demo statement "

PREDEFINED_TAGS = {
    "Groceries",
    "Fuel",
    "Salary",
    "Woolworths",
    "Checkers",
    "Pick n Pay",
    "Spar",
}

CATEGORY_DATA = {
    "Groceries": {
        "merchants": ["Checkers", "Woolworths", "Pick n Pay", "Spar"],
        "minimum": 80,
        "maximum": 750,
        "weight": 18,
    },
    "Fuel": {
        "merchants": ["Engen", "Shell", "BP", "Sasol"],
        "minimum": 250,
        "maximum": 1100,
        "weight": 5,
    },
    "Transport": {
        "merchants": ["MyCiTi", "Uber", "Bolt", "Golden Arrow"],
        "minimum": 25,
        "maximum": 250,
        "weight": 8,
    },
    "Dining Out": {
        "merchants": ["Nando's", "RocoMamas", "Spur", "Local Restaurant"],
        "minimum": 100,
        "maximum": 650,
        "weight": 7,
    },
    "Coffee": {
        "merchants": ["Vida e Caffe", "Seattle Coffee", "Coffee Shop"],
        "minimum": 25,
        "maximum": 110,
        "weight": 7,
    },
    "Shopping": {
        "merchants": ["Takealot", "Mr Price", "Checkers", "Woolworths"],
        "minimum": 100,
        "maximum": 1800,
        "weight": 5,
    },
    "Health": {
        "merchants": ["Clicks", "Dis-Chem", "Pharmacy"],
        "minimum": 60,
        "maximum": 850,
        "weight": 3,
    },
    "Entertainment": {
        "merchants": ["Ster-Kinekor", "Event Cinema", "Gaming Store"],
        "minimum": 80,
        "maximum": 600,
        "weight": 4,
    },
    "Personal Care": {
        "merchants": ["Clicks", "Barber Shop", "Salon"],
        "minimum": 60,
        "maximum": 500,
        "weight": 3,
    },
    "Home": {
        "merchants": ["Builders Warehouse", "Home Store", "Hardware Shop"],
        "minimum": 80,
        "maximum": 900,
        "weight": 3,
    },
    "Education": {
        "merchants": ["Bookshop", "Online Course", "Stationery Shop"],
        "minimum": 80,
        "maximum": 700,
        "weight": 2,
    },
}

SUBSCRIPTIONS = [
    ("Netflix", Decimal("179.00"), (2023, 11)),
    ("Spotify", Decimal("75.00"), (2023, 11)),
    ("Google One", Decimal("39.00"), (2023, 11)),
    ("Gym Membership", Decimal("499.00"), (2023, 11)),
    ("Disney+", Decimal("159.00"), (2025, 6)),
    ("Canva", Decimal("149.00"), (2026, 2)),
]

GROCERY_ITEMS = [
    "Bread",
    "Milk",
    "Eggs",
    "Chicken",
    "Rice",
    "Apples",
    "Vegetables",
    "Yoghurt",
    "Coffee",
    "Cereal",
    "Cheese",
    "Pasta",
    "Cooking Oil",
    "Laundry Detergent",
]

CASH_MERCHANTS = [
    "Weekend Market",
    "Street Food Vendor",
    "Local Bakery",
    "Cash Taxi",
]

UNMATCHED_MERCHANTS = ["Checkers", "Woolworths", "Pick n Pay", "Spar"]


# ---------------------------------------------------------------------------
# Pure helpers (no database access)
# ---------------------------------------------------------------------------

def month_range():
    """Return every month from November 2023 through the current month."""
    today = timezone.localdate()
    months = []
    year, month = 2023, 11

    while (year, month) <= (today.year, today.month):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1

    return months


def make_amount(cents):
    """Convert an integer number of cents into a Decimal amount."""
    return Decimal(cents) / Decimal("100")


def split_amount(amount, count, rng):
    """Split a receipt total into positive item totals that add up exactly."""
    total_cents = int((amount * 100).to_integral_value())

    if total_cents < count:
        count = total_cents

    cuts = sorted(rng.sample(range(1, total_cents), count - 1))
    boundaries = [0, *cuts, total_cents]

    return [
        make_amount(boundaries[i + 1] - boundaries[i])
        for i in range(count)
    ]


def month_key(year, month):
    return f"{year:04d}-{month:02d}"


def stable_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_aware_date(day):
    return timezone.make_aware(
        datetime.combine(day, time.min),
        timezone.get_current_timezone(),
    )


def last_allowed_day(year, month, today):
    """Last day of the month, capped at today for the current month."""
    last_day = calendar.monthrange(year, month)[1]

    if (year, month) == (today.year, today.month):
        return min(last_day, today.day)

    return last_day


def namespace_for(username):
    """Ownership marker stored on every generated receipt."""
    return f"newspeak-demo:{username}"


def statement_hash_for(username, month):
    return stable_hash(f"demo-statement:{username}:{month}")


def generate_entries(username, seed, today):
    """
    Build a repeatable, fictional financial history.

    Expenses are negative; income and refunds are positive.
    Every generated entry has a stable key for safe reruns.
    No entry is ever dated after today.
    """
    rng = random.Random(seed)
    entries = []

    def add_entry(year, month, day, key, amount, category, merchant, description):
        if day > last_allowed_day(year, month, today):
            return

        amount = Decimal(amount).quantize(Decimal("0.01"))

        entries.append({
            "key": f"{month_key(year, month)}:{key}",
            "date": date(year, month, day),
            "amount": amount,
            "category": category,
            "merchant": merchant,
            "description": description,
        })

    for year, month in month_range():
        last_day = last_allowed_day(year, month, today)

        years_elapsed = year - 2023
        salary = Decimal("31000.00") * (
            Decimal("1.05") ** years_elapsed
        )

        # Monthly salary. The current month may not have been paid yet.
        add_entry(
            year, month, 25, "salary",
            salary.quantize(Decimal("0.01")),
            "Salary", "Employer Payroll", "Monthly salary",
        )

        # Rent rises gradually over time.
        rent = Decimal("8500.00") * (
            Decimal("1.05") ** years_elapsed
        )
        add_entry(
            year, month, 1, "rent", -rent,
            "Rent", "Monthly Landlord", "Monthly rent",
        )

        # Regular household expenses.
        for day, key, merchant, category, low, high in [
            (3, "electricity", "Electricity Provider", "Utilities", 650, 1100),
            (5, "internet", "Internet Provider", "Utilities", 650, 850),
            (7, "mobile", "Mobile Network", "Utilities", 250, 450),
        ]:
            amount = Decimal(rng.randint(low * 100, high * 100)) / 100
            add_entry(
                year, month, day, key, -amount,
                category, merchant, f"Monthly {key}",
            )

        # Subscriptions gradually accumulate over the years.
        for index, (merchant, amount, start) in enumerate(SUBSCRIPTIONS):
            if (year, month) < start:
                continue

            add_entry(
                year, month, 9 + index, f"subscription-{index}",
                -amount, "Subscriptions", merchant,
                f"{merchant} subscription",
            )

        # Regular day-to-day spending.
        count = rng.randint(40, 50)

        categories = list(CATEGORY_DATA)
        weights = [CATEGORY_DATA[c]["weight"] for c in categories]

        for index in range(count):
            category = rng.choices(categories, weights=weights, k=1)[0]
            data = CATEGORY_DATA[category]
            merchant = rng.choice(data["merchants"])

            cents = rng.randint(
                data["minimum"] * 100,
                data["maximum"] * 100,
            )

            # December is more expensive; January is a cutback month.
            if month == 12:
                cents = int(cents * 1.35)
            elif month == 1:
                cents = int(cents * 0.80)

            amount = make_amount(cents)
            day = rng.randint(1, last_day)

            add_entry(
                year, month, day, f"variable-{index:03d}",
                -amount, category, merchant,
                f"{category} purchase",
            )

        # An occasional unexpected expense.
        if month in (3, 8) and year >= 2024:
            amount = Decimal(rng.randint(150000, 750000)) / 100
            add_entry(
                year, month, rng.randint(1, last_day), "emergency",
                -amount, "Emergency", "Unexpected Expense",
                "Unexpected expense",
            )

        # Occasional refunds make the history more realistic.
        if month in (5, 11) and year >= 2024:
            amount = Decimal(rng.randint(25000, 120000)) / 100
            add_entry(
                year, month, rng.randint(1, last_day), "refund",
                amount, "Refunds", "Retail Refund",
                "Purchase refund",
            )

    entries.sort(key=lambda item: (item["date"], item["key"]))
    return entries


def generate_receipt_plans(entries, seed, today, username):
    """
    Plan every demo receipt up front, without touching the database.

    Three kinds are produced:
      matched   - linked to a grocery bank transaction (reconciled)
      cash      - a manual cash receipt with no bank transaction
      unmatched - a receipt with no bank transaction, for the review queue

    Planning first lets the dry run report exactly what would be written and
    lets us check every file hash for collisions before any write happens.
    """
    plans = []

    for index, (year, month) in enumerate(month_range()):
        prefix = month_key(year, month)

        grocery_entries = [
            entry for entry in entries
            if entry["date"].year == year
            and entry["date"].month == month
            and entry["category"] == "Groceries"
            and entry["amount"] < 0
        ]

        if index % 3 == 1 and grocery_entries:
            entry = grocery_entries[0]
            total = abs(entry["amount"])
            item_amounts = split_amount(total, 4, random.Random(seed + index))
            item_names = random.Random(seed + index).sample(
                GROCERY_ITEMS, len(item_amounts)
            )

            plans.append({
                "kind": "matched",
                "file_hash": stable_hash(
                    f"demo-receipt:{username}:{entry['key']}"
                ),
                "entry_key": entry["key"],
                "date": entry["date"],
                "merchant": entry["merchant"],
                "total": total,
                "display_name": f"Demo receipt {prefix}.json",
                "items": list(zip(item_names, item_amounts)),
            })

        if index % 4 == 3:
            rng = random.Random(seed + index + 9000)
            cash_date = date(
                year, month, min(20, calendar.monthrange(year, month)[1])
            )

            if cash_date <= today:
                cash_total = make_amount(rng.randint(18000, 90000))
                merchant = rng.choice(CASH_MERCHANTS)
                cash_amounts = split_amount(cash_total, 3, rng)
                cash_names = rng.sample(GROCERY_ITEMS, len(cash_amounts))

                plans.append({
                    "kind": "cash",
                    "file_hash": stable_hash(
                        f"demo-cash:{username}:{prefix}"
                    ),
                    "entry_key": None,
                    "date": cash_date,
                    "merchant": merchant,
                    "total": cash_total,
                    "display_name": f"Demo cash receipt {prefix}",
                    "items": list(zip(cash_names, cash_amounts)),
                })

        if index % 5 == 2:
            rng = random.Random(seed + index + 7000)

            # Keep the total away from every bank amount in the month so the
            # receipt is genuinely unmatched.
            month_cents = {
                int(abs(entry["amount"]) * 100)
                for entry in entries
                if entry["date"].year == year
                and entry["date"].month == month
            }

            cents = rng.randint(15000, 120000)
            while cents in month_cents:
                cents = rng.randint(15000, 120000)

            total = make_amount(cents)
            day = rng.randint(1, last_allowed_day(year, month, today))
            merchant = rng.choice(UNMATCHED_MERCHANTS)
            item_amounts = split_amount(total, 3, rng)
            item_names = rng.sample(GROCERY_ITEMS, len(item_amounts))

            plans.append({
                "kind": "unmatched",
                "file_hash": stable_hash(
                    f"demo-unmatched:{username}:{prefix}:unmatched"
                ),
                "entry_key": None,
                "date": date(year, month, day),
                "merchant": merchant,
                "total": total,
                "display_name": f"Demo unmatched receipt {prefix}.json",
                "items": list(zip(item_names, item_amounts)),
            })

    return plans


# ---------------------------------------------------------------------------
# Ownership: exact, verifiable markers (a display name is never proof)
# ---------------------------------------------------------------------------

def candidate_statement_hashes(username):
    """
    Every statement file hash this seeder could ever have produced for this
    username, mapped to its month. A real uploaded statement has the hash of
    its file's bytes, so it cannot appear in this set by accident.
    """
    mapping = {}

    for year in range(2023, 2036):
        for month in range(1, 13):
            key = month_key(year, month)
            mapping[statement_hash_for(username, key)] = key

    return mapping


class DemoOwnership:
    """
    Positive identification of demo-owned records.

    receipt      user + account + namespace marker stored in raw_data
    statement    on the demo account AND file_hash recomputes from the
                 username and a month (display name is ignored)
    transaction  on the demo account AND hash key matches this seeder's exact
                 grammar AND linked to a positively identified demo statement

    If the demo user or account does not exist yet (None), nothing can be
    owned, so every pre-existing record counts as foreign.
    """

    def __init__(self, username, user_id=None, account_id=None):
        self.username = username
        self.user_id = user_id
        self.account_id = account_id
        self.namespace = namespace_for(username)
        self.hash_prefix = f"demo:{username}:"
        self.statement_hashes = candidate_statement_hashes(username)
        self._tx_pattern = re.compile(
            rf"^demo:{re.escape(username)}:(\d{{4}}-\d{{2}}):"
            r"(salary|rent|electricity|internet|mobile"
            r"|subscription-\d+|variable-\d{3}|emergency|refund)$"
        )

    def receipt(self, receipt):
        if self.user_id is None or self.account_id is None:
            return False

        data = receipt.raw_data

        return (
            receipt.user_id == self.user_id
            and receipt.account_id == self.account_id
            and isinstance(data, dict)
            and data.get("demo") is True
            and data.get("namespace") == self.namespace
        )

    def statement(self, statement):
        if self.account_id is None or statement.account_id != self.account_id:
            return False

        month = self.statement_hashes.get(statement.file_hash)

        # The deterministic hash establishes the marker; the name must also
        # agree with it. A display name alone never establishes ownership.
        return (
            month is not None
            and statement.display_name == f"{DEMO_STATEMENT_PREFIX}{month}.csv"
        )


    def transaction(self, transaction, demo_statement_ids):
        if (
            self.account_id is None
            or transaction.account_id != self.account_id
            or transaction.statement_id not in demo_statement_ids
        ):
            return False

        match = self._tx_pattern.fullmatch(transaction.hashkey or "")
        if match is None:
            return False

        month = match.group(1)

        # The transaction's month in its hash key must agree with the exact
        # deterministic hash of the statement it belongs to.
        expected_hash = statement_hash_for(self.username, month)

        return BankStatement.objects.filter(
            pk=transaction.statement_id,
            account_id=self.account_id,
            file_hash=expected_hash,
            display_name=f"{DEMO_STATEMENT_PREFIX}{month}.csv",
        ).exists()

def validate_demo_user(user, email):
    """Refuse to reuse a user that is not clearly the demo identity."""
    if user.is_staff or user.is_superuser:
        raise CommandError(
            "The chosen demo username belongs to a privileged account. "
            "Choose a different username."
        )

    if (
        user.email.strip().casefold() != email.strip().casefold()
        or user.first_name != "Demo"
        or user.last_name != "User"
    ):
        raise CommandError(
            "The username already exists but does not match the configured "
            "demo identity. Refusing to modify it."
        )


def ensure_account_is_demo_only(account, owner):
    """
    Refuse to reuse an account holding anything not positively identified as
    created by this command, including receipts that merely point at one of
    the account's transactions.
    """
    problems = []

    statements = list(BankStatement.objects.filter(account=account))
    demo_statement_ids = {s.pk for s in statements if owner.statement(s)}

    if len(demo_statement_ids) != len(statements):
        problems.append("bank statements not positively identified as demo")

    if any(
        not owner.transaction(t, demo_statement_ids)
        for t in Transaction.objects.filter(account=account)
    ):
        problems.append("transactions not positively identified as demo")

    receipts = {r.pk: r for r in Receipt.objects.filter(account=account)}
    for receipt in Receipt.objects.filter(transaction__account=account):
        receipts.setdefault(receipt.pk, receipt)

    if any(not owner.receipt(r) for r in receipts.values()):
        problems.append(
            "receipts not positively identified as demo (including receipts "
            "linked to this account's transactions from another account)"
        )

    # Demo-marked receipts must not have links to transactions that this
    # seeder cannot positively identify as belonging to this demo account.
    for receipt in receipts.values():
        if receipt.transaction_id is not None:
            linked_transaction = Transaction.objects.filter(
                pk=receipt.transaction_id
            ).first()

            if (
                linked_transaction is None
                or not owner.transaction(
                    linked_transaction, demo_statement_ids
                )
            ):
                problems.append(
                    f"receipt {receipt.pk} links to a transaction that "
                    "is not positively identified as demo data"
                )

        linked_item_transactions = Transaction.objects.filter(
            items__receipt=receipt
        ).distinct()

        for linked_transaction in linked_item_transactions:
            if not owner.transaction(
                linked_transaction, demo_statement_ids
            ):
                problems.append(
                    f"receipt {receipt.pk} has an item linked to a transaction "
                    "that is not positively identified as demo data"
                )
                break

    if problems:
        raise CommandError(
            f"Account {account.account_number} already contains "
            + "; ".join(problems)
            + ". Refusing to touch it."
        )


def find_collisions(receipt_hashes, statement_hashes, owner):
    """
    Read-only pre-flight: any record we are about to create or update that
    already exists must be owned by the demo account.
    """
    problems = []

    tx_queryset = Transaction.objects.filter(
        hashkey__startswith=owner.hash_prefix
    )
    if owner.account_id is not None:
        tx_queryset = tx_queryset.exclude(account_id=owner.account_id)
    foreign_transactions = tx_queryset.count()

    if foreign_transactions:
        problems.append(
            f"{foreign_transactions} transaction(s) with demo hash keys "
            "belong to another account"
        )

    for statement in BankStatement.objects.filter(
        file_hash__in=list(statement_hashes)
    ):
        if not owner.statement(statement):
            problems.append(
                f"statement hash {statement.file_hash[:12]}... already "
                "exists and is not owned by the demo account"
            )

    for receipt in Receipt.objects.filter(file_hash__in=list(receipt_hashes)):
        if not owner.receipt(receipt):
            problems.append(
                f"receipt hash {receipt.file_hash[:12]}... already exists "
                "and is not owned by the demo account"
            )

    if problems:
        shown = "; ".join(problems[:5])
        extra = len(problems) - 5
        suffix = f" (and {extra} more)" if extra > 0 else ""
        raise CommandError(
            f"Ownership check failed before writing anything: {shown}{suffix}."
        )


# ---------------------------------------------------------------------------
# Guarded writes: verify ownership BEFORE modifying anything
# ---------------------------------------------------------------------------

def upsert_transaction(account, hashkey, fields, owner, demo_statement_ids):
    existing = Transaction.objects.filter(hashkey=hashkey).first()

    if existing is None:
        return Transaction.objects.create(hashkey=hashkey, **fields)

    if not owner.transaction(existing, demo_statement_ids):
        raise CommandError(
            f"Transaction {hashkey!r} already exists, but its ownership "
            "could not be verified. Refusing to modify it."
        )

    for name, value in fields.items():
        setattr(existing, name, value)

    existing.save()
    return existing


def upsert_statement(account, file_hash, fields, owner):
    existing = BankStatement.objects.filter(file_hash=file_hash).first()

    if existing is None:
        return BankStatement.objects.create(
            account=account,
            file_hash=file_hash,
            **fields,
        )

    month = owner.statement_hashes.get(file_hash)

    if (
        existing.account_id != account.id
        or month is None
        or not owner.statement(existing)
    ):
        raise CommandError(
            "A bank statement with a demo file hash already exists, "
            "but its ownership could not be verified. Refusing to modify it."
        )

    for name, value in fields.items():
        setattr(existing, name, value)

    existing.save()
    return existing


def upsert_receipt(user, account, owner, plan, linked_transaction):
    fields = {
        "transaction": linked_transaction,
        "account": account,
        "entry_type": "cash" if plan["kind"] == "cash" else "receipt",
        "merchant_name": plan["merchant"],
        "total_amount": plan["total"],
        "raw_data": {
            "demo": True,
            "namespace": owner.namespace,
            "kind": plan["kind"],
            "matched": plan["kind"] == "matched",
        },
        "display_name": plan["display_name"],
        "transaction_date": make_aware_date(plan["date"]),
        "processing_status": "completed",
    }

    existing = list(Receipt.objects.filter(file_hash=plan["file_hash"]))

    for receipt in existing:
        if not owner.receipt(receipt):
            raise CommandError(
                f"A receipt with file hash {plan['file_hash'][:12]}... "
                "already exists and is not owned by the demo account. "
                "Refusing to modify it."
            )

    if len(existing) > 1:
        raise CommandError(
            f"More than one receipt has file hash {plan['file_hash'][:12]}.... "
            "Refusing to guess which one to update."
        )

    if existing:
        receipt = existing[0]
        for name, value in fields.items():
            setattr(receipt, name, value)
        receipt.save()
        return receipt

    return Receipt.objects.create(
        user=user, file_hash=plan["file_hash"], **fields
    )


def sync_items(receipt, pairs, merchant, item_date, tag):
    """
    Make a receipt's items exactly match `pairs` of (name, total).

    The receipt has already been verified as demo-owned, so its items are
    safe to update. Leftover items from a previous run are removed.
    """
    names = [name for name, _ in pairs]

    for name, total in pairs:
        item, _ = Item.objects.update_or_create(
            receipt=receipt,
            item_name=name,
            defaults={
                "unit_price": total,
                "quantity": Decimal("1.000"),
                "item_total": total,
                "merchant": merchant,
                "date": item_date,
                "direction": "debit",
                "display_name": name,
            },
        )
        item.tags.set([tag])

    extra_items = Item.objects.filter(receipt=receipt).exclude(
        item_name__in=names
    )

    for item in extra_items.iterator():
        item.delete()

# ---------------------------------------------------------------------------
# Stale-record cleanup: positively identify, verify containment, then delete
# ---------------------------------------------------------------------------

def plan_stale_records(
    user,
    account,
    owner,
    expected_receipts,
    expected_transactions,
    expected_statements,
):
    """
    Read-only cleanup plan.

    Only positively identified demo records can be candidates for deletion.
    Refuse cleanup if deleting a candidate could affect a record that will
    survive the cleanup.
    """
    statements = list(BankStatement.objects.filter(account=account))

    # Every statement on this account must be positively identified.
    foreign_statements = [
        statement for statement in statements
        if not owner.statement(statement)
    ]

    if foreign_statements:
        raise CommandError(
            "Cleanup found a statement on the demo account whose ownership "
            "could not be verified. Refusing to continue."
        )

    demo_statement_ids = {statement.pk for statement in statements}

    stale_statement_ids = {
        statement.pk
        for statement in statements
        if statement.file_hash not in expected_statements
    }

    # Verify ownership before checking whether the key is expected.
    transactions = list(Transaction.objects.filter(account=account))
    stale_transaction_ids = set()

    for transaction in transactions:
        if not owner.transaction(transaction, demo_statement_ids):
            raise CommandError(
                "Cleanup found a transaction on the demo account whose "
                "ownership could not be verified. Refusing to continue."
            )

        if transaction.hashkey not in expected_transactions:
            stale_transaction_ids.add(transaction.pk)

    receipts = list(
        Receipt.objects.filter(user=user, account=account)
    )

    stale_receipt_ids = set()

    for receipt in receipts:
        if not owner.receipt(receipt):
            raise CommandError(
                "Cleanup found a receipt on the demo account whose ownership "
                "could not be verified. Refusing to continue."
            )

        if receipt.file_hash not in expected_receipts:
            stale_receipt_ids.add(receipt.pk)

    # A stale receipt must not be deleted if it links to a transaction
    # that will survive cleanup: Receipt.delete() can change its status.
    for receipt in receipts:
        if receipt.pk not in stale_receipt_ids:
            continue

        linked_transaction_ids = set(
            Item.objects.filter(receipt=receipt)
            .exclude(transaction_id__isnull=True)
            .values_list("transaction_id", flat=True)
        )

        if receipt.transaction_id is not None:
            linked_transaction_ids.add(receipt.transaction_id)

        unsafe_links = linked_transaction_ids - stale_transaction_ids

        if unsafe_links:
            raise CommandError(
                f"Stale receipt {receipt.pk} is linked to transaction(s) "
                "that would survive cleanup. Refusing to delete it."
            )

    # A stale transaction must not have any surviving receipt or item links.
    for transaction_id in stale_transaction_ids:
        linked_receipt_ids = set(
            Receipt.objects.filter(transaction_id=transaction_id)
            .values_list("pk", flat=True)
        )

        linked_item_receipt_ids = set(
            Item.objects.filter(transaction_id=transaction_id)
            .values_list("receipt_id", flat=True)
        )

        all_linked_receipt_ids = linked_receipt_ids | linked_item_receipt_ids
        surviving_receipt_ids = all_linked_receipt_ids - stale_receipt_ids

        if surviving_receipt_ids:
            raise CommandError(
                f"Stale transaction {transaction_id} is still linked to "
                "receipt(s) that would survive cleanup. Refusing to delete it."
            )

    # Deleting a statement can delete unmatched transactions or detach
    # matched ones. Every transaction still attached to a stale statement
    # must therefore also be in the stale transaction deletion plan.
    for statement_id in stale_statement_ids:
        linked_transaction_ids = set(
            Transaction.objects.filter(statement_id=statement_id)
            .values_list("pk", flat=True)
        )

        unsafe_transactions = linked_transaction_ids - stale_transaction_ids

        if unsafe_transactions:
            raise CommandError(
                f"Stale statement {statement_id} has transaction(s) that "
                "would survive cleanup. Refusing to delete it."
            )

    return {
        "receipts": stale_receipt_ids,
        "transactions": stale_transaction_ids,
        "statements": stale_statement_ids,
    }


def delete_stale_records(plan):
    """
    Delete only a verified plan.

    Delete receipts first so their model-level cleanup runs, then transactions,
    then statements. The caller must run this inside transaction.atomic().
    """
    deleted_receipts = 0
    deleted_transactions = 0
    deleted_statements = 0

    for receipt in list(
        Receipt.objects.filter(pk__in=list(plan["receipts"]))
    ):
        receipt.delete()
        deleted_receipts += 1

    for transaction_obj in list(
        Transaction.objects.filter(pk__in=list(plan["transactions"]))
    ):
        transaction_obj.delete()
        deleted_transactions += 1

    for statement in list(
        BankStatement.objects.filter(pk__in=list(plan["statements"]))
    ):
        statement.delete()
        deleted_statements += 1


    return (
        deleted_receipts,
        deleted_transactions,
        deleted_statements,
    )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Create or update the fictional Newspeak demonstration dataset."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="newspeak_demo")
        parser.add_argument("--email", default="demo@example.com")
        parser.add_argument("--password", default=None)
        parser.add_argument("--seed", type=int, default=20261016)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run every safety check and report the plan; write nothing.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive confirmation before writing.",
        )

    def confirm_write(self, username, assume_yes):
        if assume_yes:
            return

        if not sys.stdin.isatty():
            raise CommandError(
                "Refusing to write without confirmation. Run interactively "
                "or pass --yes."
            )

        answer = input(
            f"Type the username '{username}' to write this dataset: "
        )

        if answer.strip() != username:
            raise CommandError("Confirmation did not match. Nothing written.")

    def handle(self, *args, **options):
        username = options["username"]
        email = options["email"]
        password = options["password"] or os.environ.get("DEMO_USER_PASSWORD")
        seed = options["seed"]
        today = timezone.localdate()
        hash_prefix = f"demo:{username}:"

        entries = generate_entries(username, seed, today)
        receipt_plans = generate_receipt_plans(entries, seed, today, username)

        expected_transactions = {
            f"{hash_prefix}{entry['key']}" for entry in entries
        }
        expected_statements = {
            statement_hash_for(
                username, month_key(entry["date"].year, entry["date"].month)
            )
            for entry in entries
        }
        expected_receipts = {plan["file_hash"] for plan in receipt_plans}

        # ---- Read-only pre-flight: nothing below writes to the database ----
        User = get_user_model()
        existing_user = User.objects.filter(username=username).first()
        existing_account = None

        if existing_user is not None:
            validate_demo_user(existing_user, email)
            existing_account = Account.objects.filter(
                user=existing_user, account_number=ACCOUNT_NUMBER
            ).first()

        owner = DemoOwnership(
            username,
            existing_user.id if existing_user is not None else None,
            existing_account.id if existing_account is not None else None,
        )

        stale_plan = None

        if existing_account is not None:
            ensure_account_is_demo_only(existing_account, owner)
            stale_plan = plan_stale_records(
                existing_user, existing_account, owner,
                expected_receipts, expected_transactions, expected_statements,
            )

        find_collisions(expected_receipts, expected_statements, owner)

        net_movement = sum(
            (entry["amount"] for entry in entries), Decimal("0.00")
        )

        # `funds` is never modified by this command. Whether it is an opening
        # balance or a running balance depends on the application, so a
        # projection is only offered when it cannot double-count: a brand-new
        # account that holds no demo transactions yet.
        if existing_account is None:
            stored_funds = DEFAULT_OPENING_BALANCE
            projection = stored_funds + net_movement
        else:
            stored_funds = Decimal(existing_account.funds)
            already_seeded = Transaction.objects.filter(
                account=existing_account
            ).exists()
            projection = None if already_seeded else stored_funds + net_movement

        if projection is not None and projection < 0:
            raise CommandError(
                "The projected balance is negative. Review the dataset "
                "before creating the demo account."
            )

        kinds = {"matched": 0, "cash": 0, "unmatched": 0}
        for plan in receipt_plans:
            kinds[plan["kind"]] += 1

        db = connection.settings_dict
        self.stdout.write(
            f"Target database: {db.get('NAME')} "
            f"on {db.get('HOST') or 'local socket'}"
        )
        self.stdout.write(f"Demo username: {username}")
        self.stdout.write(
            f"Date range: {entries[0]['date']} to {entries[-1]['date']}"
        )
        self.stdout.write(f"Planned bank transactions: {len(entries)}")
        self.stdout.write(
            f"Planned receipts: {kinds['matched']} matched, "
            f"{kinds['cash']} cash, {kinds['unmatched']} unmatched"
        )
        if stale_plan is not None:
            self.stdout.write(
                "Stale demo records that would be removed: "
                f"{len(stale_plan['receipts'])} receipts, "
                f"{len(stale_plan['transactions'])} transactions, "
                f"{len(stale_plan['statements'])} statements"
            )
        self.stdout.write(
            f"Stored account funds: R{stored_funds:,.2f} "
            "(this command never modifies it)"
        )
        self.stdout.write(f"Net movement of generated data: R{net_movement:,.2f}")
        if projection is not None:
            self.stdout.write(
                f"Projected balance: R{projection:,.2f} (an estimate that "
                "assumes funds is an opening balance excluding these "
                "transactions; not a stored value)"
            )
        else:
            self.stdout.write(
                "Projected balance: skipped, because the account already "
                "holds demo transactions and stored funds may already "
                "include them."
            )
        self.stdout.write("Ownership, collision and containment checks passed.")
        self.stdout.write("All generated financial data is fictional.")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: no records written."))
            return

        self.confirm_write(username, options["yes"])

        with db_transaction.atomic():
            user = User.objects.filter(username=username).first()

            if user is None:
                if not password:
                    raise CommandError(
                        "A password is required for a new demo user. "
                        "Pass --password or set DEMO_USER_PASSWORD."
                    )

                user = User(
                    username=username,
                    email=email,
                    first_name="Demo",
                    last_name="User",
                )
                user.set_password(password)
                user.save()
                self.stdout.write("Created demo user.")
            else:
                validate_demo_user(user, email)
                self.stdout.write("Reusing existing demo user.")

            # Existing accounts were verified as demo-only above, and their
            # details (name, card type, funds) are left unchanged.
            account = Account.objects.filter(
                user=user, account_number=ACCOUNT_NUMBER
            ).first()

            if account is None:
                account = Account.objects.create(
                    user=user,
                    account_number=ACCOUNT_NUMBER,
                    account_name=ACCOUNT_NAME,
                    card_type=ACCOUNT_CARD_TYPE,
                    funds=DEFAULT_OPENING_BALANCE,
                )
                self.stdout.write("Created demo account.")
            else:
                self.stdout.write("Reusing existing demo account.")

            owner = DemoOwnership(username, user.id, account.id)
            funds_before = Decimal(account.funds)


            # Recheck ownership inside the transaction immediately before
            # writing demo data.
            ensure_account_is_demo_only(account, owner)
            find_collisions(expected_receipts, expected_statements, owner)

            stale_plan = plan_stale_records(
                user,
                account,
                owner,
                expected_receipts,
                expected_transactions,
                expected_statements,
            )

            tags = {}

            for name in {
                entry["category"] for entry in entries
            } | PREDEFINED_TAGS:
                tag_owner = None if name in PREDEFINED_TAGS else user
                tag, _ = Tag.objects.get_or_create(name=name, owner=tag_owner)
                tags[name] = tag

            statements = {}
            transactions = {}

            for entry in entries:
                day = entry["date"]
                month = month_key(day.year, day.month)

                if month not in statements:
                    statements[month] = upsert_statement(
                        account,
                        statement_hash_for(username, month),
                        {
                            "display_name": f"{DEMO_STATEMENT_PREFIX}{month}.csv",
                            "doc_type": "CSV",
                            "processing_status": "completed",
                        },
                        owner,
                    )

                amount = entry["amount"]
                merchant = entry["merchant"]

                transaction_obj = upsert_transaction(
                    account,
                    f"{hash_prefix}{entry['key']}",
                    {
                        "account": account,
                        "statement": statements[month],
                        "amount": amount,
                        "transaction_type": "Income" if amount > 0 else "Expense",
                        "transaction_date": day,
                        "merchant": merchant,
                        "description": entry["description"],
                        "status": "Pending",
                        "is_cash": False,
                        "display_name": entry["description"],
                    },
                    owner,
                    {statement.pk for statement in statements.values()},
                )

                transaction_tags = [tags[entry["category"]]]

                if merchant in tags:
                    transaction_tags.append(tags[merchant])

                transaction_obj.tags.set(transaction_tags)
                transactions[entry["key"]] = transaction_obj

            for plan in receipt_plans:
                linked = (
                    transactions[plan["entry_key"]]
                    if plan["entry_key"] is not None
                    else None
                )

                receipt = upsert_receipt(user, account, owner, plan, linked)

                if linked is not None:
                    linked.status = "Reconciled"
                    linked.save(update_fields=["status"])

                sync_items(
                    receipt,
                    plan["items"],
                    plan["merchant"],
                    plan["date"],
                    tags["Groceries"],
                )

            # Re-verify against the database as it is now, then delete.
            # Any failure raises and rolls back the whole run.
            stale_plan = plan_stale_records(
                user, account, owner,
                expected_receipts, expected_transactions, expected_statements,
            )
            stale_receipts, stale_transactions, stale_statements = (
                delete_stale_records(stale_plan)
            )

            account.refresh_from_db()
            funds_after = Decimal(account.funds)

        self.stdout.write(
            f"Receipts: {kinds['matched']} matched, {kinds['cash']} cash, "
            f"{kinds['unmatched']} unmatched."
        )
        self.stdout.write(
            f"Stale demo records removed: {stale_receipts} receipts, "
            f"{stale_transactions} transactions, {stale_statements} statements."
        )
        self.stdout.write(
            f"Stored account funds: R{funds_before:,.2f} before, "
            f"R{funds_after:,.2f} after."
        )

        if funds_after != funds_before:
            self.stdout.write(
                self.style.WARNING(
                    "Stored funds changed during the run, so the application "
                    "appears to update funds from transactions. This command "
                    "does not set funds itself; treat any projection as an "
                    "estimate only."
                )
            )
        else:
            self.stdout.write(
                "Stored funds were not changed by this run."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo dataset ready. {len(entries)} bank transactions."
            )
        )
        self.stdout.write(
            "Existing records outside this demo account were not targeted."
        )