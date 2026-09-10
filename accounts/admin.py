from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from core.referrals import ensure_referral_code

User = get_user_model()


def _mint_missing_referral_codes(users):
    """Idempotently give every Coordinator/Agent that lacks one their referral
    code — a coordinator's code is state-prefixed (SMAHI-KN-7X42), an agent's
    is SMAHI-AG-XXXX (see core.referrals.default_prefix). Mirrors the API
    entry points (AdminCreateCoordinatorView, CoordinatorAgentStatusView) so a
    Django-Admin-created/edited account behaves exactly like one created in
    the app. Codes are only ever minted for role-seat holders — never
    overwritten once set."""
    minted = 0
    for user in users:
        if (
            user.role in ('state_coordinator', 'agent')
            and user.account_status in ('active', 'suspended')
            and not user.referral_code
        ):
            try:
                ensure_referral_code(user)
                minted += 1
            except Exception:
                pass
    return minted


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'role', 'account_status', 'referral_code', 'is_verified', 'is_active', 'created_at']
    list_filter = ['role', 'account_status', 'is_verified', 'is_active', 'created_at', 'country']
    search_fields = ['email', 'first_name', 'last_name', 'phone_number', 'referral_code']
    ordering = ['-created_at']
    # Machine-minted via core.referrals (creation/approval paths + admin
    # actions + save_model hook) — never hand-edited, so a typo can never
    # collide with another user's code or break the SMAHI-<TAG>-XXXX format.
    readonly_fields = ('referral_code',)
    actions = ['suspend_users', 'reactivate_users', 'generate_referral_codes']

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
        minted = _mint_missing_referral_codes(queryset)
        msg = f'{updated} user(s) reactivated.'
        if minted:
            msg += f' {minted} referral code(s) minted.'
        self.message_user(request, msg)

    @admin.action(description='Generate referral codes for selected Coordinators/Agents')
    def generate_referral_codes(self, request, queryset):
        minted = _mint_missing_referral_codes(queryset)
        self.message_user(request, f'{minted} referral code(s) minted.')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'address', 'profile_picture')}),
        ('Location', {'fields': ('country', 'state', 'lga')}),
        ('Referral', {'fields': ('referral_code', 'sponsor_coordinator', 'sponsor_agent')}),
        ('Permissions', {'fields': ('role', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'role'),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Mint the code right after the row exists (needs no id — User has
        # an AutoField already saved above) so admin-created/edited
        # Coordinators/Agents carry a code exactly like API-created ones.
        if (
            obj.role in ('state_coordinator', 'agent')
            and obj.account_status in ('active', 'suspended')
            and not obj.referral_code
        ):
            try:
                ensure_referral_code(obj)
            except Exception:
                pass
