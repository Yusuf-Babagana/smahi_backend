"""Shared business-logic functions used by more than one entry point
(an API view, a Django Admin action, ...). Keeping this logic here — not
duplicated per caller — is what "hybrid admin" actually depends on: the
agent-facing endpoint and the privileged Django Admin action must always
agree on what "approved" means.
"""
import logging
import re

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import ArtisanProfile, BusinessProfile, VerificationRequest, ActivityLog
from notifications.events import emit

logger = logging.getLogger(__name__)
User = get_user_model()


def log_activity(actor, action, target_user=None, lga=None, state=None,
                  target_repr=None, target_role=None, activity_status=''):
    """Append-only entry for the State Coordinator's Activity Log
    (ActivityLog, core/models.py). Actor-centric — records who did what —
    unlike notifications.emit(), which is recipient-centric. Best-effort:
    a logging failure must never break the real action that triggered it,
    same reasoning as every emit() call site in this codebase.

    state/lga default to the TARGET's own (not the actor's), so an
    Admin-driven action — an admin has no state of their own — still
    lands in the correct state's Coordinator log. Pass `lga`/`state`
    explicitly when they differ from the target's — e.g. a report has no
    natural `target_user` at all (DisputeReport isn't a User), so its
    location has to come from the reporter/booking instead and gets
    passed in directly, along with `target_repr`/`target_role` describing
    the report itself rather than a person.
    """
    try:
        resolved_target_repr = target_repr if target_repr is not None else (
            (f'{target_user.first_name} {target_user.last_name}'.strip() or target_user.email)
            if target_user else ''
        )
        resolved_target_role = target_role if target_role is not None else getattr(target_user, 'role', '')
        ActivityLog.objects.create(
            actor=actor,
            actor_role=getattr(actor, 'role', ''),
            action=action,
            target_user=target_user,
            target_repr=resolved_target_repr,
            target_role=resolved_target_role,
            state=state or (target_user.state if target_user else None) or getattr(actor, 'state', None),
            lga=lga or (target_user.lga if target_user else None),
            status=activity_status,
        )
    except Exception:
        logger.exception('Failed to record activity log entry (action=%s)', action)


def approve_artisan_verification(artisan_user, reviewed_by):
    """Approve an artisan's verification. reviewed_by is whoever took the
    action — an agent/coordinator (via AgentVerifyArtisanView or
    VerificationRequestViewSet.process) or an admin (via Django Admin)."""
    artisan_profile, _ = ArtisanProfile.objects.get_or_create(user=artisan_user)
    artisan_profile.verification_status = 'approved'
    artisan_profile.save(update_fields=['verification_status'])

    artisan_user.is_verified = True
    artisan_user.save(update_fields=['is_verified'])

    VerificationRequest.objects.filter(artisan=artisan_user, status='pending').update(
        status='approved', reviewed_by=reviewed_by, reviewed_at=timezone.now()
    )

    emit(
        'verification_approved',
        recipient=artisan_user,
        title='You are verified!',
        body='Your artisan profile has been verified. Clients can now see your verified badge.',
        related_object=artisan_profile,
    )
    log_activity(reviewed_by, 'artisan_verified', target_user=artisan_user, activity_status='approved')
    return artisan_profile


def reject_artisan_verification(artisan_user, reviewed_by, reason=''):
    """Reject an artisan's verification. Does not touch is_verified if it
    was never True — this only ever moves pending -> rejected."""
    artisan_profile, _ = ArtisanProfile.objects.get_or_create(user=artisan_user)
    artisan_profile.verification_status = 'rejected'
    artisan_profile.save(update_fields=['verification_status'])

    VerificationRequest.objects.filter(artisan=artisan_user, status='pending').update(
        status='rejected', rejection_reason=reason, reviewed_by=reviewed_by, reviewed_at=timezone.now()
    )

    emit(
        'verification_rejected',
        recipient=artisan_user,
        title='Verification not approved',
        body=reason or 'Your verification request was not approved. Please contact support for details.',
        related_object=artisan_profile,
    )
    log_activity(reviewed_by, 'artisan_verification_rejected', target_user=artisan_user, activity_status='rejected')
    return artisan_profile


def approve_business_verification(business_user, reviewed_by):
    """Approve a business's verification. Mirrors
    approve_artisan_verification exactly — BusinessProfile has the same
    verification_status field/choices as ArtisanProfile. reviewed_by is
    whoever took the action (agent/coordinator via AgentVerifyBusinessView,
    or admin via Django Admin). Reuses the generic 'verification_approved'
    notification event (same one artisans get) rather than adding a
    business-specific one — the title/body text is what actually
    distinguishes context for the recipient."""
    business_profile, _ = BusinessProfile.objects.get_or_create(user=business_user)
    business_profile.verification_status = 'approved'
    business_profile.save(update_fields=['verification_status'])

    business_user.is_verified = True
    business_user.save(update_fields=['is_verified'])

    emit(
        'verification_approved',
        recipient=business_user,
        title='Your business is verified!',
        body='Your business profile has been verified. Clients can now see your verified badge.',
        related_object=business_profile,
    )
    log_activity(reviewed_by, 'business_verified', target_user=business_user, activity_status='approved')
    return business_profile


def reject_business_verification(business_user, reviewed_by, reason=''):
    """Reject a business's verification. Does not touch is_verified if it
    was never True — this only ever moves pending -> rejected."""
    business_profile, _ = BusinessProfile.objects.get_or_create(user=business_user)
    business_profile.verification_status = 'rejected'
    business_profile.save(update_fields=['verification_status'])

    emit(
        'verification_rejected',
        recipient=business_user,
        title='Business verification not approved',
        body=reason or 'Your business verification request was not approved. Please contact support for details.',
        related_object=business_profile,
    )
    log_activity(reviewed_by, 'business_verification_rejected', target_user=business_user, activity_status='rejected')
    return business_profile


# --- Agent/Coordinator status transitions ---
#
# Shared by core.views.CoordinatorAgentStatusView/AdminCoordinatorStatusView
# (the API) and accounts.admin.AgentAdmin/CoordinatorAdmin (Django Admin's
# dedicated management pages) — same reasoning as every other function in
# this file: both entry points must always agree on what "approved" or
# "reactivated" means. Only Django Admin passes
# allow_reactivate_from_terminal=True — a dismissed/rejected seat being
# reversible "only from Django Admin" is this codebase's own documented
# intent (see CoordinatorAgentStatusView's original docstring), not a new
# rule invented here.

def set_agent_status(agent, new_status, actor, *, allow_reactivate_from_terminal=False):
    """Move an Agent to active/suspended/dismissed/rejected. Mints their
    referral code on first activation (idempotent — never overwrites one
    that already exists). Raises ValueError (never saves anything) if the
    agent is currently dismissed/rejected and allow_reactivate_from_terminal
    is False."""
    if not allow_reactivate_from_terminal and agent.account_status in ('dismissed', 'rejected'):
        raise ValueError(f'This agent has been {agent.account_status} and cannot be reactivated here.')

    from core.referrals import generate_referral_code

    previous_status = agent.account_status
    agent.is_active = (new_status == 'active')
    agent.account_status = new_status
    update_fields = ['is_active', 'account_status']

    if new_status == 'active' and not agent.referral_code:
        agent.referral_code = generate_referral_code('AG')
        update_fields.append('referral_code')
    agent.save(update_fields=update_fields)

    if new_status == 'active':
        action = 'agent_approved' if previous_status == 'pending_approval' else 'agent_reactivated'
    else:
        action = f'agent_{new_status}'  # 'agent_suspended' / 'agent_dismissed' / 'agent_rejected'
    log_activity(actor, action, target_user=agent, activity_status=new_status)
    return agent


def set_coordinator_status(coordinator, new_status, actor, *, allow_reactivate_from_terminal=False):
    """Move a State Coordinator to active/suspended/dismissed. Same shape
    as set_agent_status, one level up — no pending_approval step, since a
    coordinator is active immediately on creation."""
    if not allow_reactivate_from_terminal and coordinator.account_status == 'dismissed':
        raise ValueError('This coordinator has been dismissed and cannot be reactivated here.')

    from core.referrals import generate_referral_code

    coordinator.is_active = (new_status == 'active')
    coordinator.account_status = new_status
    update_fields = ['is_active', 'account_status']

    if new_status == 'active' and not coordinator.referral_code:
        state_code = (
            (coordinator.state.state_code or coordinator.state.name[:3].upper())
            if coordinator.state else 'ST'
        )
        coordinator.referral_code = generate_referral_code(state_code)
        update_fields.append('referral_code')
    coordinator.save(update_fields=update_fields)

    action = {
        'active': 'coordinator_reactivated',
        'suspended': 'coordinator_suspended',
        'dismissed': 'coordinator_dismissed',
    }[new_status]
    log_activity(actor, action, target_user=coordinator, activity_status=new_status)
    return coordinator


# --- Agent Search API (audit-trail spec item 7: "AI access strictly
# limited to Agent information") ---
#
# This is THE only sanctioned way anything — the AI assistant included —
# is allowed to look up Agent records. Both CoordinatorAgentSearchView
# (core/views.py, a real standalone REST endpoint any authorized caller
# can hit directly) and AIChatView's search_agents tool call this exact
# same function, so the two entry points can never authorize differently
# or drift on what's approved for release. Never returns a raw User row
# or queryset — only the fixed allowlist in _agent_search_summary().

AGENT_SEARCH_ALLOWED_FIELDS = ('name', 'serial_number', 'phone_number', 'state', 'lga', 'status')


def _agent_search_summary(agent):
    """The complete, fixed allowlist of Agent fields approved for AI/
    Agent-Search access. Deliberately excludes email, id/pk, address,
    gender, is_verified, timestamps, and everything else on User —
    widen this list only by explicit approval, never implicitly by
    swapping in a serializer's full output."""
    return {
        'name': f'{agent.first_name} {agent.last_name}'.strip(),
        'serial_number': agent.serial_number or '',
        'phone_number': agent.phone_number or '',
        'state': agent.state.name if agent.state else '',
        'lga': agent.lga.name if agent.lga else '',
        'status': agent.account_status,
    }


def search_agents(requesting_user, query=None, lga=None, phone_number=None, serial_number=None, limit=10):
    """The Agent Search API itself. Before returning anything, verifies
    exactly what the spec asks for, in order:
      1. Who is requesting?     -> requesting_user
      2. What is their role?    -> must be 'state_coordinator' (agents
         don't search other agents — each is scoped to their own LGA
         already; clients/artisans/admin are out of scope for this
         spec's examples)
      3. Which state/LGA?       -> requesting_user's own state_id, never
         taken from the caller-supplied query
      4. What fields permitted? -> _agent_search_summary()'s fixed keys

    Returns {'error': '<reason>', ...} on any authorization failure —
    every caller must check for that key before treating the response as
    real data (same convention as AIChatView's other tool results, e.g.
    {"reason": "not_a_client"})."""
    if not requesting_user or not requesting_user.is_authenticated:
        return {'error': 'not_authenticated'}
    if requesting_user.role != 'state_coordinator':
        return {'error': 'not_authorized', 'message': 'Only a State Coordinator can search Agent records.'}
    if not requesting_user.state_id:
        return {'error': 'no_state_assigned', 'message': 'Your account has no state assigned.'}

    # Ownership rule — reuses core.referrals._coordinator_visible_agents
    # directly (was a hand-duplicated copy of that same filter, which is
    # exactly how it drifted: that shared function was fixed to stop
    # showing unclaimed legacy agents to every coordinator in the state
    # after a real leak, but this copy wasn't touched until now). A
    # colleague's claimed agents in the same state are out of reach here —
    # the same partition multi-coordinator states rely on across every
    # coordinator-facing endpoint.
    from .referrals import _coordinator_visible_agents
    qs = _coordinator_visible_agents(requesting_user).select_related('state', 'lga')

    if lga:
        qs = qs.filter(lga__name__icontains=lga)
    if phone_number:
        # Loose match — a caller may include spaces/dashes/a leading 0
        # that the stored number doesn't, or vice versa.
        digits = re.sub(r'\D', '', phone_number)
        if digits:
            qs = qs.filter(phone_number__icontains=digits)
    if serial_number:
        qs = qs.filter(serial_number__icontains=serial_number)
    if query:
        qs = qs.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(serial_number__icontains=query) | Q(phone_number__icontains=query)
            | Q(lga__name__icontains=query)
        )

    agents = list(qs.order_by('-created_at')[:limit])
    return {
        'count': len(agents),
        'agents': [_agent_search_summary(a) for a in agents],
    }
