from django.core.management.base import BaseCommand

from apps.trips.tasks import generate_recurring_trips


class Command(BaseCommand):
    help = "Top up recurring-trip generation for all active series (synchronous, bypasses Celery)."

    def add_arguments(self, parser):
        parser.add_argument("--series-id", default=None)
        parser.add_argument("--window-days", type=int, default=14)

    def handle(self, *args, **options):
        created = generate_recurring_trips.run(
            series_id=options["series_id"], window_days=options["window_days"]
        )
        self.stdout.write(self.style.SUCCESS(f"Generated {created} trip(s)."))
