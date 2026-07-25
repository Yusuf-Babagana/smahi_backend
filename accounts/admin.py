from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'role', 'account_status', 'is_verified', 'is_active', 'created_at']
    list_filter = ['role', 'account_status', 'is_verified', 'is_active', 'created_at', 'country']
    search_fields = ['email', 'first_name', 'last_name', 'phone_number']
    ordering = ['-created_at']
    actions = ['suspend_users', 'reactivate_users']

    @admin.action(description='Suspend selected users (blocks login)')
    def suspend_users(self, request, queryset):
        # account_status is what the app's own login/session-gate logic
        # checks (see app/index.tsx and login_view) — is_active alone
        # would leave account_status='active' and the two would disagree.
        updated = queryset.exclude(id=request.user.id).update(is_active=False, account_status='suspended')
        skipped = queryset.filter(id=request.user.id).exists()
        msg = f'{updated} user(s) suspended.'
        if skipped:
            msg += ' (You cannot suspend your own account.)'
        self.message_user(request, msg)

    @admin.action(description='Reactivate selected users')
    def reactivate_users(self, request, queryset):
        updated = queryset.update(is_active=True, account_status='active')
        self.message_user(request, f'{updated} user(s) reactivated.')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'address', 'profile_picture')}),
        ('Location', {'fields': ('country', 'state', 'lga')}),
        ('Permissions', {'fields': ('role', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'role'),
        }),
    )
