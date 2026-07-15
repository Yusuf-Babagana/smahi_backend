from django.contrib import admin

from .models import OTPCode


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ['email', 'purpose', 'is_used', 'attempts', 'expires_at', 'created_at']
    list_filter = ['purpose', 'is_used']
    search_fields = ['email']
    readonly_fields = [
        'user', 'email', 'purpose', 'code_hash',
        'attempts', 'is_used', 'expires_at', 'created_at'
    ]
