from django.core.management.base import BaseCommand

from core.models import BankStatement, Receipt

INTERRUPTED_MESSAGE = (
    "Processing was interrupted by a server restart. Please upload the document again."
)


class Command(BaseCommand):
    help = (
        "Marks the bank statements and receipts which are still waiting to be parsed, or "
        "part-way through it, as failed. Documents are parsed in the background of the "
        "server that took the upload, so one that was not finished when that server "
        "stopped never will be. Run when the server starts, before it takes requests: "
        "run while it is serving, it would fail documents that are being parsed."
    )

    def handle(self, *args, **options):
        count = 0
        for model in (BankStatement, Receipt):
            count += model.objects.filter(
                processing_status__in=["pending", "processing"]
            ).update(processing_status="failed", parser_error=INTERRUPTED_MESSAGE)

        if count:
            self.stdout.write(f"Marked {count} interrupted documents as failed.")
        else:
            self.stdout.write("There are no interrupted documents.")
