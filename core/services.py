"""Shared business-logic functions used by more than one entry point
(an API view, a Django Admin action, ...). Keeping this logic here — not
duplicated per caller — is what "hybrid admin" actually depends on: the
agent-facing endpoint and the privileged Django Admin action must always
agree on what "approved" means.
"""
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from .models import ArtisanProfile, VerificationRequest, Wallet, WalletTransaction, PlatformSettings
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


# ---------------------------------------------------------------------------
# Wallet — WalletTransaction is the source of truth, Wallet.balance is a
# cache updated atomically alongside it. Nothing outside this module should
# ever write to Wallet.balance directly.
# ---------------------------------------------------------------------------

def create_wallet_transaction(user, tx_type, amount, description='', reference=None, created_by=None):
    """Create an already-COMPLETED transaction and atomically apply it to
    the cached balance. For something that must stay pending until an
    admin decides (withdrawals), use request_withdrawal() instead — this
    function always finalizes immediately."""
    reference_type = reference.__class__.__name__.lower() if reference else ''
    reference_id = reference.pk if reference else None

    with db_transaction.atomic():
        wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
        tx = WalletTransaction.objects.create(
            wallet=wallet, type=tx_type, amount=amount, status='completed',
            description=description, reference_type=reference_type,
            reference_id=reference_id, created_by=created_by,
        )
        wallet.balance = wallet.balance + amount
        wallet.save(update_fields=['balance', 'updated_at'])

    if amount > 0:
        emit(
            'wallet_credited', recipient=user, title='Wallet credited',
            body=description or f'Your wallet was credited {wallet.currency} {amount}.',
            related_object=tx,
        )
    return tx


def get_available_balance(wallet):
    """Balance minus whatever's already reserved by other pending
    withdrawal requests — prevents filing two withdrawals that together
    exceed the real balance before either is approved."""
    pending_holds = WalletTransaction.objects.filter(
        wallet=wallet, type='payout', status='pending'
    ).aggregate(total=Sum('amount'))['total'] or 0
    # pending payout amounts are stored negative, so adding them subtracts
    # the reserved portion from the available total.
    return wallet.balance + pending_holds


def request_withdrawal(user, amount):
    """amount is positive (how much the user wants to withdraw). Creates a
    PENDING negative transaction that reserves against available balance
    immediately, but does not touch the cached balance until an admin
    finalizes it via finalize_withdrawal()."""
    if amount <= 0:
        raise ValueError('Withdrawal amount must be positive.')

    settings_row = PlatformSettings.current()
    if amount < settings_row.minimum_withdrawal:
        raise ValueError(f'Minimum withdrawal is {settings_row.currency} {settings_row.minimum_withdrawal}.')
    if settings_row.maximum_withdrawal and amount > settings_row.maximum_withdrawal:
        raise ValueError(f'Maximum withdrawal is {settings_row.currency} {settings_row.maximum_withdrawal}.')

    with db_transaction.atomic():
        wallet = Wallet.objects.select_for_update().get_or_create(user=user)[0]
        available = get_available_balance(wallet)
        if amount > available:
            raise ValueError('Insufficient available balance.')

        tx = WalletTransaction.objects.create(
            wallet=wallet, type='payout', amount=-amount, status='pending',
            description='Withdrawal requested',
        )
    return tx


def finalize_withdrawal(tx, approve, admin_user=None):
    """Admin decision on a pending withdrawal. Approve completes the debit
    (balance was never touched at request time, so it's applied now).
    Reject just marks it reversed — balance was never touched, so there's
    nothing to undo."""
    with db_transaction.atomic():
        tx = WalletTransaction.objects.select_for_update().get(pk=tx.pk)
        if tx.status != 'pending':
            return tx  # already handled — no-op, avoids double-processing

        if approve:
            wallet = Wallet.objects.select_for_update().get(pk=tx.wallet_id)
            wallet.balance = wallet.balance + tx.amount  # amount is already negative
            wallet.save(update_fields=['balance', 'updated_at'])
            tx.status = 'completed'
        else:
            tx.status = 'reversed'
        tx.save(update_fields=['status'])

    recipient = tx.wallet.user
    if approve:
        emit(
            'withdrawal_approved', recipient=recipient, title='Withdrawal approved',
            body=f'Your withdrawal of {tx.wallet.currency} {abs(tx.amount)} has been approved.',
            related_object=tx,
        )
    else:
        emit(
            'withdrawal_rejected', recipient=recipient, title='Withdrawal not approved',
            body='Your withdrawal request was not approved. Contact support for details.',
            related_object=tx,
        )
    return tx
