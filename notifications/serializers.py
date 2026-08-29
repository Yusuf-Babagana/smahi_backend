from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """A user's own notification, exactly as emit() wrote it. Every field
    is read-only — a notification is only ever created via emit() and
    only ever mutated (is_read) via the mark-read endpoints, never a
    plain PATCH."""

    class Meta:
        model = Notification
        fields = [
            'id', 'event_type', 'title', 'body',
            'related_object_type', 'related_object_id',
            'is_read', 'created_at',
        ]
        read_only_fields = fields
