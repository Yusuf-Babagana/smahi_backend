"""Shared business-logic functions used by more than one entry point
(an API view, a Django Admin action, ...). Keeping this logic here — not
duplicated per caller — is what "hybrid admin" actually depends on: the
agent-facing endpoint and the privileged Django Admin action must always
agree on what "approved" means.
"""
import logging

from django.utils import timezone

from .models import ArtisanProfile, VerificationRequest, ActivityLog
from notifications.events import emit

logger = logging.getLogger(__name__)


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
