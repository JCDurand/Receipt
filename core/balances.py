"""
What a bank account holds, from its opening balance and the source documents
uploaded to it.

The opening balance (Account.funds) is what the account held on the day it was
created. From then on every line dated after that day moves it: the lines of
its bank statements, and the items of receipts paid from it which are not yet
matched to a statement line (a matched receipt is the same money as its line,
so it counts once, through the line). Lines dated on or before the creation day
are taken to be in the opening balance already.

Going back in time works the other way: the balance at the end of a day before
the account was created is the opening balance with every movement after that
day (up to the creation day) taken back out. Whether that history adds up is
not checked; the user may only have uploaded some of it.

Amounts are in the account's own currency: a line recorded in another is
converted at the rate of its own day.
"""
from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from .currency import RateBook
from .models import Item, Transaction

CENT = Decimal("0.01")


def opened_on(account):
    """The day the account's opening balance applies to."""
    return timezone.localdate(account.created_at)


def movements(account):
    """
    Every movement of money the account's documents record, as
    [(day, cents_in, cents_out)] in the account's currency, one per day, oldest
    first. Money out is positive in cents_out.
    """
    raw = []  # (day, signed amount, currency)
    for line in Transaction.objects.filter(account=account).only("amount", "currency", "transaction_date"):
        raw.append((line.transaction_date, line.amount, line.currency))

    unmatched_items = (
        Item.objects.filter(receipt__account=account, transaction__isnull=True, receipt__transaction__isnull=True)
        .select_related("receipt")
        .only("item_total", "direction", "date", "receipt__currency", "receipt__transaction_date")
    )
    for item in unmatched_items:
        day = item.date or timezone.localdate(item.receipt.transaction_date)
        signed = item.item_total if item.direction == "credit" else -item.item_total
        raw.append((day, signed, item.receipt.currency))

    book = RateBook(account.currency)
    book.prepare((currency, day) for day, _, currency in raw)

    per_day = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for day, amount, currency in raw:
        converted, _ = book.convert(Decimal(amount), currency, day)
        if converted >= 0:
            per_day[day][0] += converted
        else:
            per_day[day][1] += -converted
    return [(day, money_in, money_out) for day, (money_in, money_out) in sorted(per_day.items())]


def balance_history(account):
    """
    The account's balance at the end of each day it moved, and of the day it was
    created, as {"opened_on", "opening", "balance", "points", "below_zero"}:
      points      [{"date", "balance", "in", "out"}] oldest first, Decimals
      balance     what it holds now: the opening balance and every movement since
      below_zero  for a savings account which went under nothing after it was
                  created, the first day it did: {"date", "balance"}; else None
    """
    day0 = opened_on(account)
    opening = Decimal(account.funds)
    days = movements(account)

    after = [(d, i, o) for d, i, o in days if d > day0]
    before = [(d, i, o) for d, i, o in days if d <= day0]

    points = []
    # Back from the opening balance: the end of each earlier day is the opening
    # balance less everything that moved after it
    running = opening
    for day, money_in, money_out in reversed(before):
        points.append({"date": day, "balance": running, "in": money_in, "out": money_out})
        running -= money_in - money_out
    points.reverse()
    if not before or before[-1][0] != day0:
        points.append({"date": day0, "balance": opening, "in": Decimal(0), "out": Decimal(0)})

    # Forward from the opening balance
    running = opening
    below_zero = None
    for day, money_in, money_out in after:
        running += money_in - money_out
        points.append({"date": day, "balance": running, "in": money_in, "out": money_out})
        if below_zero is None and account.card_type == "Savings" and running < 0:
            below_zero = {"date": day, "balance": running}

    if below_zero is None and account.card_type == "Savings" and opening < 0:
        below_zero = {"date": day0, "balance": opening}

    return {
        "opened_on": day0,
        "opening": opening,
        "balance": running,
        "points": points,
        "below_zero": below_zero,
    }


def warning_text(account, below_zero):
    """What to tell the user about a savings account which went under nothing."""
    if not below_zero:
        return None
    return (
        f"This savings account's balance went below zero on {below_zero['date'].isoformat()} "
        f"({below_zero['balance'].quantize(CENT)} {account.currency}). A savings account cannot be "
        "overdrawn, so a document may be missing, duplicated or on the wrong account, or the opening "
        "balance may be wrong."
    )


def balance_summary(account, user_currency):
    """The account's balance now, for listing it: in its own currency and the user's."""
    history = balance_history(account)
    book = RateBook(user_currency)
    today = timezone.localdate()
    book.prepare([(account.currency, today)])
    converted, _ = book.convert(history["balance"], account.currency, today)
    return {
        "created_at": account.created_at,
        "opened_on": history["opened_on"].isoformat(),
        "balance": str(history["balance"].quantize(CENT)),
        "balance_converted": str(Decimal(converted).quantize(CENT)),
        "below_zero": (
            {"date": history["below_zero"]["date"].isoformat(), "balance": str(history["below_zero"]["balance"].quantize(CENT))}
            if history["below_zero"]
            else None
        ),
        "warning": warning_text(account, history["below_zero"]),
    }


def history_payload(account, user_currency):
    """The account's balance history, with each point also in the user's currency
    (at the rate of its own day), for charting every account together."""
    history = balance_history(account)
    book = RateBook(user_currency)
    book.prepare((account.currency, p["date"]) for p in history["points"])

    def both(amount, day):
        converted, _ = book.convert(amount, account.currency, day)
        return str(amount.quantize(CENT)), str(Decimal(converted).quantize(CENT))

    points = []
    for p in history["points"]:
        balance, balance_c = both(p["balance"], p["date"])
        money_in, in_c = both(p["in"], p["date"])
        money_out, out_c = both(p["out"], p["date"])
        points.append({
            "date": p["date"].isoformat(),
            "balance": balance, "in": money_in, "out": money_out,
            "balance_converted": balance_c, "in_converted": in_c, "out_converted": out_c,
        })
    summary = balance_summary(account, user_currency)
    return {
        "id": account.id,
        "account_name": account.account_name,
        "account_number": account.account_number,
        "card_type": account.card_type,
        "currency": account.currency,
        "opening": str(history["opening"].quantize(CENT)),
        **summary,
        "points": points,
    }
