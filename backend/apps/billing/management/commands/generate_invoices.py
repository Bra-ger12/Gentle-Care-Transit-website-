from django.core.management.base import BaseCommand

from apps.billing.services.pricing import generate_pending_invoices


class Command(BaseCommand):
    help = "Generate DRAFT invoices for all COMPLETED trips lacking an active invoice."

    def handle(self, *args, **options):
        invoices = generate_pending_invoices()
        self.stdout.write(self.style.SUCCESS(f"Generated {len(invoices)} invoice(s)."))
