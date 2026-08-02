from django.db import migrations


def mark_existing_verified(apps, schema_editor):
    """Accounts that predate email verification are treated as confirmed.

    They were created when no verification step existed, so they never had a
    chance to complete one. Locking them out of booking would be punishing
    people for a feature arriving after they signed up. New registrations from
    here on must verify.
    """
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_verified=False).update(is_verified=True)


def noop(apps, schema_editor):
    """Irreversible by design: we can't tell which accounts were grandfathered."""


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_riderprofile_prior_auth_number")]

    operations = [migrations.RunPython(mark_existing_verified, noop)]
