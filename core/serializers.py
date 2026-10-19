from decimal import Decimal

from rest_framework import serializers
from .models import Transaction, BankStatement, Item, TransactionTemplate, Tag, Account, Receipt, Budget
from .receipt_parsing import unit_price_for
from .currency import CURRENCIES

# The smallest quantity an Item can have (it keeps three decimal places, for weights)
MIN_QUANTITY = Decimal("0.001")

DIRECTIONS = ["debit", "credit"]

class TagSerializer(serializers.ModelSerializer):
    is_predefined = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tag
        fields = ("id", "name", "parent", "is_predefined")
        
class TransactionSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        # Tags are set through the ownership-checked tag endpoint, so that a
        # transaction cannot be given another user's tag
        read_only_fields = ("tags",)


class BankstatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatement
        fields = "__all__"


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = "__all__"


class ParsedItemSerializer(serializers.Serializer):
    """A line item read from a receipt by the parse endpoint, sent back on upload."""

    name = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, default=1, min_value=0
    )
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    # What the user added to the line in the upload dialog
    merchant = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    date = serializers.DateField(required=False, allow_null=True, default=None)
    direction = serializers.ChoiceField(choices=DIRECTIONS, default="debit")
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class ParsedTransactionSerializer(serializers.Serializer):
    """A bank statement line read by the parse endpoint, sent back (as edited) on upload."""

    name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    merchant = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    date = serializers.DateField()
    direction = serializers.ChoiceField(choices=DIRECTIONS)
    # Always positive: the direction says which way the money went
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class TransactionTemplateSerializer(serializers.ModelSerializer):
    merchant_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.all(), required=False)
    class Meta:
        model = TransactionTemplate
        fields = ['id', 'user', 'search_string', 'merchant_name', 'tags', 'created_at']
        read_only_fields = ['user', 'created_at']

    def validate_search_string(self, value):
        cleaned_value = value.strip()
        if not cleaned_value:
            raise serializers.ValidationError("Search string cannot be empty or just whitespace.")
        return cleaned_value

    def validate_tags(self, value):
        user = self.context["request"].user
        tag_ids = {tag.pk for tag in value}
        available_ids = set(
            Tag.objects.available_to(user)
            .filter(pk__in=tag_ids)
            .values_list("pk", flat=True)
        )
        if available_ids != tag_ids:
            raise serializers.ValidationError("One or more tags do not exist.")
        return value

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user = self.context["request"].user
        representation["tags"] = [
            tag.pk
            for tag in instance.tags.all()
            if tag.owner_id is None or tag.owner_id == user.pk
        ]
        return representation

class UnifiedDocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True)
    category = serializers.ChoiceField(choices=["receipt", "statement"], required=True)
    account = serializers.UUIDField(required=False, allow_null=True)
    bank = serializers.CharField(
        max_length=50, required=False, allow_blank=True
    )
    display_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    # What the document's amounts are in; the account's currency if left out
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES), required=False)
    merchant_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    transaction_date = serializers.DateField(required=False, allow_null=True)
    # The line items the client got from the parse endpoint and showed the
    # user. Sent as a JSON string in the multipart form. When present (even if
    # empty) they are saved as-is; when absent the server parses the file itself.
    items = serializers.JSONField(required=False)
    # The same for a statement's transactions: what the parse endpoint found,
    # as the user then edited it. When present they are saved as-is.
    transactions = serializers.JSONField(required=False)

    def validate_items(self, value):
        items = ParsedItemSerializer(data=value, many=True)
        items.is_valid(raise_exception=True)
        return items.validated_data

    def validate_transactions(self, value):
        transactions = ParsedTransactionSerializer(data=value, many=True)
        transactions.is_valid(raise_exception=True)
        return transactions.validated_data

    def validate(self, attrs):
        # Enforce account presence for bank statements
        if attrs.get("category") == "statement" and not attrs.get("account"):
            raise serializers.ValidationError(
                {
                    "account": "An account ID is required when uploading a bank statement."
                }
            )
        return attrs


class DocumentRenameSerializer(serializers.Serializer):
    display_name = serializers.CharField(
        max_length=255, required=True, allow_blank=False, trim_whitespace=True
    )


class LineItemDetailsSerializer(serializers.Serializer):
    """
    The details of a saved line item which the user can change, any of them alone.
    A blank display name goes back to the line's own name, and a blank merchant
    clears it.
    """

    display_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, trim_whitespace=True
    )
    merchant = serializers.CharField(
        max_length=255, required=False, allow_blank=True, trim_whitespace=True
    )
    # A receipt item may have no date of its own (it then has its receipt's)
    date = serializers.DateField(required=False, allow_null=True)
    direction = serializers.ChoiceField(choices=DIRECTIONS, required=False)
    # Only a receipt item has one: how many of the item its line is for
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, min_value=MIN_QUANTITY
    )


class ManualEntryLineItemSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=255, allow_blank=False, trim_whitespace=True
    )
    # The line's total, whatever its quantity
    cost = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    # How many of the item the line is for (5 red apples for 70.00 is quantity 5)
    quantity = serializers.DecimalField(
        max_digits=10, decimal_places=3, default=1, min_value=MIN_QUANTITY
    )
    merchant = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    date = serializers.DateField(required=False, allow_null=True, default=None)
    direction = serializers.ChoiceField(choices=DIRECTIONS, default="debit")
    tags = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)

    def validate(self, attrs):
        try:
            unit_price_for(attrs["cost"], attrs["quantity"])
        except ValueError as error:
            raise serializers.ValidationError({"quantity": [str(error)]})
        return attrs


class ManualEntrySerializer(serializers.Serializer):
    display_name = serializers.CharField(
        max_length=255, required=True, allow_blank=False, trim_whitespace=True
    )
    entry_type = serializers.ChoiceField(
        choices=["cash", "receipt", "statement"], required=True
    )
    account = serializers.UUIDField(required=False, allow_null=True)
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES), required=False)
    items = ManualEntryLineItemSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        # Cash entries aren't tied to a bank account, and a receipt's account may
        # not be known yet ("reconcile later"); a statement entry needs one.
        if attrs.get("entry_type") == "statement" and not attrs.get("account"):
            raise serializers.ValidationError(
                {"account": "An account ID is required for a statement entry."}
            )
        return attrs

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = "__all__"
        # Matching to a bank transaction goes through the ownership-checked
        # link endpoint, and tagging through the ownership-checked tag
        # endpoint, not through editing an item.
        read_only_fields = ("transaction", "tags")

class BudgetSerializer(serializers.ModelSerializer):
    """
    A monthly spending limit on one of the tags the user can use, or (with no
    tag) on all of their spending, for a period of months or for good.
    """

    tag_name = serializers.SerializerMethodField()
    tag = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), required=False, allow_null=True, default=None
    )
    months = serializers.IntegerField(min_value=1, max_value=120, required=False, allow_null=True, default=None)

    class Meta:
        model = Budget
        fields = ("id", "tag", "tag_name", "monthly_limit", "start_month", "months", "created_at")
        read_only_fields = ("created_at",)
        extra_kwargs = {"start_month": {"required": False}}

    def get_tag_name(self, budget):
        return budget.tag.name if budget.tag else "Overall spending"

    def validate_tag(self, value):
        user = self.context["request"].user
        if value is not None and not Tag.objects.available_to(user).filter(pk=value.pk).exists():
            raise serializers.ValidationError("That tag does not exist.")
        others = Budget.objects.filter(user=user, tag=value)
        if self.instance:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError(
                "There is already a budget for this tag." if value else "There is already an overall budget."
            )
        return value

    def validate_monthly_limit(self, value):
        if value <= 0:
            raise serializers.ValidationError("A budget must be more than zero.")
        return value

    def validate_start_month(self, value):
        # A budget begins at the start of a month
        return value.replace(day=1)

    def validate(self, attrs):
        # `tag` has a default, so a partial update which leaves it out must not
        # turn a tag's budget into the overall one
        if self.instance and "tag" not in self.initial_data:
            attrs.pop("tag", None)
        if self.instance and "months" not in self.initial_data:
            attrs.pop("months", None)
        return attrs


class TagAssignmentSerializer(serializers.Serializer):
    """The full set of tags a line item should have; replaces its current tags."""

    tags = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)

    def validate_tags(self, value):
        # Only the predefined tags and the user's own can be assigned
        found = list(
            Tag.objects.available_to(self.context["request"].user).filter(pk__in=value)
        )
        if len(found) != len(set(value)):
            raise serializers.ValidationError("One or more tags do not exist.")
        return found


class AccountUpdateSerializer(serializers.ModelSerializer):
    """The details of a bank account which the user can edit."""

    account_name = serializers.CharField(max_length=100, trim_whitespace=True)
    account_number = serializers.RegexField(
        r"^\d{4}$",
        error_messages={"invalid": "Account number must be exactly 4 digits."},
    )
    funds = serializers.DecimalField(max_digits=13, decimal_places=2, min_value=0)
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES), required=False)

    class Meta:
        model = Account
        fields = ("account_name", "account_number", "card_type", "funds", "currency")

    def validate_account_number(self, value):
        # The account number identifies the account, so it may not be the
        # number of another of the same user's accounts. (Their own is fine:
        # saving other details leaves it as it was.)
        others = Account.objects.filter(
            user=self.instance.user, account_number=value
        ).exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError(
                "You already have an account with that account number."
            )
        return value


class ReceiptAccountSerializer(serializers.Serializer):
    """The bank account a receipt is to be linked to."""

    account = serializers.UUIDField()
