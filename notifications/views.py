"""Every Dashboard Must Be Connected (item 10): a Notification row has
existed since this app's earliest days (emit() writes one for every
booking/verification/dispute/agent event across the whole app), and its
own model docstring already calls it "the append-only audit trail for
user-facing events" — but until now there was no way to actually read
that history back from inside the app itself, only via Django Admin. A
push notification fires once and is gone; this is what makes that
history a real, permanent, in-app inbox for every role's dashboard.
"""
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """A caller's own notifications, newest first. Strictly scoped to
    request.user — there is no way to see anyone else's from here,
    regardless of role."""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


class NotificationUnreadCountView(APIView):
    """Separate from the list endpoint on purpose — every dashboard's
    bell badge calls this on load, and shouldn't pay for a full
    paginated list just to show a number."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})


class NotificationMarkReadView(APIView):
    """Marks one notification read. 404s (not 403) for one that belongs
    to someone else, or doesn't exist — same "don't reveal existence"
    reasoning as every other object endpoint in this codebase scoped to
    request.user."""
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        try:
            notification = Notification.objects.get(id=notification_id, recipient=request.user)
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found.'}, status=status.HTTP_404_NOT_FOUND)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'marked_read': updated})
