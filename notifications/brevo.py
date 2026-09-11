import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BREVO_EMAIL_URL = 'https://api.brevo.com/v3/smtp/email'


def send_transactional_email(to_email, subject, html_content):
    """Send one email through Brevo. Returns True on success, False otherwise — never raises."""
    api_key = settings.BREVO_API_KEY
    if not api_key:
        logger.warning('BREVO_API_KEY is not configured; email to %s not sent.', to_email)
        return False

    payload = {
        'sender': {'name': settings.BREVO_SENDER_NAME, 'email': settings.BREVO_SENDER_EMAIL},
        'to': [{'email': to_email}],
        'subject': subject,
        'htmlContent': html_content,
    }
    headers = {
        'api-key': api_key,
        'accept': 'application/json',
        'content-type': 'application/json',
    }

    try:
        response = requests.post(BREVO_EMAIL_URL, json=payload, headers=headers, timeout=5)
        if response.status_code in (200, 201):
            logger.info('Brevo email dispatched successfully to %s', to_email)
            return True

        error_text = response.text
        if 'unrecognised IP address' in error_text:
            logger.error(
                'BREVO IP SECURITY RESTRICTION: Brevo rejected email to %s because the server IP address is not authorized. '
                'Action Required: Please visit https://app.brevo.com/security/authorise-ip to authorize the IP or '
                'turn off IP restrictions in Brevo Account Security Settings. Response: %s',
                to_email, error_text
            )
        else:
            logger.error(
                'Brevo rejected email to %s: %s %s',
                to_email, response.status_code, error_text[:300]
            )
    except requests.RequestException as exc:
        logger.error('Brevo request failed for %s: %s', to_email, exc)

    # Optional fallback to Django standard email backend (SMTP) if configured
    if getattr(settings, 'EMAIL_HOST_USER', '') and getattr(settings, 'EMAIL_HOST_PASSWORD', ''):
        try:
            from django.core.mail import EmailMultiAlternatives
            from django.utils.html import strip_tags

            sender = f"{settings.BREVO_SENDER_NAME} <{settings.BREVO_SENDER_EMAIL}>"
            text_body = strip_tags(html_content)
            msg = EmailMultiAlternatives(subject, text_body, sender, [to_email])
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            logger.info('Email sent successfully via Django mail backend to %s', to_email)
            return True
        except Exception as fallback_exc:
            logger.error('Django mail fallback failed for %s: %s', to_email, fallback_exc)

    return False
