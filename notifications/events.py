"""Central notification dispatcher.

Every feature that needs to notify a user should call emit() from here
instead of writing its own notification code. This is the single call
site that fans out to every channel — adding a new channel (push, a real
analytics pipeline) means changing this file once, not every feature that
already calls emit().
"""
import logging

from .models import Notification
from .brevo import send_transactional_email

logger = logging.getLogger(__name__)

# Only in-app is live for v1. Email is opt-in per event type so nothing
# starts emailing users about an event before someone has deliberately
# written and reviewed a template for it — an empty set here is a
# deliberate choice, not an oversight.
EMAIL_ENABLED_EVENTS = set()


def emit(event_type, recipient, title, body='', related_object=None):
    """Fire a notification event.

    event_type: one of Notification.EVENT_CHOICES
    recipient: the User who should be notified
    title/body: user-facing text for the in-app notification (and email,
        for events where EMAIL_ENABLED_EVENTS opts in)
    related_object: any model instance with a .pk — stored as a
        lightweight (type, id) reference so the caller never needs a new
        column or FK to point back at its source object.
    """
    related_type = related_object.__class__.__name__.lower() if related_object else ''
    related_id = related_object.pk if related_object else None

    # --- in-app channel: live today ---
    notification = Notification.objects.create(
        recipient=recipient,
        event_type=event_type,
        title=title,
        body=body,
        related_object_type=related_type,
        related_object_id=related_id,
    )

    # --- push channel ---
    _send_push(recipient, title, body, event_type, related_type, related_id)

    # --- email channel: stub, opt-in per event, reuses the existing Brevo integration ---
    if event_type in EMAIL_ENABLED_EVENTS:
        send_transactional_email(recipient.email, title, f"<p>{body}</p>")

    # --- analytics: stub hook point for a future pipeline ---
    _track_analytics(event_type, recipient)

    return notification


def _send_push(recipient, title, body, event_type, related_type, related_id):
    from .push import send_push_to_user
    send_push_to_user(recipient, title, body, data={
        'event_type': event_type,
        'related_object_type': related_type,
        'related_object_id': related_id,
    })


def _track_analytics(event_type, recipient):
    """No-op stub — hook point for a future analytics pipeline."""
    logger.debug('analytics (not yet implemented): %s by %s', event_type, recipient.email)
