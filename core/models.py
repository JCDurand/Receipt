from decimal import Decimal

from django.db import models, transaction as db_transaction
from django.db.models import CASCADE, SET_NULL, Q
import uuid
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


DEFAULT_CURRENCY = "ZAR"


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=255, unique=True)
    # The currency every figure is reported in: documents held in another
    # currency are converted to it, at the rate on the day of each line.
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        name = f"{self.first_name} {self.last_name}"
        return name if name else self.username


class Account(models.Model):
    CARD_TYPES = (
        ("Cheque", "Cheque"),
        ("Savings", "Savings"),
        ("Credit", "Credit"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")
    account_name = models.CharField(max_length=100)
    card_type = models.CharField(max_length=20, choices=CARD_TYPES, default="Cheque")
    account_number = models.CharField(max_length=4)
    # The opening balance: what the account held when it was created. Its
    # balance since is this, moved by every line dated after that day (see
    # core.balances); the opening balance itself never changes by itself.
    funds = models.DecimalField(max_digits=13, decimal_places=2, default=0.00)
    # What the account's funds are held in
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY)
    # When the account was created, which is when its opening balance applied
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # An account number identifies the account, so the same user
        # creating it twice (even under a different name) is a duplicate.
        unique_together = ("user", "account_number")

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.account_name}".strip()


class BankStatement(models.Model):
    DOC_TYPES = (
        ("CSV", "CSV"),
        ("PDF", "PDF"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    file_path = models.CharField(max_length=255, null=True, blank=True)
    display_name = models.CharField(max_length=255, null=True, blank=True)
    doc_type = models.CharField(max_length=10, null=True, blank=True, choices=DOC_TYPES)
    file_hash = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    PROCESSING_STATUS = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUS, default="completed"
    )
    parser_error = models.TextField(null=True, blank=True)
    # The bank whose statement layout this was read with ("investec", "fnb", ...)
    bank = models.CharField(max_length=50, blank=True, default="")
    # What the statement's lines are in (they may differ from the account's)
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY)

    class Meta:
        constraints = [
            # The same file content uploaded twice to the same account is a
            # duplicate upload, not a second statement. NULL hashes (statements
            # from before file_hash existed) never compare equal, so they are
            # left out of the constraint rather than treated as duplicates of
            # each other.
            models.UniqueConstraint(
                fields=["account", "file_hash"],
                condition=Q(file_hash__isnull=False),
                name="unique_statement_per_account_file_hash",
            ),
        ]

    def __str__(self):
        return f"Statement {self.id} for {self.account.account_name}".strip()


class TagQuerySet(models.QuerySet):
    def available_to(self, user):
        """
        The tags a user may see and assign: the predefined ones and their own.
        Hidden tags are the system's own (see Tag.is_hidden) and are never among them.
        """
        return self.filter(models.Q(owner__isnull=True) | models.Q(owner=user), is_hidden=False)

    def subscription(self):
        """
        The hidden tag which marks a line item as a subscription. Its migration
        creates it; should it ever be missing, it is made again rather than
        every subscription feature failing.
        """
        tag, _ = self.get_or_create(name=Tag.SUBSCRIPTION, owner=None, defaults={"is_hidden": True})
        return tag


class Tag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    # Predefined tags have no owner and are shared by every user; a tag a user
    # creates belongs to them alone.
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="tags"
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subtags",
    )
    # A tag the system keeps for itself, such as the one marking subscriptions.
    # It is never listed, offered or shown as one of a line item's tags, and
    # changing a line item's tags leaves it on.
    is_hidden = models.BooleanField(default=False)

    # The hidden tag's name: never shown, and not a name a user would give a
    # tag of their own (which may not share a predefined tag's name)
    SUBSCRIPTION = "system:subscription"

    objects = TagQuerySet.as_manager()

    class Meta:
        constraints = [
            # Two users may each have their own "Groceries"...
            models.UniqueConstraint(fields=["owner", "name"], name="unique_tag_per_owner"),
            # ...but NULL owners never compare equal, so predefined tags need
            # their own rule
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(owner__isnull=True),
                name="unique_predefined_tag",
            ),
        ]

    @property
    def is_predefined(self):
        return self.owner_id is None

    @property
    def is_subscription(self):
        return self.is_hidden and self.owner_id is None and self.name == Tag.SUBSCRIPTION

    def __str__(self):
        return f"{self.name}"


class TransactionQuerySet(models.QuerySet):
    def unmatched(self):
        """Statement lines which no receipt, and no receipt item, has been matched to."""
        return self.filter(receipts__isnull=True, items__isnull=True)

    def matched(self):
        """Statement lines which a receipt, or one of a receipt's items, has been matched to."""
        return self.filter(Q(receipts__isnull=False) | Q(items__isnull=False)).distinct()


def delete_unmatched_lines(collector, field, sub_objs, using):
    """
    What happens to a bank statement's lines when the statement is deleted (the
    `on_delete` of Transaction.statement).

    The lines nothing was matched to went with the statement and are deleted
    with it. A line which a receipt was matched to stays, because the receipt is
    bound to it and receipts outlive their statements: it no longer belongs to a
    statement, and the receipt stays matched to it.

    This is the model's rule rather than the delete view's, so it holds however a
    statement is deleted (the admin, a bulk delete, an account's cascade).
    """
    unmatched = Transaction.objects.unmatched().filter(pk__in=sub_objs.values("pk"))
    CASCADE(collector, field, unmatched, using)
    SET_NULL(collector, field, sub_objs.exclude(pk__in=unmatched.values("pk")), using)


class Transaction(models.Model):
    STATUS = (
        ("Pending", "Pending"),
        ("Reconciled", "Reconciled"),
        ("Unreconciled", "Unreconciled"),
    )

    TYPE_CHOICES = (
        ("Income", "Income"),
        ("Expense", "Expense"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
    )
    
    statement = models.ForeignKey(
        BankStatement,
        on_delete=delete_unmatched_lines,
        null=True,
        blank=True,
        related_name="transactions",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # What the amount is in. Kept on the line (not read from its statement) so
    # that it survives the statement being deleted.
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY)
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="Expense")
    transaction_date = models.DateField()
    merchant = models.CharField(max_length=255, null=True, blank=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    hashkey = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="Pending")
    is_cash = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, blank=True, related_name="transactions")
    # What the user chose to call the line. The line's own text (merchant and
    # description) is left as it was read so that the same statement still
    # reads the same when it is uploaded again; this is only what is shown.
    display_name = models.CharField(max_length=255, blank=True, default="")

    objects = TransactionQuerySet.as_manager()

    @property
    def is_matched(self):
        """Whether a receipt, or one of a receipt's items, has been matched to this line."""
        return bool(self.items.all()) or bool(self.receipts.all())

    def unreconcile_if_unmatched(self):
        """A line which nothing is matched to any more (its receipt was deleted) is no longer reconciled."""
        if self.status == "Reconciled" and not (self.receipts.exists() or self.items.exists()):
            self.status = "Pending"
            self.save(update_fields=["status"])

    def __str__(self):
        return f"{self.merchant or 'Unknown'} - {self.amount}".strip()


class Receipt(models.Model):
    ENTRY_TYPES = (
        ("cash", "Cash"),
        ("receipt", "Receipt"),
        ("statement", "Statement"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="receipts"
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )
    # Only set for records created through the manual-entry form; uploaded
    # scans/parsed receipts leave this blank.
    entry_type = models.CharField(
        max_length=10, choices=ENTRY_TYPES, null=True, blank=True
    )
    merchant_name = models.CharField(max_length=255, null=True, blank=True)
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    # What the receipt's total and its items' prices are in
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY)
    raw_data = models.JSONField(null=True, blank=True)
    receipt_path = models.CharField(max_length=255, null=True, blank=True)
    display_name = models.CharField(max_length=255, null=True, blank=True)
    uploaded_at = models.DateTimeField(default=timezone.now, editable=False)
    transaction_date = models.DateTimeField(default=timezone.now, editable=False)
    file_hash = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    PROCESSING_STATUS = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUS, default="completed"
    )
    parser_error = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            # Same rule as a bank statement's: the same file content uploaded
            # twice by the same user is a duplicate, not a second receipt.
            models.UniqueConstraint(
                fields=["user", "file_hash"],
                condition=Q(file_hash__isnull=False),
                name="unique_receipt_per_user_file_hash",
            ),
        ]

    def total_follows_items(self):
        """
        Whether the receipt's total is what its items add up to, as a manual entry's
        is, rather than a total of its own: one read from the receipt, or the amount
        of the statement line it was matched to.
        """
        added_up = sum((item.signed_total for item in self.items.all()), Decimal(0))
        return self.total_amount is not None and self.total_amount == added_up

    def set_total_from_items(self):
        """Make the receipt's total what its items add up to (nothing, if it has none)."""
        added_up = sum((item.signed_total for item in self.items.all()), Decimal(0))
        self.total_amount = added_up or None
        self.save(update_fields=["total_amount"])

    def delete(self, *args, **kwargs):
        """
        A receipt takes its line items with it: they cannot exist without it. The
        statement line it was matched to stays, as the bank's record, but is no
        longer reconciled by it.
        """
        line_ids = set(self.items.values_list("transaction_id", flat=True))
        line_ids.add(self.transaction_id)
        line_ids.discard(None)
        with db_transaction.atomic():
            result = super().delete(*args, **kwargs)
            for line in Transaction.objects.filter(pk__in=line_ids):
                line.unreconcile_if_unmatched()
        return result

    def __str__(self):
        receipt_name = (
            f"{self.user.first_name} {self.user.last_name}"
            if self.user
            else "Unassigned"
        )
        return f"{receipt_name} - Receipt #{self.id} - {self.merchant_name}".strip()


DIRECTIONS = (
    ("debit", "Debit"),
    ("credit", "Credit"),
)


class Item(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name="items")
    item_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1.000)
    item_total = models.DecimalField(max_digits=10, decimal_places=2)
    tags = models.ManyToManyField(Tag, blank=True, related_name="items")
    # What the user chose to call the item. `item_name` is left as it was read so
    # that the same receipt still reads the same when it is uploaded again; this
    # is only what is shown.
    display_name = models.CharField(max_length=255, blank=True, default="")
    # Where and when it was bought, if that differs from (or is not on) the receipt
    # itself, and whether it took money out (debit) or paid money back (credit).
    # The total is always stored positive; the direction says which way it went.
    merchant = models.CharField(max_length=255, blank=True, default="")
    date = models.DateField(null=True, blank=True)
    direction = models.CharField(max_length=6, choices=DIRECTIONS, default="debit")
    # The bank statement line this item was matched to on the Review page
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )

    @property
    def signed_total(self):
        """What the item adds to its receipt's total: money out counts for it, money back against it."""
        return -self.item_total if self.direction == "credit" else self.item_total

    def delete(self, *args, **kwargs):
        """
        Deleting an item on its own takes it out of its receipt's total, if that is
        what the total is made of, and leaves the statement line it was matched to
        unreconciled if nothing else is matched to it.
        """
        receipt = self.receipt
        line_id = self.transaction_id
        with db_transaction.atomic():
            follows_items = receipt.total_follows_items()
            result = super().delete(*args, **kwargs)
            if follows_items:
                receipt.set_total_from_items()
            for line in Transaction.objects.filter(pk=line_id):
                line.unreconcile_if_unmatched()
        return result

    def __str__(self):
        return self.item_name


class TransactionTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="templates")
    search_string = models.CharField(max_length=255)
    merchant_name = models.CharField(max_length=255)
    tags = models.ManyToManyField(Tag, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"'{self.search_string}' -> '{self.merchant_name}'"


def this_month_start():
    today = timezone.localdate()
    return today.replace(day=1)


class Budget(models.Model):
    """
    How much a user means to spend each month, under one tag or (with no tag)
    overall. A line item counts towards the budget of every tag it has, and of
    every tag above those.

    A budget applies for a period of `months` months from `start_month`, or for
    every month from then on when `months` is empty.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="budgets")
    tag = models.ForeignKey(
        Tag, on_delete=models.CASCADE, related_name="budgets", null=True, blank=True
    )
    monthly_limit = models.DecimalField(max_digits=10, decimal_places=2)
    # The first day of the first month the budget applies to
    start_month = models.DateField(default=this_month_start)
    # How many months it applies for; empty for no end
    months = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "tag"], name="unique_budget_per_tag"),
            # NULL tags never compare equal, so the overall budget needs its own rule
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(tag__isnull=True),
                name="unique_overall_budget",
            ),
        ]

    def __str__(self):
        what = self.tag.name if self.tag else "Overall"
        return f"{what}: {self.monthly_limit} a month"


class ExchangeRate(models.Model):
    """What one unit of `base` was worth in `quote` on a day, as published
    (a cache of the exchange rate service's answers). Days the market was shut
    have no row: the nearest earlier one applies."""

    base = models.CharField(max_length=3)
    quote = models.CharField(max_length=3)
    date = models.DateField()
    rate = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["base", "quote", "date"], name="unique_exchange_rate_day"),
        ]
        indexes = [models.Index(fields=["base", "quote", "date"])]

    def __str__(self):
        return f"{self.date} 1 {self.base} = {self.rate} {self.quote}"
