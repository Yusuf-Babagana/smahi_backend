import logging

import requests

from .models import DeviceToken

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'


def send_push_to_user(user, title, body, data=None):
    """Send a push to every device registered for this user via Expo's
    push API. Never raises — a failed push should never break emit()'s
    caller, and the in-app Notification row is already written regardless."""
    tokens = list(DeviceToken.objects.filter(user=user).values_list('token', flat=True))
    if not tokens:
        return

    messages = [
        {'to': token, 'title': title, 'body': body, 'sound': 'default', 'data': data or {}}
        for token in tokens
    ]

    try:
        response = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=10,
        )
        response.raise_for_status()
        _cleanup_invalid_tokens(tokens, response.json().get('data', []))
    except requests.RequestException:
        logger.exception('Push notification send failed for user %s', user.email)


def _cleanup_invalid_tokens(tokens, tickets):
    """Expo returns one ticket per message, in the same order the messages
    were sent — DeviceNotRegistered means the app was uninstalled or the
    token otherwise expired, so stop wasting sends on it."""
    invalid = [
        token for token, ticket in zip(tokens, tickets)
        if ticket.get('status') == 'error' and ticket.get('details', {}).get('error') == 'DeviceNotRegistered'
    ]
    if invalid:
        DeviceToken.objects.filter(token__in=invalid).delete()
