from django.core.management.base import BaseCommand

from apps.notifications.tasks import send_trip_reminders


class Command(BaseCommand):
    help = (
        "Send due trip reminders (synchronous, bypasses Celery). Idempotent -- safe "
        "to run repeatedly from cron in a Redis-free deployment."
    )

    def handle(self, *args, **options):
        sent = send_trip_reminders.run()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder notification(s)."))
