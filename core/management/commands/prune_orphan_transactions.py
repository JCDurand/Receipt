from django.core.management.base import BaseCommand

from core.models import Transaction


class Command(BaseCommand):
    help = (
        "Finds the statement lines which were left behind when their bank statement was "
        "deleted before statements took their unmatched lines with them: lines which belong "
        "to no statement and which no receipt is matched to. Lists them, and deletes them "
        "only with --delete. (A line added straight through the API has no statement "
        "either, so look at the list first.)"
    )

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="delete them, rather than just listing them")

    def handle(self, *args, **options):
        orphans = Transaction.objects.filter(statement__isnull=True).unmatched().select_related("account")
        if not orphans:
            self.stdout.write("There are no leftover statement lines.")
            return

        for line in orphans.order_by("transaction_date"):
            text = (line.description or line.merchant or "")[:50]
            self.stdout.write(f"{line.transaction_date}  {line.amount:>12}  {text}  ({line.account})")

        if options["delete"]:
            count = orphans.count()
            orphans.delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} statement lines."))
        else:
            self.stdout.write(f"{orphans.count()} statement lines. Run again with --delete to delete them.")
