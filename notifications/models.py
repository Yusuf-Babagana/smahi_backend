from django.db import models
from django.conf import settings


class Notification(models.Model):
    """In-app notification record. Created exclusively through
    notifications.events.emit() — no feature should create these directly.

    Doubles as the append-only audit trail for user-facing events (no
    delete action is exposed anywhere): every emit() call leaves a
    permanent, timestamped row here, which is what "audit log" means for
    v1 rather than a duplicate parallel table.
    """
    EVENT_CHOICES = [
        ('booking_created', 'Booking Created'),
        ('booking_confirmed', 'Booking Confirmed'),
        ('booking_started', 'Booking Started'),
        ('booking_completed', 'Booking Completed'),
        ('booking_cancelled', 'Booking Cancelled'),
        ('service_fee_requested', 'Service Fee Requested'),
        ('service_fee_paid', 'Service Fee Paid'),
        ('review_submitted', 'Review Submitted'),
        ('verification_approved', 'Verification Approved'),
        ('verification_rejected', 'Verification Rejected'),
        ('wallet_credited', 'Wallet Credited'),
        ('withdrawal_approved', 'Withdrawal Approved'),
        ('withdrawal_rejected', 'Withdrawal Rejected'),
        ('dispute_created', 'Dispute Created'),
        ('dispute_resolved', 'Dispute Resolved'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)

    # Lightweight (type, id) pointer instead of a GenericForeignKey — every
    # future event type can reference its source (a booking, a review, a
    # wallet transaction...) without a new column or a contenttypes
    # dependency for what's fundamentally just a display/deep-link hint.
    related_object_type = models.CharField(max_length=50, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'is_read'])]

    def __str__(self):
        return f"{self.get_event_type_display()} -> {self.recipient.email}"


class DeviceToken(models.Model):
    """One Expo push token for one device. token is globally unique (not
    per-user) — reinstalling the app or logging in as someone else on the
    same device reassigns it via update_or_create rather than leaving
    duplicate stale rows."""
    PLATFORM_CHOICES = [('ios', 'iOS'), ('android', 'Android')]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_tokens'
    )
    token = models.CharField(max_length=200, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.email} ({self.platform or 'unknown'})"


class OTPCode(models.Model):
    PURPOSE_CHOICES = [
        ('email_verify', 'Email Verification'),
        ('password_reset', 'Password Reset'),  # reserved — no flow uses it yet
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='otp_codes', null=True, blank=True
    )
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=64)  # sha256 hex — the plaintext code is never stored
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.purpose})"
