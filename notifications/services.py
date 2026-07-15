import hashlib
import hmac
import secrets
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from .brevo import send_transactional_email
from .models import OTPCode

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60

PURPOSE_EMAIL_CONTENT = {
    'email_verify': ('Your S-MAHII verification code', 'Your S-MAHII verification code is:'),
    'password_reset': ('Your S-MAHII password reset code', 'Your S-MAHII password reset code is:'),
}


class OTPError(Exception):
    """Base OTP-sending error; the message is safe to show to the user."""


class OTPCooldown(OTPError):
    pass


class OTPSendFailure(OTPError):
    pass


def _hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


def send_otp(user, purpose):
    """Generate a fresh OTP for user.email and deliver it via Brevo.

    Raises OTPCooldown (resend too soon) or OTPSendFailure (provider down).
    """
    latest = OTPCode.objects.filter(email=user.email, purpose=purpose).first()
    if latest:
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            raise OTPCooldown('Please wait a minute before requesting a new code.')

    code = f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"

    subject, intro = PURPOSE_EMAIL_CONTENT[purpose]
    sent = send_transactional_email(
        to_email=user.email,
        subject=subject,
        html_content=(
            f"<p>Hello {user.first_name},</p>"
            f"<p>{intro}</p>"
            f"<h2 style=\"letter-spacing: 4px;\">{code}</h2>"
            f"<p>The code expires in {OTP_TTL_MINUTES} minutes. "
            f"If you did not request it, you can ignore this email.</p>"
        ),
    )
    if not sent:
        raise OTPSendFailure('Could not send the verification email. Please try again later.')

    # Only after a successful send: retire older codes and store the new one
    OTPCode.objects.filter(email=user.email, purpose=purpose, is_used=False).update(is_used=True)
    OTPCode.objects.create(
        user=user,
        email=user.email,
        purpose=purpose,
        code_hash=_hash_code(code),
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
    )


def verify_otp(user, code, purpose):
    """Check a submitted code. Returns (ok, user_safe_message). Consumes the code on success."""
    otp = OTPCode.objects.filter(email=user.email, purpose=purpose, is_used=False).first()
    if otp is None:
        return False, 'No active code found. Please request a new one.'
    if timezone.now() > otp.expires_at:
        return False, 'This code has expired. Please request a new one.'
    if otp.attempts >= MAX_VERIFY_ATTEMPTS:
        return False, 'Too many incorrect attempts. Please request a new code.'

    if not hmac.compare_digest(otp.code_hash, _hash_code(code)):
        OTPCode.objects.filter(pk=otp.pk).update(attempts=F('attempts') + 1)
        return False, 'Invalid code. Please check and try again.'

    otp.is_used = True
    otp.save(update_fields=['is_used'])
    return True, 'Code verified.'
