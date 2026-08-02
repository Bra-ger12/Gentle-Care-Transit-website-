from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    VIEW = "VIEW", "Viewed"
    CREATE = "CREATE", "Created"
    UPDATE = "UPDATE", "Updated"
    DELETE = "DELETE", "Deleted"
    EXPORT = "EXPORT", "Exported"


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=10, choices=AuditAction.choices)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["model_name", "object_id"]),
            models.Index(fields=["actor", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.actor}:{self.action}:{self.model_name}#{self.object_id}"
