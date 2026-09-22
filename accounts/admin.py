from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.forms.models import BaseInlineFormSet
from django.template.response import TemplateResponse
from core.models import ArtisanProfile, BusinessProfile
from core.referrals import ACTIVE_STATUSES, assign_client_agent, ensure_referral_code, reassign_agent_coordinator
from core.services import log_activity, set_agent_status, set_coordinator_status
from .models import Agent, BusinessOwner, Client, Coordinator

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
    # '^' anchors ALL of these to istartswith so MySQL can actually use the
    # indexes on email/first_name/last_name/phone_number/referral_code (all
    # indexed — see accounts/models.py). Django ORs every search_fields
    # entry into one WHERE clause; leaving even one entry as plain icontains
    # (leading-wildcard 'LIKE %term%', unindexable) forces MySQL to fall
    # back to a full table scan for the WHOLE query regardless of how many
    # other entries are anchored — searching a full, exact, indexed email
    # was still slow after only ^-anchoring 3 of the 5 fields here, because
    # first_name/last_name were still in that same OR unanchored. The
    # trade-off (name search is now start-of-name only, not mid-name) is
    # the same one already made for phone_number/referral_code above.
    search_fields = ['^email', '^first_name', '^last_name', '^phone_number', '^referral_code']
    ordering = ['-created_at']
    # Machine-minted via core.referrals (creation/approval paths + admin
    # actions + save_model hook) — never hand-edited, so a typo can never
    # collide with another user's code or break the SMAHI-<TAG>-XXXX format.
    readonly_fields = ('referral_code',)
    actions = ['suspend_users', 'reactivate_users', 'generate_referral_codes']

    # The changelist's "N results" count re-runs the exact same filtered
    # query a second time just to count it — on the Client page (by far the
    # biggest role bucket in this single shared User table) that was a big
    # part of the slow load. Admin only ever needs "roughly how many", not
    # an exact count, so skip it (built-in ModelAdmin escape hatch).
    show_full_result_count = False

    def get_queryset(self, request):
        # Every subclass below (CoordinatorAdmin/AgentAdmin/BusinessOwnerAdmin/
        # ClientAdmin) calls super().get_queryset(request).filter(role=...) —
        # adding select_related here once, rather than in each of their
        # list_display's FK columns (state/lga/sponsor_agent/
        # sponsor_coordinator/country), avoids each of them running a
        # separate query per row per column (100 rows/page x several FK
        # columns = hundreds of extra round trips) for every one of them.
        return super().get_queryset(request).select_related(
            'country', 'state', 'lga', 'sponsor_agent', 'sponsor_coordinator',
        )

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

class AgentInlineFormSet(BaseInlineFormSet):
    """Backs AgentInline below. Ticking an existing row's delete checkbox
    must NEVER delete the agent's account — it means "this agent no
    longer reports to this coordinator," the exact same detach that
    reassign_agent_coordinator/the "Reassign to a different Coordinator"
    action already perform elsewhere, just via the inline's own
    checkbox+save instead of a separate confirmation page. Overriding
    delete_existing (rather than leaving BaseModelFormSet's default,
    which calls obj.delete()) is what makes that safe."""

    def delete_existing(self, obj, commit=True):
        obj.sponsor_coordinator = None
        if commit:
            obj.save(update_fields=['sponsor_coordinator'])


class AgentInline(admin.TabularInline):
    """Shows a coordinator's own agents directly on their change page —
    "beside each coordinator, his agents appear under him" — instead of
    admin having to separately open the Agent list and filter by
    sponsor_coordinator. Read-only identity fields (editing an agent's
    own details belongs on their own change page, linked via
    show_change_link); the delete checkbox is the "remove" half (see
    AgentInlineFormSet). Adding a brand-new agent still goes through
    AgentAdmin's own add form (email/password/state/LGA, the
    pending_approval flow, serial number minting) — an inline "add" row
    would bypass all of that, so it's disabled here in favor of
    CoordinatorAdmin.assign_agents below, which attaches an *existing*
    agent instead."""

    model = Agent
    fk_name = 'sponsor_coordinator'
    formset = AgentInlineFormSet
    verbose_name = 'Agent'
    verbose_name_plural = 'Agents reporting to this coordinator'
    extra = 0
    can_delete = True
    show_change_link = True
    fields = ['email', 'first_name', 'last_name', 'lga', 'account_status', 'serial_number']
    readonly_fields = ['email', 'first_name', 'last_name', 'lga', 'account_status', 'serial_number']

    def has_add_permission(self, request, obj):
        return False


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
    list_display = ['email', 'first_name', 'last_name', 'state', 'account_status', 'agents_count', 'referral_code', 'created_at']
    list_filter = ['account_status', 'state', 'created_at']
    readonly_fields = UserAdmin.readonly_fields + ('role',)
    actions = ['reactivate_coordinators', 'suspend_coordinators', 'dismiss_coordinators', 'assign_agents']
    inlines = [AgentInline]
    # UserAdmin's own Referral fieldset shows sponsor_coordinator/
    # sponsor_agent, which don't apply to a Coordinator — they're the top
    # of the Coordinator -> Agent -> Service Provider chain, never sponsored
    # by anyone else. Left in place, that field's dropdown lists every
    # User in the system (no formfield_for_foreignkey restriction exists
    # for it here, unlike AgentAdmin's own sponsor_coordinator field),
    # which is both pointless clutter and — the AgentInline below already
    # correctly scopes to this coordinator's own agents — confusingly
    # showed every agent from every state on this same page. Only
    # referral_code (this coordinator's own, for recruiting agents) is
    # still relevant.
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'address', 'profile_picture')}),
        ('Location', {'fields': ('country', 'state', 'lga')}),
        ('Referral', {'fields': ('referral_code',)}),
        ('Permissions', {'fields': ('role', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
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

    def get_inline_instances(self, request, obj=None):
        # AgentInline only makes sense once the coordinator exists — a
        # brand-new one on the Add page has no agents yet, and rendering
        # it there would require its (empty) management form data on
        # every coordinator-creation POST for no benefit.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    @admin.display(description='Agents')
    def agents_count(self, obj):
        # Same ownership rule as core.referrals._coordinator_visible_agents
        # (imported lazily — accounts/admin.py importing core.referrals at
        # module level already works fine elsewhere in this file, but this
        # mirrors CoordinatorOverviewSerializer.get_agents_count's own
        # local-import style for the identical reason: never drift from
        # what the coordinator's own mobile dashboard shows).
        from core.referrals import _coordinator_visible_agents
        return _coordinator_visible_agents(obj).count()

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

    @admin.action(description='Assign agent(s) to this Coordinator')
    def assign_agents(self, request, queryset):
        # The inverse direction of AgentAdmin.reassign_coordinator (pick a
        # coordinator, then choose which of ITS agents to reassign) — this
        # is "pick a coordinator, then choose which agents (in the same
        # state, unclaimed or claimed by someone else) should now report
        # to them," so it operates on exactly one coordinator rather than
        # a batch.
        if queryset.count() != 1:
            self.message_user(
                request, 'Select exactly one Coordinator to assign agents to.', level=messages.ERROR,
            )
            return
        coordinator = queryset.first()

        if 'apply' in request.POST:
            agent_ids = request.POST.getlist('agent_ids')
            agents = User.objects.filter(pk__in=agent_ids, role='agent')
            ok, errors = 0, []
            for agent in agents:
                try:
                    reassign_agent_coordinator(agent, coordinator, request.user)
                    ok += 1
                except ValueError as e:
                    errors.append(str(e))
            if ok:
                self.message_user(request, f'{ok} agent(s) assigned to {coordinator.email}.')
            elif not errors:
                self.message_user(request, 'No agents were selected.', level=messages.WARNING)
            for err in errors:
                self.message_user(request, err, level=messages.WARNING)
            return

        # Same state, not already reporting to this coordinator — includes
        # unclaimed agents (sponsor_coordinator is null) and agents
        # currently claimed by a colleague in the same state, exactly the
        # two cases reassign_agent_coordinator itself allows.
        eligible = User.objects.filter(
            role='agent', state_id=coordinator.state_id,
        ).exclude(sponsor_coordinator_id=coordinator.id).select_related('lga', 'sponsor_coordinator').order_by('email')

        return TemplateResponse(request, 'admin/assign_agents_confirmation.html', {
            **self.admin_site.each_context(request),
            'coordinator': coordinator,
            'eligible': eligible,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'assign_agents',
            'opts': self.model._meta,
            'title': f'Assign agents to {coordinator.email}:',
            'select_label': f"Agents in {coordinator.state or 'their state'} available to assign",
            'help_text': (
                'Only Agents in the same state as this Coordinator can be assigned. '
                'An agent already reporting to another Coordinator will be moved to this one.'
            ),
        })


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


class ProviderReassignInlineFormSet(BaseInlineFormSet):
    """Shared by ArtisanProfileInline/BusinessProfileInline below — same
    role as AgentInlineFormSet, one level down the chain: ticking an
    existing row's delete checkbox must never delete the artisan/business
    account, only detach them from this agent (registered_by -> None),
    the same "no longer reports to" semantics reassign_provider_owner/
    ReassignableOwnerAdminMixin already use elsewhere."""

    def delete_existing(self, obj, commit=True):
        obj.registered_by = None
        if commit:
            obj.save(update_fields=['registered_by'])


class ArtisanProfileInline(admin.TabularInline):
    """Shows an agent's own registered artisans directly on their change
    page — "beside each agent, the artisans/businesses they registered
    appear under him," the same ask CoordinatorAdmin.AgentInline already
    answers one level up. registered_by (not sponsor_agent) is the right
    scope here: it's the genuinely mutable "who currently oversees this
    provider" field reassign_provider_owner moves, whereas sponsor_agent
    is permanent referral-credit history that can point at an agent who
    no longer actively manages them (see core.referrals' own docstrings).
    Read-only + no add, same reasoning as AgentInline: editing/creating a
    profile belongs on ArtisanProfileAdmin's own form/API, not here."""

    model = ArtisanProfile
    fk_name = 'registered_by'
    formset = ProviderReassignInlineFormSet
    verbose_name = 'Artisan'
    verbose_name_plural = 'Artisans registered by this agent'
    extra = 0
    can_delete = True
    show_change_link = True
    fields = ['user', 'full_name', 'category', 'verification_status', 'created_at']
    readonly_fields = fields

    def has_add_permission(self, request, obj):
        return False

    @admin.display(description='Name')
    def full_name(self, obj):
        return f'{obj.user.first_name} {obj.user.last_name}'.strip() or '—'


class BusinessProfileInline(admin.TabularInline):
    """See ArtisanProfileInline's docstring — identical shape and reasoning,
    one model over."""

    model = BusinessProfile
    fk_name = 'registered_by'
    formset = ProviderReassignInlineFormSet
    verbose_name = 'Business'
    verbose_name_plural = 'Business owners registered by this agent'
    extra = 0
    can_delete = True
    show_change_link = True
    fields = ['user', 'business_name', 'verification_status', 'created_at']
    readonly_fields = fields

    def has_add_permission(self, request, obj):
        return False


@admin.register(Agent)
class AgentAdmin(UserAdmin):
    add_form = AgentCreationForm
    list_display = ['email', 'first_name', 'last_name', 'state', 'lga', 'account_status', 'sponsor_coordinator', 'serial_number', 'referral_code', 'created_at']
    # sponsor_coordinator here also gives a "None" bucket (Django's
    # RelatedFieldListFilter auto-includes it for a nullable FK) — combine
    # with the state filter to find currently-unclaimed agents in a state
    # (invisible to every coordinator until reassigned — see
    # core.referrals._coordinator_visible_agents) and fix them with the
    # "Reassign to a different Coordinator" action below.
    list_filter = ['account_status', 'state', 'sponsor_coordinator', 'created_at']
    readonly_fields = UserAdmin.readonly_fields + ('role', 'serial_number')
    actions = ['approve_or_reactivate_agents', 'suspend_agents', 'reject_agents', 'dismiss_agents', 'reassign_coordinator']
    inlines = [ArtisanProfileInline, BusinessProfileInline]
    # UserAdmin's Referral fieldset also shows sponsor_agent, which is
    # meaningless for an Agent — the chain is strictly Coordinator ->
    # Agent -> Service Provider, an Agent is never sponsored by another
    # Agent. Left in place, its dropdown (no formfield_for_foreignkey
    # restriction exists for it, unlike sponsor_coordinator just below)
    # lists every User of every role in the system as a choice — the
    # exact same leak CoordinatorAdmin's own fieldsets override already
    # fixed for its irrelevant sponsor fields. sponsor_coordinator stays:
    # it's genuinely meaningful here, and already properly restricted by
    # formfield_for_foreignkey below.
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone_number', 'address', 'profile_picture')}),
        ('Location', {'fields': ('country', 'state', 'lga')}),
        ('Referral', {'fields': ('referral_code', 'sponsor_coordinator')}),
        ('Permissions', {'fields': ('role', 'is_verified', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', 'phone_number', 'country', 'state', 'lga'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='agent')

    def get_inline_instances(self, request, obj=None):
        # Same reasoning as CoordinatorAdmin.get_inline_instances — a
        # brand-new agent on the Add page has registered no one yet.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'sponsor_coordinator':
            kwargs['queryset'] = User.objects.filter(
                role='state_coordinator', account_status__in=ACTIVE_STATUSES,
            ).order_by('email')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # Editing sponsor_coordinator directly on the change form (base
        # UserAdmin's Referral fieldset already exposes it) goes through
        # the same validated reassignment as the bulk action below,
        # instead of a blind save — same pattern
        # core.admin.ReassignableOwnerAdminMixin already established for
        # registered_by.
        if change and 'sponsor_coordinator' in form.changed_data and obj.sponsor_coordinator:
            try:
                reassign_agent_coordinator(obj, obj.sponsor_coordinator, request.user)
            except ValueError as e:
                self.message_user(request, str(e), level=messages.ERROR)
                return
            return  # reassign_agent_coordinator already saved it

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

    @admin.action(description='Reassign to a different Coordinator')
    def reassign_coordinator(self, request, queryset):
        if 'apply' in request.POST:
            new_coordinator = User.objects.filter(
                pk=request.POST.get('new_owner'), role='state_coordinator',
            ).first()
            if not new_coordinator:
                self.message_user(request, 'Pick a valid Coordinator.', level=messages.ERROR)
                return
            ok, errors = 0, []
            for agent in queryset:
                try:
                    reassign_agent_coordinator(agent, new_coordinator, request.user)
                    ok += 1
                except ValueError as e:
                    errors.append(str(e))
            if ok:
                self.message_user(request, f'{ok} agent(s) reassigned to {new_coordinator.email}.')
            for err in errors:
                self.message_user(request, err, level=messages.WARNING)
            return

        eligible = User.objects.filter(role='state_coordinator', account_status__in=ACTIVE_STATUSES).order_by('email')
        rows = [
            (agent, agent.sponsor_coordinator.email if agent.sponsor_coordinator else 'unclaimed (no coordinator)')
            for agent in queryset
        ]
        return TemplateResponse(request, 'admin/reassign_generic_confirmation.html', {
            **self.admin_site.each_context(request),
            'rows': rows,
            'eligible': eligible,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'reassign_coordinator',
            'opts': self.model._meta,
            'title': 'Reassign the selected Agent(s) to a different Coordinator:',
            'select_label': 'New Coordinator',
            'help_text': 'Only Coordinators in the same state as each selected agent will be accepted — anything else is rejected per-row with an explanation.',
        })


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


@admin.register(Client)
class ClientAdmin(UserAdmin):
    """A Client's own admin section. No approval step or serial number
    (clients aren't a role-seat the way agents/coordinators are) — the
    one bespoke thing here is assign_agent, which sets sponsor_agent so
    AgentClientListView (core/views.py) shows this client to that agent
    in addition to (never instead of) the existing LGA-territorial match."""
    list_display = ['email', 'first_name', 'last_name', 'state', 'lga', 'sponsor_agent', 'is_active', 'created_at']
    list_filter = ['state', 'lga', 'created_at']
    readonly_fields = UserAdmin.readonly_fields + ('role',)
    actions = ['suspend_users', 'reactivate_users', 'assign_agent']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role='client')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'sponsor_agent':
            kwargs['queryset'] = User.objects.filter(
                role='agent', account_status__in=ACTIVE_STATUSES,
            ).order_by('email')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if change and 'sponsor_agent' in form.changed_data and obj.sponsor_agent:
            try:
                assign_client_agent(obj, obj.sponsor_agent, request.user)
            except ValueError as e:
                self.message_user(request, str(e), level=messages.ERROR)
                return
            return  # assign_client_agent already saved it

        obj.role = 'client'
        super().save_model(request, obj, form, change)

    @admin.action(description='Assign to a different Agent or Coordinator')
    def assign_agent(self, request, queryset):
        if 'apply' in request.POST:
            new_owner = User.objects.filter(
                pk=request.POST.get('new_owner'), role__in=['agent', 'state_coordinator'],
            ).first()
            if not new_owner:
                self.message_user(request, 'Pick a valid Agent or Coordinator.', level=messages.ERROR)
                return
            ok, errors = 0, []
            for client in queryset:
                try:
                    assign_client_agent(client, new_owner, request.user)
                    ok += 1
                except ValueError as e:
                    errors.append(str(e))
            if ok:
                self.message_user(request, f'{ok} client(s) assigned to {new_owner.email}.')
            for err in errors:
                self.message_user(request, err, level=messages.WARNING)
            return

        eligible = User.objects.filter(
            role__in=['agent', 'state_coordinator'], account_status__in=ACTIVE_STATUSES,
        ).order_by('email')
        rows = [
            (client, (client.sponsor_agent or client.sponsor_coordinator).email
             if (client.sponsor_agent or client.sponsor_coordinator) else 'unassigned')
            for client in queryset
        ]
        return TemplateResponse(request, 'admin/reassign_generic_confirmation.html', {
            **self.admin_site.each_context(request),
            'rows': rows,
            'eligible': eligible,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'action_name': 'assign_agent',
            'opts': self.model._meta,
            'title': 'Assign the selected Client(s) to a different Agent or Coordinator:',
            'select_label': 'New Agent / Coordinator',
            'help_text': 'Only an Agent/Coordinator in the same state as each selected client will be accepted — anything else is rejected per-row with an explanation. This adds the client to that Agent’s/Coordinator’s dashboard; it never removes anyone from their existing LGA-based view.',
        })
