"""
Tests for the seed_demo_data management command.

Django runs these against a throwaway database (test_<name>) that it creates and
destroys itself, so your real data is never touched. Time is frozen at
2026-10-16 so the dataset is deterministic.

Place at core/test_seed_demo_data.py and run:

    docker compose exec web python manage.py test core.test_seed_demo_data -v 2

What is proven here:
  * Fresh run     - exact dataset size, linking, totals, nothing future-dated
  * Idempotency   - reruns change nothing (same primary keys, no duplicates)
  * Isolation     - other users' rows are byte-for-byte identical afterwards
  * Collisions    - a clashing hash / key / identity refuses the run, writes nothing
  * Ownership     - decoys and stray records block the run and are never deleted
  * Cleanup       - stale demo records are removed, nothing else
  * Atomicity     - a failure midway leaves no partial dataset
  * Safety gates  - dry run writes nothing; no write without confirmation
"""
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, Max, Sum
from django.test import TestCase
from django.utils import timezone as django_timezone

from core.management.commands import seed_demo_data as seed
from core.models import Account, BankStatement, Item, Receipt, Tag, Transaction

User = get_user_model()

FIXED_TODAY = date(2026, 10, 16)


class FrozenTimezone:
    """Delegates to django.utils.timezone but pins localdate()."""

    def __getattr__(self, name):
        return getattr(django_timezone, name)

    def localdate(self, *args, **kwargs):
        return FIXED_TODAY


class SeedTestCase(TestCase):
    USERNAME = "newspeak_demo"
    PASSWORD = "test-only-password-123"

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(seed, "timezone", FrozenTimezone())
        patcher.start()
        self.addCleanup(patcher.stop)

    @classmethod
    def seed_command(cls, *args):
        out = StringIO()
        call_command(
            "seed_demo_data", "--yes", f"--password={cls.PASSWORD}", *args,
            stdout=out,
        )
        return out.getvalue()

    def run_seed(self, *args):
        return self.seed_command(*args)

    # ---- expected data ---------------------------------------------------

    def expected(self, seed_value=20261016):
        entries = seed.generate_entries(self.USERNAME, seed_value, FIXED_TODAY)
        plans = seed.generate_receipt_plans(
            entries, seed_value, FIXED_TODAY, self.USERNAME
        )
        return entries, plans

    def demo_user(self):
        return User.objects.get(username=self.USERNAME)

    def demo_account(self):
        return Account.objects.get(
            user=self.demo_user(), account_number=seed.ACCOUNT_NUMBER
        )

    # ---- snapshots -------------------------------------------------------

    def demo_snapshot(self):
        user, account = self.demo_user(), self.demo_account()
        return {
            "statements": list(
                BankStatement.objects.filter(account=account)
                .order_by("file_hash")
                .values_list("pk", "file_hash", "display_name")
            ),
            "transactions": list(
                Transaction.objects.filter(account=account)
                .order_by("hashkey")
                .values_list(
                    "pk", "hashkey", "amount", "status",
                    "transaction_date", "statement_id",
                )
            ),
            "receipts": list(
                Receipt.objects.filter(user=user)
                .order_by("file_hash")
                .values_list("pk", "file_hash", "total_amount", "transaction_id")
            ),
            "items": list(
                Item.objects.filter(receipt__user=user)
                .order_by("receipt_id", "item_name")
                .values_list("receipt_id", "item_name", "item_total")
            ),
        }

    def outside_snapshot(self):
        """Every row that does not belong to the demo user, all columns."""
        demo = self.USERNAME

        def rows(queryset):
            return list(queryset.order_by("pk").values())

        transactions = Transaction.objects.exclude(account__user__username=demo)
        items = Item.objects.exclude(receipt__user__username=demo)

        return {
            "users": rows(User.objects.exclude(username=demo)),
            "accounts": rows(Account.objects.exclude(user__username=demo)),
            "statements": rows(
                BankStatement.objects.exclude(account__user__username=demo)
            ),
            "transactions": rows(transactions),
            "receipts": rows(Receipt.objects.exclude(user__username=demo)),
            "items": rows(items),
            "tags": rows(Tag.objects.exclude(owner__username=demo)),
            "transaction_tags": {
                t.pk: sorted(t.tags.values_list("pk", flat=True))
                for t in transactions
            },
            "item_tags": {
                i.pk: sorted(i.tags.values_list("pk", flat=True))
                for i in items
            },
        }

    # ---- fixtures for "real" users ----------------------------------------

    def make_real_user_data(
        self, label, account_number,
        receipt_hash=None, tx_hashkey=None, statement_hash=None,
    ):
        user = User.objects.create_user(
            username=f"{label}_real",
            email=f"{label}@example.com",
            password="not-a-demo-password",
        )
        account = Account.objects.create(
            user=user,
            account_number=account_number,
            account_name=f"{label} cheque",
            card_type="Cheque",
            funds=Decimal("1234.56"),
        )
        statement = BankStatement.objects.create(
            account=account,
            file_hash=statement_hash or f"real-{label}-statement",
            display_name=f"{label}_statement.pdf",
            doc_type="PDF",
            processing_status="completed",
        )
        transaction = Transaction.objects.create(
            hashkey=tx_hashkey or f"real-{label}-tx",
            account=account,
            statement=statement,
            amount=Decimal("-123.45"),
            transaction_type="Expense",
            transaction_date=date(2026, 9, 1),
            merchant="Real Merchant",
            description="real purchase",
            status="Pending",
            is_cash=False,
            display_name="real purchase",
        )
        receipt = Receipt.objects.create(
            user=user,
            file_hash=receipt_hash or f"real-{label}-receipt",
            transaction=transaction,
            account=account,
            entry_type="receipt",
            merchant_name="Real Merchant",
            total_amount=Decimal("123.45"),
            raw_data={"source": "real upload"},
            display_name=f"{label}_receipt.json",
            transaction_date=django_timezone.make_aware(datetime(2026, 9, 1)),
            processing_status="completed",
        )
        item = Item.objects.create(
            receipt=receipt,
            item_name="Real Item",
            unit_price=Decimal("123.45"),
            quantity=Decimal("1.000"),
            item_total=Decimal("123.45"),
            merchant="Real Merchant",
            date=date(2026, 9, 1),
            direction="debit",
            display_name="Real Item",
        )
        tag = Tag.objects.create(name=f"{label} tag", owner=user)
        transaction.tags.set([tag])
        item.tags.set([tag])

        return {
            "user": user, "account": account, "statement": statement,
            "transaction": transaction, "receipt": receipt, "item": item,
        }

    def database_counts(self):
        return {
            model.__name__: model.objects.count()
            for model in (
                User, Account, BankStatement, Transaction,
                Receipt, Item, Tag,
            )
        }

    def assert_nothing_exists(self, before):
        self.assertEqual(
            self.database_counts(),
            before,
            "The command changed database record counts",
        )



class SeededTestCase(SeedTestCase):
    """Runs the seeder once for the whole class; each test rolls back to it."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with mock.patch.object(seed, "timezone", FrozenTimezone()):
            cls.first_run_output = cls.seed_command()


# ---------------------------------------------------------------------------
# Fresh run
# ---------------------------------------------------------------------------

class FreshRunTests(SeededTestCase):
    def test_dataset_size_matches_the_plan(self):
        entries, plans = self.expected()
        self.assertEqual(len(entries), 1956)

        account, user = self.demo_account(), self.demo_user()

        self.assertEqual(
            Transaction.objects.filter(account=account).count(), 1956
        )
        self.assertEqual(
            BankStatement.objects.filter(account=account).count(), 36
        )

        receipts = list(Receipt.objects.filter(user=user))
        self.assertEqual(len(receipts), 27)
        self.assertEqual(
            Counter(r.raw_data["kind"] for r in receipts),
            Counter(matched=12, cash=8, unmatched=7),
        )

    def test_receipt_links_and_reconciliation(self):
        user, account = self.demo_user(), self.demo_account()

        for receipt in Receipt.objects.filter(user=user):
            if receipt.raw_data["kind"] == "matched":
                self.assertIsNotNone(receipt.transaction_id)
                self.assertEqual(receipt.transaction.status, "Reconciled")
                self.assertEqual(
                    abs(receipt.transaction.amount), receipt.total_amount
                )
            else:
                self.assertIsNone(receipt.transaction_id)

        self.assertEqual(
            Transaction.objects.filter(
                account=account, status="Reconciled"
            ).count(),
            12,
        )

    def test_item_totals_add_up_to_each_receipt_total(self):
        for receipt in Receipt.objects.filter(user=self.demo_user()):
            total = Item.objects.filter(receipt=receipt).aggregate(
                total=Sum("item_total")
            )["total"]
            self.assertEqual(total, receipt.total_amount, receipt.display_name)

    def test_nothing_is_dated_in_the_future(self):
        latest = Transaction.objects.filter(
            account=self.demo_account()
        ).aggregate(latest=Max("transaction_date"))["latest"]
        self.assertLessEqual(latest, FIXED_TODAY)

    def test_demo_records_belong_only_to_the_demo_user(self):
        user, account = self.demo_user(), self.demo_account()
        self.assertEqual(Receipt.objects.exclude(user=user).count(), 0)
        self.assertEqual(Transaction.objects.exclude(account=account).count(), 0)
        self.assertEqual(Account.objects.exclude(user=user).count(), 0)

    def test_stored_funds_are_not_modified_by_the_seeder(self):
        self.assertEqual(
            self.demo_account().funds,
            seed.DEFAULT_OPENING_BALANCE,
            "Stored funds changed during seeding, so the application updates "
            "funds from transactions. That is useful to know, not necessarily "
            "a bug: it changes how the projected balance should be read.",
        )

    def test_only_predefined_tags_are_global(self):
        self.assertEqual(
            set(
                Tag.objects.filter(owner__isnull=True, is_hidden=False)
                .values_list("name", flat=True)
            ),
            seed.PREDEFINED_TAGS,
        )

        subscription_tag = Tag.objects.get(
            name=Tag.SUBSCRIPTION, owner__isnull=True
        )
        self.assertTrue(subscription_tag.is_hidden)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class IdempotencyTests(SeededTestCase):
    def test_rerun_changes_nothing(self):
        before = self.demo_snapshot()
        out = self.run_seed()

        self.assertEqual(before, self.demo_snapshot())
        self.assertIn("Reusing existing demo user.", out)
        self.assertIn(
            "Stale demo records removed: 0 receipts, 0 transactions, "
            "0 statements.",
            out,
        )

    def test_three_runs_never_duplicate_anything(self):
        before = self.demo_snapshot()
        self.run_seed()
        self.run_seed()

        self.assertEqual(before, self.demo_snapshot())

        for model, field in (
            (Transaction, "hashkey"),
            (Receipt, "file_hash"),
            (BankStatement, "file_hash"),
        ):
            duplicates = (
                model.objects.values(field)
                .annotate(n=Count("pk"))
                .filter(n__gt=1)
            )
            self.assertFalse(duplicates.exists(), model.__name__)

        self.assertEqual(Transaction.objects.count(), 1956)
        self.assertEqual(Receipt.objects.count(), 27)

    def test_dry_run_on_existing_account_writes_nothing(self):
        before = self.demo_snapshot()
        out = self.run_seed("--dry-run")

        self.assertEqual(before, self.demo_snapshot())
        self.assertIn("Dry run: no records written.", out)
        self.assertIn("Projected balance: skipped", out)


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------

class IsolationTests(SeedTestCase):
    def test_other_users_data_is_identical_after_every_run(self):
        self.make_real_user_data("alice", "7001")
        self.make_real_user_data("bob", "7002")

        # Pre-create the shared tags so the only thing left to prove is that
        # the seeder leaves existing rows alone.
        for name in seed.PREDEFINED_TAGS:
            Tag.objects.get_or_create(name=name, owner=None)

        before = self.outside_snapshot()

        self.run_seed()
        self.assertEqual(before, self.outside_snapshot(), "after first run")

        self.run_seed()
        self.assertEqual(before, self.outside_snapshot(), "after second run")

    def test_another_users_account_with_the_same_number_is_left_alone(self):
        self.make_real_user_data("alice", seed.ACCOUNT_NUMBER)
        before = self.outside_snapshot()

        self.run_seed()

        self.assertEqual(before, self.outside_snapshot())
        self.assertEqual(
            Account.objects.filter(account_number=seed.ACCOUNT_NUMBER).count(),
            2,
        )

    def test_missing_shared_tags_are_the_only_cross_user_side_effect(self):
        self.make_real_user_data("alice", "7001")
        before_tag_ids = set(Tag.objects.values_list("pk", flat=True))

        self.run_seed()

        created = Tag.objects.exclude(pk__in=before_tag_ids)
        for tag in created:
            if tag.owner_id is None:
                self.assertIn(tag.name, seed.PREDEFINED_TAGS)
            else:
                self.assertEqual(tag.owner.username, self.USERNAME)


# ---------------------------------------------------------------------------
# Collisions and identity: refuse, and write nothing
# ---------------------------------------------------------------------------

class CollisionTests(SeedTestCase):
    def assert_refused_without_writing(self, **collision):
        self.make_real_user_data("alice", "7001", **collision)
        before = self.outside_snapshot()

        with self.assertRaises(CommandError):
            self.run_seed()

        self.assertFalse(User.objects.filter(username=self.USERNAME).exists())
        self.assertEqual(before, self.outside_snapshot())

    def test_receipt_hash_owned_by_someone_else(self):
        _, plans = self.expected()
        self.assert_refused_without_writing(receipt_hash=plans[0]["file_hash"])

    def test_transaction_hash_key_owned_by_someone_else(self):
        self.assert_refused_without_writing(
            tx_hashkey=f"demo:{self.USERNAME}:2024-01:rent"
        )

    def test_statement_hash_owned_by_someone_else(self):
        self.assert_refused_without_writing(
            statement_hash=seed.statement_hash_for(self.USERNAME, "2024-01")
        )

    def test_privileged_user_with_the_demo_username_is_refused(self):
        User.objects.create_user(
            username=self.USERNAME, email="demo@example.com", password="x",
            first_name="Demo", last_name="User", is_staff=True,
        )

        with self.assertRaises(CommandError):
            self.run_seed()

        self.assertTrue(User.objects.get(username=self.USERNAME).is_staff)
        self.assertEqual(Account.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_existing_user_with_a_different_identity_is_refused(self):
        User.objects.create_user(
            username=self.USERNAME, email="someone@else.com", password="x",
            first_name="Real", last_name="Person",
        )

        with self.assertRaises(CommandError):
            self.run_seed()

        user = User.objects.get(username=self.USERNAME)
        self.assertEqual(user.email, "someone@else.com")
        self.assertEqual(Account.objects.count(), 0)


# ---------------------------------------------------------------------------
# Ownership: decoys and strays block the run and are never deleted
# ---------------------------------------------------------------------------

class OwnershipGuardTests(SeededTestCase):
    def assert_refused_and_intact(self, expect_present):
        before = self.demo_snapshot()

        with self.assertRaises(CommandError):
            self.run_seed()

        self.assertEqual(before, self.demo_snapshot())
        self.assertTrue(expect_present())

    def test_statement_named_like_a_demo_statement_is_not_trusted(self):
        decoy = BankStatement.objects.create(
            account=self.demo_account(),
            file_hash="decoy-not-a-demo-hash",
            display_name="Demo statement 2024-01.csv",
            doc_type="CSV",
            processing_status="completed",
        )
        self.assert_refused_and_intact(
            lambda: BankStatement.objects.filter(pk=decoy.pk).exists()
        )

    def test_unmarked_receipt_on_the_demo_account_is_not_trusted(self):
        stray = Receipt.objects.create(
            user=self.demo_user(),
            file_hash="stray-receipt",
            transaction=None,
            account=self.demo_account(),
            entry_type="receipt",
            merchant_name="Real Merchant",
            total_amount=Decimal("10.00"),
            raw_data={},
            display_name="stray.json",
            transaction_date=django_timezone.make_aware(datetime(2026, 9, 1)),
            processing_status="completed",
        )
        self.assert_refused_and_intact(
            lambda: Receipt.objects.filter(pk=stray.pk).exists()
        )

    def test_non_demo_transaction_on_the_demo_account_is_not_trusted(self):
        account = self.demo_account()
        statement = BankStatement.objects.filter(account=account).first()
        foreign = Transaction.objects.create(
            hashkey="real:bank:row",
            account=account,
            statement=statement,
            amount=Decimal("-5.00"),
            transaction_type="Expense",
            transaction_date=date(2026, 9, 1),
            merchant="Real Merchant",
            description="real",
            status="Pending",
            is_cash=False,
            display_name="real",
        )
        self.assert_refused_and_intact(
            lambda: Transaction.objects.filter(pk=foreign.pk).exists()
        )

    def test_someone_elses_receipt_pointing_at_a_demo_transaction(self):
        real = self.make_real_user_data("mallory", "7003")
        demo_transaction = Transaction.objects.filter(
            account=self.demo_account()
        ).first()
        # update() avoids any model-level save logic: we are only testing the
        # seeder's reaction to the link.
        Receipt.objects.filter(pk=real["receipt"].pk).update(
            transaction=demo_transaction
        )
        outside_before = self.outside_snapshot()

        self.assert_refused_and_intact(
            lambda: Receipt.objects.filter(pk=real["receipt"].pk).exists()
        )
        self.assertEqual(outside_before, self.outside_snapshot())


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

class CleanupTests(SeededTestCase):
    def test_stale_demo_records_are_removed_and_nothing_else(self):
        self.make_real_user_data("alice", "7001")
        baseline = self.demo_snapshot()
        outside_before = self.outside_snapshot()

        user, account = self.demo_user(), self.demo_account()
        month = "2035-01"

        stale_statement = BankStatement.objects.create(
            account=account,
            file_hash=seed.statement_hash_for(self.USERNAME, month),
            display_name=f"{seed.DEMO_STATEMENT_PREFIX}{month}.csv",
            doc_type="CSV",
            processing_status="completed",
        )
        stale_transaction = Transaction.objects.create(
            hashkey=f"demo:{self.USERNAME}:{month}:rent",
            account=account,
            statement=stale_statement,
            amount=Decimal("-9999.00"),
            transaction_type="Expense",
            transaction_date=date(2026, 1, 1),
            merchant="Monthly Landlord",
            description="stale",
            status="Pending",
            is_cash=False,
            display_name="stale",
        )
        stale_receipt = Receipt.objects.create(
            user=user,
            file_hash="stale-demo-receipt",
            transaction=None,
            account=account,
            entry_type="receipt",
            merchant_name="Spar",
            total_amount=Decimal("50.00"),
            raw_data={
                "demo": True,
                "namespace": seed.namespace_for(self.USERNAME),
                "kind": "unmatched",
                "matched": False,
            },
            display_name="stale.json",
            transaction_date=django_timezone.make_aware(datetime(2026, 1, 1)),
            processing_status="completed",
        )
        stale_item = Item.objects.create(
            receipt=stale_receipt,
            item_name="Bread",
            unit_price=Decimal("50.00"),
            quantity=Decimal("1.000"),
            item_total=Decimal("50.00"),
            merchant="Spar",
            date=date(2026, 1, 1),
            direction="debit",
            display_name="Bread",
        )

        out = self.run_seed()

        self.assertFalse(BankStatement.objects.filter(pk=stale_statement.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=stale_transaction.pk).exists())
        self.assertFalse(Receipt.objects.filter(pk=stale_receipt.pk).exists())
        self.assertFalse(Item.objects.filter(pk=stale_item.pk).exists())
        self.assertIn(
            "Stale demo records removed: 1 receipts, 1 transactions, "
            "1 statements.",
            out,
        )
        self.assertEqual(baseline, self.demo_snapshot())
        self.assertEqual(outside_before, self.outside_snapshot())

    def test_changing_the_seed_is_all_or_nothing(self):
        """
        A different seed produces different records. The command must either
        complete the swap correctly or refuse and change nothing. It must never
        leave a half-converted dataset.
        """
        self.make_real_user_data("alice", "7001")
        before = self.demo_snapshot()
        outside_before = self.outside_snapshot()

        try:
            self.run_seed("--seed", "1")
        except CommandError:
            self.assertEqual(before, self.demo_snapshot())
            self.assertEqual(outside_before, self.outside_snapshot())
            return

        entries, plans = self.expected(1)
        account, user = self.demo_account(), self.demo_user()

        self.assertEqual(
            set(Transaction.objects.filter(account=account)
                .values_list("hashkey", flat=True)),
            {f"demo:{self.USERNAME}:{e['key']}" for e in entries},
        )
        self.assertEqual(
            set(Receipt.objects.filter(user=user)
                .values_list("file_hash", flat=True)),
            {p["file_hash"] for p in plans},
        )
        self.assertEqual(outside_before, self.outside_snapshot())


# ---------------------------------------------------------------------------
# Atomicity and safety gates
# ---------------------------------------------------------------------------


class AtomicityTests(SeedTestCase):
    def test_failure_midway_leaves_nothing_behind(self):
        before = self.database_counts()
        real_sync_items = seed.sync_items
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 5:
                raise RuntimeError("simulated failure")
            return real_sync_items(*args, **kwargs)

        with mock.patch.object(seed, "sync_items", flaky):
            with self.assertRaises(RuntimeError):
                self.run_seed()

        self.assert_nothing_exists(before)




class SafetyGateTests(SeedTestCase):
    def test_dry_run_on_an_empty_database_writes_nothing(self):
        before = self.database_counts()
        out = self.run_seed("--dry-run")

        self.assert_nothing_exists(before)
        self.assertIn("Dry run: no records written.", out)
        self.assertIn("Planned bank transactions: 1956", out)
        self.assertIn(
            "Planned receipts: 12 matched, 8 cash, 7 unmatched", out
        )

    def test_no_write_without_confirmation_when_not_interactive(self):
        before = self.database_counts()
        fake_sys = mock.Mock()
        fake_sys.stdin.isatty.return_value = False

        with mock.patch.object(seed, "sys", fake_sys):
            with self.assertRaises(CommandError):
                call_command(
                    "seed_demo_data", f"--password={self.PASSWORD}",
                    stdout=StringIO(),
                )

        self.assert_nothing_exists(before)

    def test_wrong_confirmation_writes_nothing(self):
        before = self.database_counts()
        fake_sys = mock.Mock()
        fake_sys.stdin.isatty.return_value = True

        with mock.patch.object(seed, "sys", fake_sys), \
                mock.patch("builtins.input", return_value="not-the-username"):
            with self.assertRaises(CommandError):
                call_command(
                    "seed_demo_data", f"--password={self.PASSWORD}",
                    stdout=StringIO(),
                )

        self.assert_nothing_exists(before)

    def test_new_demo_user_needs_a_password(self):
        before = self.database_counts()
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", "--yes", stdout=StringIO())

        self.assert_nothing_exists(before)