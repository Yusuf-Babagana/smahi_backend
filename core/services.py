"""Shared business-logic functions used by more than one entry point
(an API view, a Django Admin action, ...). Keeping this logic here — not
duplicated per caller — is what "hybrid admin" actually depends on: the
agent-facing endpoint and the privileged Django Admin action must always
agree on what "approved" means.
"""
from django.utils import timezone

from .models import ArtisanProfile, VerificationRequest
from notifications.events import emit


def approve_artisan_verification(artisan_user, reviewed_by):
    """Approve an artisan's verification. reviewed_by is whoever took the
    action — an agent/coordinator (via AgentVerifyArtisanView) or an admin
    (via Django Admin)."""
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
    return artisan_profile
