import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditAction, AuditLog


class AuditLogFactory(DjangoModelFactory):
    class Meta:
        model = AuditLog

    actor = factory.SubFactory(UserFactory)
    action = AuditAction.VIEW
    model_name = "Trip"
    object_id = factory.Sequence(lambda n: str(n))
