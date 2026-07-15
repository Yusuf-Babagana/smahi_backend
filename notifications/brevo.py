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
        response = requests.post(BREVO_EMAIL_URL, json=payload, headers=headers, timeout=10)
        if response.status_code in (200, 201):
            return True
        logger.error(
            'Brevo rejected email to %s: %s %s',
            to_email, response.status_code, response.text[:200]
        )
        return False
    except requests.RequestException as exc:
        logger.error('Brevo request failed for %s: %s', to_email, exc)
        return False
