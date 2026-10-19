"""
Converting amounts between currencies at the rate of the day they were spent.

Rates come from Frankfurter (https://frankfurter.dev), a free service with no
key which republishes the European Central Bank's daily reference rates back to
1999. Rates it has given are kept in the database, so each day's rate is asked
for once, and a lookup the service cannot answer (it is down, or slow) falls
back on the nearest rate already kept rather than failing the page.
"""
import logging
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import requests
from django.utils import timezone

from .models import DEFAULT_CURRENCY, ExchangeRate

logger = logging.getLogger(__name__)

API_URL = "https://api.frankfurter.dev/v1"
TIMEOUT = (3, 8)

# The service publishes a rate on working days only: a weekend or holiday uses
# the last one before it, so a rate up to this many days older is "the day's".
GAP_DAYS = 7

# Asked for in chunks: the service thins a long range out to weekly rates
CHUNK_DAYS = 80

# The currencies the service has rates for
CURRENCIES = {
    "AUD": "Australian Dollar",
    "BRL": "Brazilian Real",
    "CAD": "Canadian Dollar",
    "CHF": "Swiss Franc",
    "CNY": "Chinese Renminbi Yuan",
    "CZK": "Czech Koruna",
    "DKK": "Danish Krone",
    "EUR": "Euro",
    "GBP": "British Pound",
    "HKD": "Hong Kong Dollar",
    "HUF": "Hungarian Forint",
    "IDR": "Indonesian Rupiah",
    "ILS": "Israeli New Shekel",
    "INR": "Indian Rupee",
    "ISK": "Icelandic Króna",
    "JPY": "Japanese Yen",
    "KRW": "South Korean Won",
    "MXN": "Mexican Peso",
    "MYR": "Malaysian Ringgit",
    "NOK": "Norwegian Krone",
    "NZD": "New Zealand Dollar",
    "PHP": "Philippine Peso",
    "PLN": "Polish Złoty",
    "RON": "Romanian Leu",
    "SEK": "Swedish Krona",
    "SGD": "Singapore Dollar",
    "THB": "Thai Baht",
    "TRY": "Turkish Lira",
    "USD": "United States Dollar",
    "ZAR": "South African Rand",
}

CENT = Decimal("0.01")


def is_supported(code):
    return code in CURRENCIES


def conversion_label(source, target):
    """"ZAR -> USD": what a converted line is marked with."""
    return f"{source} -> {target}"


def _fetch(base, quote, start, end):
    """The service's rates for base -> quote from start to end, as {date: Decimal}.
    Empty if it cannot be reached."""
    url = f"{API_URL}/{start.isoformat()}..{end.isoformat()}"
    params = {"base": base, "symbols": quote}
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            rates = response.json().get("rates", {})
            return {
                date.fromisoformat(day): Decimal(str(by_quote[quote]))
                for day, by_quote in rates.items()
                if quote in by_quote
            }
        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning("Exchange rates %s->%s %s..%s failed (try %s): %s", base, quote, start, end, attempt + 1, error)
    return {}


class RateBook:
    """
    The rates to convert into one currency. Say which (currency, day) pairs are
    coming with `prepare`, so that the rates are loaded (and any missing ones
    fetched) together, then `convert` each amount.
    """

    def __init__(self, target):
        self.target = target
        # base -> sorted [(date, rate)]
        self._days = {}
        self._dates = {}

    def _remember(self, base, rows):
        rows = sorted(rows)
        self._days[base] = rows
        self._dates[base] = [d for d, _ in rows]

    def _lookup(self, base, day, strict=True):
        """The rate for the day: the latest at or before it (within GAP_DAYS if strict)."""
        rows = self._days.get(base)
        if not rows:
            return None
        i = bisect_right(self._dates[base], day)
        if i:
            found_day, rate = rows[i - 1]
            if not strict or (day - found_day).days <= GAP_DAYS:
                return rate
        if not strict:
            return rows[0][1]  # nothing earlier: the earliest there is
        return None

    def prepare(self, needs):
        today = timezone.localdate()
        wanted = defaultdict(set)
        for currency, day in needs:
            if currency and currency != self.target:
                wanted[currency].add(min(day, today))

        for base, days in wanted.items():
            low, high = min(days), max(days)
            stored = ExchangeRate.objects.filter(
                base=base, quote=self.target, date__gte=low - timedelta(days=GAP_DAYS), date__lte=high
            ).values_list("date", "rate")
            self._remember(base, [(d, r) for d, r in stored])

            missing = sorted(d for d in days if self._lookup(base, d) is None)
            if missing:
                self._fetch_missing(base, missing[0] - timedelta(days=GAP_DAYS), missing[-1], today)
            if not self._days.get(base):
                # Nothing for the period, and the service could not help: any
                # rate we ever kept for the pair is better than none
                kept = ExchangeRate.objects.filter(base=base, quote=self.target).values_list("date", "rate")
                self._remember(base, [(d, r) for d, r in kept])

    def _fetch_missing(self, base, start, end, today):
        end = min(end, today)
        fetched = {}
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end)
            fetched.update(_fetch(base, self.target, chunk_start, chunk_end))
            chunk_start = chunk_end + timedelta(days=1)
        if not fetched:
            return
        ExchangeRate.objects.bulk_create(
            [ExchangeRate(base=base, quote=self.target, date=d, rate=r) for d, r in fetched.items()],
            ignore_conflicts=True,
        )
        merged = dict(self._days.get(base, []))
        merged.update(fetched)
        self._remember(base, list(merged.items()))

    def rate(self, currency, day):
        """What one unit of `currency` was worth in the target on the day; None if unknown."""
        if currency == self.target:
            return Decimal(1)
        return self._lookup(currency, min(day, timezone.localdate()), strict=False)

    def convert(self, amount, currency, day):
        """(converted amount, rate). Rate is None, and the amount unchanged,
        when no rate could be found."""
        rate = self.rate(currency, day)
        if rate is None:
            return amount, None
        if currency == self.target:
            return amount, rate
        return (Decimal(amount) * rate).quantize(CENT), rate


def spot_rate(base, quote):
    """Today's rate, for converting an amount which has no date of its own (an account's funds)."""
    book = RateBook(quote)
    today = timezone.localdate()
    book.prepare([(base, today)])
    return book.rate(base, today)
