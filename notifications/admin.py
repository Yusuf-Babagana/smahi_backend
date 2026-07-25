from django.contrib import admin

from .models import OTPCode, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Read-only — this table is the audit trail for emit() calls.
    Never editable or deletable here, only ever created by
    notifications.events.emit()."""
    list_display = ['event_type', 'recipient', 'title', 'is_read', 'created_at']
    list_filter = ['event_type', 'is_read', 'created_at']
    search_fields = ['recipient__email', 'title', 'body']
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ['email', 'purpose', 'is_used', 'attempts', 'expires_at', 'created_at']
    list_filter = ['purpose', 'is_used']
    search_fields = ['email']
    readonly_fields = [
        'user', 'email', 'purpose', 'code_hash',
        'attempts', 'is_used', 'expires_at', 'created_at'
    ]
