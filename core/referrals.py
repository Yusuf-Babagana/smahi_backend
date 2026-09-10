"""Referral network business logic. Shared between API views, admin actions
and the data-migration backfill so they can never drift:

    Coordinator -> Agent -> Service Provider

* Codes are minted once and kept forever: a Coordinator gets
  ``SMAHI-<STATE>-XXXX`` (e.g. ``SMAHI-KN-7X42``) when created/activated,
  an Agent gets ``SMAHI-AG-XXXX`` (e.g. ``SMAHI-AG-92KD``) when approved.
* ``sponsor_coordinator``/``sponsor_agent`` on ``accounts.User`` are set
  permanently and never cleared, so referral history survives sponsor
  turnover.

Every function here is best-effort/idempotent-safe and never trusts a
caller-supplied owner for authorization — the caller already resolved
*who* is asking, and codes are matched case-insensitively against known
owners only.
"""
import secrets

from django.db.models import Q

from .models import ActivityLog, ArtisanProfile, BusinessProfile

REFERRAL_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
REFERRAL_BRAND = 'SMAHI'
AGENT_CODE_TAG = 'AG'
CODE_TAIL_LENGTH = 4

# Account statuses that still "hold" their role seat after creation. A code
# owner whose seat has been vacated (dismissed/rejected) or soft-deleted
# (inactive) is treated as no longer valid for new referral redemptions.
ACTIVE_STATUSES = ('active', 'suspended')

USER_MODEL = None


def _user_model():
    global USER_MODEL
    if USER_MODEL is None:
        from django.contrib.auth import get_user_model
        USER_MODEL = get_user_model()
    return USER_MODEL


def _code_tail(length=CODE_TAIL_LENGTH):
    return ''.join(secrets.choice(REFERRAL_ALPHABET) for _ in range(length))


def _normalise_tag(prefix):
    return prefix.replace('-', '').replace(' ', '').upper()


def default_prefix(user):
    """The code tag a user's role calls for: a Coordinator's state code
    (falls back to the first letters of the state name for a legacy row
    whose state somehow has none), or 'AG' for an Agent."""
    if user.role == 'state_coordinator':
        state = user.state
        return (state.state_code or state.name[:3]).upper() if state else 'ST'
    return AGENT_CODE_TAG


def generate_referral_code(prefix):
    """Mint a brand-standard, table-unique code for ``prefix`` — e.g. 'KN'
    -> ``SMAHI-KN-7X42``, 'AG' -> ``SMAHI-AG-92KD``. Retries on collision
    (codes are short, so a full sweep is astronomically unlikely); raises
    RuntimeError only if 50 consecutive attempts all collide."""
    tag = _normalise_tag(prefix)
    for _ in range(50):
        code = f'{REFERRAL_BRAND}-{tag}-{_code_tail()}'
        if not _user_model().objects.filter(referral_code__iexact=code).exists():
            return code
    raise RuntimeError(f'Could not allocate a unique referral code for prefix "{prefix}".')


def ensure_referral_code(user, prefix=None):
    """Idempotently mint ``user``'s code. Returns (code, created). A code
    that already exists is returned untouched — never overwritten, because
    a code's whole value is being permanent. The 'prefix' argument lets a
    caller override the role default (used when activating a legacy Agent
    with no code)."""
    if user.referral_code:
        return user.referral_code, False
    code = generate_referral_code(prefix or default_prefix(user))
    user.referral_code = code
    user.save(update_fields=['referral_code'])
    return code, True


def _state_summary(state):
    return {'id': state.id, 'name': state.name, 'code': state.state_code or ''} if state else None


def _owner_summary(user):
    """The fixed allowlist of owner fields surfaced to someone redeeming a
    referral code. Deliberately excludes email/phone/address — someone
    typing in a code learns the owner's badge name, role, serial number and
    state, nothing more."""
    if user is None:
        return None
    return {
        'id': user.id,
        'name': f'{user.first_name} {user.last_name}'.strip() or user.email.split('@')[0],
        'role': user.role,
        'serial_number': user.serial_number or '',
        'referral_code': user.referral_code or '',
        'state': _state_summary(user.state),
    }


def resolve_referral_code(code):
    """Resolve a bare code to its owner User, case-insensitively. Single
    source of truth for every caller; the returned reason string is turned
    into the endpoint's error message:

      * unknown / non-owner role / owner's seat vacated
          -> (None, reason)  — 'invalid' for never-had-a-code, 'not_active'
             for vacated seats ('This referral code is no longer valid.')
      * active/suspended coordinator -> the coordinator
      * active agent                 -> the agent

    The status rules mirror the seat rules behind
    'unique_active_coordinator_per_state': only occupants still holding
    their seat can receive recruits."""
    if not code:
        return None, 'invalid'
    clear = code.strip()
    user = _user_model().objects.filter(
        referral_code__iexact=clear,
        role__in=('state_coordinator', 'agent'),
    ).select_related('state').first()
    if user is None:
        return None, 'invalid'
    if user.role == 'state_coordinator':
        return (user, None) if user.account_status in ACTIVE_STATUSES else (None, 'not_active')
    # Agent: a referral code only works while the agent holds the seat —
    # pending_approval/rejected/dismissed/inactive all read as 'no longer
    # valid', echoing IsAgent's own gate.
    return (user, None) if user.account_status == 'active' else (None, 'not_active')


def coordinator_directory_entry(coordinator):
    """The stable 'this is your Coordinator' summary an Agent dashboard and
    agent-facing validations show. Public, non-sensitive fields only."""
    if coordinator is None:
        return None
    return {
        'id': coordinator.id,
        'name': f'{coordinator.first_name} {coordinator.last_name}'.strip(),
        'referral_code': coordinator.referral_code or '',
        'state': _state_summary(coordinator.state),
    }


def effective_coordinator(user):
    """Resolve the coordinator an Agent currently reports to: their
    recorded sponsor_coordinator first (the permanent referral link), and
    only if that was never set (a legacy agent backfilled before referral
    data existed) the state's current active/suspended coordinator — the
    closest present-day stand-in for 'who oversees this agent'."""
    if user.sponsor_coordinator_id:
        return user.sponsor_coordinator
    if user.role == 'agent' and user.state_id:
        return _user_model().objects.filter(
            role='state_coordinator', state_id=user.state_id, account_status__in=ACTIVE_STATUSES,
        ).select_related('state').first()
    return None


def referee_summary(owner):
    """Turn a resolved code-owner into the validator's response: a
    Coordinator referral is just them (their code means they are the
    Coordinator); an Agent referral also carries the Agent's own
    Coordinator so redeemers see the whole chain."""
    coordinator = owner if owner.role == 'state_coordinator' else owner.sponsor_coordinator
    return {
        'valid': True,
        'role': owner.role,
        'code': owner.referral_code,
        'coordinator': coordinator_directory_entry(coordinator) or (
            coordinator_directory_entry(owner) if owner.role == 'state_coordinator' else None
        ),
        'agent': _owner_summary(owner) if owner.role == 'agent' else None,
    }


def _recruited_query(owner, provider_model):
    """All Service Providers whose registration chain bottoms out at
    ``owner``. For a Coordinator: anyone they registered directly, and
    anyone whose user.sponsor_coordinator points at them — which covers
    both providers registered by an Agent under them AND providers who
    redeemed the Coordinator's own referral code on self-registration (this
    field is set permanently, so the chain survives turnover). For an
    Agent: only what they personally registered."""
    if owner.role == 'state_coordinator':
        return provider_model.objects.filter(
            Q(registered_by_id=owner.id) | Q(user__sponsor_coordinator_id=owner.id)
        ).distinct()
    return provider_model.objects.filter(registered_by_id=owner.id)


def referral_stats(user):
    """Counts for the logged-in user's referral dashboard. Never counts
    outside the user's own recruitment network — a Coordinator sees Agents
    and Service Providers under their own state/chain only; an Agent sees
    only what they personally registered."""
    arts = ArtisanProfile.objects
    bizes = BusinessProfile.objects
    if user.role == 'state_coordinator':
        agents_in_state = _user_model().objects.filter(role='agent', state_id=user.state_id)
        a = _recruited_query(user, ArtisanProfile).count()
        b = _recruited_query(user, BusinessProfile).count()
        return {
            'role': 'state_coordinator',
            'total_agents': agents_in_state.count(),
            'active_agents': agents_in_state.filter(account_status='active').count(),
            'pending_agents': agents_in_state.filter(account_status='pending_approval').count(),
            'total_service_providers_recorded': a + b,
            'total_artisans': a,
            'total_businesses': b,
        }
    if user.role == 'agent':
        a = ArtisanProfile.objects.filter(registered_by_id=user.id).count()
        b = BusinessProfile.objects.filter(registered_by_id=user.id).count()
        return {
            'role': 'agent',
            'total_service_providers_registered': a + b,
            'total_artisans_registered': a,
            'total_businesses_registered': b,
        }
    return {'role': user.role or 'client', 'total_service_providers_registered': 0}


def recent_network_activity(user, limit=5):
    """Most recent creation/registration events inside ``user``'s network
    for the referral dashboard's 'recent activity' strip. A Coordinator
    sees their whole state's agent/provider activity; an Agent only their
    own registrations."""
    actions = ('agent_created', 'artisan_registered', 'business_registered')
    if user.role == 'state_coordinator':
        log = ActivityLog.objects.filter(state_id=user.state_id)
    else:
        log = ActivityLog.objects.filter(actor_id=user.id)
    log = log.filter(action__in=actions).order_by('-created_at')[:limit]
    return [{
        'action': e.action,
        'target': e.target_repr,
        'created_at': e.created_at,
    } for e in log]