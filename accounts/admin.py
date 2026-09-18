from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from core.referrals import ensure_referral_code
from core.services import log_activity, set_agent_status, set_coordinator_status
from .models import Agent, BusinessOwner, Coordinator

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


# --- Dedicated management pages for Coordinators, Agents, and Business
# Owners — proxy models of User (accounts/models.py), so a colleague
# doesn't have to filter the generic Users list by role every time.
# Coordinator/Agent reuse core.services.set_coordinator_status/
# set_agent_status — the exact same rules CoordinatorAgentStatusView/
# AdminCoordinatorStatusView enforce via the mobile app's API — so a
# Django-Admin-driven status change can never quietly disagree with an
# API-driven one, and both get an ActivityLog entry.

class CoordinatorCreationForm(UserCreationForm):
    """add_form (not form/change-form) is what BaseUserAdmin.get_form()
    actually uses on the Add page (see django.contrib.auth.admin.UserAdmin
    .get_form — it swaps in add_form whenever obj is None); ModelAdmin.
    get_form() rebuilds this form's Meta.fields from CoordinatorAdmin.
    add_fieldsets below, so subclassing UserCreationForm (not a plain
    ModelForm) is what keeps password1/password2 hashing working."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A Coordinator's referral code is state-prefixed (core.referrals
        # .default_prefix) — without a state there's nothing to mint from,
        # same requirement AdminCreateCoordinatorView enforces.
        self.fields['state'].required = True


@admin.register(Coordinator)
class CoordinatorAdmin(UserAdmin):
    add_form = CoordinatorCreationForm
    list_display = ['email', 'first_name', 'last_name', 'state', 'account_status', 'referral_code', 'created_at']
    list_filter = ['account_status', 'state', 'created_at']
    readonly_fields = UserAdmin.readonly_fields + ('role',)
    actions = ['reactivate_coordinators', 'suspend_coordinators', 'dismiss_coordinators']
    # Base UserAdmin.add_fieldsets has no Location section at all — without
    # this, the add form couldn't satisfy the form's own required-state
    # validation above.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'country', 'state'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='state_coordinator')

    def save_model(self, request, obj, form, change):
        # A coordinator is active immediately on creation — no
        # pending_approval step (AdminCreateCoordinatorView's own
        # reasoning: unlike an agent, nobody else has to vouch for them).
        obj.role = 'state_coordinator'
        is_new = not change
        super().save_model(request, obj, form, change)
        if is_new:
            log_activity(request.user, 'coordinator_created', target_user=obj, activity_status='active')

    def _transition(self, request, queryset, new_status):
        ok, errors = 0, []
        for coordinator in queryset:
            try:
                set_coordinator_status(coordinator, new_status, request.user, allow_reactivate_from_terminal=True)
                ok += 1
            except ValueError as e:
                errors.append(str(e))
        if ok:
            self.message_user(request, f'{ok} coordinator(s) set to {new_status}.')
        for err in errors:
            self.message_user(request, err, level=messages.WARNING)

    @admin.action(description='Reactivate selected Coordinators')
    def reactivate_coordinators(self, request, queryset):
        self._transition(request, queryset, 'active')

    @admin.action(description='Suspend selected Coordinators')
    def suspend_coordinators(self, request, queryset):
        self._transition(request, queryset, 'suspended')

    @admin.action(description='Dismiss selected Coordinators')
    def dismiss_coordinators(self, request, queryset):
        self._transition(request, queryset, 'dismissed')


class AgentCreationForm(UserCreationForm):
    """See CoordinatorCreationForm's docstring — same add_form mechanism."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['state'].required = True
        self.fields['lga'].required = True

    def clean(self):
        cleaned = super().clean()
        state, lga = cleaned.get('state'), cleaned.get('lga')
        # Same rule CoordinatorCreateAgentView enforces server-side — an
        # LGA that belongs to a different state than the one selected
        # would silently misroute this agent's territory scoping
        # everywhere else in the app.
        if state and lga and lga.state_id != state.id:
            raise forms.ValidationError('The selected LGA does not belong to the selected state.')
        return cleaned


@admin.register(Agent)
class AgentAdmin(UserAdmin):
    add_form = AgentCreationForm
    list_display = ['email', 'first_name', 'last_name', 'state', 'lga', 'account_status', 'serial_number', 'referral_code', 'created_at']
    list_filter = ['account_status', 'state', 'created_at']
    readonly_fields = UserAdmin.readonly_fields + ('role', 'serial_number')
    actions = ['approve_or_reactivate_agents', 'suspend_agents', 'reject_agents', 'dismiss_agents']
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'country', 'state', 'lga'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='agent')

    def save_model(self, request, obj, form, change):
        obj.role = 'agent'
        is_new = not change
        if is_new:
            # Matches CoordinatorCreateAgentView: a hand-created agent
            # starts pending_approval, not immediately active — someone
            # (here: whoever is using this form) still has to approve them.
            obj.account_status = 'pending_approval'
        super().save_model(request, obj, form, change)
        if is_new and not obj.serial_number and obj.state_id:
            state = obj.state
            state_code = state.state_code or state.name[:3].upper()
            obj.serial_number = f'AGT-{state_code}-{obj.id:05d}'
            obj.save(update_fields=['serial_number'])
        if is_new:
            log_activity(request.user, 'agent_created', target_user=obj, activity_status='pending_approval')

    def _transition(self, request, queryset, new_status):
        ok, errors = 0, []
        for agent in queryset:
            try:
                set_agent_status(agent, new_status, request.user, allow_reactivate_from_terminal=True)
                ok += 1
            except ValueError as e:
                errors.append(str(e))
        if ok:
            self.message_user(request, f'{ok} agent(s) set to {new_status}.')
        for err in errors:
            self.message_user(request, err, level=messages.WARNING)

    @admin.action(description='Approve / reactivate selected Agents')
    def approve_or_reactivate_agents(self, request, queryset):
        self._transition(request, queryset, 'active')

    @admin.action(description='Suspend selected Agents')
    def suspend_agents(self, request, queryset):
        self._transition(request, queryset, 'suspended')

    @admin.action(description='Reject selected Agents (never approved)')
    def reject_agents(self, request, queryset):
        self._transition(request, queryset, 'rejected')

    @admin.action(description='Dismiss selected Agents')
    def dismiss_agents(self, request, queryset):
        self._transition(request, queryset, 'dismissed')


@admin.register(BusinessOwner)
class BusinessOwnerAdmin(UserAdmin):
    """No bespoke lifecycle exists for this role anywhere in the codebase
    (no approval step, no dedicated ActivityLog actions the way agents/
    coordinators have) — this is a filtered, easier-to-find view onto the
    same suspend/reactivate every other user already has. Pairs with
    BusinessProfileAdmin (core/admin.py), which covers the business's own
    profile/verification/registered_by rather than the account itself."""
    list_display = ['email', 'first_name', 'last_name', 'state', 'lga', 'account_status', 'registration_fee_paid', 'is_verified', 'created_at']
    list_filter = ['account_status', 'is_verified', 'state', 'created_at']
    readonly_fields = UserAdmin.readonly_fields + ('role',)
    actions = ['suspend_users', 'reactivate_users']
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'country', 'state', 'lga'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='business')

    def save_model(self, request, obj, form, change):
        obj.role = 'business'
        super().save_model(request, obj, form, change)
