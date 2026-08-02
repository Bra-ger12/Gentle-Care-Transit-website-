from django.core.management.base import BaseCommand

from apps.notifications.tasks import check_document_expiry


class Command(BaseCommand):
    help = (
        "Alert drivers/admins about expired or expiring licenses (synchronous, "
        "bypasses Celery). Idempotent -- safe to run daily from cron."
    )

    def handle(self, *args, **options):
        sent = check_document_expiry.run()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} expiry notification(s)."))
