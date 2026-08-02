from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "category", "title", "is_read", "created_at")
    list_filter = ("category", "is_read")
    search_fields = ("recipient__email", "title", "body", "dedupe_key")
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ()


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "email_enabled", "sms_enabled", "updated_at")
    search_fields = ("user__email",)
